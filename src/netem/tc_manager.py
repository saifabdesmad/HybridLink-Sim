"""Gestionnaire d'emulation reseau (tc netem Linux et fallback logiciel stochastique)."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from src.common.models import LinkType

logger = logging.getLogger("hybridlink.netem")


@dataclass
class NetemProfile:
    latency_ms: float = 10.0
    jitter_ms: float = 1.0
    loss_percent: float = 0.0
    bandwidth_kbps: int = 1000
    is_up: bool = True


class SimulatedChannel:
    """Canal logiciel avec perturbation stochastique (delai gaussien + pertes de Bernoulli)."""

    def __init__(self, name: str, profile: NetemProfile) -> None:
        self.name = name
        self.profile = profile
        self.forward_callback: Callable[[bytes], None] | None = None
        self.packets_dropped = 0
        self.packets_forwarded = 0

    async def inject_packet(self, data: bytes) -> None:
        """Injecte un paquet dans le canal et applique la loi de probabilite."""
        if not self.profile.is_up:
            self.packets_dropped += 1
            return

        # Tirage aleatoire de perte (Loi de Bernoulli)
        if self.profile.loss_percent > 0.0:
            if random.random() * 100.0 < self.profile.loss_percent:
                self.packets_dropped += 1
                return

        # Calcul du delai stochastique : Loi normale tronquee N(mu, sigma)
        delay_ms = random.gauss(self.profile.latency_ms, self.profile.jitter_ms)
        delay_ms = max(0.5, delay_ms)  # Pas de delai negatif

        # Attente asynchrone non bloquante avant transmission
        await asyncio.sleep(delay_ms / 1000.0)

        self.packets_forwarded += 1
        if self.forward_callback:
            self.forward_callback(data)


class TrafficControlManager:
    """Gestionnaire de regles tc netem avec fallback automatique si non disponible."""

    def __init__(self, interface_a: str = "eth0", interface_b: str = "eth0") -> None:
        self.interface_a = interface_a
        self.interface_b = interface_b
        self.has_tc = bool(shutil.which("tc") and os.name != "nt")

        if self.has_tc:
            logger.info("[NETEM] Utilitaire Linux tc detecte. Emulation au niveau noyau activee.")
        else:
            logger.info("[NETEM] Fallback logiciel stochastique active (compatible multiplateforme).")

        # Profils actifs
        self.profiles: dict[LinkType, NetemProfile] = {
            LinkType.LINK_A: NetemProfile(latency_ms=8.0, jitter_ms=1.5, loss_percent=0.1, is_up=True),
            LinkType.LINK_B: NetemProfile(latency_ms=45.0, jitter_ms=12.0, loss_percent=1.5, is_up=True),
        }

        # Canaux logiciels
        self.channels: dict[LinkType, SimulatedChannel] = {
            LinkType.LINK_A: SimulatedChannel("Channel_A", self.profiles[LinkType.LINK_A]),
            LinkType.LINK_B: SimulatedChannel("Channel_B", self.profiles[LinkType.LINK_B]),
        }

    def apply_profile(
        self,
        link: LinkType,
        latency_ms: float,
        jitter_ms: float,
        loss_percent: float,
        bandwidth_kbps: int = 1000,
        is_up: bool = True,
    ) -> None:
        """Applique une nouvelle regle de perturbation sur un lien."""
        p = self.profiles[link]
        p.latency_ms = latency_ms
        p.jitter_ms = jitter_ms
        p.loss_percent = loss_percent
        p.bandwidth_kbps = bandwidth_kbps
        p.is_up = is_up

        logger.info(
            f"[NETEM APPLY] {link.value} -> Latence: {latency_ms:.1f}ms (±{jitter_ms:.1f}ms) | "
            f"Perte: {loss_percent:.1f}% | Etat: {'UP' if is_up else 'DOWN'}"
        )

        # Si tc Linux disponible et droits root presents
        if self.has_tc and os.geteuid() == 0:  # type: ignore[attr-defined]
            iface = self.interface_a if link == LinkType.LINK_A else self.interface_b
            self._apply_linux_tc(iface, latency_ms, jitter_ms, loss_percent, is_up)

    def cut_link(self, link: LinkType) -> None:
        """Simule une coupure franche du lien."""
        self.apply_profile(link, latency_ms=1000.0, jitter_ms=0.0, loss_percent=100.0, is_up=False)

    def restore_link(
        self,
        link: LinkType,
        latency_ms: float = 8.0,
        jitter_ms: float = 1.5,
        loss_percent: float = 0.1,
    ) -> None:
        """Retablit un lien avec des conditions saines."""
        self.apply_profile(link, latency_ms=latency_ms, jitter_ms=jitter_ms, loss_percent=loss_percent, is_up=True)

    def _apply_linux_tc(
        self,
        iface: str,
        latency_ms: float,
        jitter_ms: float,
        loss_percent: float,
        is_up: bool,
    ) -> None:
        """Execute la commande tc qdisc netem du noyau Linux."""
        try:
            if not is_up or loss_percent >= 100.0:
                cmd = f"tc qdisc replace dev {iface} root netem loss 100%"
            else:
                cmd = (
                    f"tc qdisc replace dev {iface} root netem delay {latency_ms:.1f}ms {jitter_ms:.1f}ms "
                    f"loss {loss_percent:.2f}%"
                )
            subprocess.run(cmd.split(), check=True, capture_output=True)
        except Exception as e:
            logger.warning(f"[NETEM TC WARNING] Impossible d'appliquer la commande tc : {e}")
