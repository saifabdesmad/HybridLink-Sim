"""Moteur de simulation de drone (Autopilot) MAVLink 2.

Gere la dynamique de vol simplifiee, l'emission de telemetrie, l'execution des commandes,
la verification cryptographique et la machine a etats de securite (Failsafe).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable

from src.common.config import DEFAULT_CONFIG
from src.common.crypto import MavlinkSecurityEngine, SecurityReport
from src.common.models import FlightMode, VehicleState
from src.common.protocol import MavlinkCodec, mavlink2

logger = logging.getLogger("hybridlink.vehicle")


class SimulatedAutopilot:
    """Simulateur de vecteur aerien avec dynamique physique et controle de securite MAVLink."""

    def __init__(
        self,
        sys_id: int = DEFAULT_CONFIG.VEHICLE_SYSID,
        comp_id: int = DEFAULT_CONFIG.VEHICLE_COMPID,
        secret_key: bytes | None = DEFAULT_CONFIG.DEFAULT_SHARED_SECRET,
        failsafe_timeout_s: float = DEFAULT_CONFIG.FAILSAFE_TIMEOUT_SEC,
        enforce_security: bool = True,
    ) -> None:
        self.sys_id = sys_id
        self.comp_id = comp_id
        self.failsafe_timeout_s = failsafe_timeout_s
        self.enforce_security = enforce_security

        resolved_key = secret_key or DEFAULT_CONFIG.DEFAULT_SHARED_SECRET
        self.codec = MavlinkCodec(sys_id, comp_id, secret_key=resolved_key, link_id=1)
        if not enforce_security:
            self.codec.disable_signing()
        self.security_engine = MavlinkSecurityEngine(
            secret_key=resolved_key,
            enforce_security=enforce_security,
        )

        self.state = VehicleState()

        # Coordonnees d'origine (Laboratoire Heudiasyc, Compiegne)
        self.home_lat = 49.4000000
        self.home_lon = 2.8000000
        self.home_alt = 0.0

        self.target_alt = 0.0
        self.climb_rate_ms = 2.0
        self.start_time = time.time()
        self.is_running = False

        # Suivi d'audit de securite
        self.fraudulent_commands_executed = 0
        self.last_security_report: SecurityReport | None = None

        # Callback pour l'envoi de trames reseau
        self.send_packet_callback: Callable[[bytes], None] | None = None

    def handle_incoming_frame(self, data: bytes) -> bool:
        """Traite une trame MAVLink recue apres validation cryptographique et anti-rejeu.

        Retourne True si la trame est valide et traitee, False si rejetee.
        """
        # 1. Controle de Securite MAVLink 2 (HMAC + Fenetre anti-rejeu)
        report = self.security_engine.verify_frame(data)
        self.last_security_report = report

        if not report.is_valid:
            logger.warning(
                f"[VEHICLE REJET SECURITE] {report.reason} "
                f"(Rejeu={report.is_replayed}, Falsifie={report.is_tampered}, NonSigne={report.is_unsigned})"
            )
            self.state.rejected_commands_count += 1
            return False

        # 2. Decodage applicatif
        messages, errors = self.codec.decode_buffer(data)

        if errors:
            for err in errors:
                logger.warning(f"[VEHICLE ERREUR PROTOCOLE] {err}")
                self.state.rejected_commands_count += 1
            return False

        for msg in messages:
            msg_type = msg.get_type()
            if msg_type == "HEARTBEAT":
                self.state.last_gcs_heartbeat_time = time.time()
                if self.state.failsafe_active:
                    logger.info("[VEHICLE FAILSAFE CLEAR] Signal GCS retabli.")

            elif msg_type == "COMMAND_LONG":
                # Si la securite etait desactivee et qu'un attaquant a reussi a faire executer
                if not self.enforce_security and (report.is_unsigned or report.link_id == 0):
                    self.fraudulent_commands_executed += 1
                self._process_command_long(msg)

        return True

    def _process_command_long(self, cmd: mavlink2.MAVLink_command_long_message) -> None:
        """Traite une commande MAV_CMD."""
        cmd_id = cmd.command
        result = mavlink2.MAV_RESULT_ACCEPTED
        cmd_name = f"CMD_{cmd_id}"

        if cmd_id == mavlink2.MAV_CMD_COMPONENT_ARM_DISARM:
            arm_action = bool(cmd.param1 == 1.0)
            self.state.armed = arm_action
            cmd_name = "ARM" if arm_action else "DISARM"
            logger.info(f"[VEHICLE COMMAND] {'Armement' if arm_action else 'Desarmement'} execute.")

        elif cmd_id == mavlink2.MAV_CMD_NAV_TAKEOFF:
            if not self.state.armed:
                logger.warning("[VEHICLE COMMAND DENIED] Decollage refuse : drone non arme.")
                result = mavlink2.MAV_RESULT_TEMPORARILY_REJECTED
            else:
                self.target_alt = cmd.param7 if cmd.param7 > 0 else 10.0
                self.state.flight_mode = FlightMode.GUIDED
                cmd_name = f"TAKEOFF(alt={self.target_alt}m)"
                logger.info(f"[VEHICLE COMMAND] Decollage accepte vers altitude {self.target_alt} m.")

        elif cmd_id == mavlink2.MAV_CMD_NAV_RETURN_TO_LAUNCH:
            self.state.flight_mode = FlightMode.RTL
            cmd_name = "RTL"
            logger.info("[VEHICLE COMMAND] Mode Return-To-Launch (RTL) active.")

        elif cmd_id == mavlink2.MAV_CMD_NAV_LAND:
            self.target_alt = 0.0
            self.state.flight_mode = FlightMode.LAND
            cmd_name = "LAND"
            logger.info("[VEHICLE COMMAND] Atterrissage active.")

        elif cmd_id == mavlink2.MAV_CMD_DO_SET_MODE:
            cmd_name = f"SET_MODE({cmd.param1})"
            logger.info(f"[VEHICLE COMMAND] Changement de mode : {cmd.param1}")

        else:
            logger.info(f"[VEHICLE COMMAND] Commande {cmd_id} recue.")

        if result == mavlink2.MAV_RESULT_ACCEPTED:
            self.state.executed_commands_count += 1
            self.state.last_command_executed = cmd_name

        # Emettre l'accuse de reception (COMMAND_ACK)
        ack_bytes = self.codec.encode_command_ack(cmd_id, result)
        if self.send_packet_callback:
            self.send_packet_callback(ack_bytes)

    def update_physics(self, dt: float) -> None:
        """Met a jour la dynamique simplifiee du drone."""
        now = time.time()

        # 1. Verification du Failsafe (propriete de surete)
        time_since_gcs = now - self.state.last_gcs_heartbeat_time
        if time_since_gcs > self.failsafe_timeout_s and not self.state.failsafe_active:
            self.state.failsafe_active = True
            self.state.flight_mode = FlightMode.RTL
            logger.critical(
                f"[FAILSAFE DECLENCHE] Aucune reception GCS depuis {time_since_gcs:.2f}s "
                f"(seuil: {self.failsafe_timeout_s}s) -> Passage immediat en RTL !"
            )

        # 2. Evolution de l'altitude selon le mode
        if self.state.flight_mode in (FlightMode.GUIDED, FlightMode.AUTO):
            if self.state.altitude_m < self.target_alt:
                self.state.altitude_m = min(self.target_alt, self.state.altitude_m + self.climb_rate_ms * dt)
                self.state.vz = self.climb_rate_ms
            elif self.state.altitude_m > self.target_alt:
                self.state.altitude_m = max(self.target_alt, self.state.altitude_m - self.climb_rate_ms * dt)
                self.state.vz = -self.climb_rate_ms
            else:
                self.state.vz = 0.0
        elif self.state.flight_mode in (FlightMode.RTL, FlightMode.LAND):
            if self.state.altitude_m > 0.0:
                self.state.altitude_m = max(0.0, self.state.altitude_m - 1.0 * dt)
                self.state.vz = -1.0
            else:
                self.state.altitude_m = 0.0
                self.state.vz = 0.0
                if self.state.flight_mode == FlightMode.LAND:
                    self.state.armed = False
                    self.state.flight_mode = FlightMode.STANDBY

        self.state.relative_altitude_m = self.state.altitude_m

        # 3. Trajectoire orbitale si en vol
        if self.state.armed and self.state.altitude_m > 1.0:
            elapsed = now - self.start_time
            radius_deg = 0.0003
            self.state.latitude = self.home_lat + radius_deg * math.sin(elapsed * 0.2)
            self.state.longitude = self.home_lon + radius_deg * math.cos(elapsed * 0.2)
            self.state.yaw = math.fmod(elapsed * 10.0, 360.0)

        # Batterie
        if self.state.armed:
            self.state.battery_percent = max(0.0, self.state.battery_percent - 0.01 * dt)

    def generate_heartbeat(self) -> bytes:
        """Cree la trame HEARTBEAT standard."""
        base_mode = (
            mavlink2.MAV_MODE_FLAG_SAFETY_ARMED if self.state.armed else 0
        ) | mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED

        status = (
            mavlink2.MAV_STATE_CRITICAL
            if self.state.failsafe_active
            else (mavlink2.MAV_STATE_ACTIVE if self.state.armed else mavlink2.MAV_STATE_STANDBY)
        )
        return self.codec.encode_heartbeat(
            mav_type=mavlink2.MAV_TYPE_QUADROTOR,
            autopilot=mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
            base_mode=base_mode,
            custom_mode=0,
            system_status=status,
        )

    def generate_attitude(self) -> bytes:
        """Cree la trame ATTITUDE."""
        boot_ms = int((time.time() - self.start_time) * 1000)
        return self.codec.encode_attitude(
            time_boot_ms=boot_ms,
            roll=self.state.roll,
            pitch=self.state.pitch,
            yaw=math.radians(self.state.yaw),
        )

    def generate_global_position(self) -> bytes:
        """Cree la trame GLOBAL_POSITION_INT."""
        boot_ms = int((time.time() - self.start_time) * 1000)
        return self.codec.encode_global_position(
            time_boot_ms=boot_ms,
            lat_deg=self.state.latitude,
            lon_deg=self.state.longitude,
            alt_m=self.state.altitude_m,
            relative_alt_m=self.state.relative_altitude_m,
            vx_ms=self.state.vx,
            vy_ms=self.state.vy,
            vz_ms=self.state.vz,
            hdg_cdeg=int(self.state.yaw * 100),
        )
