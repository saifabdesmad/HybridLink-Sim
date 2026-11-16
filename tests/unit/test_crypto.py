"""Tests unitaires du moteur cryptographique MAVLink 2 et de l'anti-rejeu."""

import time

from src.common.crypto import AntiReplayWindow, MavlinkSecurityEngine
from src.common.protocol import MavlinkCodec, mavlink2


def test_anti_replay_window_strictly_increasing() -> None:
    """Verifie l'acceptation normale de timestamps strictement croissants."""
    win = AntiReplayWindow(window_size=10)
    now_usec = int(time.time() * 100000)

    ok1, _ = win.check_and_update(now_usec)
    ok2, _ = win.check_and_update(now_usec + 100)
    ok3, _ = win.check_and_update(now_usec + 200)

    assert ok1 is True
    assert ok2 is True
    assert ok3 is True


def test_anti_replay_window_detects_replay() -> None:
    """Verifie le rejet immediat d'un timestamp deja vu (rejeu direct)."""
    win = AntiReplayWindow(window_size=10)
    now_usec = int(time.time() * 100000)

    win.check_and_update(now_usec)
    win.check_and_update(now_usec + 50)

    # Rejeu du premier timestamp
    is_valid, reason = win.check_and_update(now_usec)
    assert is_valid is False
    assert "deja enregistre" in reason


def test_security_engine_validates_legitimate_frame() -> None:
    """Verifie qu'une trame signee avec la bonne cle et un timestamp valide est acceptee."""
    key = b"CorrectKey1234567890123456789012"
    codec = MavlinkCodec(sys_id=255, comp_id=190, secret_key=key, link_id=1)
    engine = MavlinkSecurityEngine(secret_key=key, enforce_security=True)

    frame = codec.encode_command_long(
        target_system=1,
        target_component=1,
        command_id=mavlink2.MAV_CMD_NAV_TAKEOFF,
        param7=15.0,
    )

    report = engine.verify_frame(frame)
    assert report.is_valid is True
    assert engine.accepted_packets_count == 1
    assert engine.rejected_packets_count == 0


def test_security_engine_rejects_wrong_key() -> None:
    """Verifie le rejet d'une trame signee avec une fausse cle."""
    good_key = b"CorrectKey1234567890123456789012"
    bad_key = b"AttackerKey000000000000000000000"

    attacker_codec = MavlinkCodec(sys_id=255, comp_id=190, secret_key=bad_key, link_id=1)
    engine = MavlinkSecurityEngine(secret_key=good_key, enforce_security=True)

    frame = attacker_codec.encode_command_long(
        target_system=1,
        target_component=1,
        command_id=mavlink2.MAV_CMD_NAV_LAND,
    )

    report = engine.verify_frame(frame)
    assert report.is_valid is False
    assert report.is_tampered is True
    assert "invalide" in report.reason.lower()


def test_security_engine_rejects_unsigned_frame_when_enforced() -> None:
    """Verifie le rejet d'une trame depourvue de signature si la securite est activee."""
    key = b"CorrectKey1234567890123456789012"
    unsigned_codec = MavlinkCodec(sys_id=255, comp_id=190, secret_key=None)
    engine = MavlinkSecurityEngine(secret_key=key, enforce_security=True)

    frame = unsigned_codec.encode_command_long(
        target_system=1,
        target_component=1,
        command_id=mavlink2.MAV_CMD_NAV_LAND,
    )

    report = engine.verify_frame(frame)
    assert report.is_valid is False
    assert report.is_unsigned is True
