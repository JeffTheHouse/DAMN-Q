"""Multi-seed runner and analytic verifier for the frozen Step 1 reference benchmark.

Usage:
    python benchmarks/run_reference_benchmark.py
    python benchmarks/run_reference_benchmark.py --seeds 10 --until 40000 --json
"""

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from damn_q.runner import load_experiment, run_experiment

REF_JSON = Path(__file__).resolve().parent / "repeater_3node_ref.json"
DEFAULT_SEEDS = list(range(101, 111))


def analytic_lossless_prediction(doc):
    """Closed-form delivery fidelity and latency when `loss_p = 0` on all four links."""
    link_delays = {}
    link_depols = {}
    for c in doc["connections"]:
        key = (c["from"]["component"], c["to"]["component"])
        link_delays[key] = c.get("delay", 0)
        link_depols[key] = c.get("depolarization_p", 0.0)

    d = link_delays[("source_a", "memory_a_1")]
    p_ch = link_depols[("source_a", "memory_a_1")]

    mem_p = {
        comp["id"]: comp["params"]["depolarization_p"]
        for comp in doc["components"]
        if comp["type"] == "quantum_memory"
    }
    swap_delay = next(
        comp["params"]["delay"]
        for comp in doc["components"]
        if comp["type"] == "entanglement_swapper"
    )
    period = next(
        comp["params"]["delay"]
        for comp in doc["components"]
        if comp["type"] == "source"
    )
    tick_s = doc["run"]["tick_duration_s"]

    # Exact storage ticks when both links succeed simultaneously on every attempt:
    #   arrival at memories:        t_arr = k*T + d
    #   peer herald received:       t_her = t_arr + 1 + d   -> t_mid = d + 1
    #   swap outcome at endpoints:  t_end_rel = t_her + swap_delay + d -> t_end = 2*d + 1 + swap_delay
    t_mid = d + 1
    t_end = 2 * d + 1 + swap_delay
    latency_ticks = 3 * d + 1 + swap_delay

    prod = (1.0 - 4.0 * p_ch / 3.0) ** 4
    prod *= (1.0 - 4.0 * mem_p["memory_a_1"] / 3.0) ** t_end
    prod *= (1.0 - 4.0 * mem_p["memory_a_2"] / 3.0) ** t_mid
    prod *= (1.0 - 4.0 * mem_p["memory_b_1"] / 3.0) ** t_mid
    prod *= (1.0 - 4.0 * mem_p["memory_b_2"] / 3.0) ** t_end
    fidelity = (1.0 + 3.0 * prod) / 4.0

    return {
        "fidelity": float(fidelity),
        "latency_ticks": float(latency_ticks),
        "latency_s": float(latency_ticks * tick_s),
        "asymptotic_lossless_rate_per_s": float(1.0 / (period * tick_s)),
        "t_mid_ticks": int(t_mid),
        "t_end_ticks": int(t_end),
    }


