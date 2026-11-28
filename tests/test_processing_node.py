"""Tests for the Delft-Eindhoven processing-node repeater and cross-simulator benchmark."""

import pytest

from benchmarks.run_delft_eindhoven_benchmark import run_delft_eindhoven_study
from damn_q.processing_node import ProcessingNodeConfig, run_processing_node


def test_ideal_processing_node_delivers_unit_fidelity_and_matches_analytic_rate():
    res = run_processing_node(
        ProcessingNodeConfig(
            until_s=60.0,
            seed=42,
            elementary_fidelity=1.0,
            gate_depol_p=0.0,
            attempt_dephasing_p=0.0,
            storage_t1_s=0.0,
            storage_t2_s=0.0,
            bsm_visibility=1.0,
        )
    )
    assert res["delivered_pairs"] > 100
    assert res["fidelity"]["mean"] == pytest.approx(1.0, abs=1e-12)
    # Within 15% of exact analytic sequential-heralding rate over 60s
    assert abs(res["delivered_pairs_per_s"] - res["analytic_no_cutoff_rate_hz"]) / res["analytic_no_cutoff_rate_hz"] < 0.15


def test_cutoff_improves_fidelity_under_attempt_induced_dephasing_and_t2():
    base = dict(
        until_s=25.0,
        seed=7,
        elementary_fidelity=0.95,
        gate_depol_p=0.01,
        attempt_dephasing_p=0.003,
        storage_t1_s=10.0,
        storage_t2_s=1.0,
        bsm_visibility=0.98,
    )
    no_cut = run_processing_node(ProcessingNodeConfig(**base, max_attempts_cutoff=0))
    with_cut = run_processing_node(ProcessingNodeConfig(**base, max_attempts_cutoff=120))

    assert no_cut["delivered_pairs"] > 20
    assert with_cut["delivered_pairs"] > 10
    assert with_cut["cutoffs"] > 0
    assert with_cut["fidelity"]["mean"] > no_cut["fidelity"]["mean"] + 0.02


def test_processing_node_config_validation():
    for bad in (
        {"storage_t1_s": 1.0, "storage_t2_s": 3.0},
        {"elementary_fidelity": 0.1},
        {"herald_prefactor": 0.0},
        {"until_s": 0.0},
        {"max_attempts_cutoff": -1},
    ):
        with pytest.raises(ValueError):
            run_processing_node(ProcessingNodeConfig(**bad))


def test_delft_eindhoven_study_runs_cleanly():
    report = run_delft_eindhoven_study(seeds=(1, 2), until_s=10.0)
    assert report["scenarios"]["ideal"]["mean_fidelity"]["mean"] == pytest.approx(1.0, abs=1e-12)
    assert (
        report["scenarios"]["hardware_with_cutoff"]["mean_fidelity"]["mean"]
        > report["scenarios"]["hardware_no_cutoff"]["mean_fidelity"]["mean"]
    )
