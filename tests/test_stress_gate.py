import json
import numpy as np

from damn_q.chain import ChainConfig, run_repeater_chain
from damn_q.runner import load_experiment, run_experiment
from damn_q.schema import validate_experiment


def test_backend_duration_retention_stays_bounded_at_10x_horizon():
    """Extending run duration 10x in streaming mode must not grow live/cancelled queues."""
    base = dict(
        num_hops=4,
        seed=101,
        loss_p=0.5,
        channel_depolarization_p=0.005,
        memory_depolarization_p=0.0005,
        memory_cutoff=400.0,
        trace=False,
    )
    r_1x = run_repeater_chain(ChainConfig(**base, until=4000))
    r_10x = run_repeater_chain(ChainConfig(**base, until=40000))

    assert r_10x["cutoff_expiries"] > r_1x["cutoff_expiries"] * 5
    assert r_10x["live_queue_len"] <= 20
    assert r_10x["cancelled_queue_len"] < 64


def test_backend_streaming_vs_trace_invariance_under_high_loss_and_cutoffs():
    base = dict(
        num_hops=2,
        until=10000,
        seed=101,
        loss_p=0.5,
        channel_depolarization_p=0.005,
        memory_depolarization_p=0.0005,
        memory_cutoff=400.0,
    )
    r_stream = run_repeater_chain(ChainConfig(**base, trace=False))
    r_trace = run_repeater_chain(ChainConfig(**base, trace=True))

    assert r_stream["delivered_pairs"] == r_trace["delivered_pairs"]
    assert r_stream["attempts"] == r_trace["attempts"]
    assert r_stream["swaps_completed"] == r_trace["swaps_completed"]
    assert r_stream["cutoff_expiries"] == r_trace["cutoff_expiries"]
    assert np.isclose(r_stream["fidelity"]["mean"], r_trace["fidelity"]["mean"], atol=1e-12)
    assert np.isclose(r_stream["latency_ticks"]["mean"], r_trace["latency_ticks"]["mean"], atol=1e-12)


def test_component_graph_zero_delivery_and_export_roundtrip():
    """Exported JSON from a zero-delivery run validates and reproduces identically in the runner."""
    exp = load_experiment("benchmarks/repeater_3node_ref.json")
    for ch in exp["connections"]:
        if "loss_p" in ch:
            ch["loss_p"] = 1.0
    exp["run"]["until"] = 4000

    # Round-trip through JSON string as the browser export/import does
    reloaded = json.loads(json.dumps(exp))
    validate_experiment(reloaded)

    r1 = run_experiment(exp)
    r2 = run_experiment(reloaded)
    assert r1["measurements"][0]["pairs"] == 0
    assert r2["measurements"][0]["pairs"] == 0
    assert r1["measurements"] == r2["measurements"]


def test_stress_gate_cli_exits_nonzero_in_json_mode_on_failure(monkeypatch):
    import benchmarks.run_stress_gate as sg

    fake_fail = {
        "gate_passed": False,
        "hop_sweep": [],
        "duration_retention": {"passed": False},
        "trace_invariance": {"passed": False},
    }
    monkeypatch.setattr(sg, "run_stress_gate", lambda **kw: fake_fail)
    assert sg.main(["--json"]) == 1


def test_stress_gate_detects_latency_only_trace_mismatch(monkeypatch):
    import benchmarks.run_stress_gate as sg

    base_row = {
        "num_hops": 2,
        "until_ticks": 1000,
        "delivered_pairs": 5,
        "attempts": 20,
        "swaps_completed": 5,
        "cutoff_expiries": 1,
        "live_queue_len": 4,
        "cancelled_queue_len": 0,
        "fidelity": {"mean": 0.75},
        "latency_ticks": {"mean": 200.0},
        "peak_ram_kib": 100.0,
        "process_peak_rss_mib": 25.0,
        "wall_time_s": 0.1,
        "profile": {"dominant": "registers"},
    }

    def fake_bench(*args, **kwargs):
        row = dict(base_row)
        row["latency_ticks"] = dict(base_row["latency_ticks"])
        if kwargs.get("trace"):
            row["latency_ticks"]["mean"] = 205.0
        return {"rows": [row]}

    monkeypatch.setattr(sg, "run_chain_scaling_benchmark", fake_bench)
    report = sg.run_stress_gate(hops_list=(2,), hop_until=1000, dur_hops=2, dur_base=1000)
    assert report["trace_invariance"]["passed"] is False
    assert report["gate_passed"] is False


