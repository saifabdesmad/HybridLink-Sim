"""Point d'entree du conteneur/processus GCS (Station Sol MAVLink 2)."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from src.common.config import DEFAULT_CONFIG
from src.gcs.station import GroundControlStation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [GCS] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.gcs")


class GcsUdpClient(asyncio.DatagramProtocol):
    """Client/Serveur UDP pour la station sol."""

    def __init__(self, gcs: GroundControlStation, target_host: str, target_port: int) -> None:
        self.gcs = gcs
        self.target_host = target_host
        self.target_port = target_port
        self.transport: asyncio.DatagramTransport | None = None

        self.gcs.send_packet_callback = self.send_packet

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore
        logger.info(
            f"Station Sol active. Ecoute sur port {DEFAULT_CONFIG.GCS_PORT}. "
            f"Cible: {self.target_host}:{self.target_port}"
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.gcs.handle_incoming_frame(data)

    def send_packet(self, data: bytes) -> None:
        if self.transport:
            try:
                self.transport.sendto(data, (self.target_host, self.target_port))
            except Exception as e:
                logger.error(f"Erreur d'envoi UDP GCS vers {self.target_host}:{self.target_port}: {e}")


async def run_gcs() -> None:
    port = int(os.getenv("GCS_PORT", str(DEFAULT_CONFIG.GCS_PORT)))
    target_host = os.getenv("TARGET_HOST", "127.0.0.1")
    target_port = int(os.getenv("TARGET_PORT", str(DEFAULT_CONFIG.VEHICLE_PORT)))

    secret_key = os.getenv("MAVLINK_SECRET_KEY", "HybridLinkSimSecretKeyHeudiasyc!").encode("utf-8")
    auto_mission = os.getenv("AUTO_MISSION", "true").lower() == "true"

    gcs = GroundControlStation(secret_key=secret_key)

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GcsUdpClient(gcs, target_host, target_port),
        local_addr=("0.0.0.0", port),
    )

    logger.info("Demarrage de la boucle de controle GCS...")
    start_time = time.time()
    armed_sent = False
    takeoff_sent = False

    try:
        while True:
            await asyncio.sleep(1.0)
            now = time.time()
            elapsed = now - start_time

            # Envoi periodique du Heartbeat GCS (1 Hz)
            protocol.send_packet(gcs.generate_heartbeat())

            # Mission de demonstration automatique
            if auto_mission and gcs.connected:
                if elapsed >= 2.0 and not armed_sent:
                    protocol.send_packet(gcs.send_arm(True))
                    armed_sent = True

                if elapsed >= 5.0 and not takeoff_sent:
                    protocol.send_packet(gcs.send_takeoff(12.0))
                    takeoff_sent = True

            # Affichage periodique du statut du drone
            if gcs.connected:
                logger.info(
                    f"[STATUT DRONE] Alt: {gcs.vehicle_alt:.1f}m | "
                    f"Arme: {gcs.vehicle_armed} | Failsafe: {gcs.vehicle_failsafe} | "
                    f"Trames recues: {gcs.telemetry_count}"
                )
            else:
                logger.info("[STATUT GCS] En attente de connexion avec le drone...")

    except asyncio.CancelledError:
        logger.info("Arret demande de la station sol.")
    finally:
        transport.close()


def main() -> None:
    try:
        asyncio.run(run_gcs())
    except KeyboardInterrupt:
        logger.info("Station sol arretee par l'utilisateur.")


if __name__ == "__main__":
    main()
