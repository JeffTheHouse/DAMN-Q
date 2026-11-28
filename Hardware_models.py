"""Physical hardware models for DAMN-Q (Step 3).

Pure functions that turn physical parameters into the simulator's exact-backend
quantities: fibre loss and propagation delay, Werner-state initial Bell pairs,
elapsed-time amplitude damping and dephasing (T1/T2), and geometric sampling for
dark counts. The exact density-matrix backend applies the resulting channels.

This module lives at the repository root with the other simulator modules so
that component modules can import it without importing the `damn_q` package
(whose `__init__` loads the runner, which imports those component modules).

Conventions
-----------
- Times in the simulator are integer ticks. Fibre propagation is converted with
  `run.tick_duration_s` and rounded to whole ticks, because storage decoherence
  is evaluated on integer storage durations.
- A parameter value of 0 for T1/T2 disables that decoherence process.
"""

import math

import numpy as np

# Group velocity in standard single-mode fibre (about c / 1.5).
FIBRE_SPEED_KM_PER_S = 200_000.0

# Typical telecom fibre attenuation near 1550 nm.
DEFAULT_FIBRE_ATTENUATION_DB_PER_KM = 0.2

_PHI_PLUS_IDEAL = np.array(
    [[0.5, 0.0, 0.0, 0.5], [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.5, 0.0, 0.0, 0.5]]
)


def fibre_loss_p(length_km, attenuation_db_per_km=DEFAULT_FIBRE_ATTENUATION_DB_PER_KM, coupling_loss_db=0.0):
    """Probability that a photon is lost in a fibre segment with coupling loss.

    Transmission is 10^(-(alpha * L + c) / 10) for attenuation alpha (dB/km),
    length L (km), and fixed coupling loss c (dB).
    """
    if length_km < 0 or attenuation_db_per_km < 0 or coupling_loss_db < 0:
        raise ValueError("Fibre length, attenuation, and coupling loss must be non-negative.")
    total_db = attenuation_db_per_km * length_km + coupling_loss_db
    if total_db == 0.0:
        return 0.0
    return 1.0 - 10.0 ** (-total_db / 10.0)


def combined_loss_p(loss_p, extra_loss_p):
    """Compose two independent loss probabilities.

    Returns `loss_p` unchanged when `extra_loss_p` is 0, so existing experiments
    keep exactly the same floating-point threshold.
    """
    if extra_loss_p == 0.0:
        return loss_p
    return 1.0 - (1.0 - loss_p) * (1.0 - extra_loss_p)


def propagation_ticks(length_km, tick_duration_s):
    """Fibre propagation delay in whole simulation ticks (0 for zero length)."""
    if length_km == 0:
        return 0
    if length_km < 0:
        raise ValueError("Fibre length must be non-negative.")
    if tick_duration_s is None or tick_duration_s <= 0:
        raise ValueError("Fibre propagation requires run.tick_duration_s > 0.")
    seconds = length_km / FIBRE_SPEED_KM_PER_S
    # Round half up (not Python's banker's rounding) so 2.5 ticks maps to 3 predictably.
    return int(math.floor(seconds / tick_duration_s + 0.5))


def werner_bell_density(fidelity):
    """Density matrix of a Werner state with |Phi+> fidelity `fidelity`.

    rho_F = F |Phi+><Phi+| + (1 - F)/3 (I - |Phi+><Phi+|), valid for F in [1/4, 1].
    At F = 1 this is exactly the ideal |Phi+> density matrix.
    """
    if not (0.25 <= fidelity <= 1.0):
        raise ValueError(f"Initial Bell-pair fidelity must be in [0.25, 1], got {fidelity}.")
    if fidelity == 1.0:
        return _PHI_PLUS_IDEAL.astype(complex)
    phi = _PHI_PLUS_IDEAL.astype(complex)
    return ((4.0 * fidelity - 1.0) / 3.0) * phi + ((1.0 - fidelity) / 3.0) * np.identity(4, dtype=complex)


def validate_storage_times(t1_ticks, t2_ticks):
    """Raise ValueError unless T1/T2 are non-negative and T2 <= 2 T1 when both are set."""
    if t1_ticks < 0 or t2_ticks < 0:
        raise ValueError("T1 and T2 must be non-negative (0 disables the process).")
    if t1_ticks > 0 and t2_ticks > 0 and t2_ticks > 2.0 * t1_ticks:
        raise ValueError(f"T2 must satisfy T2 <= 2*T1 (got T1={t1_ticks}, T2={t2_ticks}).")


def amplitude_damping_kraus(gamma):
    """Kraus operators of amplitude damping with decay probability gamma."""
    k0 = np.array([[1.0, 0.0], [0.0, math.sqrt(1.0 - gamma)]], dtype=complex)
    k1 = np.array([[0.0, math.sqrt(gamma)], [0.0, 0.0]], dtype=complex)
    return [k0, k1]


def phase_damping_kraus(lam):
    """Kraus operators of pure dephasing with off-diagonal shrink factor sqrt(1 - lam)."""
    k0 = np.array([[1.0, 0.0], [0.0, math.sqrt(1.0 - lam)]], dtype=complex)
    k1 = np.array([[0.0, 0.0], [0.0, math.sqrt(lam)]], dtype=complex)
    return [k0, k1]


def storage_decoherence_kraus(ticks, t1_ticks, t2_ticks):
    """Return (amplitude_damping_ops, phase_damping_ops) for `ticks` of storage.

    Elapsed-time model (exact for a single qubit held for `ticks`):
      - Amplitude damping: gamma = 1 - exp(-t / T1), so populations relax as exp(-t/T1)
        and coherences shrink by exp(-t / (2 T1)).
      - Pure dephasing rate: 1/T_phi = 1/T2 - 1/(2 T1). Coherences shrink in total by
        exp(-t / T2) across both processes.
    Empty lists mean the process is disabled or has no effect for this duration.
    """
    if ticks < 0:
        raise ValueError(f"Storage duration must be non-negative, got {ticks}")
    if ticks == 0:
        return [], []
    validate_storage_times(t1_ticks, t2_ticks)

    ad_ops = []
    if t1_ticks > 0:
        gamma = 1.0 - math.exp(-ticks / t1_ticks)
        if gamma > 0.0:
            ad_ops = amplitude_damping_kraus(gamma)

    pd_ops = []
    if t2_ticks > 0:
        inv_tphi = 1.0 / t2_ticks - (1.0 / (2.0 * t1_ticks) if t1_ticks > 0 else 0.0)
        if inv_tphi > 0.0:
            lam = 1.0 - math.exp(-2.0 * ticks * inv_tphi)
            if lam > 0.0:
                pd_ops = phase_damping_kraus(lam)
    return ad_ops, pd_ops


def geometric_gap(rate, rng):
    """Sample the number of ticks until the next event of a per-tick Bernoulli(rate) process.

    Support is {1, 2, ...} with P(G = k) = (1 - rate)^(k - 1) * rate. Sampling one gap per
    event keeps dark-count simulation cost proportional to the number of counts, not ticks.
    """
    if not (0.0 < rate <= 1.0):
        raise ValueError(f"Per-tick event rate must be in (0, 1], got {rate}")
    if rate == 1.0:
        return 1
    u = rng.random()
    return max(1, int(math.ceil(math.log1p(-u) / math.log1p(-rate))))
