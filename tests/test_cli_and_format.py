import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from Auto_connector import connect
from Classic_data_reader import Classic_data_reader
from Emitter import scheduler
from Entanglment_swapping_module import Entaglment_swapping_module
from Measurer import Measuring_Device
from Measurer_memory_paired import Measurer_memory_paired
from Memory import Quantum_memory
from Orchestrator import Orchestrator
from Pauli_corrector import Pauli_corrector
from Source import Source
from damn_q import ExperimentValidationError, run_experiment, validate_experiment


ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "experiments"


def test_cli_ideal_repeater_produces_exact_phi_plus():
    proc = subprocess.run(
        [sys.executable, "-m", "damn_q", "run", str(EXPERIMENTS / "repeater_ideal.json"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    assert res["schema_version"] == "1.0"
    assert isinstance(res["simulator_version"], str) and res["simulator_version"]
    assert len(res["measurements"]) == 1
    m = res["measurements"][0]
    assert m["pairs"] == 1
    assert m["all_shared_register"] is True
    assert np.isclose(m["mean_fidelity"], 1.0, atol=1e-12)


def test_cli_noisy_repeater_matches_analytic_fidelity():
    proc = subprocess.run(
        [sys.executable, "-m", "damn_q", "run", str(EXPERIMENTS / "repeater_noisy_memory.json"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    res = json.loads(proc.stdout)
    m = res["measurements"][0]
    assert m["pairs"] == 1
    assert m["all_shared_register"] is True

    p_mem = (0.01, 0.02, 0.015, 0.025)
    t_mem = (12, 6, 6, 12)
    prod = 1.0
    for p_i, t_i in zip(p_mem, t_mem):
        prod *= (1.0 - 4.0 * p_i / 3.0) ** t_i
    expected_f = (1.0 + 3.0 * prod) / 4.0

    assert np.isclose(m["mean_fidelity"], expected_f, atol=1e-12)


def test_cli_reproduces_python_wired_tutorial_repeater_with_seed():
    seed = 1234
    until = 100

    # Run Python-wired repeater directly
    scheduler.reset()
    rng_state = random.getstate()
    random.seed(seed)
    try:
        source_a = Source(1, 1, 2)
        source_b = Source(2, 1, 2)
        memory_a_1 = Quantum_memory(1, 0, 0, 100)
        memory_a_2 = Quantum_memory(2, 0, 0, 100)
        memory_b_1 = Quantum_memory(3, 0, 0, 100)
        memory_b_2 = Quantum_memory(4, 0, 0, 100)
        es = Entaglment_swapping_module(1, 1)
        orchestrator = Orchestrator(1, 0)
        pc = Pauli_corrector(1, 0)
        m_a = Measurer_memory_paired(1, 0, 0, 0)
        m_b = Measuring_Device(2, 0, 0, 0)
        reader = Classic_data_reader(1)

        connect(source_a.out_ch_1, memory_a_1.ch_in_q, 5)
        connect(source_a.out_ch_2, memory_a_2.ch_in_q, 5)
        connect(source_b.out_ch_1, memory_b_1.ch_in_q, 5)
        connect(source_b.out_ch_2, memory_b_2.ch_in_q, 5)
        connect(memory_a_1.ch_out_q, m_a.ch_in_q)
        connect(memory_b_2.ch_out_q, pc.ch_in_q)
        connect(pc.ch_out_q, m_b.ch_in_q)
        connect(memory_a_2.ch_out_q, es.ch_in_q_1)
        connect(memory_b_1.ch_out_q, es.ch_in_q_2)
        connect(memory_a_2.ch_out_c, orchestrator.ch_in_memory_1)
        connect(memory_b_1.ch_out_c, orchestrator.ch_in_memory_2)
        connect(orchestrator.ch_out_memory_1, memory_a_2.ch_in_c)
        connect(orchestrator.ch_out_memory_2, memory_b_1.ch_in_c)
        connect(es.ch_out_c_1, m_a.ch_in_es, 5)
        connect(es.ch_out_c_2, pc.ch_in_es, 5)
        connect(memory_a_1.ch_out_paired_memory, memory_a_2.ch_in_paired_memory, 5)
        connect(memory_a_2.ch_out_paired_memory, memory_a_1.ch_in_paired_memory, 5)
        connect(memory_b_1.ch_out_paired_memory, memory_b_2.ch_in_paired_memory, 5)
        connect(memory_b_2.ch_out_paired_memory, memory_b_1.ch_in_paired_memory, 5)
        connect(memory_a_1.ch_out_c, m_a.ch_in_memory_c)
        connect(m_a.ch_out_memory_c, memory_a_1.ch_in_c)
        connect(memory_b_2.ch_out_c, pc.ch_in_memory)
        connect(pc.ch_out_memory, memory_b_2.ch_in_c)
        connect(m_a.ch_out_result, reader.input_2)
        connect(m_b.ch_out_result, reader.input_1)

        scheduler.run(until)
        py_counts = {
            "00": reader.count_00,
            "01": reader.count_01,
            "10": reader.count_10,
            "11": reader.count_11,
        }
    finally:
        random.setstate(rng_state)

    # Run JSON project via CLI in a fresh subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "damn_q", "run", str(EXPERIMENTS / "repeater_tutorial_z.json"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    cli_counts = json.loads(proc.stdout)["readers"]["reader"]
    assert cli_counts == py_counts
    assert cli_counts["01"] == 0
    assert cli_counts["10"] == 0
    assert cli_counts["00"] + cli_counts["11"] > 0


def test_invalid_graphs_fail_before_executing_any_events(tmp_path):
    # Track whether scheduler.run was ever reached by setting a sentinel
    scheduler.reset()
    bad_docs = [
        # Unsupported schema version
        {"schema_version": "9.9", "run": {"until": 10}, "components": [{"id": "s", "type": "source"}]},
        # Source delay <= 0
        {"schema_version": "1.0", "run": {"until": 10}, "components": [{"id": "s", "type": "source", "params": {"delay": 0}}]},
        # Incompatible port kinds (quantum -> classical)
        {
            "schema_version": "1.0",
            "run": {"until": 10},
            "components": [
                {"id": "s", "type": "source", "params": {"delay": 1}},
                {"id": "r", "type": "classic_data_reader"},
            ],
            "connections": [
                {"from": {"component": "s", "port": "out_ch_1"}, "to": {"component": "r", "port": "input_1"}},
            ],
        },
        # Wrong direction (in -> in)
        {
            "schema_version": "1.0",
            "run": {"until": 10},
            "components": [
                {"id": "m1", "type": "quantum_memory"},
                {"id": "m2", "type": "quantum_memory"},
            ],
            "connections": [
                {"from": {"component": "m1", "port": "ch_in_q"}, "to": {"component": "m2", "port": "ch_in_q"}},
            ],
        },
        # Classical link with quantum depolarization noise
        {
            "schema_version": "1.0",
            "run": {"until": 10},
            "components": [
                {"id": "m", "type": "quantum_memory"},
                {"id": "o", "type": "orchestrator"},
            ],
            "connections": [
                {
                    "from": {"component": "m", "port": "ch_out_c"},
                    "to": {"component": "o", "port": "ch_in_memory_1"},
                    "depolarization_p": 0.1,
                },
            ],
        },
    ]

    for doc in bad_docs:
        with pytest.raises(ExperimentValidationError):
            run_experiment(doc)
        # No events were scheduled or executed
        assert scheduler.time == 0
        assert scheduler._queue == []

    # Also verify CLI returns non-zero exit code on invalid JSON project
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps(bad_docs[2]), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "damn_q", "validate", str(bad_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "incompatible port types" in proc.stderr


def test_cli_validate_and_manifest_commands():
    val = subprocess.run(
        [sys.executable, "-m", "damn_q", "validate", str(EXPERIMENTS / "repeater_ideal.json")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "OK:" in val.stdout

    man = subprocess.run(
        [sys.executable, "-m", "damn_q", "manifest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(man.stdout)
    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["simulator_version"], str) and payload["simulator_version"]
    assert "quantum_memory" in payload["components"]
    assert "entanglement_swapper" in payload["components"]


def test_validator_rejects_quantum_fanout_nonfinite_horizon_duplicate_probe_and_unhashable_type():
    # 1. Quantum fan-out from one quantum output port to two destinations
    quantum_fanout = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [
            {"id": "s", "type": "source", "params": {"delay": 1}},
            {"id": "p1", "type": "endpoint_probe"},
            {"id": "p2", "type": "endpoint_probe"},
        ],
        "connections": [
            {"from": {"component": "s", "port": "out_ch_1"}, "to": {"component": "p1", "port": "ch_in_q"}},
            {"from": {"component": "s", "port": "out_ch_1"}, "to": {"component": "p2", "port": "ch_in_q"}},
        ],
    }
    with pytest.raises(ExperimentValidationError, match="fans out quantum output port"):
        validate_experiment(quantum_fanout)

    # 2. Non-finite run horizon (inf / nan)
    for bad_until in (float("inf"), float("nan")):
        nonfinite = {
            "schema_version": "1.0",
            "run": {"until": bad_until},
            "components": [{"id": "s", "type": "source", "params": {"delay": 1}}],
        }
        with pytest.raises(ExperimentValidationError, match="run.until"):
            validate_experiment(nonfinite)

    # 3. Bell-fidelity measurement referencing the same probe twice
    dup_probe = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [{"id": "p1", "type": "endpoint_probe"}],
        "measurements": [{"type": "bell_fidelity", "probes": ["p1", "p1"]}],
    }
    with pytest.raises(ExperimentValidationError, match="two distinct endpoint probes"):
        validate_experiment(dup_probe)

    # 4. Unhashable (list-valued) component type raises ExperimentValidationError, not TypeError
    list_type = {
        "schema_version": "1.0",
        "run": {"until": 10},
        "components": [{"id": "bad", "type": ["source"]}],
    }
    with pytest.raises(ExperimentValidationError, match="must be a string"):
        validate_experiment(list_type)
