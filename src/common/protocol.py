"""Gestionnaire de protocole MAVLink 2 utilisant pymavlink.

Assure l'encapsulation, le decodage, la signature cryptographique et la detection d'erreurs.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

# Forcer MAVLink 2.0
os.environ["MAVLINK20"] = "1"
from pymavlink.dialects.v20 import ardupilotmega as mavlink2  # type: ignore

logger = logging.getLogger(__name__)


class MavlinkCodec:
    """Encodeur / decodeur de trames MAVLink 2 avec support de la signature HMAC-SHA256."""

    def __init__(self, sys_id: int, comp_id: int, secret_key: bytes | None = None, link_id: int = 1) -> None:
        self.sys_id = sys_id
        self.comp_id = comp_id
        self.mav = mavlink2.MAVLink(None, srcSystem=sys_id, srcComponent=comp_id)
        self.signing: mavlink2.MAVLinkSigning | None = None

        if secret_key is not None:
            self.configure_signing(secret_key, link_id=link_id, sign_outgoing=True)

    def configure_signing(self, secret_key: bytes, link_id: int = 1, sign_outgoing: bool = True) -> None:
        """Active la signature MAVLink 2 avec la cle privee pre-partagee."""
        # Cle 256 bits = 32 octets
        if len(secret_key) != 32:
            secret_key = secret_key.ljust(32, b"\x00")[:32]

        self.signing = mavlink2.MAVLinkSigning()
        self.signing.secret_key = secret_key
        self.signing.link_id = link_id
        # Timestamp en unites de 10 microsecondes depuis 2015-01-01
        self.signing.timestamp = int((time.time() - 1420070400.0) * 100000)
        self.signing.sign_outgoing = sign_outgoing
        self.mav.signing = self.signing

    def disable_signing(self) -> None:
        """Desactive la signature (mode non securise pour les tests d'attaque)."""
        self.signing = mavlink2.MAVLinkSigning()
        self.signing.secret_key = None
        self.signing.sign_outgoing = False
        self.signing.allow_unsigned_callback = lambda mav, msgId: True
        self.mav.signing = self.signing

    def _ensure_monotonic_timestamp(self) -> None:
        """Garantit un timestamp strictement croissant meme en cas d'appels consecutifs rapides."""
        if self.signing:
            current_time_ts = int((time.time() - 1420070400.0) * 100000)
            self.signing.timestamp = max(self.signing.timestamp + 1, current_time_ts)

    def encode_heartbeat(
        self,
        mav_type: int = mavlink2.MAV_TYPE_QUADROTOR,
        autopilot: int = mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
        base_mode: int = mavlink2.MAV_MODE_FLAG_SAFETY_ARMED,
        custom_mode: int = 0,
        system_status: int = mavlink2.MAV_STATE_ACTIVE,
    ) -> bytes:
        """Encode un paquet HEARTBEAT (1 Hz)."""
        self._ensure_monotonic_timestamp()
        msg = self.mav.heartbeat_encode(mav_type, autopilot, base_mode, custom_mode, system_status)
        return msg.pack(self.mav)  # type: ignore

    def encode_attitude(
        self,
        time_boot_ms: int,
        roll: float,
        pitch: float,
        yaw: float,
        rollspeed: float = 0.0,
        pitchspeed: float = 0.0,
        yawspeed: float = 0.0,
    ) -> bytes:
        """Encode l'attitude angulaire du drone."""
        self._ensure_monotonic_timestamp()
        msg = self.mav.attitude_encode(
            time_boot_ms, roll, pitch, yaw, rollspeed, pitchspeed, yawspeed
        )
        return msg.pack(self.mav)  # type: ignore

    def encode_global_position(
        self,
        time_boot_ms: int,
        lat_deg: float,
        lon_deg: float,
        alt_m: float,
        relative_alt_m: float,
        vx_ms: float = 0.0,
        vy_ms: float = 0.0,
        vz_ms: float = 0.0,
        hdg_cdeg: int = 0,
    ) -> bytes:
        """Encode la position GPS globale (coordonnees entieres en 1e7 degres)."""
        self._ensure_monotonic_timestamp()
        msg = self.mav.global_position_int_encode(
            time_boot_ms,
            int(lat_deg * 1e7),
            int(lon_deg * 1e7),
            int(alt_m * 1000),
            int(relative_alt_m * 1000),
            int(vx_ms * 100),
            int(vy_ms * 100),
            int(vz_ms * 100),
            hdg_cdeg,
        )
        return msg.pack(self.mav)  # type: ignore

    def encode_command_long(
        self,
        target_system: int,
        target_component: int,
        command_id: int,
        confirmation: int = 0,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0,
    ) -> bytes:
        """Encode une commande de vol (COMMAND_LONG)."""
        self._ensure_monotonic_timestamp()
        msg = self.mav.command_long_encode(
            target_system,
            target_component,
            command_id,
            confirmation,
            param1,
            param2,
            param3,
            param4,
            param5,
            param6,
            param7,
        )
        return msg.pack(self.mav)  # type: ignore

    def encode_command_ack(
        self, command_id: int, result: int = mavlink2.MAV_RESULT_ACCEPTED
    ) -> bytes:
        """Encode l'accuse de reception d'une commande."""
        self._ensure_monotonic_timestamp()
        msg = self.mav.command_ack_encode(command_id, result)
        return msg.pack(self.mav)  # type: ignore

    def decode_buffer(self, buffer: bytes) -> tuple[list[Any], list[str]]:
        """Decode un tampon d'octets et retourne les messages valides et les erreurs eventuelles."""
        messages: list[Any] = []
        errors: list[str] = []

        try:
            parsed = self.mav.parse_buffer(buffer)
            if parsed is not None:
                messages.extend(parsed)
        except mavlink2.MAVError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"Erreur inattendue de decodage: {e}")

        return messages, errors
