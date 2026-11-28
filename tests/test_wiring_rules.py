import numpy as np
import pytest

from Auto_connector import connect
from Classic_data_reader import Classic_data_reader
from Detector_module import Detector_module
from Emitter import Handler, bind
from Entanglment_swapping_module import Entaglment_swapping_module
from Measurer import Measuring_Device
from Measurer_memory_paired import Measurer_memory_paired
from Memory import Quantum_memory
from Orchestrator import Orchestrator
from Pauli_corrector import Pauli_corrector
from Qubits import Qubit, State
from Signals import Ready, Release
from Simulation import Simulation
from Source import Source
from damn_q import COMPONENT_MANIFEST, ExperimentValidationError, validate_experiment


KET0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
CANONICAL_MESSAGE_TYPES = {
    "BellOutcome",
    "MeasurementOutcome",
    "MemoryReady",
    "MemoryReadoutRequest",
    "PeerHerald",
}


def test_manifest_declares_wiring_rules_for_all_35_ports():
    port_count = 0
    for ctype, spec in COMPONENT_MANIFEST.items():
        for pname, pspec in spec["ports"].items():
            port_count += 1
            assert "max_connections" in pspec, f"{ctype}.{pname} missing max_connections"
            if pspec["kind"] == "quantum":
                assert pspec["max_connections"] == 1, f"{ctype}.{pname} must not fan out/in"
            else:
                assert pspec.get("message_type") in CANONICAL_MESSAGE_TYPES, (
                    f"{ctype}.{pname} missing canonical message_type"
                )
            if pspec["direction"] == "in":
                assert pspec["max_connections"] == 1, f"Input {ctype}.{pname} must default to 1"
    assert port_count == 39


def test_python_api_rejects_fanout_on_all_six_quantum_outputs():
    sim = Simulation()
    src = Source(1, delay=5, type=2, sim=sim)
    mem = Quantum_memory(1, 0.0, sim=sim)
    pc = Pauli_corrector(1, sim=sim)
    det = Detector_module(1, sim=sim)

    quantum_outputs = [
        src.out_ch_1,
        src.out_ch_2,
        mem.ch_out_q,
        pc.ch_out_q,
        det.output_a_1,
        det.output_a_2,
    ]
    for idx, port in enumerate(quantum_outputs):
        m1 = Measuring_Device(100 + idx * 2, delay=0, sim=sim)
        m2 = Measuring_Device(101 + idx * 2, delay=0, sim=sim)
        connect(port, m1.ch_in_q)
        with pytest.raises(ValueError, match="fan out"):
            connect(port, m2.ch_in_q)
        with pytest.raises(ValueError, match="fan out"):
            bind(port, m2.ch_in_q)


def test_python_api_rejects_command_fanout_and_input_fanin_atomically():
    sim = Simulation()
    orch = Orchestrator(1, sim=sim)
    mem_a = Quantum_memory(1, 0.0, sim=sim)
    mem_b = Quantum_memory(2, 0.0, sim=sim)

    # Command output cannot broadcast to two memories
    connect(orch.ch_out_memory_1, mem_a.ch_in_c)
    with pytest.raises(ValueError, match="fan out"):
        connect(orch.ch_out_memory_1, mem_b.ch_in_c)

    # Input cannot accept two upstream producers; failed connect leaves source untouched
    src1 = Source(1, delay=5, type=1, sim=sim)
    src2 = Source(2, delay=5, type=1, sim=sim)
    m = Measuring_Device(1, delay=0, sim=sim)
    connect(src1.out_ch_1, m.ch_in_q)
    with pytest.raises(ValueError, match="fan in"):
        connect(src2.out_ch_1, m.ch_in_q)
    # src2.out_ch_1 must still be free (no dangling link left behind)
    m_other = Measuring_Device(2, delay=0, sim=sim)
    connect(src2.out_ch_1, m_other.ch_in_q)

    # Cross-kind (quantum -> classical) rejected directly in Python
    reader = Classic_data_reader(1, sim=sim)
    src3 = Source(3, delay=5, type=1, sim=sim)
    with pytest.raises(ValueError, match="incompatible port kinds"):
        connect(src3.out_ch_1, reader.input_1)


def test_python_api_allows_outcome_broadcast_but_rejects_duplicates():
    sim = Simulation()
    m = Measuring_Device(1, delay=0, sim=sim)
    r1 = Classic_data_reader(1, sim=sim)
    r2 = Classic_data_reader(2, sim=sim)

    connect(m.ch_out_result, r1.input_1)
    connect(m.ch_out_result, r2.input_1)
    with pytest.raises(ValueError, match="fan in|Duplicate"):
        connect(m.ch_out_result, r1.input_1)


