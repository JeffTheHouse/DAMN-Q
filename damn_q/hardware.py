"""Compatibility re-export of the Step 3 hardware models.

The implementation lives in the root-level `Hardware_models` module so that
simulator components can import it without triggering the `damn_q` package
initializer (which imports the runner and therefore those components).
"""

from Hardware_models import (  # noqa: F401
    DEFAULT_FIBRE_ATTENUATION_DB_PER_KM,
    FIBRE_SPEED_KM_PER_S,
    amplitude_damping_kraus,
    combined_loss_p,
    fibre_loss_p,
    geometric_gap,
    phase_damping_kraus,
    propagation_ticks,
    storage_decoherence_kraus,
    validate_storage_times,
    werner_bell_density,
)
