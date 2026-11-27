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


def test_pyodide_worker_bootstrap_and_bundle_builder():
    from pathlib import Path
    from damn_q.web_bundle import build_pyodide_bundle

    bundle = build_pyodide_bundle()
    assert "Simulation.py" in bundle
    assert "damn_q/manifest.py" in bundle
    assert "damn_q/runner.py" in bundle
    assert "damn_q/schema.py" in bundle

    worker_js = Path("damn_q/web/pyodide_worker.js").read_text(encoding="utf-8")
    start = worker_js.index("# --- DAMN_Q_WORKER_BOOTSTRAP_START ---")
    end = worker_js.index("# --- DAMN_Q_WORKER_BOOTSTRAP_END ---")
    py_code = worker_js[start:end]

    ns = {}
    exec(py_code, ns)

    manifest = json.loads(ns["_worker_manifest"]())
    assert "schema_version" in manifest
    assert "manifest_version" in manifest
    assert "components" in manifest
    assert "channels" in manifest

    exp = load_experiment("experiments/repeater_ideal.json")
    val = json.loads(ns["_worker_validate"](json.dumps(exp)))
    assert val["valid"] is True

    res = json.loads(ns["_worker_run"](json.dumps(exp)))
    assert np.isclose(res["measurements"][0]["mean_fidelity"], 1.0, atol=1e-12)
