"""Moteur cryptographique MAVLink 2 et fenetre anti-rejeu (style IPsec RFC 4303).

Fournit l'authentification MAVLink 2 (SHA-256 avec cle secrete), le controle strict
des horodatages et la protection contre les attaques par rejeu.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

logger = logging.getLogger("hybridlink.crypto")


@dataclass
class SecurityReport:
    is_valid: bool
    reason: str
    link_id: int
    timestamp_usec: int
    is_replayed: bool = False
    is_tampered: bool = False
    is_unsigned: bool = False


class AntiReplayWindow:
    """Fenetre glissante anti-rejeu basee sur le principe de l'IPsec ESP (RFC 4303).

    Maintient le timestamp le plus eleve recu et un ensemble des timestamps
    recus dans la fenetre recente sans risque de rejeu.
    """

    def __init__(self, window_size: int = 64) -> None:
        self.window_size = window_size
        self.max_timestamp: int = 0
        self.seen_timestamps: set[int] = set()

    def check_and_update(self, timestamp: int) -> tuple[bool, str]:
        """Verifie si un timestamp est valide (strictement croissant ou dans la fenetre non encore vu)."""
        if self.max_timestamp == 0:
            self.max_timestamp = timestamp
            self.seen_timestamps.add(timestamp)
            return True, "Initialisation de la fenetre anti-rejeu"

        # Cas 1 : Nouveau paquet plus recent
        if timestamp > self.max_timestamp:
            self.max_timestamp = timestamp
            self.seen_timestamps.add(timestamp)
            # Nettoyer les elements hors fenetre
            min_valid = self.max_timestamp - (self.window_size * 100000)
            self.seen_timestamps = {t for t in self.seen_timestamps if t >= min_valid}
            return True, "Paquet recent accepte"

        # Cas 2 : Paquet plus vieux que le seuil de la fenetre
        min_valid = self.max_timestamp - (self.window_size * 100000)
        if timestamp < min_valid:
            return False, f"Timestamp trop ancien ({timestamp} < seuil {min_valid}) - Rejeu suspecte"

        # Cas 3 : Paquet dans la fenetre mais deja vu
        if timestamp in self.seen_timestamps:
            return False, f"Timestamp {timestamp} deja enregistre - Attaque par rejeu detectee !"

        # Cas 4 : Paquet dans la fenetre et pas encore vu (reordonnancement legitime)
        self.seen_timestamps.add(timestamp)
        return True, "Paquet reordonne accepte dans la fenetre"


class MavlinkSecurityEngine:
    """Moteur de validation de securite pour trames MAVLink 2."""

    def __init__(
        self,
        secret_key: bytes,
        enforce_security: bool = True,
        window_size: int = 64,
    ) -> None:
        if len(secret_key) != 32:
            secret_key = secret_key.ljust(32, b"\x00")[:32]
        self.secret_key = secret_key
        self.enforce_security = enforce_security
        self.replay_windows: dict[tuple[int, int], AntiReplayWindow] = {}
        self.window_size = window_size

        self.rejected_packets_count = 0
        self.accepted_packets_count = 0
        self.replay_attempts_count = 0
        self.tamper_attempts_count = 0

    def verify_frame(self, frame_bytes: bytes) -> SecurityReport:
        """Verifie la structure, la signature et l'anti-rejeu d'une trame MAVLink 2."""
        # Mode vulnerable (sans securite pour benchmark comparatif)
        if not self.enforce_security:
            return SecurityReport(
                is_valid=True,
                reason="Securite desactivee (mode vulnerable)",
                link_id=0,
                timestamp_usec=0,
            )

        if len(frame_bytes) < 25:
            self.rejected_packets_count += 1
            return SecurityReport(
                is_valid=False,
                reason=f"Trame trop courte ({len(frame_bytes)}B < 25B)",
                link_id=0,
                timestamp_usec=0,
                is_unsigned=True,
            )

        magic = frame_bytes[0]
        if magic != 0xFD:
            self.rejected_packets_count += 1
            return SecurityReport(
                is_valid=False,
                reason=f"Magic byte invalide (0x{magic:02X} != 0xFD)",
                link_id=0,
                timestamp_usec=0,
            )

        incompat_flags = frame_bytes[2]
        is_signed = bool(incompat_flags & 0x01)
        if not is_signed:
            self.rejected_packets_count += 1
            return SecurityReport(
                is_valid=False,
                reason="Trame non signee (Flag incompat 0x01 absent)",
                link_id=0,
                timestamp_usec=0,
                is_unsigned=True,
            )

        sys_id = frame_bytes[5]
        sig_block = frame_bytes[-13:]
        link_id = sig_block[0]
        ts_bytes = sig_block[1:7]
        recv_sig = sig_block[7:13]

        timestamp = int.from_bytes(ts_bytes, byteorder="little", signed=False)

        # 1. Verification de la fenetre anti-rejeu
        window_key = (sys_id, link_id)
        if window_key not in self.replay_windows:
            self.replay_windows[window_key] = AntiReplayWindow(self.window_size)

        is_timestamp_valid, ts_reason = self.replay_windows[window_key].check_and_update(timestamp)
        if not is_timestamp_valid:
            self.rejected_packets_count += 1
            self.replay_attempts_count += 1
            return SecurityReport(
                is_valid=False,
                reason=ts_reason,
                link_id=link_id,
                timestamp_usec=timestamp,
                is_replayed=True,
            )

        # 2. Verification de la signature MAVLink 2 (SHA-256 avec cle secrete en prefixe)
        data_to_sign = frame_bytes[:-6]
        h = hashlib.new("sha256")
        h.update(self.secret_key)
        h.update(data_to_sign)
        computed_sig_48 = h.digest()[:6]

        if not hmac.compare_digest(recv_sig, computed_sig_48):
            self.rejected_packets_count += 1
            self.tamper_attempts_count += 1
            return SecurityReport(
                is_valid=False,
                reason="Signature cryptographique invalide (Falsification ou cle incorrecte)",
                link_id=link_id,
                timestamp_usec=timestamp,
                is_tampered=True,
            )

        self.accepted_packets_count += 1
        return SecurityReport(
            is_valid=True,
            reason="Signature et fenetre anti-rejeu valides",
            link_id=link_id,
            timestamp_usec=timestamp,
        )
