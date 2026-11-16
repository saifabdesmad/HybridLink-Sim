"""Test d'integration bout-en-bout du Link-Manager : routage adaptatif, failover et deduplication."""


from src.common.models import LinkType
from src.gcs.station import GroundControlStation
from src.link_manager.fsm import RouterState
from src.link_manager.router import HybridLinkRouter
from src.vehicle.autopilot import SimulatedAutopilot


def test_hybrid_router_uplink_switching() -> None:
    """Verifie le basculement dynamique des commandes montantes du Lien A vers le Lien B."""
    router = HybridLinkRouter(hysteresis_stability_s=0.2)
    gcs = GroundControlStation()

    packets_on_a: list[bytes] = []
    packets_on_b: list[bytes] = []

    router.send_to_link_a = lambda data: packets_on_a.append(data)
    router.send_to_link_b = lambda data: packets_on_b.append(data)

    # 1. Etat nominal : envoi d'une commande d'armement -> doit passer sur Lien A
    arm_pkt = gcs.send_arm(True)
    state = router.route_uplink_gcs_to_vehicle(arm_pkt)
    assert state == RouterState.PRIMARY_LINK_A
    assert len(packets_on_a) == 1
    assert len(packets_on_b) == 0

    # 2. Simulation de panne du Lien A
    router.monitor_a.mark_down()
    router.monitor_b.mark_healthy()

    # 3. Envoi d'une commande de decollage -> doit etre routee sur Lien B
    takeoff_pkt = gcs.send_takeoff(15.0)
    state = router.route_uplink_gcs_to_vehicle(takeoff_pkt)
    assert state == RouterState.FAILOVER_LINK_B
    assert len(packets_on_a) == 1
    assert len(packets_on_b) == 1


def test_hybrid_router_downlink_deduplication() -> None:
    """Verifie que les trames dupliquees sur les deux liens sont filtrees avant la GCS."""
    router = HybridLinkRouter()
    vehicle = SimulatedAutopilot()

    gcs_received_packets: list[bytes] = []
    router.send_to_gcs = lambda data: gcs_received_packets.append(data)

    # Generer une trame de telemetrie
    hb_pkt = vehicle.generate_heartbeat()

    # Le drone emet la meme trame simultanement sur le Lien A et le Lien B
    delivered_a = router.route_downlink_vehicle_to_gcs(hb_pkt, LinkType.LINK_A)
    delivered_b = router.route_downlink_vehicle_to_gcs(hb_pkt, LinkType.LINK_B)

    # La premiere trame doit etre relayee, la seconde doit etre classee comme doublon et jetee
    assert delivered_a is True
    assert delivered_b is False
    assert len(gcs_received_packets) == 1
