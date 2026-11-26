import numpy as np
import random
from Operators import *
from Data import *


def _projectors_for_basis(use_x):
    p0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
    p1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)
    if use_x:
        p0 = h_operator @ p0 @ h_operator
        p1 = h_operator @ p1 @ h_operator
    return p0, p1


def measure(measurement_id, qubit, x_basis_p):
    use_x = random.random() < x_basis_p
    m_axis = "x" if use_x else "z"
    rho = np.asarray(qubit.state.density_matrix, dtype=complex)
    dim = rho.shape[0]
    p0, p1 = _projectors_for_basis(use_x)

    if dim == 2:
        prob_0 = float(np.clip(np.real(np.trace(p0 @ rho)), 0.0, 1.0))
        if random.random() < prob_0:
            outcome = "0"
            proj, prob = p0, prob_0
        else:
            outcome = "1"
            proj, prob = p1, 1.0 - prob_0

        if prob > 0.0:
            qubit.state.density_matrix = (proj @ rho @ proj) / prob
        else:
            qubit.state.density_matrix = proj.copy()
        return Measurement_output(measurement_id, outcome, m_axis=m_axis)

    if dim == 4:
        m0 = np.kron(p0, i_operator)
        m1 = np.kron(p1, i_operator)
        prob_0 = float(np.clip(np.real(np.trace(m0 @ rho)), 0.0, 1.0))
        if random.random() < prob_0:
            outcome = "0"
            m_op, prob = m0, prob_0
        else:
            outcome = "1"
            m_op, prob = m1, 1.0 - prob_0

        post = (m_op @ rho @ m_op) / prob
        # Partial trace over the measured (first) qubit to get the partner's 2x2 state
        partner = np.einsum("ijik->jk", post.reshape(2, 2, 2, 2))
        qubit.state.density_matrix = partner
        return Measurement_output(measurement_id, outcome, m_axis=m_axis)

    raise ValueError(f"Unsupported density matrix dimension: {dim}")
