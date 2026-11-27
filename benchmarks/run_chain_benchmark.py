"""Step 2 scaling benchmark: N-hop repeater chain wall time, peak RAM, and phase breakdown.

Usage:
    python benchmarks/run_chain_benchmark.py
    python benchmarks/run_chain_benchmark.py --hops 1,2,4,8 --until 40000 --cutoff 400 --json
"""

import argparse
import ctypes
import gc
import json
import os
import sys
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from damn_q.chain import ChainConfig, run_repeater_chain


def _process_peak_rss_mib():
    """Return process peak resident set size in MiB (Windows & POSIX)."""
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        handle = k32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return pmc.PeakWorkingSetSize / (1024.0 * 1024.0)
        return 0.0
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS returns bytes; Linux returns KiB
        if sys.platform == "darwin":
            return usage / (1024.0 * 1024.0)
        return usage / 1024.0
    except Exception:
        return 0.0


def run_chain_scaling_benchmark(
    hops_list=(1, 2, 4, 8),
    *,
    until=40000,
    seed=101,
    memory_cutoff=0.0,
    loss_p=0.2,
    channel_depolarization_p=0.005,
    memory_depolarization_p=0.0005,
    trace=False,
):
    rows = []
    for n_hops in hops_list:
        cfg = ChainConfig(
            num_hops=n_hops,
            until=until,
            seed=seed,
            loss_p=loss_p,
            channel_depolarization_p=channel_depolarization_p,
            memory_depolarization_p=memory_depolarization_p,
            memory_cutoff=memory_cutoff,
            trace=trace,
            profile=True,
        )
        gc.collect()
        tracemalloc.start()
        try:
            res = run_repeater_chain(cfg)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        res["peak_ram_kib"] = peak_bytes / 1024.0
        res["process_peak_rss_mib"] = _process_peak_rss_mib()
        rows.append(res)

    return {
        "until_ticks": until,
        "seed": seed,
        "memory_cutoff": memory_cutoff,
        "trace": trace,
        "rows": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run DAMN-Q Step 2 N-hop repeater scaling benchmark.")
    parser.add_argument("--hops", default="1,2,4,8", help="Comma-separated chain lengths (default: 1,2,4,8).")
    parser.add_argument("--until", type=int, default=40000, help="Simulation horizon in ticks (default: 40000).")
    parser.add_argument("--seed", type=int, default=101, help="RNG seed (default: 101).")
    parser.add_argument("--cutoff", type=float, default=0.0, help="Memory cutoff in ticks (0 = none).")
    parser.add_argument("--trace", action="store_true", help="Retain full sample traces instead of O(1) streaming.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    hops_list = [int(x.strip()) for x in args.hops.split(",") if x.strip()]
    if not hops_list or any(h < 1 for h in hops_list):
        parser.error("--hops must be a comma-separated list of integers >= 1.")

    report = run_chain_scaling_benchmark(
        hops_list=hops_list,
        until=args.until,
        seed=args.seed,
        memory_cutoff=args.cutoff,
        trace=args.trace,
    )

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0

    print(
        f"Chain Scaling Benchmark (until={args.until} ticks, seed={args.seed}, "
        f"cutoff={args.cutoff}, trace={args.trace})"
    )
    print(
        f"{'Hops':>4} | {'Pairs/s':>9} | {'Mean F':>8} | {'Cutoffs':>7} | "
        f"{'Wall (s)':>8} | {'Peak KiB':>9} | {'Proc MiB':>8} | {'Dominant':>11}"
    )
    print("-" * 85)
    for r in report["rows"]:
        f_mean = r["fidelity"]["mean"] if r["fidelity"] else float("nan")
        dom = r["profile"]["dominant"]
        print(
            f"{r['num_hops']:>4} | {r['delivered_pairs_per_s']:>9.1f} | {f_mean:>8.4f} | "
            f"{r['cutoff_expiries']:>7} | {r['wall_time_s']:>8.3f} | "
            f"{r['peak_ram_kib']:>9.1f} | {r['process_peak_rss_mib']:>8.1f} | {dom:>11}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
