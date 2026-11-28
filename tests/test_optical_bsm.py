"""Tests for probabilistic attempt-tagged Source and click-driven time-gated Optical_bsm."""

import math

import numpy as np
import pytest

from Auto_connector import connect
from Emitter import Handler
from Optical_bsm import Optical_bsm
from Qubits import Qubit, State
from Simulation import Simulation
from Source import Source
from States import phi_plus
from benchmarks.run_hefei_reproduction import analytic_hefei_prediction, run_hefei_trial_sim
from damn_q.runner import run_experiment
from damn_q.schema import ExperimentValidationError, validate_experiment


def test_source_emission_p_and_attempt_id_tagging():
    sim = Simulation(seed=12)
    src = Source("s", delay=1, type=2, sim=sim, emission_p=0.5)
    got = []
    src.out_ch_1.add_handler(Handler(got.append, sim=sim, kind="quantum"))
    sim.run(2000)

    assert src.attempts == 2000
    assert src.emitted == len(got)
    assert abs(src.emitted - 1000) < 5 * math.sqrt(500)
    # Every emitted qubit carries its monotonically increasing attempt_id.
    ids = [q.attempt_id for q in got]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_optical_bsm_coincidence_window_accepts_in_window_and_expires_out_of_window():
    sim = Simulation(seed=0)
    bsm = Optical_bsm("bsm", delay=0, coincidence_window=2.0, linear_optical_efficiency=1.0, sim=sim)
    heralds = []
    bsm.ch_out_c_1.add_handler(Handler(heralds.append, sim=sim, kind="classical"))

    # Pair 1: arrives 2 ticks apart (inside window=2) -> heralds
    q1a, q1b = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    q2a, q2b = Qubit.bell_state(3, 4, State(phi_plus.copy()))
    sim.add(10, lambda: bsm.ch_in_q_1.handle(q1b))
    sim.add(12, lambda: bsm.ch_in_q_2.handle(q2a))

    # Pair 2: arrives 5 ticks apart (outside window=2) -> expires, no herald
    q3a, q3b = Qubit.bell_state(5, 6, State(phi_plus.copy()))
    q4a, q4b = Qubit.bell_state(7, 8, State(phi_plus.copy()))
    sim.add(20, lambda: bsm.ch_in_q_1.handle(q3b))
    sim.add(25, lambda: bsm.ch_in_q_2.handle(q4a))
    sim.run(30)

    assert bsm.true_heralds == 1
    assert bsm.false_heralds == 0
    assert len(heralds) == 1
    # Surviving remote pair (q1a, q2b) shares a 2-qubit register
    assert q1a.register is q2b.register
    # Expired photon q3b was traced out
    assert q3b.state is None
    assert bsm.expired_photons >= 1


def test_optical_bsm_gaussian_jitter_matches_analytic_erf_window_probability():
    # For t1, t2 ~ N(0, sigma^2), |t1 - t2| <= W has exact probability erf(W / (2*sigma)).
    sigma = 0.5
    window = 1.0
    expected_p = math.erf(window / (2.0 * sigma))
    n_trials = 3000

    sim = Simulation(seed=99)
    bsm = Optical_bsm(
        "bsm",
        delay=0,
        coincidence_window=window,
        jitter_std=sigma,
        linear_optical_efficiency=1.0,
        sim=sim,
    )
    for k in range(1, n_trials + 1):
        t = k * 20
        def send_pair():
            _, qb = Qubit.bell_state(1, 2, State(phi_plus.copy()))
            qa, _ = Qubit.bell_state(3, 4, State(phi_plus.copy()))
            bsm.ch_in_q_1.handle(qb)
            bsm.ch_in_q_2.handle(qa)
        sim.add(t, send_pair)
    sim.run(n_trials * 20 + 50)

    observed_p = bsm.true_heralds / n_trials
    se = math.sqrt(expected_p * (1.0 - expected_p) / n_trials)
    assert abs(observed_p - expected_p) < 4.5 * se


def test_optical_bsm_linear_optical_efficiency_half_splits_heralds_and_ambiguous():
    n_trials = 2000
    sim = Simulation(seed=7)
    bsm = Optical_bsm("bsm", delay=0, coincidence_window=0.0, linear_optical_efficiency=0.5, sim=sim)
    for k in range(1, n_trials + 1):
        def send_pair():
            _, qb = Qubit.bell_state(1, 2, State(phi_plus.copy()))
            qa, _ = Qubit.bell_state(3, 4, State(phi_plus.copy()))
            bsm.ch_in_q_1.handle(qb)
            bsm.ch_in_q_2.handle(qa)
        sim.add(k * 5, send_pair)
    sim.run(n_trials * 5 + 10)

    assert bsm.true_heralds + bsm.ambiguous_patterns == n_trials
    assert abs(bsm.true_heralds - n_trials / 2) < 5 * math.sqrt(n_trials / 4)


