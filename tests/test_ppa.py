import pytest
from ppa.tech_nodes import get_node, interpolate, VALID_NODES
from ppa.estimator import PPAEstimator
from ppa.report import format_report, to_dict, export_csv, export_json
from sim.pipeline import build_default_pipeline
import tempfile
import os


def get_all_metrics():
    engine = build_default_pipeline()
    return [s.metrics for s in engine.get_stages()]


def test_smaller_node_is_faster():
    metrics = get_all_metrics()
    est_28 = PPAEstimator("28nm").estimate(metrics)
    est_7  = PPAEstimator("7nm").estimate(metrics)
    assert est_7.fmax_ghz > est_28.fmax_ghz


def test_smaller_node_is_smaller_area():
    metrics = get_all_metrics()
    est_28 = PPAEstimator("28nm").estimate(metrics)
    est_7  = PPAEstimator("7nm").estimate(metrics)
    assert est_7.die_area_mm2 < est_28.die_area_mm2


def test_total_power_is_positive():
    metrics = get_all_metrics()
    for node in VALID_NODES:
        result = PPAEstimator(node).estimate(metrics)
        assert result.total_power_mw > 0


def test_gate_equivalents_positive():
    metrics = get_all_metrics()
    result = PPAEstimator("7nm").estimate(metrics)
    assert result.total_gate_equivalents > 0
    for name, est in result.per_stage.items():
        assert est.gate_equivalents >= 0


def test_fmax_within_physical_bounds():
    metrics = get_all_metrics()
    for node in VALID_NODES:
        result = PPAEstimator(node).estimate(metrics)
        assert 0 < result.fmax_ghz <= 10.0, f"Fmax out of bounds at {node}: {result.fmax_ghz}"


def test_all_stages_in_per_stage():
    metrics = get_all_metrics()
    result = PPAEstimator("7nm").estimate(metrics)
    for m in metrics:
        assert m.name in result.per_stage


def test_invalid_node_raises():
    with pytest.raises(ValueError):
        PPAEstimator("3nm").estimate([])


def test_report_format_contains_node():
    metrics = get_all_metrics()
    result = PPAEstimator("16nm").estimate(metrics)
    report = format_report(result)
    assert "16nm" in report
    assert "Fmax" in report


def test_to_dict_has_required_keys():
    metrics = get_all_metrics()
    result = PPAEstimator("7nm").estimate(metrics)
    d = to_dict(result)
    for key in ["tech_node", "fmax_ghz", "die_area_mm2", "total_power_mw", "per_stage"]:
        assert key in d


def test_export_csv():
    metrics = get_all_metrics()
    result = PPAEstimator("7nm").estimate(metrics)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    try:
        export_csv(result, path)
        assert os.path.getsize(path) > 0
        with open(path) as f:
            header = f.readline()
            assert "stage" in header
            assert "fmax_ghz" in header
    finally:
        os.unlink(path)


def test_tech_node_interpolation():
    p = interpolate("28nm", "7nm", 0.5)
    n28 = get_node("28nm")
    n7  = get_node("7nm")
    assert n7.gate_delay_ps < p.gate_delay_ps < n28.gate_delay_ps


def test_5nm_faster_than_7nm():
    metrics = get_all_metrics()
    r7 = PPAEstimator("7nm").estimate(metrics)
    r5 = PPAEstimator("5nm").estimate(metrics)
    assert r5.fmax_ghz >= r7.fmax_ghz
