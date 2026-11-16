"""Attaque par Rejeu (Replay Attack).

Intercepte une commande legitime passee et la retransmet a l'identique
pour forcer une action non consentie par l'operateur.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("hybridlink.attacker.replay")


class ReplayAttack:
    """Attaque par rejeu d'une trame signee anterieure."""

    def __init__(self, captured_frame: bytes) -> None:
        self.captured_frame = captured_frame
        self.injection_count = 0

    def generate_attack_frame(self) -> bytes:
        """Produit la trame rejouee (exacte copie bit-a-bit de la trame interceptee)."""
        self.injection_count += 1
        logger.warning(
            f"[ATTAQUE REJEU] Injection trame rejouee #{self.injection_count} "
            f"({len(self.captured_frame)} octets)"
        )
        return self.captured_frame
