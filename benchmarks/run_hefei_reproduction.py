"""Hefei optical entanglement swapping reproduction (Sun et al., Phys. Rev. A 95, 032306, 2017).

Drives a click-driven, time-gated `Optical_bsm` at Eve from independently specified
physical inputs:
  - Alice -> Eve fibre: 14.7 km, 3 dB loss (74 us one-way propagation)
  - Bob -> Eve fibre:   10.6 km, 6 dB loss (53 us one-way + 21 us synchronization offset)
  - Probabilistic pulsed sources (`emission_p`)
  - Detector efficiency (`detector_efficiency`), dark-count rate (`dark_count_rate`),
    Gaussian timing jitter (`jitter_std`), coincidence window (`coincidence_window`)
  - Linear-optical BSM efficiency (`0.5`) and two-photon HOM visibility (`visibility`)

Compares simulated true heralds, false (accidental) heralds, raw remote fidelity,
and background-corrected fidelity against analytic predictions from the same inputs.

Usage:
    python -m benchmarks.run_hefei_reproduction
    python -m benchmarks.run_hefei_reproduction --seeds 10 --trials 5000 --json
"""

import argparse
import json
import math
import sys

import numpy as np

from Auto_connector import connect
from Hardware_models import fibre_loss_p
from Optical_bsm import Optical_bsm
from Pauli_corrector import Pauli_corrector
from Simulation import Simulation
from Source import Source
from States import phi_plus
from Emitter import Handler


def analytic_hefei_prediction(
    *,
    trials,
    emission_p,
    loss_a_db,
    loss_b_db,
    detector_efficiency,
    linear_optical_efficiency,
    coincidence_window,
    jitter_std,
    visibility,
):
    """Analytic expected true heralds and background-free fidelity from independent inputs."""
    t_a = 1.0 - fibre_loss_p(0.0, 0.0, loss_a_db)
    t_b = 1.0 - fibre_loss_p(0.0, 0.0, loss_b_db)
    p_in_window = 1.0 if jitter_std == 0.0 else math.erf(coincidence_window / (2.0 * jitter_std))
    p_true_per_trial = (
        (emission_p ** 2)
        * t_a
        * t_b
        * (detector_efficiency ** 2)
        * linear_optical_efficiency
        * p_in_window
    )
    expected_true_heralds = trials * p_true_per_trial
    expected_true_fidelity = (1.0 + 3.0 * visibility) / 4.0
    return {
        "p_in_window": p_in_window,
        "p_true_per_trial": p_true_per_trial,
        "expected_true_heralds": expected_true_heralds,
        "expected_true_fidelity": expected_true_fidelity,
    }


def run_hefei_trial_sim(
    *,
    seed=42,
    trials=2000,
    period=20,
    emission_p=0.5,
    loss_a_db=3.0,
    loss_b_db=6.0,
    detector_efficiency=0.7,
    dark_count_rate=1e-4,
    coincidence_window=1.0,
    jitter_std=0.4,
    visibility=0.80,
    linear_optical_efficiency=0.5,
):
    """Run synchronized optical entanglement swapping with click-driven `Optical_bsm`.

    Alice's and Bob's local photons are stored in lightweight attempt-indexed slots;
    when Eve's `Optical_bsm` emits a herald, the corresponding remote pair's fidelity
    to |Phi+> (after Pauli correction) is evaluated on the exact `Register`.
    """
    sim = Simulation(seed=seed)
    src_a = Source("alice_source", period, 2, sim=sim, emission_p=emission_p)
    src_b = Source("bob_source", period, 2, sim=sim, emission_p=emission_p)
    bsm = Optical_bsm(
        "eve_bsm",
        delay=1,
        coincidence_window=coincidence_window,
        jitter_std=jitter_std,
        detector_efficiency=detector_efficiency,
        dark_count_rate=dark_count_rate,
        visibility=visibility,
        linear_optical_efficiency=linear_optical_efficiency,
        sim=sim,
    )

    # Local remote photons held briefly until Eve's herald decision
    local_a = {}
    local_b = {}

    def on_local_a(q):
        local_a[q.attempt_id] = q

    def on_local_b(q):
        local_b[q.attempt_id] = q

    h_a = Handler(on_local_a, sim=sim, kind="quantum", max_connections=1)
    h_b = Handler(on_local_b, sim=sim, kind="quantum", max_connections=1)

    connect(src_a.out_ch_1, h_a, delay=0, sim=sim)
    connect(src_b.out_ch_2, h_b, delay=0, sim=sim)

    # Synchronized arrival at Eve: 74 ticks on Alice (14.7 km, 3 dB) and
    # 53 + 21 = 74 ticks on Bob (10.6 km, 6 dB + 21 tick synchronization offset).
    connect(
        src_a.out_ch_2,
        bsm.ch_in_q_1,
        delay=74,
        loss_p=fibre_loss_p(0.0, 0.0, loss_a_db),
        sim=sim,
    )
    connect(
        src_b.out_ch_1,
        bsm.ch_in_q_2,
        delay=74,
        loss_p=fibre_loss_p(0.0, 0.0, loss_b_db),
        sim=sim,
    )

    from Operators import x_operator, z_operator

    fidelities = []
    true_herald_fidelities = []

    def on_herald(outcome):
        # Identify the most recent synchronized attempt that arrived at Eve (delay 74 + bsm delay 1)
        t_emit = sim.time - 75
        attempt = int(round(t_emit / period))
        qa = local_a.pop(attempt, None)
        qb = local_b.pop(attempt, None)
        if qa is not None and qb is not None and qa.register is not None and qa.register is qb.register:
            if outcome[1] == "1":
                qb.apply_unitary(x_operator)
            if outcome[0] == "1":
                qb.apply_unitary(z_operator)
            joint = qa.register.reduced_density_matrix([qa, qb])
            f_val = float(np.real(np.trace(phi_plus @ joint)))
            fidelities.append(f_val)
            true_herald_fidelities.append(f_val)
        else:
            # False / accidental herald: unentangled or missing remote pair -> random fidelity 0.25
            fidelities.append(0.25)
        if qa is not None:
            qa.state = None
        if qb is not None:
            qb.state = None

    bsm.ch_out_c_1.add_handler(Handler(on_herald, sim=sim, kind="classical"))

    until = trials * period + 100
    sim.run(until)

    mean_raw_f = (sum(fidelities) / len(fidelities)) if fidelities else None
    mean_true_f = (sum(true_herald_fidelities) / len(true_herald_fidelities)) if true_herald_fidelities else None
    return {
        "seed": seed,
        "trials": trials,
        "heralds": bsm.counter,
        "true_heralds": bsm.true_heralds,
        "false_heralds": bsm.false_heralds,
        "ambiguous_patterns": bsm.ambiguous_patterns,
        "missed_detections": bsm.missed_detections,
        "expired_photons": bsm.expired_photons,
        "raw_mean_fidelity": mean_raw_f,
        "true_herald_mean_fidelity": mean_true_f,
    }


