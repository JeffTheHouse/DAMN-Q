"""Step 3 hardware-model tests: formulas, Kraus channels, BSM visibility, detectors, schema."""

import copy
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from Auto_connector import connect
from Hardware_models import (
    amplitude_damping_kraus,
    combined_loss_p,
    fibre_loss_p,
    geometric_gap,
    phase_damping_kraus,
    propagation_ticks,
    storage_decoherence_kraus,
    validate_storage_times,
    werner_bell_density,
)
from Measurer import Measuring_Device
from Memory import Quantum_memory
from Qubits import Qubit, Register, State
from Signals import Release
from Simulation import Simulation
from Source import Source
from States import phi_plus
from damn_q.runner import EndpointProbe, _connection_quantum_effects, load_experiment, run_experiment
from damn_q.schema import ExperimentValidationError, validate_experiment

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "experiments"


# ---------------------------------------------------------------- formulas

def test_fibre_loss_zero_length_is_zero_and_matches_db_formula():
    assert fibre_loss_p(0.0) == 0.0
    # 10 km at 0.2 dB/km = 2 dB -> transmission 10^(-0.2)
    assert fibre_loss_p(10.0, 0.2, 0.0) == pytest.approx(1.0 - 10 ** (-0.2), rel=1e-12)
    # Coupling loss adds in dB, independent of length.
    assert fibre_loss_p(0.0, 0.2, 3.0) == pytest.approx(1.0 - 10 ** (-0.3), rel=1e-12)


def test_fibre_loss_rejects_negative_inputs():
    with pytest.raises(ValueError):
        fibre_loss_p(-1.0)
    with pytest.raises(ValueError):
        fibre_loss_p(1.0, attenuation_db_per_km=-0.1)


def test_combined_loss_is_identity_when_extra_loss_is_zero():
    # Exact identity (no float drift) keeps existing experiments bit-identical.
    assert combined_loss_p(0.3, 0.0) == 0.3
    assert combined_loss_p(0.5, 0.5) == pytest.approx(0.75)


def test_propagation_ticks_uses_speed_and_rounds_half_up():
    # 10 km / 200000 km/s = 50 us; at 10 us/tick that is 5 ticks.
    assert propagation_ticks(10.0, 1e-5) == 5
    # 5 km -> 25 us -> 2.5 ticks, rounded half up to 3 (not banker's rounding to 2).
    assert propagation_ticks(5.0, 1e-5) == 3
    assert propagation_ticks(0.0, None) == 0


def test_propagation_requires_tick_duration_for_nonzero_length():
    with pytest.raises(ValueError, match="tick_duration_s"):
        propagation_ticks(1.0, None)


def test_werner_state_fidelity_and_ideal_limit():
    assert np.allclose(werner_bell_density(1.0), phi_plus)
    for f in (0.25, 0.6, 0.9):
        rho = werner_bell_density(f)
        assert np.trace(rho).real == pytest.approx(1.0)
        assert np.trace(phi_plus @ rho).real == pytest.approx(f)
    # F = 1/4 is the maximally mixed state.
    assert np.allclose(werner_bell_density(0.25), np.eye(4) / 4)


@pytest.mark.parametrize("bad", [0.1, 1.01, -0.5])
def test_werner_rejects_fidelity_out_of_range(bad):
    with pytest.raises(ValueError):
        werner_bell_density(bad)


def test_storage_times_validation():
    validate_storage_times(0, 0)
    validate_storage_times(10, 20)  # T2 = 2 T1 is the physical limit
    with pytest.raises(ValueError, match="T2 <= 2\\*T1"):
        validate_storage_times(10, 25)
    with pytest.raises(ValueError):
        validate_storage_times(-1, 0)


def _is_trace_preserving(ops):
    total = sum(k.conj().T @ k for k in ops)
    return np.allclose(total, np.eye(2))


def test_kraus_sets_are_trace_preserving():
    for gamma in (0.0, 0.1, 0.9, 1.0):
        assert _is_trace_preserving(amplitude_damping_kraus(gamma))
    for lam in (0.0, 0.3, 1.0):
        assert _is_trace_preserving(phase_damping_kraus(lam))


def test_storage_kraus_zero_duration_or_disabled_is_empty():
    assert storage_decoherence_kraus(0, 10, 10) == ([], [])
    assert storage_decoherence_kraus(5, 0, 0) == ([], [])


