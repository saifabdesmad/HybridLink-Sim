"""Point d'entree du conteneur/processus METRICS."""

from __future__ import annotations

import argparse
import logging

from src.metrics.evaluator import MonteCarloEvaluator
from src.metrics.plot import MetricsPlotter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [METRICS-MAIN] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hybridlink.metrics")


def run_full_pipeline(runs: int = 30) -> None:
    """Execute la campagne Monte Carlo complete et genere les visualisations associees."""
    logger.info(f"Demarrage de la campagne d'evaluation complete ({runs} runs)...")
    evaluator = MonteCarloEvaluator(runs=runs)
    evaluator.run_all_evaluations()

    logger.info("Generation des visualisations graphiques...")
    plotter = MetricsPlotter()
    plot_files = plotter.generate_all_plots()

    logger.info("Evaluation complete terminee avec succes.")
    for p in plot_files:
        logger.info(f" - Graphique : {p}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full metrics evaluation and report pipeline")
    parser.add_argument("--runs", type=int, default=30, help="Nombre de runs Monte Carlo (defaut: 30)")
    args = parser.parse_args()

    run_full_pipeline(runs=args.runs)


if __name__ == "__main__":
    main()
