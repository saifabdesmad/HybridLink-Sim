"""Configuration globale pour le projet HybridLink-Sim.

Definit les constantes reseau, protocolaires, temporelles et cryptographiques.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    # Identifiants MAVLink (SysID / CompID)
    VEHICLE_SYSID: int = 1
    VEHICLE_COMPID: int = 1
    GCS_SYSID: int = 255
    GCS_COMPID: int = 190

    # Ports reseau par defaut
    VEHICLE_HOST: str = os.getenv("VEHICLE_HOST", "0.0.0.0")
    VEHICLE_PORT: int = int(os.getenv("VEHICLE_PORT", "14560"))

    GCS_HOST: str = os.getenv("GCS_HOST", "0.0.0.0")
    GCS_PORT: int = int(os.getenv("GCS_PORT", "14550"))

    # Ports des liaisons hybrides
    LINK_A_PORT: int = int(os.getenv("LINK_A_PORT", "14551"))  # Simule ExpressLRS
    LINK_B_PORT: int = int(os.getenv("LINK_B_PORT", "14552"))  # Simule Cellulaire 4G/5G

    # Frequences d'emission
    HEARTBEAT_FREQ_HZ: float = 1.0
    TELEMETRY_FREQ_HZ: float = 4.0
    PING_FREQ_HZ: float = 2.0

    # Parametres de Sûrete & Failsafe
    FAILSAFE_TIMEOUT_SEC: float = 3.0  # Si aucun battement de coeur apres 3s -> RTL
    HYSTERESIS_STABILITY_SEC: float = 2.0  # Duree de stabilite requise pour basculer
    RTT_MAX_LINK_A_MS: float = 25.0
    LOSS_MAX_LINK_A_PERCENT: float = 5.0

    # Parametres Cryptographiques MAVLink 2
    # Cle secrete partagee par defaut (256 bits = 32 octets)
    DEFAULT_SHARED_SECRET: bytes = b"HybridLinkSimSecretKeyHeudiasyc!"
    SIGNING_LINK_ID_A: int = 1
    SIGNING_LINK_ID_B: int = 2


DEFAULT_CONFIG = SimConfig()
