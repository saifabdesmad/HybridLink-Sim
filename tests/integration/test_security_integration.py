"""Tests d'integration comparatifs : evaluation face aux 4 cyberattaques avec et sans securite."""


from src.attacker.engine import AttackEngine
from src.common.models import FlightMode
from src.gcs.station import GroundControlStation
from src.vehicle.autopilot import SimulatedAutopilot


def test_attack_spoofing_comparison() -> None:
    """Compare l'attaque par usurpation (Spoofing) avec securite OFF vs securite ON."""
    key = b"SharedKeyHeudiasyc12345678901234"
    attacker = AttackEngine(target_host="127.0.0.1", target_port=14560)

    # 1. CAS SANS SECURITE (Vulnerable)
    vulnerable_vehicle = SimulatedAutopilot(secret_key=key, enforce_security=False)
    vulnerable_vehicle.state.armed = True
    vulnerable_vehicle.state.flight_mode = FlightMode.GUIDED

    # L'attaquant injecte un atterrissage pirate non signe
    spoofed_frame = attacker.spoofing.generate_unsigned_land_command()
    vulnerable_vehicle.handle_incoming_frame(spoofed_frame)

    # Le drone sans securite execute l'ordre pirate et passe en LAND !
    assert vulnerable_vehicle.state.flight_mode == FlightMode.LAND
    assert vulnerable_vehicle.fraudulent_commands_executed >= 1

    # 2. CAS AVEC SECURITE MAVLINK 2 (Durci)
    hardened_vehicle = SimulatedAutopilot(secret_key=key, enforce_security=True)
    hardened_vehicle.state.armed = True
    hardened_vehicle.state.flight_mode = FlightMode.GUIDED

    # L'attaquant tente d'injecter le meme ordre non signe
    accepted = hardened_vehicle.handle_incoming_frame(spoofed_frame)

    # Le drone securise rejette categoriquement la trame, conserve son mode et zero commande pirate
    assert accepted is False
    assert hardened_vehicle.state.flight_mode == FlightMode.GUIDED
    assert hardened_vehicle.fraudulent_commands_executed == 0
    assert hardened_vehicle.state.rejected_commands_count >= 1


def test_attack_replay_comparison() -> None:
    """Compare l'attaque par rejeu (Replay) avec securite OFF vs securite ON."""
    key = b"SharedKeyHeudiasyc12345678901234"
    gcs = GroundControlStation(secret_key=key)
    attacker = AttackEngine(target_host="127.0.0.1", target_port=14560)

    # La GCS genere une commande legitime (ex: LAND)
    legit_land = gcs.send_land()

    # 1. CAS SANS SECURITE (Anti-rejeu inactif)
    vulnerable_vehicle = SimulatedAutopilot(secret_key=key, enforce_security=False)
    vulnerable_vehicle.state.armed = True
    vulnerable_vehicle.state.flight_mode = FlightMode.GUIDED

    # Rejeu de la commande passee
    replayed_frame = attacker.execute_replay(legit_land)
    vulnerable_vehicle.handle_incoming_frame(replayed_frame)
    assert vulnerable_vehicle.state.flight_mode == FlightMode.LAND

    # 2. CAS AVEC SECURITE (Fenetre anti-rejeu active)
    hardened_vehicle = SimulatedAutopilot(secret_key=key, enforce_security=True)
    hardened_vehicle.state.armed = True
    hardened_vehicle.state.flight_mode = FlightMode.GUIDED

    # Le drone recoit d'abord la trame legitime
    first_reception = hardened_vehicle.handle_incoming_frame(legit_land)
    assert first_reception is True
    assert hardened_vehicle.state.flight_mode == FlightMode.LAND

    # Remettre en mode GUIDED pour tester l'impact d'un rejeu
    hardened_vehicle.state.flight_mode = FlightMode.GUIDED

    # L'attaquant rejoue la meme trame avec le meme timestamp
    replay_reception = hardened_vehicle.handle_incoming_frame(replayed_frame)

    # La fenetre anti-rejeu doit detecter et bloquer le rejeu
    assert replay_reception is False
    assert hardened_vehicle.state.flight_mode == FlightMode.GUIDED
    assert hardened_vehicle.security_engine.replay_attempts_count >= 1


def test_attack_tampering_comparison() -> None:
    """Verifie le rejet d'une trame dont des octets ont ete alteres en vol."""
    key = b"SharedKeyHeudiasyc12345678901234"
    gcs = GroundControlStation(secret_key=key)
    attacker = AttackEngine(target_host="127.0.0.1", target_port=14560)

    legit_cmd = gcs.send_takeoff(20.0)
    tampered_cmd = attacker.execute_tampering(legit_cmd)

    hardened_vehicle = SimulatedAutopilot(secret_key=key, enforce_security=True)
    accepted = hardened_vehicle.handle_incoming_frame(tampered_cmd)

    # L'alteration invalide le HMAC-SHA256 -> trame rejetee
    assert accepted is False
    assert hardened_vehicle.security_engine.tamper_attempts_count >= 1
