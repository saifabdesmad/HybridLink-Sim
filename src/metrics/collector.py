"""Collecteur et exportateur de metriques de performance et de securite."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger("hybridlink.metrics.collector")


@dataclass
class MetricSample:
    timestamp: float
    scenario: str
    run_id: int
    active_link: str
    fsm_state: str
    rtt_ms: float
    jitter_ms: float
    loss_percent: float
    availability_percent: float
    failsafe_triggered: bool
    failover_time_ms: float = 0.0
    recovery_time_ms: float = 0.0
    security_enforced: bool = True
    malicious_injected: int = 0
    malicious_rejected: int = 0
    fraudulent_executed: int = 0


class MetricsCollector:
    """Enregistre les echantillons temporels et exporte au format CSV."""

    def __init__(self, output_dir: Path | str = "data/metrics") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.samples: list[MetricSample] = []

    def record_sample(self, sample: MetricSample) -> None:
        """Ajoute un point de mesure au collecteur."""
        self.samples.append(sample)

    def export_csv(self, filename: str) -> Path:
        """Exporte l'ensemble des donnees collectees dans un fichier CSV."""
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"
        file_path = self.output_dir / filename

        records = [asdict(s) for s in self.samples]
        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False)
        logger.info(f"[METRIQUES EXPORT] {len(records)} echantillons enregistres dans {file_path}")
        return file_path

    def clear(self) -> None:
        """Reinitialise le tampon de collecte."""
        self.samples.clear()
