"""Attaque par Alteration de Trame (Message Tampering / Man-in-the-Middle).

Intercepte une trame legitime et falsifie des octets de sa charge utile
(par exemple, modification de l'altitude d'un ordre de vol).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("hybridlink.attacker.tampering")


class TamperingAttack:
    """Modificateur d'integrite sur paquet en transit."""

    @staticmethod
    def tamper_payload(frame_bytes: bytes, byte_offset: int = 12, flip_mask: int = 0xFF) -> bytes:
        """Altere un octet de la charge utile pour simuler une falsification en vol."""
        if len(frame_bytes) <= byte_offset:
            byte_offset = len(frame_bytes) // 2

        arr = bytearray(frame_bytes)
        arr[byte_offset] ^= flip_mask

        logger.warning(
            f"[ATTAQUE ALTERATION] Bit-flip applique a l'offset {byte_offset} "
            f"(valeur alteree: 0x{arr[byte_offset]:02X})"
        )
        return bytes(arr)