def test_memory_addressed_release_ignores_wrong_memory_id():
    sim = Simulation()
    mem_a = Quantum_memory("mem_a", depolarization_p=0, delay=0, capacity=4, sim=sim)
    mem_b = Quantum_memory("mem_b", depolarization_p=0, delay=0, capacity=4, sim=sim)

    ready_a = []
    out_a = []
    out_b = []
    bind(mem_a.ch_out_c, Handler(lambda m: ready_a.append(m)))
    bind(mem_a.ch_out_q, Handler(lambda q: out_a.append(q)))
    bind(mem_b.ch_out_q, Handler(lambda q: out_b.append(q)))

    qa = Qubit(1, State(KET0.copy()))
    qb = Qubit(2, State(KET0.copy()))

    # Both memories store slot_id=0
    mem_a.ch_in_q.handle(qa)
    mem_a.ch_in_paired_memory.handle(1)
    mem_b.ch_in_q.handle(qb)
    mem_b.ch_in_paired_memory.handle(1)
    sim.run(0)

    assert ready_a == [Ready(0, memory_id="mem_a")]

    # Release addressed to mem_a sent to mem_b must NOT release mem_b's slot 0
    req_for_a = Release(0, memory_id="mem_a")
    mem_b.ch_in_c.handle(req_for_a)
    sim.run(1)
    assert out_b == []
    assert len(mem_b.memory) == 1

    # Sending it to mem_a releases qa cleanly
    mem_a.ch_in_c.handle(req_for_a)
    sim.run(2)
    assert out_a == [qa]
    assert len(mem_a.memory) == 0


def test_validator_rejects_fanin_command_fanout_duplicate_inactive_and_wrong_message_type():
    # 1. Quantum input fan-in
    q_fanin = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "s1", "type": "source", "params": {"delay": 1, "type": 1}},
            {"id": "s2", "type": "source", "params": {"delay": 1, "type": 1}},
            {"id": "m", "type": "measurer"},
        ],
        "connections": [
            {"from": {"component": "s1", "port": "out_ch_1"}, "to": {"component": "m", "port": "ch_in_q"}},
            {"from": {"component": "s2", "port": "out_ch_1"}, "to": {"component": "m", "port": "ch_in_q"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="fans in to quantum input port"):
        validate_experiment(q_fanin)

    # 2. Classical command output fan-out (Swap Controller -> two memories)
    cmd_fanout = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "o", "type": "orchestrator"},
            {"id": "m1", "type": "quantum_memory"},
            {"id": "m2", "type": "quantum_memory"},
        ],
        "connections": [
            {"from": {"component": "o", "port": "ch_out_memory_1"}, "to": {"component": "m1", "port": "ch_in_c"}},
            {"from": {"component": "o", "port": "ch_out_memory_1"}, "to": {"component": "m2", "port": "ch_in_c"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="fans out classical output port"):
        validate_experiment(cmd_fanout)

    # 3. Classical message type mismatch: BellOutcome -> PeerHerald
    wrong_msg = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "es", "type": "entanglement_swapper"},
            {"id": "m", "type": "quantum_memory"},
        ],
        "connections": [
            {"from": {"component": "es", "port": "ch_out_c_1"}, "to": {"component": "m", "port": "ch_in_paired_memory"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="incompatible classical message types"):
        validate_experiment(wrong_msg)

    # 4. Inactive port: source.out_ch_2 when type == 1
    inactive_port = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "s", "type": "source", "params": {"delay": 1, "type": 1}},
            {"id": "p", "type": "endpoint_probe"},
        ],
        "connections": [
            {"from": {"component": "s", "port": "out_ch_2"}, "to": {"component": "p", "port": "ch_in_q"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="inactive"):
        validate_experiment(inactive_port)

    # 5. Duplicate edge on broadcast classical output
    dup_edge = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "m", "type": "measurer"},
            {"id": "r", "type": "classic_data_reader"},
        ],
        "connections": [
            {"from": {"component": "m", "port": "ch_out_result"}, "to": {"component": "r", "port": "input_1"}},
            {"from": {"component": "m", "port": "ch_out_result"}, "to": {"component": "r", "port": "input_1"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="duplicates existing connection"):
        validate_experiment(dup_edge)

    # 6. Broadcast outcome to two distinct readers IS allowed
    valid_broadcast = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "m", "type": "measurer"},
            {"id": "r1", "type": "classic_data_reader"},
            {"id": "r2", "type": "classic_data_reader"},
        ],
        "connections": [
            {"from": {"component": "m", "port": "ch_out_result"}, "to": {"component": "r1", "port": "input_1"}},
            {"from": {"component": "m", "port": "ch_out_result"}, "to": {"component": "r2", "port": "input_1"}},
        ],
    }
    validate_experiment(valid_broadcast)
