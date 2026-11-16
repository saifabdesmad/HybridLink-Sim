"""Module d'evaluation continue de la qualite des liens (RTT, Gigue RFC 3550, Pertes)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.common.models import LinkHealthStatus, LinkType


@dataclass
class LinkStats:
    link_type: LinkType
    rtt_ms: float = 10.0
    jitter_ms: float = 1.0
    packet_loss_rate: float = 0.0  # 0.0 a 1.0
    consecutive_heartbeats_missed: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    last_packet_time: float = field(default_factory=time.time)
    status: LinkHealthStatus = LinkHealthStatus.HEALTHY

    # Fenetre glissante de sequence pour calcul de perte
    _received_sequences: set[int] = field(default_factory=set)
    _max_seq_seen: int = -1
    _seq_window_size: int = 50

    # Variables internes pour le calcul de gigue (RFC 3550)
    _last_transit_time_ms: float | None = None


class LinkQualityMonitor:
    """Sonde et estime la qualite reseau d'une liaison selon les standards de l'IETF."""

    def __init__(
        self,
        link_type: LinkType,
        rtt_threshold_degraded_ms: float = 60.0,
        rtt_threshold_down_ms: float = 250.0,
        loss_threshold_degraded: float = 0.08,  # 8%
        loss_threshold_down: float = 0.35,      # 35%
        max_missed_heartbeats: int = 2,
    ) -> None:
        self.link_type = link_type
        self.rtt_threshold_degraded_ms = rtt_threshold_degraded_ms
        self.rtt_threshold_down_ms = rtt_threshold_down_ms
        self.loss_threshold_degraded = loss_threshold_degraded
        self.loss_threshold_down = loss_threshold_down
        self.max_missed_heartbeats = max_missed_heartbeats

        self.stats = LinkStats(link_type=link_type)
        self.pending_pings: dict[int, float] = {}

    def mark_down(self) -> None:
        """Force l'etat du lien a DOWN (pour simulation/tests)."""
        self.stats.consecutive_heartbeats_missed = self.max_missed_heartbeats + 1
        self.stats.status = LinkHealthStatus.DOWN

    def mark_degraded(self, rtt_ms: float = 120.0, loss: float = 0.15) -> None:
        """Force l'etat du lien a DEGRADED (pour simulation/tests)."""
        self.stats.rtt_ms = rtt_ms
        self.stats.packet_loss_rate = loss
        self.stats.consecutive_heartbeats_missed = 1
        self.stats.status = LinkHealthStatus.DEGRADED

    def mark_healthy(self, rtt_ms: float = 8.0, loss: float = 0.0) -> None:
        """Force l'etat du lien a HEALTHY (pour simulation/tests)."""
        self.stats.rtt_ms = rtt_ms
        self.stats.packet_loss_rate = loss
        self.stats.consecutive_heartbeats_missed = 0
        self.stats.last_packet_time = time.time()
        self.stats.status = LinkHealthStatus.HEALTHY

    def register_packet_sent(self, seq: int) -> None:
        """Enregistre l'emission d'un paquet."""
        self.stats.packets_sent += 1
        self.pending_pings[seq] = time.time()

    def register_packet_received(self, seq: int, send_timestamp: float | None = None) -> None:
        """Enregistre la reception d'un paquet et met a jour RTT, gigue et pertes."""
        now = time.time()
        self.stats.packets_received += 1
        self.stats.last_packet_time = now
        self.stats.consecutive_heartbeats_missed = 0

        # 1. Calcul du RTT si timestamp d'origine connu ou ping en attente
        measured_rtt_ms: float | None = None
        if seq in self.pending_pings:
            sent_time = self.pending_pings.pop(seq)
            measured_rtt_ms = (now - sent_time) * 1000.0
        elif send_timestamp is not None:
            measured_rtt_ms = max(0.1, (now - send_timestamp) * 1000.0)

        if measured_rtt_ms is not None:
            # Lissage exponentiel (EWMA alpha=0.2)
            self.stats.rtt_ms = (0.8 * self.stats.rtt_ms) + (0.2 * measured_rtt_ms)

            # 2. Calcul de la Gigue selon l'algorithme standard RFC 3550 (RTP/RTCP)
            transit_ms = measured_rtt_ms / 2.0
            if self.stats._last_transit_time_ms is not None:
                d = abs(transit_ms - self.stats._last_transit_time_ms)
                self.stats.jitter_ms += (d - self.stats.jitter_ms) / 16.0
            self.stats._last_transit_time_ms = transit_ms

        # 3. Calcul du taux de perte sur fenetre glissante
        self._update_loss_rate(seq)

        # 4. Evaluation de l'etat de sante
        self.evaluate_health()

    def _update_loss_rate(self, seq: int) -> None:
        """Met a jour le taux de perte de paquets sur une fenetre glissante de sequence MAVLink."""
        if self.stats._max_seq_seen == -1:
            self.stats._max_seq_seen = seq
            self.stats._received_sequences.add(seq)
            return

        diff = (seq - self.stats._max_seq_seen) % 256
        if diff < 128:
            self.stats._max_seq_seen = seq

        self.stats._received_sequences.add(seq)

        window_min = (self.stats._max_seq_seen - self.stats._seq_window_size) % 256
        self.stats._received_sequences = {
            s for s in self.stats._received_sequences
            if (s - window_min) % 256 <= self.stats._seq_window_size
        }

        expected = min(self.stats.packets_sent, self.stats._seq_window_size)
        if expected > 5:
            received = len(self.stats._received_sequences)
            loss = max(0.0, 1.0 - (received / expected))
            self.stats.packet_loss_rate = (0.7 * self.stats.packet_loss_rate) + (0.3 * loss)

    def register_missed_heartbeat(self) -> None:
        """Incremente le compteur de battements de coeur manques."""
        self.stats.consecutive_heartbeats_missed += 1
        self.evaluate_health()

    def evaluate_health(self) -> LinkHealthStatus:
        """Evalue l'etat global du lien (HEALTHY, DEGRADED, DOWN)."""
        now = time.time()
        time_since_last_pkt = now - self.stats.last_packet_time

        if (
            self.stats.consecutive_heartbeats_missed >= self.max_missed_heartbeats
            or time_since_last_pkt > 3.0
            or self.stats.rtt_ms >= self.rtt_threshold_down_ms
            or self.stats.packet_loss_rate >= self.loss_threshold_down
        ):
            self.stats.status = LinkHealthStatus.DOWN
        elif (
            self.stats.rtt_ms >= self.rtt_threshold_degraded_ms
            or self.stats.packet_loss_rate >= self.loss_threshold_degraded
            or self.stats.consecutive_heartbeats_missed == 1
        ):
            self.stats.status = LinkHealthStatus.DEGRADED
        else:
            self.stats.status = LinkHealthStatus.HEALTHY

        return self.stats.status

    @property
    def score(self) -> float:
        """Indice synthetique de qualite entre 0.0 (inutilisable) et 1.0 (parfait)."""
        if self.stats.status == LinkHealthStatus.DOWN:
            return 0.0

        rtt_factor = max(0.0, 1.0 - (self.stats.rtt_ms / self.rtt_threshold_down_ms))
        loss_factor = max(0.0, 1.0 - (self.stats.packet_loss_rate / self.loss_threshold_down))
        jitter_factor = max(0.0, 1.0 - (self.stats.jitter_ms / 50.0))

        return 0.5 * rtt_factor + 0.3 * loss_factor + 0.2 * jitter_factor