def test_optical_bsm_dark_counts_produce_false_heralds_without_photons():
    sim = Simulation(seed=5)
    bsm = Optical_bsm("bsm", delay=0, coincidence_window=0.0, dark_count_rate=0.2, sim=sim)
    heralds = []
    bsm.ch_out_c_1.add_handler(Handler(heralds.append, sim=sim, kind="classical"))
    sim.run(1000)

    assert bsm.true_heralds == 0
    assert bsm.false_heralds == bsm.dark_dark_heralds == len(heralds)
    # Expected ~0.2^2 * 1000 = 40 dark-dark heralds
    assert 15 < bsm.false_heralds < 75


def test_optical_bsm_one_sided_traffic_keeps_buffer_bounded():
    sim = Simulation(seed=0)
    bsm = Optical_bsm("bsm", delay=0, coincidence_window=1.0, sim=sim)
    for t in range(1, 5001):
        sim._time = t  # noqa: SLF001
        _, q = Qubit.bell_state(1, 2, State(phi_plus.copy()))
        bsm.ch_in_q_1.handle(q)
    assert len(bsm._buf_1) <= 2  # noqa: SLF001
    assert bsm.expired_photons >= 4998


def test_optical_bsm_json_schema_and_runner_integration():
    doc = {
        "schema_version": "1.0",
        "name": "Optical BSM JSON smoke test",
        "run": {"until": 100, "seed": 42},
        "components": [
            {"id": "sa", "type": "source", "params": {"delay": 5, "type": 2, "emission_p": 0.8}},
            {"id": "sb", "type": "source", "params": {"delay": 5, "type": 2, "emission_p": 0.8}},
            {
                "id": "bsm",
                "type": "optical_bsm",
                "params": {
                    "delay": 1,
                    "coincidence_window": 1.0,
                    "jitter_std": 0.2,
                    "detector_efficiency": 0.9,
                    "dark_count_rate": 0.01,
                    "visibility": 0.85,
                    "linear_optical_efficiency": 0.5,
                },
            },
        ],
        "connections": [
            {"from": {"component": "sa", "port": "out_ch_2"}, "to": {"component": "bsm", "port": "ch_in_q_1"}, "delay": 5},
            {"from": {"component": "sb", "port": "out_ch_1"}, "to": {"component": "bsm", "port": "ch_in_q_2"}, "delay": 5},
        ],
        "measurements": [],
    }
    validate_experiment(doc)
    res = run_experiment(doc)
    bsm_m = res["metrics"]["optical_bsms"]["bsm"]
    assert bsm_m["heralds"] == bsm_m["true_heralds"] + bsm_m["false_heralds"]

    # Reject invalid optical_bsm / source parameters
    bad = dict(doc)
    bad["components"] = [dict(doc["components"][0], params={"delay": 5, "type": 2, "emission_p": 0.0})]
    bad["connections"] = []
    with pytest.raises(ExperimentValidationError):
        validate_experiment(bad)


def test_hefei_reproduction_matches_analytic_rate_and_fidelity():
    params = dict(
        trials=3000,
        emission_p=0.5,
        loss_a_db=3.0,
        loss_b_db=6.0,
        detector_efficiency=0.7,
        dark_count_rate=1e-4,
        coincidence_window=1.0,
        jitter_std=0.4,
        visibility=0.80,
        linear_optical_efficiency=0.5,
    )
    pred = analytic_hefei_prediction(
        trials=params["trials"],
        emission_p=params["emission_p"],
        loss_a_db=params["loss_a_db"],
        loss_b_db=params["loss_b_db"],
        detector_efficiency=params["detector_efficiency"],
        linear_optical_efficiency=params["linear_optical_efficiency"],
        coincidence_window=params["coincidence_window"],
        jitter_std=params["jitter_std"],
        visibility=params["visibility"],
    )
    res = run_hefei_trial_sim(seed=42, **params)
    assert res["true_heralds"] > 10
    assert abs(res["true_heralds"] - pred["expected_true_heralds"]) < 4.5 * math.sqrt(pred["expected_true_heralds"])
    assert abs(res["true_herald_mean_fidelity"] - pred["expected_true_fidelity"]) < 0.15
