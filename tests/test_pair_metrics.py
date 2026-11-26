from pathlib import Path

import numpy as np

from Classic_data_reader import Classic_data_reader
from Emitter import Handler, bind
from Entanglment_swapping_module import Entaglment_swapping_module
from Pauli_corrector import Pauli_corrector
from Qubits import Qubit, State
from Signals import BellOutcome, MeasurementResult
from Simulation import Simulation
from States import phi_plus
from damn_q import run_experiment
from damn_q.runner import EndpointProbe, _BellFidelityRecorder

ROOT = Path(__file__).resolve().parent.parent


class _FixedRng:
    def __init__(self, values):
        self._values = list(values)
        self._idx = 0

    def random(self):
        v = self._values[self._idx % len(self._values)]
        self._idx += 1
        return v


def test_busy_bsm_explicitly_rejects_second_qubit_on_same_side():
    sim = Simulation(seed=1)
    es = Entaglment_swapping_module(1, delay=0, sim=sim)

    a1, a2 = Qubit.bell_state(1, 2, State(phi_plus.copy()), pair_id=10)
    extra1, extra2 = Qubit.bell_state(3, 4, State(phi_plus.copy()), pair_id=11)
    b1, b2 = Qubit.bell_state(5, 6, State(phi_plus.copy()), pair_id=12)

    outcomes = []
    bind(es.ch_out_c_1, Handler(lambda m: outcomes.append(m)))

    # Two qubits arrive on side 1 before side 2 arrives
    es.ch_in_q_1.handle(a2)
    es.ch_in_q_1.handle(extra2)

    assert es.rejected_count == 1
    assert extra2.state is None  # explicitly discarded/traced out
    assert es.counter == 0

    # Side 2 arrives and completes the swap with the first waiting qubit (a2)
    es.ch_in_q_2.handle(b1)
    sim.run(1)

    assert es.counter == 1
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], BellOutcome)
    assert outcomes[0].swap_id == 1
    assert a1.pair_id == 1 and b2.pair_id == 1
    assert a1.register is b2.register


def test_pauli_corrector_matches_out_of_order_swaps_by_swap_id():
    sim = Simulation()
    # Force swap 1 -> "01" (needs X), swap 2 -> "10" (needs Z)
    sim.rng = _FixedRng([0.375, 0.625])
    es = Entaglment_swapping_module(1, delay=0, sim=sim)
    pc = Pauli_corrector(1, delay=0, sim=sim)

    outcomes = []
    corrected = []
    bind(es.ch_out_c_2, Handler(lambda m: outcomes.append(m)))
    bind(pc.ch_out_q, Handler(lambda q: corrected.append(q)))

    # Perform two swaps
    a1_1, a2_1 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    b1_1, b2_1 = Qubit.bell_state(3, 4, State(phi_plus.copy()))
    es.ch_in_q_1.handle(a2_1)
    es.ch_in_q_2.handle(b1_1)

    a1_2, a2_2 = Qubit.bell_state(5, 6, State(phi_plus.copy()))
    b1_2, b2_2 = Qubit.bell_state(7, 8, State(phi_plus.copy()))
    es.ch_in_q_1.handle(a2_2)
    es.ch_in_q_2.handle(b1_2)
    sim.run(0)

    assert len(outcomes) == 2
    assert outcomes[0] == "01" and outcomes[0].swap_id == 1
    assert outcomes[1] == "10" and outcomes[1].swap_id == 2
    assert b2_1.pair_id == 1 and b2_2.pair_id == 2

    # Deliver qubits in order [swap 2, swap 1] while Bell outcomes arrive in order [swap 1, swap 2]
    pc.ch_in_q.handle(b2_2)
    pc.ch_in_q.handle(b2_1)
    pc.ch_in_es.handle(outcomes[0])  # swap 1 -> must match b2_1, NOT b2_2
    pc.ch_in_es.handle(outcomes[1])  # swap 2 -> must match b2_2
    sim.run(1)

    assert len(corrected) == 2
    # Both pairs must be exact |Phi+> despite reversed arrival order!
    joint_1 = a1_1.register.reduced_density_matrix([a1_1, b2_1])
    joint_2 = a1_2.register.reduced_density_matrix([a1_2, b2_2])
    assert np.allclose(joint_1, phi_plus)
    assert np.allclose(joint_2, phi_plus)


def test_joint_outcome_counter_matches_out_of_order_by_pair_id_and_tracks_unmatched():
    reader = Classic_data_reader(1)

    # Side 1 receives pair 2 ("1") then pair 1 ("0") plus unmatched pair 3 ("1")
    reader.input_1.handle(MeasurementResult("1", pair_id=2, basis="z"))
    reader.input_1.handle(MeasurementResult("0", pair_id=1, basis="z"))
    reader.input_1.handle(MeasurementResult("1", pair_id=3, basis="z"))

    # Side 2 receives pair 1 ("0") then pair 2 ("1")
    reader.input_2.handle(MeasurementResult("0", pair_id=1, basis="z"))
    reader.input_2.handle(MeasurementResult("1", pair_id=2, basis="z"))

    assert reader.count_00 == 1
    assert reader.count_11 == 1
    assert reader.count_01 == 0
    assert reader.count_10 == 0
    assert reader.unmatched_1 == 1
    assert reader.unmatched_2 == 0


def test_endpoint_probe_captures_fidelity_at_delivery_before_later_mutations():
    sim = Simulation()
    pa = EndpointProbe("probe_a", sim)
    pb = EndpointProbe("probe_b", sim)
    rec = _BellFidelityRecorder("probe_a", "probe_b", pa, pb)

    q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()), pair_id=99, created_at=10)
    sim.run(25)
    pa.handle_qubit(q1)
    sim.run(27)
    pb.handle_qubit(q2)

    # Mutate/destroy the qubit AFTER delivery -> must not affect delivery-time fidelity!
    q1.depolarize(0.75)
    q2.state = None

    summary = rec.to_dict()
    assert summary["captured_at"] == "delivery"
    assert summary["pairs"] == 1
    assert summary["unmatched_a"] == 0
    assert summary["unmatched_b"] == 0
    assert np.isclose(summary["mean_fidelity"], 1.0, atol=1e-12)
    assert summary["delivery_times"] == [27]
    assert summary["latencies"] == [17]
    assert summary["mean_latency"] == 17.0


def test_repeater_reports_separate_attempts_heralds_swaps_and_delivery_latency():
    res = run_experiment(ROOT / "experiments" / "repeater_ideal.json")
    m = res["measurements"][0]
    assert m["captured_at"] == "delivery"
    assert m["pairs"] == 1
    assert m["unmatched_a"] == 0 and m["unmatched_b"] == 0
    assert m["delivery_times"] == [117]
    assert m["latencies"] == [17]
    assert m["mean_latency"] == 17.0
    assert np.isclose(m["mean_fidelity"], 1.0, atol=1e-12)

    metrics = res["metrics"]
    assert metrics["sources"]["source_a"]["attempts"] == 1
    assert metrics["sources"]["source_b"]["attempts"] == 1
    assert metrics["memories"]["memory_a_1"]["heralded_pairs"] == 1
    assert metrics["memories"]["memory_a_1"]["evicted"] == 0
    assert metrics["swappers"]["es"]["completed"] == 1
    assert metrics["swappers"]["es"]["rejected"] == 0
