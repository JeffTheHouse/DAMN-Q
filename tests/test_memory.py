import numpy as np
import pytest

from Auto_connector import connect
from Classic_data_reader import Classic_data_reader
from Emitter import Handler, bind, scheduler
from Entanglment_swapping_module import Entaglment_swapping_module
from Measurer import Measuring_Device
from Measurer_memory_paired import Measurer_memory_paired
from Memory import Quantum_memory
from Orchestrator import Orchestrator
from Pauli_corrector import Pauli_corrector
from Qubits import Qubit, State
from Source import Source
from States import phi_plus


KET0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
KET1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)


def test_same_tick_arrivals_do_not_overwrite():
    mem = Quantum_memory(1, depolarization_p=0, delay=0, capacity=10)
    q1 = Qubit(1, State(KET0.copy()))
    q2 = Qubit(2, State(KET1.copy()))

    # Both arrive at the same scheduler timestamp (t=0)
    mem.ch_in_q.handle(q1)
    mem.ch_in_q.handle(q2)

    assert len(mem.temperory_memory) == 2
    assert len(mem.memory) == 0
    assert mem.occupied_slots == 2

    # Confirm both via paired-memory heralding
    mem.ch_in_paired_memory.handle(1)
    mem.ch_in_paired_memory.handle(1)

    assert len(mem.temperory_memory) == 0
    assert len(mem.memory) == 2

    # Release in FIFO order
    released = []
    bind(mem.ch_out_q, Handler(lambda q: released.append(q)))
    mem.ch_in_c.handle(1)
    mem.ch_in_c.handle(1)
    scheduler.run(1)

    assert released == [q1, q2]


def test_single_qubit_source_assigns_integer_id():
    src = Source(1, delay=1, type=1)
    received = []
    bind(src.out_ch_1, Handler(lambda q: received.append(q)))

    scheduler.run(1)

    assert len(received) == 1
    assert isinstance(received[0].id, int)


def test_memory_lifecycle_failed_herald_eviction_and_empty_release():
    mem = Quantum_memory(1, depolarization_p=0, delay=0, capacity=2)
    released = []
    ready_signals = []
    bind(mem.ch_out_q, Handler(lambda q: released.append(q)))
    bind(mem.ch_out_c, Handler(lambda m: ready_signals.append(m)))

    # 1. Release request when no confirmed slot exists is a safe no-op
    mem.ch_in_c.handle(1)
    scheduler.run(1)
    assert released == []

    # 2. Failed herald removes pending slot and traces out its qubit
    q1, q1_partner = Qubit.bell_state(1, 2, State(np.kron(KET0, KET1)))
    mem.ch_in_q.handle(q1)
    assert mem.occupied_slots == 1
    mem.ch_in_paired_memory.handle(0)
    assert mem.occupied_slots == 0
    assert q1.state is None
    assert np.allclose(q1_partner.state.density_matrix, KET1)

    # 3. Eviction of pending slot + late herald does not corrupt subsequent slot
    q2 = Qubit(3, State(KET0.copy()))
    q3 = Qubit(4, State(KET1.copy()))
    q4 = Qubit(5, State(KET0.copy()))
    mem.ch_in_q.handle(q2)
    mem.ch_in_q.handle(q3)
    assert mem.occupied_slots == 2

    # Third arrival evicts oldest (q2)
    mem.ch_in_q.handle(q4)
    assert mem.occupied_slots == 2
    assert q2.state is None

    # Late herald for evicted q2 is ignored; next two heralds confirm q3 and q4
    mem.ch_in_paired_memory.handle(1)
    assert len(mem.memory) == 0
    mem.ch_in_paired_memory.handle(1)
    mem.ch_in_paired_memory.handle(1)
    assert len(mem.memory) == 2

    # 4. Eviction of a confirmed slot after readiness was sent leaves extra release as no-op
    q5 = Qubit(6, State(KET1.copy()))
    mem.ch_in_q.handle(q5)  # evicts oldest confirmed (q3)
    assert q3.state is None
    assert len(mem.memory) == 1  # only q4 remains confirmed

    mem.ch_in_c.handle(1)  # releases q4
    mem.ch_in_c.handle(1)  # stale request for evicted q3 -> safe no-op
    scheduler.run(5)
    assert released == [q4]