def _apply(ops, rho):
    return sum(k @ rho @ k.conj().T for k in ops)


def test_amplitude_damping_relaxes_population_as_exp_minus_t_over_t1():
    t, t1 = 5, 10.0
    ad_ops, pd_ops = storage_decoherence_kraus(t, t1, 0)
    assert pd_ops == []
    excited = np.diag([0.0, 1.0]).astype(complex)
    rho = _apply(ad_ops, excited)
    assert rho[1, 1].real == pytest.approx(math.exp(-t / t1), rel=1e-12)


def test_storage_coherence_decays_as_exp_minus_t_over_t2():
    t, t1, t2 = 5, 10.0, 10.0
    ad_ops, pd_ops = storage_decoherence_kraus(t, t1, t2)
    plus = 0.5 * np.array([[1, 1], [1, 1]], dtype=complex)
    rho = _apply(pd_ops, _apply(ad_ops, plus))
    assert rho[0, 1].real == pytest.approx(0.5 * math.exp(-t / t2), rel=1e-12)
    assert _is_trace_preserving(ad_ops) and _is_trace_preserving(pd_ops)


def test_pure_t2_equal_2t1_has_no_extra_dephasing():
    # T2 = 2 T1 means 1/Tphi = 0: only amplitude damping acts on coherences.
    ad_ops, pd_ops = storage_decoherence_kraus(4, 10.0, 20.0)
    assert pd_ops == []
    assert ad_ops


def test_geometric_gap_rate_one_is_always_one_tick():
    rng = random.Random(0)
    assert all(geometric_gap(1.0, rng) == 1 for _ in range(10))


def test_geometric_gap_mean_matches_inverse_rate():
    rng = random.Random(42)
    rate = 0.05
    gaps = [geometric_gap(rate, rng) for _ in range(20000)]
    assert min(gaps) >= 1
    assert np.mean(gaps) == pytest.approx(1.0 / rate, rel=0.03)


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_geometric_gap_rejects_invalid_rate(bad):
    with pytest.raises(ValueError):
        geometric_gap(bad, random.Random(0))


# ---------------------------------------------------------------- quantum primitives

def test_qubit_apply_kraus_matches_numpy_channel():
    rho = np.array([[0.6, 0.2 - 0.1j], [0.2 + 0.1j, 0.4]], dtype=complex)
    q = Qubit(1, State(rho.copy()))
    ops = amplitude_damping_kraus(0.3)
    q.apply_kraus(ops)
    assert np.allclose(q.register.density_matrix, _apply(ops, rho))


def test_bell_measure_imperfect_visibility_one_matches_ideal_exactly():
    def build():
        q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
        q3, q4 = Qubit.bell_state(3, 4, State(phi_plus.copy()))
        return q2, q3

    a2, a3 = build()
    b2, b3 = build()
    out_ideal, reg_ideal = Register.bell_measure(a2, a3, rng=random.Random(5))
    out_imp, reg_imp = Register.bell_measure_imperfect(b2, b3, visibility=1.0, rng=random.Random(5))
    assert out_ideal == out_imp
    assert np.allclose(reg_ideal.density_matrix, reg_imp.density_matrix)


def test_bell_measure_imperfect_zero_visibility_leaves_maximally_mixed_pair():
    # Phi+ on (1,2) and (3,4). Tracing out the measured middle pair (2,3) from the
    # product state leaves (1,4) maximally mixed: I/4 on the two-qubit register.
    q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    q3, q4 = Qubit.bell_state(3, 4, State(phi_plus.copy()))
    outcome, reg = Register.bell_measure_imperfect(q2, q3, visibility=0.0, rng=random.Random(9))
    assert outcome in {"00", "01", "10", "11"}
    assert set(reg.qubits) == {q1, q4}
    assert np.allclose(reg.density_matrix, np.eye(4) / 4)


def test_bell_measure_imperfect_rejects_bad_visibility():
    q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    with pytest.raises(ValueError):
        Register.bell_measure_imperfect(q1, q2, visibility=1.5, rng=random.Random(0))


# ---------------------------------------------------------------- components

def _sink(sim):
    probe = EndpointProbe("probe", sim)
    return probe


