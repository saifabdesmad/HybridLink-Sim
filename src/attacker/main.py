"""Point d'entree du conteneur d'attaque ATTACKER."""

from __future__ import annotations

import asyncio
import logging
import os

from src.attacker.engine import AttackEngine
from src.common.config import DEFAULT_CONFIG
from src.gcs.station import GroundControlStation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ATTACKER] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.attacker")


class AttackerUdpClient(asyncio.DatagramProtocol):
    """Client UDP pour l'injection malveillante."""

    def __init__(self, target_host: str, target_port: int) -> None:
        self.target_host = target_host
        self.target_port = target_port
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore

    def send_packet(self, data: bytes) -> None:
        if self.transport:
            self.transport.sendto(data, (self.target_host, self.target_port))


async def run_attacker() -> None:
    target_host = os.getenv("TARGET_HOST", "vehicle")
    target_port = int(os.getenv("TARGET_PORT", str(DEFAULT_CONFIG.VEHICLE_PORT)))
    attack_type = os.getenv("ATTACK_TYPE", "spoofing").lower()
    delay_s = float(os.getenv("ATTACK_DELAY_SEC", "5.0"))

    logger.info(f"Conteneur d'attaque arme contre {target_host}:{target_port}. Attaque: {attack_type}")
    logger.info(f"Attente de {delay_s}s avant declenchement de l'attaque...")
    await asyncio.sleep(delay_s)

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: AttackerUdpClient(target_host, target_port),
        local_addr=("0.0.0.0", 0),
    )

    engine = AttackEngine(target_host, target_port)
    engine.send_packet = protocol.send_packet

    if attack_type == "spoofing":
        logger.warning("Injection de 3 commandes usurpées d'atterrissage forcé...")
        for _ in range(3):
            engine.execute_spoofing_unsigned_land()
            await asyncio.sleep(1.0)

    elif attack_type == "tampering":
        logger.warning("Falsification et réinjection de commande avec bit-flip...")
        legit_gcs = GroundControlStation()
        legit_pkt = legit_gcs.send_arm(True)
        engine.execute_tampering(legit_pkt)

    elif attack_type == "replay":
        logger.warning("Interception d'une commande légitime et rejeu malveillant...")
        legit_gcs = GroundControlStation()
        legit_pkt = legit_gcs.send_land()
        await asyncio.sleep(2.0)
        engine.execute_replay(legit_pkt)

    elif attack_type == "dos":
        logger.warning("Inondation par déni de service (DoS) pendant 5s...")
        await engine.execute_dos_flood(duration_s=5.0)

    transport.close()
    logger.info("Campagne d'attaque achevée.")


def main() -> None:
    try:
        asyncio.run(run_attacker())
    except KeyboardInterrupt:
        logger.info("Attaquant interrompu.")


if __name__ == "__main__":
    main()
