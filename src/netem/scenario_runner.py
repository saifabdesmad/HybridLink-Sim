"""Executeur de scenarios d'evaluation sous perturbations reseau YAML."""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from src.common.models import LinkType
from src.netem.tc_manager import TrafficControlManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SCENARIO-RUNNER] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.scenario")


class ScenarioRunner:
    """Charge et orchestre chronologiquement les evenements d'un scenario d'evaluation."""

    def __init__(self, scenario_path: Path, tc_manager: TrafficControlManager | None = None) -> None:
        self.scenario_path = scenario_path
        self.tc = tc_manager or TrafficControlManager()
        self.scenario_data = self._load_scenario()

    def _load_scenario(self) -> dict[str, Any]:
        """Parse le fichier YAML de scenario."""
        if not self.scenario_path.exists():
            raise FileNotFoundError(f"Scenario introuvable: {self.scenario_path}")
        with open(self.scenario_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data  # type: ignore

    async def run(self) -> None:
        """Execute le scenario pas a pas selon la ligne de temps definie."""
        name = self.scenario_data.get("name", "inconnu")
        desc = self.scenario_data.get("description", "")
        duration = float(self.scenario_data.get("duration_sec", 20.0))
        events = sorted(self.scenario_data.get("events", []), key=lambda e: float(e["time_s"]))

        logger.info(f"=== DEBUT DU SCENARIO : {name} ===")
        logger.info(f"Description : {desc}")
        logger.info(f"Duree prevue : {duration}s | Nombre d'evenements : {len(events)}")

        # 1. Application des conditions initiales
        init_a = self.scenario_data.get("link_a", {})
        self.tc.apply_profile(
            LinkType.LINK_A,
            latency_ms=float(init_a.get("latency_ms", 8.0)),
            jitter_ms=float(init_a.get("jitter_ms", 1.5)),
            loss_percent=float(init_a.get("loss_percent", 0.1)),
            is_up=bool(init_a.get("status", "UP") == "UP"),
        )

        init_b = self.scenario_data.get("link_b", {})
        self.tc.apply_profile(
            LinkType.LINK_B,
            latency_ms=float(init_b.get("latency_ms", 45.0)),
            jitter_ms=float(init_b.get("jitter_ms", 12.0)),
            loss_percent=float(init_b.get("loss_percent", 1.5)),
            is_up=bool(init_b.get("status", "UP") == "UP"),
        )

        # 2. Boucle temporelle d'evenements
        start_time = time.time()
        event_idx = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed >= duration:
                break

            # Verifier si un evenement doit se declencher
            while event_idx < len(events) and events[event_idx]["time_s"] <= elapsed:
                ev = events[event_idx]
                self._dispatch_event(ev, elapsed)
                event_idx += 1

            await asyncio.sleep(0.1)

        logger.info(f"=== FIN DU SCENARIO : {name} ({duration}s ecoulees) ===")

    def _dispatch_event(self, event: dict[str, Any], elapsed: float) -> None:
        """Execute l'action specifique de l'evenement."""
        action = event.get("action", "")
        params = event.get("params", {})
        desc = event.get("description", "")

        logger.warning(
            f"[EVENEMENT SCENARIO t={elapsed:.1f}s] Action: {action} | Info: {desc}"
        )

        if action in ("update_link_a", "restore_link_a"):
            self.tc.apply_profile(
                LinkType.LINK_A,
                latency_ms=float(params.get("latency_ms", 8.0)),
                jitter_ms=float(params.get("jitter_ms", 1.5)),
                loss_percent=float(params.get("loss_percent", 0.1)),
                is_up=bool(params.get("status", "UP") == "UP"),
            )
        elif action == "cut_link_a":
            self.tc.cut_link(LinkType.LINK_A)

        elif action in ("update_link_b", "congest_link_b"):
            self.tc.apply_profile(
                LinkType.LINK_B,
                latency_ms=float(params.get("latency_ms", 45.0)),
                jitter_ms=float(params.get("jitter_ms", 12.0)),
                loss_percent=float(params.get("loss_percent", 1.5)),
                is_up=bool(params.get("status", "UP") == "UP"),
            )
        elif action == "cut_link_b":
            self.tc.cut_link(LinkType.LINK_B)

        elif action == "total_blackout":
            self.tc.cut_link(LinkType.LINK_A)
            self.tc.cut_link(LinkType.LINK_B)


def main() -> None:
    parser = argparse.ArgumentParser(description="HybridLink-Sim Scenario Runner")
    parser.add_argument(
        "--scenario",
        type=str,
        default="01_nominal",
        help="Nom du scenario sans extension ou chemin vers fichier yaml",
    )
    args = parser.parse_args()

    scen_str = args.scenario
    if not scen_str.endswith(".yaml"):
        scen_str = f"{scen_str}.yaml"

    path = Path("scenarios") / scen_str
    if not path.exists():
        path = Path(args.scenario)

    runner = ScenarioRunner(path)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
