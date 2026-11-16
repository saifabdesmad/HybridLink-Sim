"""Modeles de donnees types pour HybridLink-Sim."""

import time
from dataclasses import dataclass, field
from enum import StrEnum


class FlightMode(StrEnum):
    INITIALIZING = "INITIALIZING"
    STANDBY = "STANDBY"
    GUIDED = "GUIDED"
    AUTO = "AUTO"
    RTL = "RTL"      # Return To Launch (Failsafe mode)
    LAND = "LAND"
    HOLD = "HOLD"


class LinkType(StrEnum):
    LINK_A = "LINK_A"  # Simule ExpressLRS (C2 haute priorite, faible latence)
    LINK_B = "LINK_B"  # Simule 4G/5G (Debit plus eleve, latence plus variable)


class LinkHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class VehicleState:
    armed: bool = False
    flight_mode: FlightMode = FlightMode.STANDBY
    latitude: float = 49.4000000  # Lat Heudiasyc / Compiegne (degres)
    longitude: float = 2.8000000  # Lon Heudiasyc / Compiegne (degres)
    altitude_m: float = 0.0
    relative_altitude_m: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    battery_percent: float = 100.0
    failsafe_active: bool = False
    last_gcs_heartbeat_time: float = field(default_factory=time.time)
    executed_commands_count: int = 0
    rejected_commands_count: int = 0
    last_command_executed: str = ""


@dataclass
class LinkQuality:
    link_type: LinkType
    rtt_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_rate: float = 0.0  # 0.0 a 1.0 (ou 0 a 100%)
    consecutive_heartbeats_missed: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    status: LinkHealthStatus = LinkHealthStatus.HEALTHY
    last_packet_time: float = field(default_factory=time.time)


@dataclass
class TelemetryFrame:
    timestamp: float
    armed: bool
    mode: str
    lat: float
    lon: float
    alt: float
    battery: float
    failsafe: bool
