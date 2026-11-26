import random
from Data import *


def measure(measurement_id, qubit, x_basis_p, rng=None):
    """Measure `qubit` in X or Z basis. `rng` defaults to the module RNG."""
    draw = rng if rng is not None else random
    use_x = draw.random() < x_basis_p
    basis = "x" if use_x else "z"
    if qubit.register is None:
        raise ValueError("Cannot measure a qubit with no state.")
    outcome = qubit.register.measure(qubit, basis=basis, rng=rng)
    return Measurement_output(measurement_id, outcome, m_axis=basis)
