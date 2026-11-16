"""Machine a Etats Finis (FSM) de selection de lien avec hysterese temporelle."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from src.common.config import DEFAULT_CONFIG
from src.common.models import LinkHealthStatus
from src.link_manager.monitor import LinkQualityMonitor

logger = logging.getLogger("hybridlink.fsm")


class RouterState(StrEnum):
    PRIMARY_LINK_A = "PRIMARY_LINK_A"    # ExpressLRS actif (nominal)
    FAILOVER_LINK_B = "FAILOVER_LINK_B"  # 4G/5G actif (repli)
    DUAL_REDUNDANT = "DUAL_REDUNDANT"    # Emission dupliquee sur les 2 liens
    TOTAL_BLACKOUT = "TOTAL_BLACKOUT"    # Perte totale des 2 liens


@dataclass
class StateTransition:
    timestamp: float
    old_state: RouterState
    new_state: RouterState
    reason: str


class FailoverFSM:
    """Automate de basculement robuste avec hysterese anti-flapping."""

    def __init__(
        self,
        hysteresis_stability_s: float = DEFAULT_CONFIG.HYSTERESIS_STABILITY_SEC,
        initial_state: RouterState = RouterState.PRIMARY_LINK_A,
    ) -> None:
        self.current_state = initial_state
        self.hysteresis_stability_s = hysteresis_stability_s

        # Suivi d'hysterese
        self.link_a_recovered_since: float | None = None
        self.transitions: list[StateTransition] = []
        self.state_time_start: float = time.time()
        self.time_in_state: dict[RouterState, float] = {s: 0.0 for s in RouterState}

    def update(
        self,
        monitor_a: LinkQualityMonitor,
        monitor_b: LinkQualityMonitor,
    ) -> RouterState:
        """Evalue les sondes et applique les transitions avec regle d'hysterese."""
        now = time.time()
        health_a = monitor_a.evaluate_health()
        health_b = monitor_b.evaluate_health()

        old_state = self.current_state
        new_state = old_state
        reason = ""

        # Mise a jour du temps passe dans l'etat courant
        dt = now - self.state_time_start
        self.time_in_state[old_state] += dt
        self.state_time_start = now

        # 1. Verification de la panne totale (Blackout)
        if health_a == LinkHealthStatus.DOWN and health_b == LinkHealthStatus.DOWN:
            new_state = RouterState.TOTAL_BLACKOUT
            reason = "Perte simultanee du Lien A (Radio) et du Lien B (Cellulaire)"

        # 2. Etat courant : PRIMARY_LINK_A (Nominal)
        elif old_state == RouterState.PRIMARY_LINK_A:
            if health_a == LinkHealthStatus.DOWN:
                if health_b in (LinkHealthStatus.HEALTHY, LinkHealthStatus.DEGRADED):
                    new_state = RouterState.FAILOVER_LINK_B
                    reason = f"Coupure brutale Lien A (RTT={monitor_a.stats.rtt_ms:.1f}ms, Loss={monitor_a.stats.packet_loss_rate:.1%}) -> Basculement Lien B"
            elif health_a == LinkHealthStatus.DEGRADED:
                if health_b == LinkHealthStatus.HEALTHY:
                    new_state = RouterState.FAILOVER_LINK_B
                    reason = f"Degradation critique Lien A (RTT={monitor_a.stats.rtt_ms:.1f}ms) -> Basculement preventif Lien B"

        # 3. Etat courant : FAILOVER_LINK_B (Repli)
        elif old_state == RouterState.FAILOVER_LINK_B:
            if health_b == LinkHealthStatus.DOWN and health_a in (LinkHealthStatus.HEALTHY, LinkHealthStatus.DEGRADED):
                new_state = RouterState.PRIMARY_LINK_A
                reason = "Coupure Lien B alors que Lien A est disponible -> Retour d'urgence Lien A"
                self.link_a_recovered_since = None

            elif health_a == LinkHealthStatus.HEALTHY:
                # Regle d'Hysterese : Lien A doit rester sain pendant au moins T_hysteresis
                if self.link_a_recovered_since is None:
                    self.link_a_recovered_since = now
                    logger.info(
                        f"[HYSTERESE ARMED] Lien A de nouveau SAIN (Score={monitor_a.score:.2f}). "
                        f"Observation requise pendant {self.hysteresis_stability_s}s..."
                    )
                elif (now - self.link_a_recovered_since) >= self.hysteresis_stability_s:
                    new_state = RouterState.PRIMARY_LINK_A
                    reason = (
                        f"Lien A stabilise depuis {now - self.link_a_recovered_since:.1f}s "
                        f"(Score={monitor_a.score:.2f}) -> Fin de repli, retour Lien A"
                    )
                    self.link_a_recovered_since = None
            else:
                # Si le Lien A retombe pendant la periode d'observation, reset du timer d'hysterese
                if self.link_a_recovered_since is not None:
                    logger.warning("[HYSTERESE RESET] Instabilite detectee sur Lien A pendant observation.")
                    self.link_a_recovered_since = None

        # 4. Etat courant : TOTAL_BLACKOUT
        elif old_state == RouterState.TOTAL_BLACKOUT:
            if health_a == LinkHealthStatus.HEALTHY:
                new_state = RouterState.PRIMARY_LINK_A
                reason = "Retablissement du Lien A apres blackout"
            elif health_b in (LinkHealthStatus.HEALTHY, LinkHealthStatus.DEGRADED):
                new_state = RouterState.FAILOVER_LINK_B
                reason = "Retablissement du Lien B apres blackout"

        # Application de la transition
        if new_state != old_state:
            self._apply_transition(old_state, new_state, reason)

        return self.current_state

    def _apply_transition(self, old_state: RouterState, new_state: RouterState, reason: str) -> None:
        """Enregistre et notifie un changement d'etat."""
        t = StateTransition(
            timestamp=time.time(),
            old_state=old_state,
            new_state=new_state,
            reason=reason,
        )
        self.transitions.append(t)
        self.current_state = new_state
        logger.warning(
            f"[FSM TRANSITION] {old_state.value} ===> {new_state.value} | Raison: {reason}"
        )

    @property
    def switch_count(self) -> int:
        """Nombre total de basculements effectues."""
        return len(self.transitions)