def test_quantum_memory_storage_decoherence_applied_at_release():
    sim = Simulation(seed=0)
    mem = Quantum_memory("m", 0.0, delay=0, sim=sim, t1=10, t2=10)
    probe = _sink(sim)
    connect(mem.ch_out_q, probe.ch_in_q, sim=sim)

    qubit = Qubit(1, State(0.5 * np.array([[1, 1], [1, 1]], dtype=complex)))
    mem.handle_receive(qubit)
    mem.handle_paired_memory(1)  # legacy untagged herald: slot becomes confirmed
    slot = next(iter(mem.memory))
    sim.run(until=5)
    mem.handle_classic(Release(slot, memory_id=mem.id))
    sim.run(until=6)

    assert len(probe.qubits) == 1
    _, out = probe.qubits[0]
    rho = out.register.reduced_density_matrix([out])
    assert rho[0, 1].real == pytest.approx(0.5 * math.exp(-5 / 10), rel=1e-9)


def test_quantum_memory_default_t1_t2_do_not_change_state():
    sim = Simulation(seed=0)
    mem = Quantum_memory("m", 0.0, delay=0, sim=sim)
    probe = _sink(sim)
    connect(mem.ch_out_q, probe.ch_in_q, sim=sim)
    mem.handle_receive(Qubit(1, State(0.5 * np.array([[1, 1], [1, 1]], dtype=complex))))
    mem.handle_paired_memory(1)
    slot = next(iter(mem.memory))
    sim.run(until=7)
    mem.handle_classic(Release(slot, memory_id=mem.id))
    sim.run(until=8)
    _, out = probe.qubits[0]
    assert out.register.reduced_density_matrix([out])[0, 1].real == pytest.approx(0.5)


def test_quantum_memory_rejects_t2_above_twice_t1():
    with pytest.raises(ValueError, match="T2 <= 2\\*T1"):
        Quantum_memory("m", 0.0, sim=Simulation(seed=0), t1=10, t2=25)


def test_source_initial_fidelity_sets_pair_quality():
    sim = Simulation(seed=0)
    src = Source("s", 1, 2, sim=sim, initial_fidelity=0.8)
    p1, p2 = _sink(sim), EndpointProbe("probe2", sim)
    connect(src.out_ch_1, p1.ch_in_q, sim=sim)
    connect(src.out_ch_2, p2.ch_in_q, sim=sim)
    sim.run(until=1)
    (_, q1), (_, q2) = p1.qubits[0], p2.qubits[0]
    joint = q1.register.reduced_density_matrix([q1, q2])
    assert np.trace(phi_plus @ joint).real == pytest.approx(0.8, rel=1e-9)


def test_source_rejects_fidelity_below_werner_floor():
    with pytest.raises(ValueError):
        Source("s", 1, 2, sim=Simulation(seed=0), initial_fidelity=0.1)


def test_detector_efficiency_one_detects_every_qubit():
    sim = Simulation(seed=7)
    dev = Measuring_Device("m", 0, detector_efficiency=1.0, sim=sim)
    for i in range(200):
        dev.handle(Qubit(i, State(np.diag([1.0, 0.0]).astype(complex))))
    assert dev.missed_detections == 0


def test_detector_efficiency_half_detects_about_half():
    sim = Simulation(seed=7)
    dev = Measuring_Device("m", 0, detector_efficiency=0.5, sim=sim)
    results = []
    dev.ch_out_result.add_handler(_collector(results, sim))
    n = 2000
    for i in range(n):
        dev.handle(Qubit(i, State(np.diag([1.0, 0.0]).astype(complex))))
    sim.run(until=1)
    assert len(results) + dev.missed_detections == n
    assert abs(len(results) - n / 2) < 5 * math.sqrt(n / 4)


def test_detector_efficiency_must_be_positive():
    with pytest.raises(ValueError):
        Measuring_Device("m", 0, detector_efficiency=0.0, sim=Simulation(seed=0))


def _collector(results, sim):
    from Emitter import Handler

    return Handler(results.append, sim=sim, kind="classical")


def test_dark_counts_have_no_pair_id_and_expected_rate():
    sim = Simulation(seed=3)
    dev = Measuring_Device("m", 0, dark_count_rate=0.05, sim=sim)
    results = []
    dev.ch_out_result.add_handler(_collector(results, sim))
    sim.run(until=20000)
    expected = 0.05 * 20000
    assert abs(dev.dark_counts - expected) < 5 * math.sqrt(expected)
    assert len(results) == dev.dark_counts
    assert all(getattr(r, "pair_id", None) is None for r in results)


