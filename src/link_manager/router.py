"""Routeur Hybride Multipath MAVLink 2 avec gestion du failover et deduplication."""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable

from src.common.config import DEFAULT_CONFIG
from src.common.models import LinkType
from src.link_manager.fsm import FailoverFSM, RouterState
from src.link_manager.monitor import LinkQualityMonitor

logger = logging.getLogger("hybridlink.router")


class HybridLinkRouter:
    """Gestionnaire de routage hybride assurant la continuite de service MAVLink."""

    def __init__(
        self,
        hysteresis_stability_s: float = DEFAULT_CONFIG.HYSTERESIS_STABILITY_SEC,
    ) -> None:
        self.monitor_a = LinkQualityMonitor(LinkType.LINK_A, rtt_threshold_degraded_ms=40.0)
        self.monitor_b = LinkQualityMonitor(LinkType.LINK_B, rtt_threshold_degraded_ms=100.0)
        self.fsm = FailoverFSM(hysteresis_stability_s=hysteresis_stability_s)

        # Cache de deduplication pour les flux descendants (Vehicle -> GCS)
        # Stocke les cles (sys_id, comp_id, seq) avec leur timestamp
        self._seen_packet_ids: deque[tuple[int, int, int, float]] = deque(maxlen=256)

        # Callbacks de transport reseau
        self.send_to_gcs: Callable[[bytes], None] | None = None
        self.send_to_link_a: Callable[[bytes], None] | None = None
        self.send_to_link_b: Callable[[bytes], None] | None = None

    def route_uplink_gcs_to_vehicle(self, data: bytes) -> RouterState:
        """Achemine une commande de la station sol vers le vecteur selon l'etat de la FSM."""
        # Verification et mise a jour de la FSM
        current_state = self.fsm.update(self.monitor_a, self.monitor_b)

        # Extraction minimale de l'en-tete MAVLink 2 (seq est a l'index 4)
        seq = data[4] if len(data) > 4 else 0

        if current_state == RouterState.PRIMARY_LINK_A:
            if self.send_to_link_a:
                self.monitor_a.register_packet_sent(seq)
                self.send_to_link_a(data)

        elif current_state == RouterState.FAILOVER_LINK_B:
            if self.send_to_link_b:
                self.monitor_b.register_packet_sent(seq)
                self.send_to_link_b(data)

        elif current_state == RouterState.DUAL_REDUNDANT:
            if self.send_to_link_a:
                self.monitor_a.register_packet_sent(seq)
                self.send_to_link_a(data)
            if self.send_to_link_b:
                self.monitor_b.register_packet_sent(seq)
                self.send_to_link_b(data)

        elif current_state == RouterState.TOTAL_BLACKOUT:
            logger.warning("[ROUTER DROP] Blackout total : commande GCS rejetee par defaut de lien.")

        return current_state

    def route_downlink_vehicle_to_gcs(self, data: bytes, source_link: LinkType) -> bool:
        """Traite et dedoublonne la telemetrie descendante recue d'un des deux liens."""
        now = time.time()

        # Enregistrement de reception sur la sonde appropriee
        seq = data[4] if len(data) > 4 else 0
        sys_id = data[5] if len(data) > 5 else 0
        comp_id = data[6] if len(data) > 6 else 0

        if source_link == LinkType.LINK_A:
            self.monitor_a.register_packet_received(seq)
        else:
            self.monitor_b.register_packet_received(seq)

        # Filtre anti-doublon (si emission dupliquee sur A et B)
        pkt_key = (sys_id, comp_id, seq)
        # Verifier si cette trame a deja ete relayee dans les dernieres 500ms
        for s_id, c_id, s_num, t_recv in self._seen_packet_ids:
            if (s_id, c_id, s_num) == pkt_key and (now - t_recv) < 0.5:
                # Doublon detecte -> on le jette sans l'envoyer a la GCS
                return False

        self._seen_packet_ids.append((sys_id, comp_id, seq, now))

        # Relayer a la GCS
        if self.send_to_gcs:
            self.send_to_gcs(data)
            return True

        return False

    def periodic_tick(self) -> RouterState:
        """Verification cyclique de la FSM et detection des timeouts."""
        return self.fsm.update(self.monitor_a, self.monitor_b)
