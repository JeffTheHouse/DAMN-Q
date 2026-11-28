"""Compare the ideal tutorial repeater with its hardware-noise variant across seeds.

Reports, per experiment, the mean and standard deviation over seeds of:
  - coincidences  = counts 00 + 11 (correlated outcomes in the Z basis)
  - anticorrelations = counts 01 + 10 (errors for an ideal |Phi+> pair)
  - total         = all matched outcome pairs
  - correlation_fraction = coincidences / total

Usage:
    python -m benchmarks.run_hardware_profile
    python -m benchmarks.run_hardware_profile --seeds 20 --json
"""

import argparse
import json
import math
import sys
from pathlib import Path

from damn_q.runner import run_experiment

ROOT = Path(__file__).resolve().parent.parent
IDEAL_JSON = ROOT / "experiments" / "repeater_tutorial_z.json"
HARDWARE_JSON = ROOT / "experiments" / "repeater_tutorial_hardware.json"


def _summary(values):
    n = len(values)
    if n == 0:
        return {"mean": None, "std": None}
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {"mean": mean, "std": math.sqrt(var)}


def _counts_for_seed(path, seed):
    result = run_experiment(path, seed_override=seed)
    reader = result["readers"]["reader"]
    coincidences = reader["00"] + reader["11"]
    anticorrelations = reader["01"] + reader["10"]
    total = coincidences + anticorrelations
    return {
        "coincidences": coincidences,
        "anticorrelations": anticorrelations,
        "total": total,
        "correlation_fraction": (coincidences / total) if total else None,
    }


def profile_hardware(seeds=range(1, 11), ideal_path=IDEAL_JSON, hardware_path=HARDWARE_JSON):
    """Return per-experiment seed statistics for the ideal and hardware variants."""
    report = {"seeds": list(seeds), "experiments": {}}
    for label, path in (("ideal", ideal_path), ("hardware", hardware_path)):
        per_seed = [_counts_for_seed(path, s) for s in seeds]
        fractions = [r["correlation_fraction"] for r in per_seed if r["correlation_fraction"] is not None]
        report["experiments"][label] = {
            "path": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
            "coincidences": _summary([r["coincidences"] for r in per_seed]),
            "anticorrelations": _summary([r["anticorrelations"] for r in per_seed]),
            "total": _summary([r["total"] for r in per_seed]),
            "correlation_fraction": _summary(fractions),
            "per_seed": per_seed,
        }
    return report


def _format_table(report):
    lines = [f"Seeds: {len(report['seeds'])} ({report['seeds'][0]}..{report['seeds'][-1]})"]
    header = f"{'experiment':<10} {'coincidences':>16} {'anticorrelations':>18} {'total':>14} {'corr. fraction':>18}"
    lines.append(header)
    lines.append("-" * len(header))
    for label, data in report["experiments"].items():
        def fmt(stat, digits=1):
            if stat["mean"] is None:
                return "n/a"
            return f"{stat['mean']:.{digits}f} +/- {stat['std']:.{digits}f}"
        frac = data["correlation_fraction"]
        frac_text = "n/a" if frac["mean"] is None else f"{frac['mean']:.3f} +/- {frac['std']:.3f}"
        lines.append(
            f"{label:<10} {fmt(data['coincidences']):>16} {fmt(data['anticorrelations']):>18} "
            f"{fmt(data['total']):>14} {frac_text:>18}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ideal vs hardware-noise tutorial profile.")
    parser.add_argument("--seeds", type=int, default=10, help="number of seeds (1..N)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)
    report = profile_hardware(seeds=range(1, args.seeds + 1))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_table(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