def _summary(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "std": None}
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1) if len(vals) > 1 else 0.0
    return {"mean": m, "std": math.sqrt(var)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hefei optical BSM experimental reproduction.")
    parser.add_argument("--seeds", type=int, default=5, help="number of seeds (1..N)")
    parser.add_argument("--trials", type=int, default=4000, help="synchronized emission trials per seed")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)

    params = dict(
        trials=args.trials,
        emission_p=0.5,
        loss_a_db=3.0,
        loss_b_db=6.0,
        detector_efficiency=0.7,
        dark_count_rate=1e-4,
        coincidence_window=1.0,
        jitter_std=0.4,
        visibility=0.80,
        linear_optical_efficiency=0.5,
    )
    analytic = analytic_hefei_prediction(
        trials=params["trials"],
        emission_p=params["emission_p"],
        loss_a_db=params["loss_a_db"],
        loss_b_db=params["loss_b_db"],
        detector_efficiency=params["detector_efficiency"],
        linear_optical_efficiency=params["linear_optical_efficiency"],
        coincidence_window=params["coincidence_window"],
        jitter_std=params["jitter_std"],
        visibility=params["visibility"],
    )
    runs = [run_hefei_trial_sim(seed=s, **params) for s in range(1, args.seeds + 1)]
    report = {
        "params": params,
        "analytic": analytic,
        "simulated": {
            "true_heralds": _summary([r["true_heralds"] for r in runs]),
            "false_heralds": _summary([r["false_heralds"] for r in runs]),
            "raw_mean_fidelity": _summary([r["raw_mean_fidelity"] for r in runs]),
            "true_herald_mean_fidelity": _summary([r["true_herald_mean_fidelity"] for r in runs]),
        },
        "runs": runs,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        sim = report["simulated"]
        print(f"Hefei Optical BSM Reproduction ({args.seeds} seeds x {args.trials} trials)")
        print(f"  Analytic true heralds:  {analytic['expected_true_heralds']:.1f} (P_in_window={analytic['p_in_window']:.4f})")
        print(f"  Simulated true heralds: {sim['true_heralds']['mean']:.1f} +/- {sim['true_heralds']['std']:.1f}")
        print(f"  Simulated false heralds:{sim['false_heralds']['mean']:.2f} +/- {sim['false_heralds']['std']:.2f}")
        print(f"  Analytic true fidelity: {analytic['expected_true_fidelity']:.4f}")
        print(f"  Simulated true fidelity:{sim['true_herald_mean_fidelity']['mean']:.4f} +/- {sim['true_herald_mean_fidelity']['std']:.4f}")
        print(f"  Simulated raw fidelity: {sim['raw_mean_fidelity']['mean']:.4f} +/- {sim['raw_mean_fidelity']['std']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
