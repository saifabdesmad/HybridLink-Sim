"""Tests unitaires de la Machine a Etats Finis (FSM) et de l'hysterese anti-flapping."""

import time

from src.common.models import LinkType
from src.link_manager.fsm import FailoverFSM, RouterState
from src.link_manager.monitor import LinkQualityMonitor


def test_fsm_initial_state() -> None:
    fsm = FailoverFSM(hysteresis_stability_s=1.0)
    assert fsm.current_state == RouterState.PRIMARY_LINK_A
    assert fsm.switch_count == 0


def test_fsm_failover_when_link_a_fails() -> None:
    """Verifie le basculement immediat sur Link B lors d'une coupure du Link A."""
    fsm = FailoverFSM(hysteresis_stability_s=1.0)
    mon_a = LinkQualityMonitor(LinkType.LINK_A)
    mon_b = LinkQualityMonitor(LinkType.LINK_B)

    # Simuler Link A DOWN et Link B HEALTHY
    mon_a.mark_down()
    mon_b.mark_healthy()

    state = fsm.update(mon_a, mon_b)
    assert state == RouterState.FAILOVER_LINK_B
    assert fsm.switch_count == 1
    assert "Basculement" in fsm.transitions[0].reason


def test_fsm_hysteresis_prevents_immediate_switchback() -> None:
    """Verifie que l'hysterese empeche le retour premature sur Link A (anti-flapping)."""
    fsm = FailoverFSM(hysteresis_stability_s=0.5, initial_state=RouterState.FAILOVER_LINK_B)
    mon_a = LinkQualityMonitor(LinkType.LINK_A)
    mon_b = LinkQualityMonitor(LinkType.LINK_B)

    mon_a.mark_healthy()
    mon_b.mark_healthy()

    # Premier tick : Link A redevient sain, l'hysterese doit s'armer sans basculer
    state = fsm.update(mon_a, mon_b)
    assert state == RouterState.FAILOVER_LINK_B
    assert fsm.link_a_recovered_since is not None

    # Temps < seuil d'hysterese (0.5s)
    time.sleep(0.2)
    state = fsm.update(mon_a, mon_b)
    assert state == RouterState.FAILOVER_LINK_B

    # Temps ecoule >= 0.5s -> transition validee vers Link A
    time.sleep(0.35)
    state = fsm.update(mon_a, mon_b)
    assert state == RouterState.PRIMARY_LINK_A
    assert fsm.switch_count == 1


def test_fsm_hysteresis_reset_on_flapping() -> None:
    """Verifie que toute instabilite pendant la periode d'observation reset l'hysterese."""
    fsm = FailoverFSM(hysteresis_stability_s=0.5, initial_state=RouterState.FAILOVER_LINK_B)
    mon_a = LinkQualityMonitor(LinkType.LINK_A)
    mon_b = LinkQualityMonitor(LinkType.LINK_B)

    mon_a.mark_healthy()
    fsm.update(mon_a, mon_b)
    assert fsm.link_a_recovered_since is not None

    # Link A retombe a DEGRADED avant la fin des 0.5s
    time.sleep(0.2)
    mon_a.mark_degraded()
    fsm.update(mon_a, mon_b)

    # Le timer doit avoir ete reinitialise
    assert fsm.link_a_recovered_since is None
    assert fsm.current_state == RouterState.FAILOVER_LINK_B


def test_fsm_total_blackout() -> None:
    """Verifie l'etat TOTAL_BLACKOUT si les 2 liens sont perdus."""
    fsm = FailoverFSM()
    mon_a = LinkQualityMonitor(LinkType.LINK_A)
    mon_b = LinkQualityMonitor(LinkType.LINK_B)

    mon_a.mark_down()
    mon_b.mark_down()

    state = fsm.update(mon_a, mon_b)
    assert state == RouterState.TOTAL_BLACKOUT
