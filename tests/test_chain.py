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
        assert row["process_peak_rss_mib"] > 0.0
        assert row["profile"]["dominant"] in ("registers", "events", "diagnostics")


def test_intermediate_swaps_wait_for_classical_notification_delay():
    """In a lossless 4-hop chain, downstream swap at node 2 must wait for swap_delay + link_delay."""
    from damn_q.chain import RepeaterChain

    cfg = ChainConfig(
        num_hops=4,
        until=1000,
        seed=1,
        attempt_period=200,
        link_delay=50,
        swap_delay=100,
        loss_p=0.0,
        channel_depolarization_p=0.0,
        memory_depolarization_p=0.0,
        memory_cutoff=0.0,
    )
    chain = RepeaterChain(cfg)
    swap_times = []
    orig_try_swap = chain._try_swap

    def _recording_try_swap(node):
        before = chain.swaps_completed
        orig_try_swap(node)
        if chain.swaps_completed > before:
            swap_times.append((node, chain.sim.time))

    chain._try_swap = _recording_try_swap
    res = chain.run()
    assert res["delivered_pairs"] >= 1
    # First wave: elementary heralds arrive at t = 200 + 50 + 1 + 50 = 301.
    # Nodes 1 and 3 swap at t = 301; node 2 must wait swap_delay (100) + 1 * link_delay (50) = 150 -> t = 451.
    first_wave = swap_times[:3]
    assert {n for n, _ in first_wave} == {1, 2, 3}
    by_node = dict(first_wave)
    assert by_node[1] == 301
    assert by_node[3] == 301
    assert by_node[2] == 451


def test_cutoff_applies_through_delivery():
    """A lossless 2-hop chain with 75-tick cutoff must NOT deliver pairs stored for 102 ticks."""
    cfg = ChainConfig(
        num_hops=2,
        until=2000,
        seed=101,
        attempt_period=200,
        link_delay=50,
        swap_delay=1,
        loss_p=0.0,
        channel_depolarization_p=0.0,
        memory_depolarization_p=0.0,
        memory_cutoff=75.0,
    )
    res = run_repeater_chain(cfg)
    assert res["delivered_pairs"] == 0
    assert res["cutoff_expiries"] > 0


def test_cancelled_cutoff_events_do_not_accumulate_with_horizon():
    """Cancelled cutoff handles are compacted so queue size stays bounded over long horizons."""
    from damn_q.chain import RepeaterChain

    base = dict(
        num_hops=2,
        seed=101,
        attempt_period=200,
        link_delay=50,
        swap_delay=1,
        loss_p=0.0,
        channel_depolarization_p=0.0,
        memory_depolarization_p=0.0,
        memory_cutoff=50000.0,
    )
    c_short = RepeaterChain(ChainConfig(**base, until=4000))
    c_short.run()
    c_long = RepeaterChain(ChainConfig(**base, until=40000))
    c_long.run()

    cancelled_short = sum(1 for _, _, h in c_short.sim._queue if h.cancelled)
    cancelled_long = sum(1 for _, _, h in c_long.sim._queue if h.cancelled)
    assert cancelled_short < 64
    assert cancelled_long < 64


def test_cutoff_exact_boundary_is_consistent_across_1hop_and_2hop():
    """At exact boundary (storage age == memory_cutoff), both 1-hop and 2-hop expire the pair."""
    # 1-hop: arrival at t0 + 50, herald/delivery at t0 + 101 -> storage age = 51 ticks.
    res_1hop = run_repeater_chain(
        ChainConfig(
            num_hops=1,
            until=1000,
            seed=101,
            attempt_period=200,
            link_delay=50,
            swap_delay=1,
            loss_p=0.0,
            channel_depolarization_p=0.0,
            memory_depolarization_p=0.0,
            memory_cutoff=51.0,
        )
    )
    # 2-hop: arrival at t0 + 50, delivery at t0 + 152 -> storage age = 102 ticks.
    res_2hop = run_repeater_chain(
        ChainConfig(
            num_hops=2,
            until=1000,
            seed=101,
            attempt_period=200,
            link_delay=50,
            swap_delay=1,
            loss_p=0.0,
            channel_depolarization_p=0.0,
            memory_depolarization_p=0.0,
            memory_cutoff=102.0,
        )
    )
    assert res_1hop["delivered_pairs"] == 0
    assert res_1hop["cutoff_expiries"] > 0
    assert res_2hop["delivered_pairs"] == 0
    assert res_2hop["cutoff_expiries"] > 0


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"attempt_period": 0},
        {"attempt_period": -10},
        {"attempt_period": float("nan")},
        {"attempt_period": float("inf")},
        {"until": float("inf")},
        {"memory_cutoff": float("nan")},
        {"link_delay": -1},
        {"swap_delay": -1},
        {"tick_duration_s": 0},
        {"loss_p": 1.5},
        {"channel_depolarization_p": -0.1},
        {"memory_depolarization_p": 1.1},
    ],
)
def test_chain_config_rejects_invalid_parameters(bad_kwargs):
    with pytest.raises(ValueError):
        run_repeater_chain(ChainConfig(**bad_kwargs))
