"""Delft-Eindhoven processing-node cross-simulator benchmark (Avis et al., 2023).

Compares three matched regimes on the published 4-segment Dutch fibre route
(83 km / 19 km / 75 km / 50 km, 0.2 dB/km):
  1. Ideal processing-node baseline (verifies F = 1.0 and analytic sequential rate)
  2. NV-like hardware noise without cutoff (attempt-induced dephasing + T1/T2 + gate noise)
  3. Same hardware noise with a memory cutoff (demonstrates fidelity gain vs rate cost)

Usage:
    python -m benchmarks.run_delft_eindhoven_benchmark
    python -m benchmarks.run_delft_eindhoven_benchmark --seeds 5 --until-s 20 --json
"""

import argparse
import json
import math
import sys

from damn_q.processing_node import ProcessingNodeConfig, run_processing_node


def _summary(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "std": None}
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1) if len(vals) > 1 else 0.0
    return {"mean": m, "std": math.sqrt(var)}


def run_delft_eindhoven_study(*, seeds=range(1, 6), until_s=20.0):
    seed_list = list(seeds)
    scenarios = {
        "ideal": dict(
            until_s=until_s,
            elementary_fidelity=1.0,
            gate_depol_p=0.0,
            attempt_dephasing_p=0.0,
            storage_t1_s=0.0,
            storage_t2_s=0.0,
            bsm_visibility=1.0,
            max_attempts_cutoff=0,
        ),
        "hardware_no_cutoff": dict(
            until_s=until_s,
            elementary_fidelity=0.95,
            gate_depol_p=0.01,
            attempt_dephasing_p=0.002,
            storage_t1_s=10.0,
            storage_t2_s=1.0,
            bsm_visibility=0.98,
            max_attempts_cutoff=0,
        ),
        "hardware_with_cutoff": dict(
            until_s=until_s,
            elementary_fidelity=0.95,
            gate_depol_p=0.01,
            attempt_dephasing_p=0.002,
            storage_t1_s=10.0,
            storage_t2_s=1.0,
            bsm_visibility=0.98,
            max_attempts_cutoff=150,
        ),
    }

    report = {"seeds": seed_list, "until_s": until_s, "scenarios": {}}
    for name, kwargs in scenarios.items():
        runs = [run_processing_node(ProcessingNodeConfig(seed=s, **kwargs)) for s in seed_list]
        report["scenarios"][name] = {
            "analytic_no_cutoff_rate_hz": runs[0]["analytic_no_cutoff_rate_hz"],
            "delivered_pairs_per_s": _summary([r["delivered_pairs_per_s"] for r in runs]),
            "mean_fidelity": _summary([r["fidelity"]["mean"] for r in runs]),
            "cutoffs": _summary([r["cutoffs"] for r in runs]),
        }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Delft-Eindhoven processing-node benchmark.")
    parser.add_argument("--seeds", type=int, default=5, help="number of seeds (1..N)")
    parser.add_argument("--until-s", type=float, default=20.0, help="simulated duration in seconds")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)

    report = run_delft_eindhoven_study(seeds=range(1, args.seeds + 1), until_s=args.until_s)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Delft-Eindhoven Processing-Node Benchmark ({args.seeds} seeds, until={args.until_s}s)")
        print(f"{'scenario':<22} {'rate (Hz)':>18} {'mean fidelity':>18} {'cutoffs':>14}")
        print("-" * 76)
        for name, s in report["scenarios"].items():
            r = s["delivered_pairs_per_s"]
            f = s["mean_fidelity"]
            c = s["cutoffs"]
            f_str = f"{f['mean']:.4f} +/- {f['std']:.4f}" if f["mean"] is not None else "n/a"
            print(
                f"{name:<22} {r['mean']:>7.2f} +/- {r['std']:<6.2f} "
                f"{f_str:>18} {c['mean']:>6.1f} +/- {c['std']:<5.1f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
