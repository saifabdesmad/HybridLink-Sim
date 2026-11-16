"""Passerelle proxy UDP NetEm avec injection dynamique de perturbations."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from src.common.config import DEFAULT_CONFIG
from src.common.models import LinkType
from src.netem.scenario_runner import ScenarioRunner
from src.netem.tc_manager import TrafficControlManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NETEM-PROXY] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.netem")


class NetemUdpBridge(asyncio.DatagramProtocol):
    """Pont UDP appliquant les delais, la gigue et les pertes configurees."""

    def __init__(
        self,
        tc_manager: TrafficControlManager,
        link_type: LinkType,
        target_host: str,
        target_port: int,
    ) -> None:
        self.tc_manager = tc_manager
        self.link_type = link_type
        self.target_host = target_host
        self.target_port = target_port
        self.transport: asyncio.DatagramTransport | None = None

        channel = self.tc_manager.channels[link_type]
        channel.forward_callback = self._forward_packet

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        # Injection asynchrone dans le canal perturbe
        channel = self.tc_manager.channels[self.link_type]
        asyncio.create_task(channel.inject_packet(data))

    def _forward_packet(self, data: bytes) -> None:
        if self.transport:
            try:
                self.transport.sendto(data, (self.target_host, self.target_port))
            except Exception as e:
                logger.error(f"Erreur transmission NetEm {self.link_type.value}: {e}")


async def run_netem_gateway() -> None:
    dest_host = os.getenv("VEHICLE_HOST", "vehicle")
    dest_port = int(os.getenv("VEHICLE_PORT", str(DEFAULT_CONFIG.VEHICLE_PORT)))

    port_a = int(os.getenv("LINK_A_PORT", str(DEFAULT_CONFIG.LINK_A_PORT)))
    port_b = int(os.getenv("LINK_B_PORT", str(DEFAULT_CONFIG.LINK_B_PORT)))

    scenario_name = os.getenv("SCENARIO", "01_nominal")
    if not scenario_name.endswith(".yaml"):
        scenario_name = f"{scenario_name}.yaml"

    tc_manager = TrafficControlManager()
    loop = asyncio.get_running_loop()

    # Ponts UDP pour chaque lien
    t_a, _ = await loop.create_datagram_endpoint(
        lambda: NetemUdpBridge(tc_manager, LinkType.LINK_A, dest_host, dest_port),
        local_addr=("0.0.0.0", port_a),
    )
    t_b, _ = await loop.create_datagram_endpoint(
        lambda: NetemUdpBridge(tc_manager, LinkType.LINK_B, dest_host, dest_port),
        local_addr=("0.0.0.0", port_b),
    )

    logger.info(
        f"Passerelle NetEm prete : Lien A sur :{port_a} -> {dest_host}:{dest_port} | "
        f"Lien B sur :{port_b} -> {dest_host}:{dest_port}"
    )

    # Lancement du scenario en tache de fond
    scen_path = Path("scenarios") / scenario_name
    if scen_path.exists():
        runner = ScenarioRunner(scen_path, tc_manager)
        asyncio.create_task(runner.run())
    else:
        logger.warning(f"Fichier scenario {scen_path} non trouve, profils par defaut conserves.")

    try:
        while True:
            await asyncio.sleep(5.0)
            ca = tc_manager.channels[LinkType.LINK_A]
            cb = tc_manager.channels[LinkType.LINK_B]
            logger.info(
                f"[STATISTIQUES NETEM] Canal A: {ca.packets_forwarded} transmis, {ca.packets_dropped} jetes | "
                f"Canal B: {cb.packets_forwarded} transmis, {cb.packets_dropped} jetes"
            )
    except asyncio.CancelledError:
        logger.info("Arret de la passerelle NetEm.")
    finally:
        t_a.close()
        t_b.close()


def main() -> None:
    try:
        asyncio.run(run_netem_gateway())
    except KeyboardInterrupt:
        logger.info("NetEm arrete.")


if __name__ == "__main__":
    main()