def _summary_stats(values):
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=0)),
        "min": float(np.min(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
    }


def run_reference_benchmark(seeds=None, until=None, ref_path=REF_JSON):
    """Execute the analytic lossless check plus the multi-seed lossy benchmark."""
    seeds = list(DEFAULT_SEEDS if seeds is None else seeds)
    if not seeds:
        raise ValueError("seeds must be a non-empty sequence.")
    base_doc = load_experiment(ref_path)
    if until is not None:
        base_doc = copy.deepcopy(base_doc)
        base_doc["run"]["until"] = until

    tick_s = base_doc["run"]["tick_duration_s"]

    # 1. Lossless analytic check (single deterministic run over 10 cycles)
    lossless_doc = copy.deepcopy(base_doc)
    lossless_doc["run"]["until"] = 2200
    lossless_doc["run"]["seed"] = seeds[0]
    for conn in lossless_doc["connections"]:
        if "loss_p" in conn:
            conn["loss_p"] = 0.0

    analytic = analytic_lossless_prediction(lossless_doc)
    lossless_res = run_experiment(lossless_doc)
    ll_m = lossless_res["measurements"][0]
    lossless_check = {
        "expected_fidelity": analytic["fidelity"],
        "simulated_fidelity": ll_m["mean_fidelity"],
        "fidelity_abs_err": abs(ll_m["mean_fidelity"] - analytic["fidelity"]),
        "expected_latency_ticks": analytic["latency_ticks"],
        "simulated_latency_ticks": ll_m["mean_latency"],
        "pairs_delivered": ll_m["pairs"],
        "all_shared_register": ll_m["all_shared_register"],
        "passed": (
            abs(ll_m["mean_fidelity"] - analytic["fidelity"]) < 1e-12
            and abs(ll_m["mean_latency"] - analytic["latency_ticks"]) < 1e-12
            and ll_m["all_shared_register"] is True
        ),
    }

    # 2. Multi-seed lossy reference runs
    per_seed = []
    all_fidelities = []
    all_latencies_ticks = []
    rates_per_s = []
    t0 = time.perf_counter()

    for seed in seeds:
        res = run_experiment(base_doc, seed_override=seed)
        m = res["measurements"][0]
        rates_per_s.append(m["delivered_pairs_per_s"])
        all_fidelities.extend(m["fidelities"])
        all_latencies_ticks.extend(m["latencies"])
        per_seed.append(
            {
                "seed": seed,
                "pairs": m["pairs"],
                "delivered_pairs_per_s": m["delivered_pairs_per_s"],
                "mean_fidelity": m["mean_fidelity"],
                "mean_latency_ticks": m["mean_latency"],
                "mean_latency_s": m["mean_latency_s"],
                "unmatched_a": m["unmatched_a"],
                "unmatched_b": m["unmatched_b"],
                "all_shared_register": m["all_shared_register"],
                "attempts_a": res["metrics"]["sources"]["source_a"]["attempts"],
                "attempts_b": res["metrics"]["sources"]["source_b"]["attempts"],
                "heralded_a": res["metrics"]["memories"]["memory_a_1"]["heralded_pairs"],
                "heralded_b": res["metrics"]["memories"]["memory_b_1"]["heralded_pairs"],
                "swaps_completed": res["metrics"]["swappers"]["es"]["completed"],
                "swaps_rejected": res["metrics"]["swappers"]["es"]["rejected"],
            }
        )

    wall_s = time.perf_counter() - t0
    all_latencies_us = [v * tick_s * 1e6 for v in all_latencies_ticks]

    return {
        "benchmark": base_doc["name"],
        "simulator_version": lossless_res["simulator_version"],
        "schema_version": lossless_res["schema_version"],
        "until_ticks": base_doc["run"]["until"],
        "tick_duration_s": tick_s,
        "simulated_duration_s": base_doc["run"]["until"] * tick_s,
        "seeds": seeds,
        "wall_time_s": wall_s,
        "analytic_lossless": analytic,
        "lossless_check": lossless_check,
        "aggregate": {
            "total_pairs": len(all_fidelities),
            "delivered_pairs_per_s": _summary_stats(rates_per_s),
            "fidelity_at_delivery": _summary_stats(all_fidelities),
            "latency_ticks": _summary_stats(all_latencies_ticks),
            "latency_us": _summary_stats(all_latencies_us),
        },
        "per_seed": per_seed,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the frozen Step 1 DAMN-Q reference benchmark.")
    parser.add_argument("--seeds", type=int, default=len(DEFAULT_SEEDS), help="Number of seeds starting at 101.")
    parser.add_argument("--until", type=int, default=None, help="Override simulation horizon (ticks).")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    if args.seeds < 1:
        parser.error("--seeds must be >= 1.")

    seeds = list(range(101, 101 + args.seeds))
    report = run_reference_benchmark(seeds=seeds, until=args.until)
    exit_code = 0 if report["lossless_check"]["passed"] else 1

    if args.as_json:
        print(json.dumps(report, indent=2))
        return exit_code

    lc = report["lossless_check"]
    agg = report["aggregate"]
    print(f"Benchmark: {report['benchmark']} (DAMN-Q v{report['simulator_version']})")
    print(
        f"Lossless analytic check: {'PASS' if lc['passed'] else 'FAIL'} | "
        f"F={lc['simulated_fidelity']:.12f} (expected {lc['expected_fidelity']:.12f}, err={lc['fidelity_abs_err']:.2e}), "
        f"L={lc['simulated_latency_ticks']:.1f} ticks"
    )
    print(
        f"Lossy multi-seed ({len(seeds)} seeds x {report['simulated_duration_s']*1e3:.1f} ms, "
        f"wall={report['wall_time_s']:.2f}s):"
    )
    r = agg["delivered_pairs_per_s"]
    f = agg["fidelity_at_delivery"]
    lat = agg["latency_us"]
    print(f"  Delivered pairs/s : mean={r['mean']:.1f} +/- {r['std']:.1f} (min={r['min']:.1f}, max={r['max']:.1f})")
    if f is None:
        print("  Delivery fidelity : unavailable (0 delivered pairs)")
    else:
        print(f"  Delivery fidelity : mean={f['mean']:.6f} +/- {f['std']:.6f} (p50={f['p50']:.6f}, min={f['min']:.6f}, max={f['max']:.6f})")
    if lat is None:
        print("  Delivery latency  : unavailable (0 delivered pairs)")
    else:
        print(f"  Delivery latency  : mean={lat['mean']:.1f} us (p50={lat['p50']:.1f} us, p95={lat['p95']:.1f} us, min={lat['min']:.1f} us, max={lat['max']:.1f} us)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
