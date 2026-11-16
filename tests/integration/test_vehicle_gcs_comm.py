"""Test d'integration : communication directe MAVLink 2 entre GCS et Vehicle."""

import asyncio

import pytest

from src.common.models import FlightMode
from src.common.protocol import mavlink2
from src.gcs.station import GroundControlStation
from src.vehicle.autopilot import SimulatedAutopilot


@pytest.mark.asyncio
async def test_gcs_vehicle_direct_handshake() -> None:
    """Verifie le handshake Heartbeat, l'armement, le decollage et la reception d'ACK."""
    key = b"TestSecretKeyHeudiasyc1234567890"
    vehicle = SimulatedAutopilot(secret_key=key)
    gcs = GroundControlStation(secret_key=key)

    # Brancher les callbacks de communication directe (boucle locale)
    vehicle.send_packet_callback = gcs.handle_incoming_frame
    gcs.send_packet_callback = lambda data: None if vehicle.handle_incoming_frame(data) else None

    # 1. Echange de Heartbeats
    hb_v = vehicle.generate_heartbeat()
    gcs.handle_incoming_frame(hb_v)
    assert gcs.connected is True

    hb_g = gcs.generate_heartbeat()
    vehicle.handle_incoming_frame(hb_g)
    assert vehicle.state.last_gcs_heartbeat_time > 0

    # 2. Ordre d'armement
    arm_cmd = gcs.send_arm(True)
    vehicle.handle_incoming_frame(arm_cmd)
    assert vehicle.state.armed is True
    assert gcs.acks_received.get(mavlink2.MAV_CMD_COMPONENT_ARM_DISARM) == mavlink2.MAV_RESULT_ACCEPTED

    # 3. Ordre de decollage (Takeoff 15m)
    takeoff_cmd = gcs.send_takeoff(15.0)
    vehicle.handle_incoming_frame(takeoff_cmd)
    assert vehicle.state.flight_mode == FlightMode.GUIDED
    assert gcs.acks_received.get(mavlink2.MAV_CMD_NAV_TAKEOFF) == mavlink2.MAV_RESULT_ACCEPTED

    # 4. Simulation de dynamique physique sur 3 secondes
    for _ in range(30):
        vehicle.update_physics(0.1)

    assert vehicle.state.altitude_m > 5.0  # Le drone est en montee

    # 5. Envoi de telemetrie de position vers la GCS
    pos_frame = vehicle.generate_global_position()
    gcs.handle_incoming_frame(pos_frame)
    assert gcs.vehicle_alt > 5.0


@pytest.mark.asyncio
async def test_failsafe_trigger_on_heartbeat_loss() -> None:
    """Verifie la propriete de surete : basculement en RTL apres perte du signal GCS pendant >3s."""
    key = b"TestSecretKeyHeudiasyc1234567890"
    vehicle = SimulatedAutopilot(secret_key=key, failsafe_timeout_s=1.0)
    gcs = GroundControlStation(secret_key=key)

    # Armer et decoller
    vehicle.handle_incoming_frame(gcs.send_arm(True))
    vehicle.handle_incoming_frame(gcs.send_takeoff(10.0))
    initial_mode: FlightMode = vehicle.state.flight_mode
    assert initial_mode == FlightMode.GUIDED

    # Simuler l'ecoulement du temps sans aucun heartbeat GCS
    await asyncio.sleep(1.2)
    vehicle.update_physics(0.1)

    # Le failsafe doit etre actif et le mode bascule en RTL
    final_mode: FlightMode = vehicle.state.flight_mode
    assert vehicle.state.failsafe_active is True
    assert final_mode == FlightMode.RTL
