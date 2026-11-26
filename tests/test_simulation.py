from pathlib import Path

import numpy as np

from Auto_connector import connect
from Detector_module import Detector_module
from Emitter import Handler, bind, scheduler
from Measurer import Measuring_Device
from Qubits import Qubit, State
from Simulation import Simulation
from Source import Source
from States import phi_plus
from damn_q import run_experiment

ROOT = Path(__file__).resolve().parent.parent


def test_two_simulations_do_not_share_clock_or_queue():
    sim_a = Simulation()
    sim_b = Simulation()
    events_a = []
    events_b = []
    src_a = Source(1, delay=5, type=1, sim=sim_a)
    bind(src_a.out_ch_1, Handler(lambda q: events_a.append(sim_a.time)))
    src_b = Source(2, delay=7, type=1, sim=sim_b)
    bind(src_b.out_ch_1, Handler(lambda q: events_b.append(sim_b.time)))

    sim_a.run(12)

    assert events_a == [5, 10]
    assert events_b == []
    assert sim_a.time == 12
    assert sim_b.time == 0
    assert len(sim_b._queue) == 1


def test_components_default_to_global_scheduler_only_without_sim():
    scheduler.reset()
    sim = Simulation()
    Source(1, delay=3, type=1, sim=sim)
    assert scheduler._queue == []

    Source(2, delay=3, type=1)
    assert len(scheduler._queue) == 1
    scheduler.reset()


def test_link_ids_are_per_simulation():
    sim_a = Simulation()
    sim_b = Simulation()
    assert [sim_a.next_link_id(), sim_a.next_link_id()] == [0, 1]
    assert sim_b.next_link_id() == 0


def test_seeded_simulations_reproduce_and_reset_restores_stream():
    first = Simulation(seed=99)
    second = Simulation(seed=99)
    draws_first = [first.rng.random() for _ in range(5)]
    draws_second = [second.rng.random() for _ in range(5)]
    assert draws_first == draws_second

    first.reset()
    assert [first.rng.random() for _ in range(5)] == draws_first


def test_detector_counters_are_bounded_when_trace_is_off():
    sim = Simulation()
    det = Detector_module(1, trace=False, sim=sim)
    n_pairs = 2000
    for i in range(n_pairs):
        q1, _ = Qubit.bell_state(2 * i, 2 * i + 1, State(phi_plus.copy()))
        det.result_a_1(q1)
    sim.run(0)

    assert det.ebits_1 == n_pairs
    assert det.Total_qubits_1 == n_pairs
    assert det.list_a_1 == []


def test_detector_trace_keeps_references_only_when_enabled():
    sim = Simulation()
    det = Detector_module(1, trace=True, sim=sim)
    for i in range(10):
        q1, _ = Qubit.bell_state(2 * i, 2 * i + 1, State(phi_plus.copy()))
        det.result_a_1(q1)
    sim.run(0)

    assert det.ebits_1 == 10
    assert len(det.list_a_1) == 10


def test_run_experiment_leaves_global_scheduler_untouched():
    scheduler.reset()
    before = (scheduler.time, len(scheduler._queue))
    result = run_experiment(ROOT / "experiments" / "repeater_ideal.json")
    assert (scheduler.time, len(scheduler._queue)) == before
    assert np.isclose(result["measurements"][0]["mean_fidelity"], 1.0, atol=1e-12)


def test_connect_and_bind_reject_cross_simulation_wiring():
    import pytest

    sim_a = Simulation(seed=1)
    sim_b = Simulation(seed=2)
    src_a = Source(1, delay=5, type=1, sim=sim_a)
    m_a = Measuring_Device(1, delay=0, sim=sim_a)
    m_b = Measuring_Device(2, delay=0, sim=sim_b)
    m_default = Measuring_Device(3, delay=0)

    with pytest.raises(ValueError, match="different Simulation"):
        connect(src_a.out_ch_1, m_b.ch_in_q)

    with pytest.raises(ValueError, match="different Simulation"):
        connect(src_a.out_ch_1, m_b.ch_in_q, sim=sim_a)

    with pytest.raises(ValueError, match="different Simulation"):
        connect(src_a.out_ch_1, m_a.ch_in_q, sim=sim_b)

    with pytest.raises(ValueError, match="different Simulation"):
        connect(src_a.out_ch_1, m_default.ch_in_q)

    with pytest.raises(ValueError, match="different Simulation"):
        bind(src_a.out_ch_1, m_b.ch_in_q)

    # Same-simulation connect() without explicit sim= infers sim_a cleanly
    results = []
    connect(src_a.out_ch_1, m_a.ch_in_q, delay=1)
    bind(m_a.ch_out_result, Handler(lambda r: results.append(r)))
    sim_a.run(10)
    assert len(results) == 1
    assert sim_b._queue == []