@pytest.mark.parametrize("ticks", [0, 1, 2])
def test_storage_depolarization_accrues_locally_over_integer_ticks(ticks):
    p = 0.2
    mem = Quantum_memory(1, depolarization_p=p, delay=0, capacity=4)
    released = []
    bind(mem.ch_out_q, Handler(lambda q: released.append(q)))

    q_keep, q_stored = Qubit.bell_state(1, 2, State(np.kron(KET0, KET1)))
    mem.ch_in_q.handle(q_stored)
    mem.ch_in_paired_memory.handle(1)

    scheduler.run(ticks)
    mem.ch_in_c.handle(1)
    scheduler.run(ticks + 1)

    assert len(released) == 1
    reg = q_keep.register
    assert reg is q_stored.register
    # Untouched partner stays |0><0|
    assert np.allclose(reg.reduced_density_matrix([q_keep]), KET0)
    # Stored qubit matches exact composed single-qubit depolarizing channel
    lam = (1.0 - 4.0 * p / 3.0) ** ticks
    expected_stored = lam * KET1 + (1.0 - lam) * (0.5 * np.eye(2))
    assert np.allclose(reg.reduced_density_matrix([q_stored]), expected_stored)


def test_storage_depolarization_rejects_fractional_ticks():
    mem = Quantum_memory(1, depolarization_p=0.8, delay=0, capacity=4)
    q = Qubit(1, State(KET0.copy()))
    mem.ch_in_q.handle(q)
    mem.ch_in_paired_memory.handle(1)

    scheduler.run(1.5)
    with pytest.raises(ValueError, match="integer storage ticks"):
        mem.ch_in_c.handle(1)


def _build_wired_repeater(p_mem=(0.0, 0.0, 0.0, 0.0), link_delay=5, swap_delay=1):
    """Build the 3-node repeater with 4 memories and return endpoint captures."""
    source_a = Source(1, 100, 2)  # single pair emitted at t=100 within run window
    source_b = Source(2, 100, 2)

    mem_a1 = Quantum_memory(1, p_mem[0], 0, 100)
    mem_a2 = Quantum_memory(2, p_mem[1], 0, 100)
    mem_b1 = Quantum_memory(3, p_mem[2], 0, 100)
    mem_b2 = Quantum_memory(4, p_mem[3], 0, 100)

    es = Entaglment_swapping_module(1, swap_delay)
    orch = Orchestrator(1, 0)
    pc = Pauli_corrector(1, 0)

    connect(source_a.out_ch_1, mem_a1.ch_in_q, link_delay)
    connect(source_a.out_ch_2, mem_a2.ch_in_q, link_delay)
    connect(source_b.out_ch_1, mem_b1.ch_in_q, link_delay)
    connect(source_b.out_ch_2, mem_b2.ch_in_q, link_delay)

    connect(mem_a2.ch_out_q, es.ch_in_q_1)
    connect(mem_b1.ch_out_q, es.ch_in_q_2)

    connect(mem_a2.ch_out_c, orch.ch_in_memory_1)
    connect(mem_b1.ch_out_c, orch.ch_in_memory_2)
    connect(orch.ch_out_memory_1, mem_a2.ch_in_c)
    connect(orch.ch_out_memory_2, mem_b1.ch_in_c)

    connect(mem_a1.ch_out_paired_memory, mem_a2.ch_in_paired_memory, link_delay)
    connect(mem_a2.ch_out_paired_memory, mem_a1.ch_in_paired_memory, link_delay)
    connect(mem_b1.ch_out_paired_memory, mem_b2.ch_in_paired_memory, link_delay)
    connect(mem_b2.ch_out_paired_memory, mem_b1.ch_in_paired_memory, link_delay)

    connect(es.ch_out_c_2, pc.ch_in_es, link_delay)
    connect(mem_b2.ch_out_q, pc.ch_in_q)
    connect(mem_b2.ch_out_c, pc.ch_in_memory)
    connect(pc.ch_out_memory, mem_b2.ch_in_c)

    # Request a1 from mem_a1 when swap outcome arrives on side A
    connect(es.ch_out_c_1, mem_a1.ch_in_c, link_delay)

    end_a = []
    end_b = []
    bind(mem_a1.ch_out_q, Handler(lambda q: end_a.append(q)))
    bind(pc.ch_out_q, Handler(lambda q: end_b.append(q)))
    return end_a, end_b


def test_wired_repeater_with_memories_produces_exact_phi_plus():
    end_a, end_b = _build_wired_repeater(p_mem=(0.0, 0.0, 0.0, 0.0))

    scheduler.run(150)

    assert len(end_a) == 1
    assert len(end_b) == 1
    q_a, q_b = end_a[0], end_b[0]
    assert q_a.register is q_b.register
    joint = q_a.register.reduced_density_matrix([q_a, q_b])
    assert np.allclose(joint, phi_plus)


