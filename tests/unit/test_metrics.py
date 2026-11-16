"""Tests unitaires du collecteur, de l'evaluateur Monte Carlo et du generateur de graphiques."""

from pathlib import Path

from src.metrics.collector import MetricSample, MetricsCollector
from src.metrics.evaluator import MonteCarloEvaluator
from src.metrics.plot import MetricsPlotter


def test_metrics_collector_export(tmp_path: Path) -> None:
    """Verifie l'enregistrement et l'export CSV des echantillons de metriques."""
    collector = MetricsCollector(output_dir=tmp_path)
    sample = MetricSample(
        timestamp=1000.0,
        scenario="test_scen",
        run_id=1,
        active_link="LINK_A",
        fsm_state="PRIMARY_LINK_A",
        rtt_ms=8.5,
        jitter_ms=1.2,
        loss_percent=0.1,
        availability_percent=100.0,
        failsafe_triggered=False,
    )
    collector.record_sample(sample)
    csv_file = collector.export_csv("test_export.csv")

    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "test_scen" in content
    assert "PRIMARY_LINK_A" in content


def test_monte_carlo_confidence_interval() -> None:
    """Verifie le calcul statistique de la moyenne et de l'intervalle de confiance a 95%."""
    evaluator = MonteCarloEvaluator(runs=30)
    data = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.3, 9.7]
    mean, ci = evaluator.compute_ci95(data)

    assert 9.9 <= mean <= 10.1
    assert ci > 0.0  # Demi-largeur d'intervalle non nulle


def test_metrics_plotter_generation(tmp_path: Path) -> None:
    """Verifie la generation de fichiers images PNG par le traceur."""
    plotter = MetricsPlotter(output_dir=tmp_path)
    timeline_png = plotter.plot_latency_timeline()
    assert timeline_png.exists()
    assert timeline_png.suffix == ".png"
    assert timeline_png.stat().st_size > 1000  # Fichier image valide