def test_pyodide_worker_bootstrap_and_bundle_builder(tmp_path):
    """Unpack the generated bundle into an isolated directory and run the worker bootstrap from it alone."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    from damn_q.web_bundle import write_pyodide_bundle

    bundle_path = write_pyodide_bundle(tmp_path / "damn_q_bundle.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    # Unpack bundle into a clean directory with NO source checkout on sys.path
    unpack_dir = tmp_path / "unpacked"
    for rel_path, src in bundle.items():
        target = unpack_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src, encoding="utf-8")

    worker_js = Path("damn_q/web/pyodide_worker.js").read_text(encoding="utf-8")
    start = worker_js.index("# --- DAMN_Q_WORKER_BOOTSTRAP_START ---")
    end = worker_js.index("# --- DAMN_Q_WORKER_BOOTSTRAP_END ---")
    py_bootstrap = worker_js[start:end]

    exp_ideal = json.dumps(load_experiment("experiments/repeater_ideal.json"))
    exp_tut = json.dumps(load_experiment("experiments/repeater_tutorial_z.json"))

    driver = (
        py_bootstrap
        + "\n"
        + f"m = json.loads(_worker_manifest())\n"
        + f"assert 'schema_version' in m and 'components' in m and 'channels' in m\n"
        + f"v = json.loads(_worker_validate({exp_ideal!r}))\n"
        + f"assert v['valid'] is True and v['schema_version'] == m['schema_version']\n"
        + f"r1 = json.loads(_worker_run({exp_ideal!r}))\n"
        + f"assert r1['ok'] is True\n"
        + f"assert abs(r1['result']['measurements'][0]['mean_fidelity'] - 1.0) < 1e-12\n"
        + f"r2 = json.loads(_worker_run({exp_tut!r}))\n"
        + f"assert r2['ok'] is True\n"
        + f"assert r2['result']['readers']['reader'] == {{'00': 39, '01': 0, '10': 0, '11': 44}}\n"
        + f"bad = json.loads({exp_ideal!r}); bad['run']['until'] = 0\n"
        + f"r3 = json.loads(_worker_run(json.dumps(bad)))\n"
        + f"assert r3['ok'] is False and any('run.until' in e for e in r3['errors']), r3\n"
        + f"assert 'Traceback' not in json.dumps(r3)\n"
        + "print('BUNDLE_ISOLATED_OK')\n"
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(unpack_dir)!r})\n" + driver],
        cwd=str(unpack_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Isolated bundle failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "BUNDLE_ISOLATED_OK" in proc.stdout


def test_stress_gate_includes_hardware_hop_sweep_and_isolated_parity():
    from benchmarks.run_chain_benchmark import run_chain_scaling_benchmark
    from benchmarks.run_stress_gate import run_stress_gate

    hw_kwargs = dict(
        hops_list=(2,),
        until=4000,
        seed=101,
        loss_p=0.0,
        channel_depolarization_p=0.0,
        memory_depolarization_p=0.0,
        length_km=2.0,
        initial_fidelity=0.95,
        memory_t1_ticks=2000.0,
        memory_t2_ticks=1500.0,
        bsm_visibility=0.95,
        detector_efficiency=0.9,
    )
    iso = run_chain_scaling_benchmark(**hw_kwargs, isolate_processes=True)["rows"][0]
    inp = run_chain_scaling_benchmark(**hw_kwargs, isolate_processes=False)["rows"][0]
    assert iso["delivered_pairs"] == inp["delivered_pairs"] > 0
    assert np.isclose(iso["fidelity"]["mean"], inp["fidelity"]["mean"], atol=1e-12)

    report = run_stress_gate(
        hops_list=(2, 4),
        hop_until=4000,
        dur_hops=2,
        dur_base=6000,
        dur_mult=2,
        loss_p=0.2,
    )
    assert report["hardware_hop_sweep"]["passed"] is True
    assert len(report["hardware_hop_sweep"]["rows"]) == 2
    assert report["gate_passed"] is True