@pytest.mark.parametrize("x_basis_p", [0.0, 1.0])
def test_wired_repeater_with_memories_matches_in_z_and_x_basis(x_basis_p):
    source_a = Source(1, 20, 2)
    source_b = Source(2, 20, 2)

    mem_a1 = Quantum_memory(1, 0, 0, 100)
    mem_a2 = Quantum_memory(2, 0, 0, 100)
    mem_b1 = Quantum_memory(3, 0, 0, 100)
    mem_b2 = Quantum_memory(4, 0, 0, 100)

    es = Entaglment_swapping_module(1, 1)
    orch = Orchestrator(1, 0)
    pc = Pauli_corrector(1, 0)
    m_a = Measurer_memory_paired(1, 0, x_basis_p=x_basis_p)
    m_b = Measuring_Device(2, 0, x_basis_p=x_basis_p)
    reader = Classic_data_reader(1)

    connect(source_a.out_ch_1, mem_a1.ch_in_q, 5)
    connect(source_a.out_ch_2, mem_a2.ch_in_q, 5)
    connect(source_b.out_ch_1, mem_b1.ch_in_q, 5)
    connect(source_b.out_ch_2, mem_b2.ch_in_q, 5)

    connect(mem_a1.ch_out_q, m_a.ch_in_q)
    connect(mem_b2.ch_out_q, pc.ch_in_q)
    connect(pc.ch_out_q, m_b.ch_in_q)

    connect(mem_a2.ch_out_q, es.ch_in_q_1)
    connect(mem_b1.ch_out_q, es.ch_in_q_2)

    connect(mem_a2.ch_out_c, orch.ch_in_memory_1)
    connect(mem_b1.ch_out_c, orch.ch_in_memory_2)
    connect(orch.ch_out_memory_1, mem_a2.ch_in_c)
    connect(orch.ch_out_memory_2, mem_b1.ch_in_c)

    connect(es.ch_out_c_1, m_a.ch_in_es, 5)
    connect(es.ch_out_c_2, pc.ch_in_es, 5)

    connect(mem_a1.ch_out_paired_memory, mem_a2.ch_in_paired_memory, 5)
    connect(mem_a2.ch_out_paired_memory, mem_a1.ch_in_paired_memory, 5)
    connect(mem_b1.ch_out_paired_memory, mem_b2.ch_in_paired_memory, 5)
    connect(mem_b2.ch_out_paired_memory, mem_b1.ch_in_paired_memory, 5)

    connect(mem_a1.ch_out_c, m_a.ch_in_memory_c)
    connect(m_a.ch_out_memory_c, mem_a1.ch_in_c)
    connect(mem_b2.ch_out_c, pc.ch_in_memory)
    connect(pc.ch_out_memory, mem_b2.ch_in_c)

    connect(m_a.ch_out_result, reader.input_2)
    connect(m_b.ch_out_result, reader.input_1)

    scheduler.run(300)

    total = reader.count_00 + reader.count_11
    assert total >= 10
    assert reader.count_01 == 0
    assert reader.count_10 == 0


def test_wired_repeater_with_memory_noise_matches_analytic_fidelity():
    # Storage durations for link_delay=5, swap_delay=1:
    #   arrival at all 4 memories: t = 100 + 5 = 105
    #   paired herald arrives:     t = 105 + 1 + 5 = 111
    #   middle memories release:   t = 111 -> t_a2 = t_b1 = 6
    #   swap outcome arrives:      t = 111 + 1 + 5 = 117
    #   endpoint memories release: t = 117 -> t_a1 = t_b2 = 12
    p_mem = (0.01, 0.02, 0.015, 0.025)
    t_mem = (12, 6, 6, 12)

    end_a, end_b = _build_wired_repeater(p_mem=p_mem, link_delay=5, swap_delay=1)
    scheduler.run(150)

    assert len(end_a) == 1
    assert len(end_b) == 1
    q_a, q_b = end_a[0], end_b[0]
    assert q_a.register is q_b.register

    joint = q_a.register.reduced_density_matrix([q_a, q_b])
    fidelity = float(np.real(np.trace(phi_plus @ joint)))

    prod = 1.0
    for p_i, t_i in zip(p_mem, t_mem):
        prod *= (1.0 - 4.0 * p_i / 3.0) ** t_i
    expected_f = (1.0 + 3.0 * prod) / 4.0

    assert np.isclose(fidelity, expected_f, atol=1e-12)
