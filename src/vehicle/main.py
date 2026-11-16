"""Point d'entree du conteneur/processus VEHICLE (Drone MAVLink 2)."""

from __future__ import annotations

import asyncio
import logging
import os

from src.common.config import DEFAULT_CONFIG
from src.vehicle.autopilot import SimulatedAutopilot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [VEHICLE] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.vehicle")


class VehicleUdpServer(asyncio.DatagramProtocol):
    """Serveur UDP asynchrone pour la reception et l'envoi de trames MAVLink 2."""

    def __init__(self, autopilot: SimulatedAutopilot, target_host: str, target_port: int) -> None:
        self.autopilot = autopilot
        self.target_host = target_host
        self.target_port = target_port
        self.transport: asyncio.DatagramTransport | None = None
        self.last_client_addr: tuple[str, int] | None = None

        # Configurer le callback d'envoi de l'autopilote
        self.autopilot.send_packet_callback = self.send_packet

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore
        logger.info(
            f"Serveur UDP vehicule actif. Ecoute sur port {DEFAULT_CONFIG.VEHICLE_PORT}. "
            f"Destination par defaut: {self.target_host}:{self.target_port}"
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.last_client_addr = addr
        self.autopilot.handle_incoming_frame(data)

    def send_packet(self, data: bytes) -> None:
        """Envoie un paquet UDP vers le client ou l'hote cible."""
        if self.transport:
            dest = self.last_client_addr or (self.target_host, self.target_port)
            try:
                self.transport.sendto(data, dest)
            except Exception as e:
                logger.error(f"Erreur d'envoi UDP vers {dest}: {e}")


async def run_vehicle() -> None:
    port = int(os.getenv("VEHICLE_PORT", str(DEFAULT_CONFIG.VEHICLE_PORT)))
    target_host = os.getenv("TARGET_HOST", "127.0.0.1")
    target_port = int(os.getenv("TARGET_PORT", str(DEFAULT_CONFIG.GCS_PORT)))

    secret_key = os.getenv("MAVLINK_SECRET_KEY", "HybridLinkSimSecretKeyHeudiasyc!").encode("utf-8")
    autopilot = SimulatedAutopilot(secret_key=secret_key)

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: VehicleUdpServer(autopilot, target_host, target_port),
        local_addr=("0.0.0.0", port),
    )

    logger.info("Demarrage de la boucle de dynamique de vol et de telemetrie...")
    dt = 0.1  # 10 Hz
    hb_counter = 0
    telem_counter = 0

    try:
        while True:
            await asyncio.sleep(dt)
            autopilot.update_physics(dt)

            # Heartbeat a 1 Hz (tous les 10 cycles a 10 Hz)
            hb_counter += 1
            if hb_counter >= 10:
                hb_counter = 0
                protocol.send_packet(autopilot.generate_heartbeat())

            # Telemetrie Attitude & Position a 4 Hz (tous les ~2.5 cycles)
            telem_counter += 1
            if telem_counter >= 2:
                telem_counter = 0
                protocol.send_packet(autopilot.generate_attitude())
                protocol.send_packet(autopilot.generate_global_position())

    except asyncio.CancelledError:
        logger.info("Arret demande du simulateur vehicule.")
    finally:
        transport.close()


def main() -> None:
    try:
        asyncio.run(run_vehicle())
    except KeyboardInterrupt:
        logger.info("Processus vehicule arrete par l'utilisateur.")


if __name__ == "__main__":
    main()
