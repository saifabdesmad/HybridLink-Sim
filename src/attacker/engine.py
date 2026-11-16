"""Moteur d'orchestration des attaques cybernetiques."""

from __future__ import annotations

import logging
from collections.abc import Callable

from src.attacker.attacks.dos import DosFloodAttack
from src.attacker.attacks.replay import ReplayAttack
from src.attacker.attacks.spoofing import SpoofingAttack
from src.attacker.attacks.tampering import TamperingAttack

logger = logging.getLogger("hybridlink.attacker.engine")


class AttackEngine:
    """Orchestrateur des campagnes d'injection malveillante."""

    def __init__(self, target_host: str, target_port: int) -> None:
        self.target_host = target_host
        self.target_port = target_port
        self.spoofing = SpoofingAttack()
        self.tampering = TamperingAttack()
        self.dos = DosFloodAttack(target_host, target_port)
        self.send_packet: Callable[[bytes], None] | None = None

    def execute_spoofing_unsigned_land(self) -> bytes:
        """Injecte une commande d'atterrissage non signee."""
        pkt = self.spoofing.generate_unsigned_land_command()
        if self.send_packet:
            self.send_packet(pkt)
        return pkt

    def execute_spoofing_bogus_disarm(self) -> bytes:
        """Injecte une commande de desarment signee avec une fausse cle."""
        pkt = self.spoofing.generate_bogus_signed_disarm_command()
        if self.send_packet:
            self.send_packet(pkt)
        return pkt

    def execute_replay(self, legitimate_packet: bytes) -> bytes:
        """Execute une attaque par rejeu sur un paquet intercepte."""
        replay = ReplayAttack(legitimate_packet)
        pkt = replay.generate_attack_frame()
        if self.send_packet:
            self.send_packet(pkt)
        return pkt

    def execute_tampering(self, legitimate_packet: bytes) -> bytes:
        """Execute une falsification de charge utile sur un paquet intercepte."""
        tampered_pkt = self.tampering.tamper_payload(legitimate_packet)
        if self.send_packet:
            self.send_packet(tampered_pkt)
        return tampered_pkt

    async def execute_dos_flood(self, duration_s: float = 3.0) -> int:
        """Lance une inondation DoS."""
        if self.send_packet:
            self.dos.send_callback = lambda data, h, p: self.send_packet(data)  # type: ignore[misc]
        await self.dos.run_flood(duration_s=duration_s)
        return self.dos.packets_flooded
