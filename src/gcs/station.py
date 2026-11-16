"""Module Station Sol (Ground Control Station - GCS) MAVLink 2.

Assure l'emission periodique de battements de coeur GCS, l'envoi de commandes de vol signees
et le suivi en direct de l'etat du drone (altitude, batterie, mode).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from src.common.config import DEFAULT_CONFIG
from src.common.protocol import MavlinkCodec, mavlink2

logger = logging.getLogger("hybridlink.gcs")


class GroundControlStation:
    """Station de controle sol emettrice de commandes et auditrice de telemetrie."""

    def __init__(
        self,
        sys_id: int = DEFAULT_CONFIG.GCS_SYSID,
        comp_id: int = DEFAULT_CONFIG.GCS_COMPID,
        secret_key: bytes | None = DEFAULT_CONFIG.DEFAULT_SHARED_SECRET,
    ) -> None:
        self.sys_id = sys_id
        self.comp_id = comp_id
        self.codec = MavlinkCodec(sys_id, comp_id, secret_key=secret_key, link_id=1)

        # Suivi de l'etat du drone distant
        self.connected = False
        self.last_vehicle_heartbeat_time = 0.0
        self.vehicle_armed = False
        self.vehicle_mode = "UNKNOWN"
        self.vehicle_alt = 0.0
        self.vehicle_lat = 0.0
        self.vehicle_lon = 0.0
        self.vehicle_battery = 100.0
        self.vehicle_failsafe = False

        self.telemetry_count = 0
        self.acks_received: dict[int, int] = {}
        self.pending_command_times: dict[int, float] = {}
        self.last_command_rtt_ms: float = 0.0

        self.send_packet_callback: Callable[[bytes], None] | None = None

    def handle_incoming_frame(self, data: bytes) -> None:
        """Traite les trames MAVLink recues du vecteur ou du proxy."""
        messages, errors = self.codec.decode_buffer(data)

        if errors:
            for err in errors:
                logger.warning(f"[GCS REJET] Trame rejetee: {err}")

        for msg in messages:
            msg_type = msg.get_type()
            self.telemetry_count += 1

            if msg_type == "HEARTBEAT":
                self.connected = True
                self.last_vehicle_heartbeat_time = time.time()
                self.vehicle_armed = bool(msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED)
                self.vehicle_failsafe = bool(msg.system_status == mavlink2.MAV_STATE_CRITICAL)

            elif msg_type == "GLOBAL_POSITION_INT":
                self.vehicle_lat = msg.lat / 1e7
                self.vehicle_lon = msg.lon / 1e7
                self.vehicle_alt = msg.relative_alt / 1000.0

            elif msg_type == "COMMAND_ACK":
                cmd_id = msg.command
                result = msg.result
                self.acks_received[cmd_id] = result
                if cmd_id in self.pending_command_times:
                    self.last_command_rtt_ms = (time.time() - self.pending_command_times[cmd_id]) * 1000.0
                    del self.pending_command_times[cmd_id]
                res_str = "ACCEPTED" if result == mavlink2.MAV_RESULT_ACCEPTED else f"CODE_{result}"
                logger.info(
                    f"[GCS RECEPTION ACK] Commande {cmd_id} acquittee : {res_str} "
                    f"(RTT: {self.last_command_rtt_ms:.1f} ms)"
                )

    def generate_heartbeat(self) -> bytes:
        """Cree un battement de coeur GCS (MAV_TYPE_GCS)."""
        return self.codec.encode_heartbeat(
            mav_type=mavlink2.MAV_TYPE_GCS,
            autopilot=mavlink2.MAV_AUTOPILOT_INVALID,
            base_mode=0,
            custom_mode=0,
            system_status=mavlink2.MAV_STATE_ACTIVE,
        )

    def send_arm(self, arm: bool = True) -> bytes:
        """Envoie l'ordre d'armement ou de desarment."""
        cmd_id = mavlink2.MAV_CMD_COMPONENT_ARM_DISARM
        self.pending_command_times[cmd_id] = time.time()
        logger.info(f"[GCS EMISSION] Envoi de l'ordre d'{'armement' if arm else 'desarmement'}...")
        return self.codec.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=cmd_id,
            param1=1.0 if arm else 0.0,
        )

    def send_takeoff(self, altitude_m: float = 15.0) -> bytes:
        """Envoie l'ordre de decollage a l'altitude specifiee."""
        cmd_id = mavlink2.MAV_CMD_NAV_TAKEOFF
        self.pending_command_times[cmd_id] = time.time()
        logger.info(f"[GCS EMISSION] Envoi de l'ordre de decollage vers {altitude_m} m...")
        return self.codec.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=cmd_id,
            param7=altitude_m,
        )

    def send_rtl(self) -> bytes:
        """Envoie l'ordre de Return-To-Launch."""
        cmd_id = mavlink2.MAV_CMD_NAV_RETURN_TO_LAUNCH
        self.pending_command_times[cmd_id] = time.time()
        logger.info("[GCS EMISSION] Envoi de l'ordre RTL (Return To Launch)...")
        return self.codec.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=cmd_id,
        )

    def send_land(self) -> bytes:
        """Envoie l'ordre d'atterrissage direct."""
        cmd_id = mavlink2.MAV_CMD_NAV_LAND
        self.pending_command_times[cmd_id] = time.time()
        logger.info("[GCS EMISSION] Envoi de l'ordre Land (Atterrissage)...")
        return self.codec.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=cmd_id,
        )
