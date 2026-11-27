import numpy as np
import pytest

from benchmarks.run_reference_benchmark import (
    REF_JSON,
    analytic_lossless_prediction,
    run_reference_benchmark,
)
from damn_q import ExperimentValidationError, run_experiment, validate_experiment
from damn_q.runner import load_experiment


def test_reference_benchmark_json_is_valid_and_reports_rates_with_tick_duration():
    doc = load_experiment(REF_JSON)
    validate_experiment(doc)
    res = run_experiment(doc, until_override=4000, seed_override=101)
    assert res["tick_duration_s"] == 1e-6
    assert np.isclose(res["simulated_duration_s"], 0.004)
    m = res["measurements"][0]
    assert m["captured_at"] == "delivery"
    assert m["pairs"] > 0
    assert m["unmatched_a"] == 0 and m["unmatched_b"] == 0
    assert m["all_shared_register"] is True
    assert m["delivered_pairs_per_s"] > 0
    assert np.isclose(m["mean_latency_s"], m["mean_latency"] * 1e-6)


def test_schema_rejects_invalid_tick_duration_s():
    for bad_tick in (0, -1e-6, float("inf"), float("nan"), "1e-6", True):
        doc = {
            "schema_version": "1.0",
            "run": {"until": 10, "tick_duration_s": bad_tick},
            "components": [{"id": "s", "type": "source", "params": {"delay": 1}}],
        }
        with pytest.raises(ExperimentValidationError, match="tick_duration_s"):
            validate_experiment(doc)


def test_step1_reference_benchmark_analytic_check_and_multiseed_bounds():
    report_a = run_reference_benchmark(seeds=[101, 102, 103], until=10000)
    report_b = run_reference_benchmark(seeds=[101, 102, 103], until=10000)

    # Lossless analytic verification matches to machine precision
    lc = report_a["lossless_check"]
    assert lc["passed"] is True
    assert lc["fidelity_abs_err"] < 1e-12
    assert lc["simulated_latency_ticks"] == 152.0

    # Deterministic across identical seeds
    assert report_a["per_seed"] == report_b["per_seed"]
    assert report_a["aggregate"] == report_b["aggregate"]

    # Lossy regime bounds: every delivered pair has latency >= L_exact and fidelity <= F_exact
    f_exact = analytic_lossless_prediction(load_experiment(REF_JSON))["fidelity"]
    agg = report_a["aggregate"]
    assert agg["total_pairs"] > 0
    assert agg["delivered_pairs_per_s"]["mean"] > 0
    assert agg["latency_ticks"]["min"] >= 152.0
    assert agg["fidelity_at_delivery"]["max"] <= f_exact + 1e-12
    assert agg["fidelity_at_delivery"]["min"] >= 0.25 - 1e-12

    for s in report_a["per_seed"]:
        assert s["unmatched_a"] == 0
        assert s["unmatched_b"] == 0
        assert s["all_shared_register"] is True
        assert s["swaps_rejected"] == 0
