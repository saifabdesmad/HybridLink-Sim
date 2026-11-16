"""Point d'entree du conteneur/processus LINK-MANAGER."""

from __future__ import annotations

import asyncio
import logging
import os

from src.common.config import DEFAULT_CONFIG
from src.common.models import LinkType
from src.link_manager.router import HybridLinkRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [LINK-MANAGER] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.link_manager")


class GcsUplinkProtocol(asyncio.DatagramProtocol):
    """Reception des commandes GCS montantes."""

    def __init__(self, router: HybridLinkRouter) -> None:
        self.router = router
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.router.route_uplink_gcs_to_vehicle(data)


class LinkDownlinkProtocol(asyncio.DatagramProtocol):
    """Reception de la telemetrie descendante sur un lien specifique (A ou B)."""

    def __init__(self, router: HybridLinkRouter, link_type: LinkType) -> None:
        self.router = router
        self.link_type = link_type
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.router.route_downlink_vehicle_to_gcs(data, self.link_type)


async def run_link_manager() -> None:
    # Parametres reseau
    gcs_host = os.getenv("GCS_HOST", "127.0.0.1")
    gcs_port = int(os.getenv("GCS_PORT", str(DEFAULT_CONFIG.GCS_PORT)))

    link_a_host = os.getenv("LINK_A_HOST", "127.0.0.1")
    link_a_port = int(os.getenv("LINK_A_PORT", str(DEFAULT_CONFIG.LINK_A_PORT)))

    link_b_host = os.getenv("LINK_B_HOST", "127.0.0.1")
    link_b_port = int(os.getenv("LINK_B_PORT", str(DEFAULT_CONFIG.LINK_B_PORT)))

    router = HybridLinkRouter()
    loop = asyncio.get_running_loop()

    # 1. Endpoint pour ecouter la GCS (port d'entree proxy montante 14555)
    gcs_proxy_port = int(os.getenv("GCS_PROXY_PORT", "14555"))
    gcs_trans, _ = await loop.create_datagram_endpoint(
        lambda: GcsUplinkProtocol(router),
        local_addr=("0.0.0.0", gcs_proxy_port),
    )

    # 2. Endpoint pour Lien A (emission/reception)
    link_a_listen_port = int(os.getenv("LINK_A_LISTEN_PORT", "14561"))
    link_a_trans, _ = await loop.create_datagram_endpoint(
        lambda: LinkDownlinkProtocol(router, LinkType.LINK_A),
        local_addr=("0.0.0.0", link_a_listen_port),
    )

    # 3. Endpoint pour Lien B (emission/reception)
    link_b_listen_port = int(os.getenv("LINK_B_LISTEN_PORT", "14562"))
    link_b_trans, _ = await loop.create_datagram_endpoint(
        lambda: LinkDownlinkProtocol(router, LinkType.LINK_B),
        local_addr=("0.0.0.0", link_b_listen_port),
    )

    # Configurer les sorties de routage
    def send_to_gcs_impl(data: bytes) -> None:
        gcs_trans.sendto(data, (gcs_host, gcs_port))

    def send_to_link_a_impl(data: bytes) -> None:
        link_a_trans.sendto(data, (link_a_host, link_a_port))

    def send_to_link_b_impl(data: bytes) -> None:
        link_b_trans.sendto(data, (link_b_host, link_b_port))

    router.send_to_gcs = send_to_gcs_impl
    router.send_to_link_a = send_to_link_a_impl
    router.send_to_link_b = send_to_link_b_impl

    logger.info(
        f"Link-Manager actif : Entree GCS sur :{gcs_proxy_port} | "
        f"Lien A vers {link_a_host}:{link_a_port} | Lien B vers {link_b_host}:{link_b_port}"
    )

    try:
        report_counter = 0
        while True:
            await asyncio.sleep(0.1)
            state = router.periodic_tick()

            report_counter += 1
            if report_counter >= 20:  # Toutes les 2 secondes
                report_counter = 0
                sa = router.monitor_a.stats
                sb = router.monitor_b.stats
                logger.info(
                    f"[QUALITE LIENS] FSM: {state.value} | "
                    f"Lien A: RTT={sa.rtt_ms:.1f}ms, Jitter={sa.jitter_ms:.1f}ms, Perte={sa.packet_loss_rate:.1%} ({sa.status.value}) | "
                    f"Lien B: RTT={sb.rtt_ms:.1f}ms, Jitter={sb.jitter_ms:.1f}ms, Perte={sb.packet_loss_rate:.1%} ({sb.status.value})"
                )

    except asyncio.CancelledError:
        logger.info("Arret demande du Link-Manager.")
    finally:
        gcs_trans.close()
        link_a_trans.close()
        link_b_trans.close()


def main() -> None:
    try:
        asyncio.run(run_link_manager())
    except KeyboardInterrupt:
        logger.info("Link-Manager arrete.")


if __name__ == "__main__":
    main()
