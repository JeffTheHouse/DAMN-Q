import random
from Data import *


def measure(measurement_id, qubit, x_basis_p):
    use_x = random.random() < x_basis_p
    basis = "x" if use_x else "z"
    if qubit.register is None:
        raise ValueError("Cannot measure a qubit with no state.")
    outcome = qubit.register.measure(qubit, basis=basis)
    return Measurement_output(measurement_id, outcome, m_axis=basis)
