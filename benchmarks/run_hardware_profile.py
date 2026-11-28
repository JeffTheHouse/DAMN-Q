"""Hardware-noise profile: Z-basis correlation, delivery fidelity, and false coincidences.

Reports three calibrated comparisons across seeds:
  1. Tutorial Z-basis repeater (`repeater_tutorial_z.json` vs
     `repeater_tutorial_hardware.json`): pair-ID-matched coincidences and
     anticorrelations, plus windowed physical coincidences (true vs accidental).
  2. Delivery fidelity on a 2-hop repeater chain (`damn_q.chain`): ideal vs
     Step 3 hardware profile (10 km fibre, Werner F=0.95, T1=200 / T2=150,
     BSM visibility 0.9, detector efficiency 0.8).
  3. False-coincidence check with 100% source-link loss and dark counts enabled:
     verifies pair-ID-matched outcomes remain 0 while windowed accidental
     coincidences follow the expected rate.

Usage:
    python -m benchmarks.run_hardware_profile
    python -m benchmarks.run_hardware_profile --seeds 10 --json
"""

import argparse
import copy
import json
import math
import sys
from pathlib import Path

from damn_q.chain import ChainConfig, run_repeater_chain
from damn_q.runner import load_experiment, run_experiment

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
    coinc = result["metrics"]["readers_coincidences"]["reader"]
    coincidences = reader["00"] + reader["11"]
    anticorrelations = reader["01"] + reader["10"]
    total = coincidences + anticorrelations
    return {
        "coincidences": coincidences,
        "anticorrelations": anticorrelations,
        "total": total,
        "correlation_fraction": (coincidences / total) if total else None,
        "physical_coincidences": coinc["total"],
        "true_pair_coincidences": coinc["true_pair_coincidences"],
        "accidental_coincidences": coinc["accidental_coincidences"],
    }


def _chain_fidelity_profile(seeds):
    ideal_fids, ideal_rates = [], []
    hw_fids, hw_rates = [], []
    for s in seeds:
        r_ideal = run_repeater_chain(
            ChainConfig(
                num_hops=2,
                until=10000,
                seed=s,
                tick_duration_s=1e-5,
                attempt_period=20,
                link_delay=5,
                swap_delay=1,
                loss_p=0.0,
                channel_depolarization_p=0.0,
                memory_depolarization_p=0.0,
            )
        )
        r_hw = run_repeater_chain(
            ChainConfig(
                num_hops=2,
                until=10000,
                seed=s,
                tick_duration_s=1e-5,
                attempt_period=20,
                link_delay=0,
                swap_delay=1,
                loss_p=0.0,
                channel_depolarization_p=0.0,
                memory_depolarization_p=0.0,
                length_km=10.0,
                initial_fidelity=0.95,
                memory_t1_ticks=200.0,
                memory_t2_ticks=150.0,
                bsm_visibility=0.9,
                detector_efficiency=0.8,
            )
        )
        if r_ideal["fidelity"]["mean"] is not None:
            ideal_fids.append(r_ideal["fidelity"]["mean"])
        ideal_rates.append(r_ideal["delivered_pairs_per_s"])
        if r_hw["fidelity"]["mean"] is not None:
            hw_fids.append(r_hw["fidelity"]["mean"])
        hw_rates.append(r_hw["delivered_pairs_per_s"])
    return {
        "ideal": {
            "mean_fidelity": _summary(ideal_fids),
            "delivered_pairs_per_s": _summary(ideal_rates),
        },
        "hardware": {
            "mean_fidelity": _summary(hw_fids),
            "delivered_pairs_per_s": _summary(hw_rates),
        },
    }


def _false_coincidence_profile(seeds, *, dark_rate=0.05, until=1000):
    base = load_experiment(IDEAL_JSON)
    doc = copy.deepcopy(base)
    doc["run"]["until"] = until
    for c in doc["connections"]:
        if c["from"]["component"].startswith("source_"):
            c["loss_p"] = 1.0
    for comp in doc["components"]:
        if comp["type"] in ("measurer", "measurer_memory_paired"):
            comp["params"]["dark_count_rate"] = dark_rate

    pair_totals, accidentals = [], []
    for s in seeds:
        res = run_experiment(doc, seed_override=s)
        pair_totals.append(sum(res["readers"]["reader"].values()))
        accidentals.append(res["metrics"]["readers_coincidences"]["reader"]["accidental_coincidences"])
    return {
        "dark_count_rate": dark_rate,
        "until": until,
        "expected_accidental_mean": (dark_rate ** 2) * until,
        "pair_id_matched_total": _summary(pair_totals),
        "accidental_coincidences": _summary(accidentals),
    }


def profile_hardware(seeds=range(1, 11), ideal_path=IDEAL_JSON, hardware_path=HARDWARE_JSON):
    """Return per-experiment seed statistics for Z-basis, delivery fidelity, and dark counts."""
    seed_list = list(seeds)
    report = {"seeds": seed_list, "experiments": {}}
    for label, path in (("ideal", ideal_path), ("hardware", hardware_path)):
        per_seed = [_counts_for_seed(path, s) for s in seed_list]
        fractions = [r["correlation_fraction"] for r in per_seed if r["correlation_fraction"] is not None]
        report["experiments"][label] = {
            "path": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
            "coincidences": _summary([r["coincidences"] for r in per_seed]),
            "anticorrelations": _summary([r["anticorrelations"] for r in per_seed]),
            "total": _summary([r["total"] for r in per_seed]),
            "correlation_fraction": _summary(fractions),
            "accidental_coincidences": _summary([r["accidental_coincidences"] for r in per_seed]),
            "per_seed": per_seed,
        }
    report["chain_delivery_fidelity"] = _chain_fidelity_profile(seed_list)
    report["false_coincidence_check"] = _false_coincidence_profile(seed_list)
    return report


def _fmt(stat, digits=1):
    if stat["mean"] is None:
        return "n/a"
    return f"{stat['mean']:.{digits}f} +/- {stat['std']:.{digits}f}"


def _format_table(report):
    lines = [f"Seeds: {len(report['seeds'])} ({report['seeds'][0]}..{report['seeds'][-1]})"]
    header = (
        f"{'experiment':<10} {'pair 00+11':>14} {'pair 01+10':>14} "
        f"{'pair total':>14} {'corr. frac':>16} {'accidental':>14}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for label, data in report["experiments"].items():
        lines.append(
            f"{label:<10} {_fmt(data['coincidences']):>14} {_fmt(data['anticorrelations']):>14} "
            f"{_fmt(data['total']):>14} {_fmt(data['correlation_fraction'], 3):>16} "
            f"{_fmt(data['accidental_coincidences']):>14}"
        )

    cf = report["chain_delivery_fidelity"]
    lines.append("")
    lines.append("2-hop repeater chain delivery fidelity (exact Register):")
    for label in ("ideal", "hardware"):
        lines.append(
            f"  {label:<10} fidelity={_fmt(cf[label]['mean_fidelity'], 4)}  "
            f"rate={_fmt(cf[label]['delivered_pairs_per_s'], 1)} pairs/s"
        )

    fc = report["false_coincidence_check"]
    lines.append("")
    lines.append(
        f"False-coincidence check (100% link loss, dark_rate={fc['dark_count_rate']}, "
        f"until={fc['until']}): pair_id_matched={_fmt(fc['pair_id_matched_total'], 1)}, "
        f"accidental={_fmt(fc['accidental_coincidences'], 2)} "
        f"(expected ~{fc['expected_accidental_mean']:.2f})"
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ideal vs hardware-noise profile.")
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
