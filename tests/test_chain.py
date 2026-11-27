import numpy as np
import pytest

from benchmarks.run_chain_benchmark import run_chain_scaling_benchmark
from benchmarks.run_reference_benchmark import REF_JSON, analytic_lossless_prediction
from damn_q.chain import ChainConfig, run_repeater_chain
from damn_q.runner import load_experiment


def test_chain_2hop_lossless_matches_step1_analytic_fidelity_and_latency():
    analytic = analytic_lossless_prediction(load_experiment(REF_JSON))
    cfg = ChainConfig(
        num_hops=2,
        until=2200,
        seed=101,
        attempt_period=200,
        link_delay=50,
        swap_delay=1,
        loss_p=0.0,
        channel_depolarization_p=0.005,
        memory_depolarization_p=0.0005,
        memory_cutoff=0.0,
    )
    res = run_repeater_chain(cfg)
    assert res["delivered_pairs"] >= 9
    assert np.isclose(res["fidelity"]["mean"], analytic["fidelity"], atol=1e-12)
    assert np.isclose(res["latency_ticks"]["mean"], analytic["latency_ticks"], atol=1e-12)


@pytest.mark.parametrize("num_hops", [1, 2, 4, 8])
def test_chain_noiseless_delivers_exact_phi_plus_at_arbitrary_length(num_hops):
    cfg = ChainConfig(
        num_hops=num_hops,
        until=3000,
        seed=7,
        attempt_period=200,
        link_delay=20,
        swap_delay=1,
        loss_p=0.0,
        channel_depolarization_p=0.0,
        memory_depolarization_p=0.0,
        memory_cutoff=0.0,
    )
    res = run_repeater_chain(cfg)
    assert res["delivered_pairs"] > 0
    assert np.isclose(res["fidelity"]["mean"], 1.0, atol=1e-12)


def test_memory_cutoff_improves_delivery_fidelity_and_records_expiries():
    base = dict(
        num_hops=2,
        until=40000,
        seed=101,
        attempt_period=200,
        link_delay=50,
        swap_delay=1,
        loss_p=0.2,
        channel_depolarization_p=0.005,
        memory_depolarization_p=0.0005,
    )
    no_cutoff = run_repeater_chain(ChainConfig(**base, memory_cutoff=0.0))
    with_cutoff = run_repeater_chain(ChainConfig(**base, memory_cutoff=400.0))

    assert no_cutoff["cutoff_expiries"] == 0
    assert with_cutoff["cutoff_expiries"] > 0
    assert with_cutoff["delivered_pairs"] > 0
    assert with_cutoff["fidelity"]["mean"] > no_cutoff["fidelity"]["mean"] + 0.02


def test_streaming_stats_keep_no_samples_unless_trace_enabled():
    cfg_stream = ChainConfig(num_hops=2, until=4000, seed=101, trace=False)
    cfg_trace = ChainConfig(num_hops=2, until=4000, seed=101, trace=True)
    res_stream = run_repeater_chain(cfg_stream)
    res_trace = run_repeater_chain(cfg_trace)

    assert "samples" not in res_stream["fidelity"]
    assert "samples" not in res_stream["latency_ticks"]
    assert len(res_trace["fidelity"]["samples"]) == res_trace["delivered_pairs"]
    assert len(res_trace["latency_ticks"]["samples"]) == res_trace["delivered_pairs"]
    assert np.isclose(res_stream["fidelity"]["mean"], res_trace["fidelity"]["mean"], atol=1e-12)


def test_chain_scaling_benchmark_reports_wall_time_peak_ram_and_dominant_phase():
    report = run_chain_scaling_benchmark(hops_list=(1, 2, 4), until=6000, seed=101, memory_cutoff=400)
    assert len(report["rows"]) == 3
    for row in report["rows"]:
        assert row["wall_time_s"] >= 0.0
        assert row["peak_ram_kib"] > 0.0
        assert row["profile"]["dominant"] in ("registers", "events", "diagnostics")
