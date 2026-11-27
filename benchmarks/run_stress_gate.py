"""Step 2 backend stress-testing gate.

Runs three independent checks in fresh subprocesses per configuration:
  1. Hop-count scaling sweep: 8, 16, 32, 64 hops
  2. Duration / retention sweep: fixed topology (4 hops, high loss, frequent expiries)
     at 1x and 10x horizon in streaming mode to detect O(T) memory or queue growth
  3. Streaming vs trace invariance check: verifies trace=True leaves seeded results identical

Usage:
    python benchmarks/run_stress_gate.py
    python benchmarks/run_stress_gate.py --hops 8,16,32,64 --hop-until 20000 --dur-base 20000 --json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.run_chain_benchmark import run_chain_scaling_benchmark


def run_stress_gate(
    hops_list=(8, 16, 32, 64),
    *,
    hop_until=20000,
    dur_hops=4,
    dur_base=20000,
    dur_mult=10,
    seed=101,
    loss_p=0.5,
    memory_cutoff=400.0,
):
    # 1. Hop-count sweep (high loss + cutoff, isolated process per hop count)
    hop_sweep = run_chain_scaling_benchmark(
        hops_list=hops_list,
        until=hop_until,
        seed=seed,
        memory_cutoff=memory_cutoff,
        loss_p=loss_p,
        trace=False,
        isolate_processes=True,
    )["rows"]

    # 2. 1x vs 10x duration retention sweep (fixed topology, streaming mode)
    dur_1x = run_chain_scaling_benchmark(
        hops_list=(dur_hops,),
        until=dur_base,
        seed=seed,
        memory_cutoff=memory_cutoff,
        loss_p=loss_p,
        trace=False,
        isolate_processes=True,
    )["rows"][0]
    dur_10x = run_chain_scaling_benchmark(
        hops_list=(dur_hops,),
        until=dur_base * dur_mult,
        seed=seed,
        memory_cutoff=memory_cutoff,
        loss_p=loss_p,
        trace=False,
        isolate_processes=True,
    )["rows"][0]

    # 3. Streaming vs trace invariance (same seed, high loss + expiries)
    tr_off = run_chain_scaling_benchmark(
        hops_list=(dur_hops,),
        until=dur_base,
        seed=seed,
        memory_cutoff=memory_cutoff,
        loss_p=loss_p,
        trace=False,
        isolate_processes=True,
    )["rows"][0]
    tr_on = run_chain_scaling_benchmark(
        hops_list=(dur_hops,),
        until=dur_base,
        seed=seed,
        memory_cutoff=memory_cutoff,
        loss_p=loss_p,
        trace=True,
        isolate_processes=True,
    )["rows"][0]

    trace_invariant = (
        tr_off["delivered_pairs"] == tr_on["delivered_pairs"]
        and tr_off["attempts"] == tr_on["attempts"]
        and tr_off["swaps_completed"] == tr_on["swaps_completed"]
        and tr_off["cutoff_expiries"] == tr_on["cutoff_expiries"]
        and (
            tr_off["delivered_pairs"] == 0
            or abs(tr_off["fidelity"]["mean"] - tr_on["fidelity"]["mean"]) < 1e-12
        )
    )

    return {
        "hop_sweep": hop_sweep,
        "duration_retention": {
            "hops": dur_hops,
            "base_until": dur_base,
            "mult": dur_mult,
            "run_1x": dur_1x,
            "run_10x": dur_10x,
        },
        "trace_invariance": {
            "passed": trace_invariant,
            "stream_delivered": tr_off["delivered_pairs"],
            "trace_delivered": tr_on["delivered_pairs"],
            "stream_peak_kib": tr_off["peak_ram_kib"],
            "trace_peak_kib": tr_on["peak_ram_kib"],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run DAMN-Q Step 2 backend stress gate.")
    parser.add_argument("--hops", default="8,16,32,64", help="Comma-separated hop counts (default: 8,16,32,64).")
    parser.add_argument("--hop-until", type=int, default=20000, help="Horizon for hop sweep (default: 20000).")
    parser.add_argument("--dur-hops", type=int, default=4, help="Fixed hop count for duration sweep (default: 4).")
    parser.add_argument("--dur-base", type=int, default=20000, help="Base horizon for 1x vs 10x sweep (default: 20000).")
    parser.add_argument("--loss-p", type=float, default=0.5, help="Per-photon loss probability (default: 0.5).")
    parser.add_argument("--cutoff", type=float, default=400.0, help="Memory cutoff in ticks (default: 400.0).")
    parser.add_argument("--seed", type=int, default=101, help="RNG seed (default: 101).")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    hops_list = [int(x.strip()) for x in args.hops.split(",") if x.strip()]
    report = run_stress_gate(
        hops_list=hops_list,
        hop_until=args.hop_until,
        dur_hops=args.dur_hops,
        dur_base=args.dur_base,
        seed=args.seed,
        loss_p=args.loss_p,
        memory_cutoff=args.cutoff,
    )

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0

    print("=== 1. Hop-Count Sweep (fresh process per hop count) ===")
    print(
        f"{'Hops':>4} | {'Deliv':>5} | {'Expir':>5} | {'LiveQ':>5} | {'CancQ':>5} | "
        f"{'Wall (s)':>8} | {'Peak KiB':>9} | {'Proc MiB':>8} | {'Dominant':>10}"
    )
    print("-" * 82)
    for r in report["hop_sweep"]:
        print(
            f"{r['num_hops']:>4} | {r['delivered_pairs']:>5} | {r['cutoff_expiries']:>5} | "
            f"{r['live_queue_len']:>5} | {r['cancelled_queue_len']:>5} | "
            f"{r['wall_time_s']:>8.3f} | {r['peak_ram_kib']:>9.1f} | "
            f"{r['process_peak_rss_mib']:>8.1f} | {r['profile']['dominant']:>10}"
        )

    print("\n=== 2. Duration Retention Sweep (1x vs 10x, streaming mode) ===")
    d = report["duration_retention"]
    for label, r in (("1x", d["run_1x"]), (f"{d['mult']}x", d["run_10x"])):
        print(
            f"{label:>3} (until={r['until_ticks']:>6}): deliv={r['delivered_pairs']:>4}, "
            f"expiries={r['cutoff_expiries']:>5}, liveQ={r['live_queue_len']:>3}, "
            f"cancQ={r['cancelled_queue_len']:>3}, wall={r['wall_time_s']:.3f}s, "
            f"peak_kib={r['peak_ram_kib']:.1f}, proc_mib={r['process_peak_rss_mib']:.1f}"
        )

    print("\n=== 3. Streaming vs Trace Invariance ===")
    ti = report["trace_invariance"]
    print(
        f"passed={ti['passed']} (stream_delivered={ti['stream_delivered']}, "
        f"trace_delivered={ti['trace_delivered']}, "
        f"stream_peak_kib={ti['stream_peak_kib']:.1f}, trace_peak_kib={ti['trace_peak_kib']:.1f})"
    )
    return 0 if ti["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