def test_zero_dark_count_rate_schedules_nothing():
    sim = Simulation(seed=3)
    Measuring_Device("m", 0, sim=sim)
    assert sim._queue == []  # noqa: SLF001 - no dark-count process started


# ---------------------------------------------------------------- runner and schema

def test_connection_fibre_adds_delay_and_loss():
    conn = {"from": {}, "to": {}, "delay": 2, "length_km": 10, "loss_p": 0.0}
    delay, loss = _connection_quantum_effects(conn, 1e-5)
    assert delay == 2 + 5
    assert loss == pytest.approx(1.0 - 10 ** (-0.2), rel=1e-12)


def test_connection_without_fibre_keys_is_unchanged():
    conn = {"from": {}, "to": {}, "delay": 3, "loss_p": 0.25}
    assert _connection_quantum_effects(conn, None) == (3, 0.25)


def _base_doc():
    return load_experiment(EXPERIMENTS / "repeater_tutorial_z.json")


def test_schema_rejects_fibre_on_classical_connection():
    doc = _base_doc()
    conn = next(c for c in doc["connections"] if c["from"]["port"] == "ch_out_result")
    conn["length_km"] = 1.0
    with pytest.raises(ExperimentValidationError, match="classical and cannot set fibre"):
        validate_experiment(doc)


def test_schema_requires_tick_duration_for_fibre_length():
    doc = _base_doc()
    doc["connections"][0]["length_km"] = 1.0
    with pytest.raises(ExperimentValidationError, match="tick_duration_s"):
        validate_experiment(doc)
    doc["run"]["tick_duration_s"] = 1e-5
    validate_experiment(doc)


def test_schema_rejects_negative_fibre_length_and_bad_attenuation():
    doc = _base_doc()
    doc["run"]["tick_duration_s"] = 1e-5
    doc["connections"][0]["length_km"] = -1.0
    doc["connections"][1]["attenuation_db_per_km"] = -0.2
    with pytest.raises(ExperimentValidationError) as exc:
        validate_experiment(doc)
    text = str(exc.value)
    assert "length_km" in text and "attenuation_db_per_km" in text


def test_schema_rejects_t2_above_twice_t1_on_memory():
    doc = _base_doc()
    mem = next(c for c in doc["components"] if c["type"] == "quantum_memory")
    mem["params"] = {"t1_ticks": 10, "t2_ticks": 25}
    with pytest.raises(ExperimentValidationError, match="T2 must satisfy"):
        validate_experiment(doc)


@pytest.mark.parametrize(
    "comp_type, params",
    [
        ("source", {"initial_fidelity": 0.1}),
        ("entanglement_swapper", {"visibility": 1.5}),
        ("measurer", {"detector_efficiency": 0.0}),
        ("measurer", {"dark_count_rate": 2.0}),
        ("measurer_memory_paired", {"detector_efficiency": 1.5}),
    ],
)
def test_schema_rejects_out_of_range_hardware_parameters(comp_type, params):
    doc = _base_doc()
    comp = next(c for c in doc["components"] if c["type"] == comp_type)
    comp["params"] = dict(comp.get("params", {}), **params)
    with pytest.raises(ExperimentValidationError):
        validate_experiment(doc)


# ---------------------------------------------------------------- regressions

def test_default_tutorial_counts_are_unchanged():
    result = run_experiment(EXPERIMENTS / "repeater_tutorial_z.json")
    assert result["readers"]["reader"] == {"00": 39, "01": 0, "10": 0, "11": 44}


def test_default_noisy_memory_fidelity_is_unchanged():
    result = run_experiment(EXPERIMENTS / "repeater_noisy_memory.json")
    assert result["measurements"][0]["mean_fidelity"] == 0.5701501371007607


def test_hardware_tutorial_runs_and_reports_errors():
    result = run_experiment(EXPERIMENTS / "repeater_tutorial_hardware.json")
    reader = result["readers"]["reader"]
    total = sum(reader.values())
    assert total > 0
    # Hardware noise introduces anticorrelated (error) outcomes that the ideal run never shows.
    assert reader["01"] + reader["10"] > 0
    assert result["schema_version"] == "1.0"


def test_hardware_tutorial_is_deterministic_for_fixed_seed():
    a = run_experiment(EXPERIMENTS / "repeater_tutorial_hardware.json")
    b = run_experiment(EXPERIMENTS / "repeater_tutorial_hardware.json")
    assert a["readers"] == b["readers"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
