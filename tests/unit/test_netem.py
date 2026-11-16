"""Tests unitaires du gestionnaire NetEm et de l'interpreteur de scenarios YAML."""

from pathlib import Path

import pytest

from src.common.models import LinkType
from src.netem.scenario_runner import ScenarioRunner
from src.netem.tc_manager import NetemProfile, SimulatedChannel, TrafficControlManager


@pytest.mark.asyncio
async def test_simulated_channel_forwarding() -> None:
    """Verifie la transmission normale avec delai positif et sans perte."""
    profile = NetemProfile(latency_ms=10.0, jitter_ms=1.0, loss_percent=0.0, is_up=True)
    channel = SimulatedChannel("TestChannel", profile)

    received_data: list[bytes] = []
    channel.forward_callback = lambda data: received_data.append(data)

    test_pkt = b"HEARTBEAT_DATA_123"
    await channel.inject_packet(test_pkt)

    assert len(received_data) == 1
    assert received_data[0] == test_pkt
    assert channel.packets_forwarded == 1
    assert channel.packets_dropped == 0


@pytest.mark.asyncio
async def test_simulated_channel_packet_drop_when_down() -> None:
    """Verifie le rejet immediat des trames lorsque le lien est coupe (DOWN)."""
    profile = NetemProfile(latency_ms=10.0, jitter_ms=1.0, loss_percent=100.0, is_up=False)
    channel = SimulatedChannel("TestChannelDown", profile)

    received_data: list[bytes] = []
    channel.forward_callback = lambda data: received_data.append(data)

    await channel.inject_packet(b"TEST_DROP")

    assert len(received_data) == 0
    assert channel.packets_dropped == 1
    assert channel.packets_forwarded == 0


def test_scenario_loader_and_dispatch() -> None:
    """Verifie le chargement d'un fichier YAML et le declenchement d'actions sur tc_manager."""
    scen_path = Path("scenarios/02_degradation_link_a.yaml")
    assert scen_path.exists()

    tc = TrafficControlManager()
    runner = ScenarioRunner(scen_path, tc)

    assert runner.scenario_data["name"] == "02_degradation_link_a"
    assert len(runner.scenario_data["events"]) == 2

    # Verifier l'application d'un evenement de coupure
    runner._dispatch_event({"action": "cut_link_a", "params": {}, "description": "Test cut"}, elapsed=5.0)
    assert tc.profiles[LinkType.LINK_A].is_up is False
    assert tc.profiles[LinkType.LINK_A].loss_percent == 100.0

    # Verifier le retablissement
    runner._dispatch_event({
        "action": "restore_link_a",
        "params": {"latency_ms": 12.0, "jitter_ms": 2.0, "loss_percent": 0.5, "status": "UP"},
        "description": "Test restore",
    }, elapsed=10.0)
    assert tc.profiles[LinkType.LINK_A].is_up is True
    assert tc.profiles[LinkType.LINK_A].latency_ms == 12.0
