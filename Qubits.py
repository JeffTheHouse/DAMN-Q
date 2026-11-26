import random
import numpy as np
from Operators import *
from States import *


def _draw(rng=None):
    """Uniform draw from `rng` (e.g. a Simulation's stream), or the module RNG."""
    return (rng if rng is not None else random).random()


_BELL_STATES = (
    ("00", np.array([1.0, 0.0, 0.0, 1.0], dtype=complex) / np.sqrt(2.0)),   # |Phi+>
    ("01", np.array([0.0, 1.0, 1.0, 0.0], dtype=complex) / np.sqrt(2.0)),   # |Psi+>
    ("10", np.array([1.0, 0.0, 0.0, -1.0], dtype=complex) / np.sqrt(2.0)),  # |Phi->
    ("11", np.array([0.0, 1.0, -1.0, 0.0], dtype=complex) / np.sqrt(2.0)),  # |Psi->
)


def _apply_single_qubit_op(rho, n_qubits, idx, op):
    r"""Return (op_idx) rho (op_idx)^\dagger for an n-qubit density matrix."""
    tensor = rho.reshape((2,) * (2 * n_qubits))
    tensor = np.tensordot(op, tensor, axes=([1], [idx]))
    tensor = np.moveaxis(tensor, 0, idx)
    tensor = np.tensordot(op.conj(), tensor, axes=([1], [n_qubits + idx]))
    tensor = np.moveaxis(tensor, 0, n_qubits + idx)
    dim = 1 << n_qubits
    return tensor.reshape((dim, dim))


def _partial_trace_single(rho, n_qubits, idx):
    """Trace out qubit `idx` from an n-qubit density matrix."""
    tensor = rho.reshape((2,) * (2 * n_qubits))
    reduced = np.trace(tensor, axis1=idx, axis2=n_qubits + idx)
    dim = 1 << (n_qubits - 1)
    return reduced.reshape((dim, dim))


def _projectors_for_basis(basis):
    p0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
    p1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)
    if basis == "x":
        p0 = h_operator @ p0 @ h_operator
        p1 = h_operator @ p1 @ h_operator
    elif basis != "z":
        raise ValueError(f"Unsupported measurement basis: {basis!r}")
    return p0, p1


class Register:
    """Density-matrix register owning an ordered list of Qubit handles."""

    def __init__(self, density_matrix, qubits=None):
        self.density_matrix = np.asarray(density_matrix, dtype=complex)
        self._qubits = []
        if qubits is not None:
            for q in qubits:
                self.attach(q)

    @property
    def qubits(self):
        return tuple(self._qubits)

    @property
    def num_qubits(self):
        dim = self.density_matrix.shape[0]
        return int(round(np.log2(dim)))

    def attach(self, qubit):
        if qubit in self._qubits:
            qubit._register = self
            return
        if qubit._register is not None and qubit._register is not self:
            raise ValueError(
                f"Qubit {qubit.id!r} is already owned by another register."
            )
        if len(self._qubits) >= self.num_qubits:
            raise ValueError(
                f"Register already has {len(self._qubits)} qubit(s) for a {self.num_qubits}-qubit state."
            )
        self._qubits.append(qubit)
        qubit._register = self

    def index_of(self, qubit):
        try:
            return self._qubits.index(qubit)
        except ValueError as exc:
            raise ValueError(f"Qubit {qubit.id!r} is not in this register.") from exc

    def apply_unitary(self, qubit, unitary):
        idx = self.index_of(qubit)
        n = self.num_qubits
        u = np.asarray(unitary, dtype=complex)
        self.density_matrix = _apply_single_qubit_op(self.density_matrix, n, idx, u)

    def apply_kraus(self, qubit, kraus_ops):
        idx = self.index_of(qubit)
        n = self.num_qubits
        rho = self.density_matrix
        out = np.zeros_like(rho, dtype=complex)
        for k_op in kraus_ops:
            k = np.asarray(k_op, dtype=complex)
            out += _apply_single_qubit_op(rho, n, idx, k)
        self.density_matrix = out

    def depolarize(self, qubit, p):
        if p == 0:
            return
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"Depolarization probability must be in [0, 1], got {p}")
        idx = self.index_of(qubit)
        n = self.num_qubits
        rho = self.density_matrix
        self.density_matrix = (1.0 - p) * rho + (p / 3.0) * (
            _apply_single_qubit_op(rho, n, idx, x_operator)
            + _apply_single_qubit_op(rho, n, idx, y_operator)
            + _apply_single_qubit_op(rho, n, idx, z_operator)
        )

    def reduced_density_matrix(self, target_qubits):
        """Return the reduced density matrix of `target_qubits` in the given order."""
        target_qubits = list(target_qubits)
        if not target_qubits:
            raise ValueError("target_qubits must be non-empty.")
        target_indices = [self.index_of(q) for q in target_qubits]
        if len(set(target_indices)) != len(target_indices):
            raise ValueError("target_qubits contains duplicates.")

        n = self.num_qubits
        rho = self.density_matrix
        remaining = list(range(n))
        for idx in sorted(set(range(n)) - set(target_indices), reverse=True):
            rho = _partial_trace_single(rho, len(remaining), idx)
            remaining.pop(idx)

        k = len(remaining)
        perm = [remaining.index(t) for t in target_indices]
        if perm != list(range(k)):
            tensor = rho.reshape((2,) * (2 * k))
            axes = perm + [k + p for p in perm]
            tensor = np.transpose(tensor, axes)
            dim = 1 << k
            rho = tensor.reshape((dim, dim))
        return rho.copy()

    def trace_out(self, qubit):
        """Remove `qubit` from this register via partial trace."""
        idx = self.index_of(qubit)
        n = self.num_qubits
        self._qubits.pop(idx)
        qubit._register = None
        if n > 1:
            self.density_matrix = _partial_trace_single(self.density_matrix, n, idx)
        else:
            self.density_matrix = np.array([[1.0]], dtype=complex)

    def measure(self, qubit, basis="z", rng=None):
        """Projectively measure `qubit` in `basis` ('z' or 'x').

        For multi-qubit registers, `qubit` is detached into its own 1-qubit
        register holding the post-measurement eigenstate, and the remaining
        qubits stay in this register with their exact conditional state.
        """
        idx = self.index_of(qubit)
        n = self.num_qubits
        p0, p1 = _projectors_for_basis(basis)
        rho = self.density_matrix

        post0 = _apply_single_qubit_op(rho, n, idx, p0)
        prob_0 = float(np.clip(np.real(np.trace(post0)), 0.0, 1.0))

        if _draw(rng) < prob_0:
            outcome = "0"
            proj, post_unnorm, prob = p0, post0, prob_0
        else:
            outcome = "1"
            post1 = _apply_single_qubit_op(rho, n, idx, p1)
            prob = float(np.clip(np.real(np.trace(post1)), 0.0, 1.0))
            proj, post_unnorm = p1, post1

        post = (post_unnorm / prob) if prob > 0.0 else None

        if n == 1:
            self.density_matrix = post if post is not None else proj.copy()
        else:
            remaining_rho = _partial_trace_single(post, n, idx) if post is not None else _partial_trace_single(rho, n, idx)
            self._qubits.pop(idx)
            qubit._register = None
            self.density_matrix = remaining_rho
            # Detach measured qubit into its own post-measurement 1-qubit state
            collapsed = State(proj.copy())
            collapsed.attach(qubit)

        return outcome

    @classmethod
    def join(cls, reg_a, reg_b):
        """Join two distinct registers into one combined register."""
        if reg_a is reg_b:
            return reg_a
        joint_rho = np.kron(reg_a.density_matrix, reg_b.density_matrix)
        joint = State(joint_rho)
        moving = list(reg_a._qubits) + list(reg_b._qubits)
        reg_a._qubits = []
        reg_b._qubits = []
        for q in moving:
            q._register = None
            joint.attach(q)
        return joint

    @classmethod
    def ensure_joint(cls, q1, q2):
        if q1._register is None or q2._register is None:
            raise ValueError("Cannot join qubits when one or both have no register.")
        if q1._register is q2._register:
            return q1._register
        return cls.join(q1._register, q2._register)

    @classmethod
    def bell_measure(cls, q1, q2, rng=None):
        """Perform a Bell-basis measurement on `q1` and `q2`.

        Returns `(outcome, remaining_register)` where `outcome` is one of:
          - "00": |Phi+> (correction I)
          - "01": |Psi+> (correction X)
          - "10": |Phi-> (correction Z)
          - "11": |Psi-> (correction ZX)
        """
        if q1 is q2:
            raise ValueError("Bell measurement requires two distinct qubits.")
        reg = cls.ensure_joint(q1, q2)
        i1 = reg.index_of(q1)
        i2 = reg.index_of(q2)
        n = reg.num_qubits
        rest = [i for i in range(n) if i not in (i1, i2)]

        perm = [i1, i2] + rest
        axes = perm + [n + p for p in perm]
        tensor = np.transpose(reg.density_matrix.reshape((2,) * (2 * n)), axes)
        dim_rest = 1 << (n - 2)
        tensor = tensor.reshape((4, dim_rest, 4, dim_rest))

        candidates = []
        probs = []
        for label, ket in _BELL_STATES:
            unnorm = np.einsum("a,abcd,c->bd", ket.conj(), tensor, ket)
            p = float(np.clip(np.real(np.trace(unnorm)), 0.0, 1.0))
            candidates.append((label, unnorm, p))
            probs.append(p)

        total = sum(probs)
        r = _draw(rng) * total
        cumulative = 0.0
        chosen = candidates[-1]
        for cand in candidates:
            cumulative += cand[2]
            if r <= cumulative and cand[2] > 0.0:
                chosen = cand
                break

        outcome, unnorm_rest, prob = chosen
        remaining_qubits = [reg._qubits[i] for i in rest]
        q1._register = None
        q2._register = None

        if remaining_qubits:
            reg._qubits = remaining_qubits
            reg.density_matrix = unnorm_rest / prob
            for q in remaining_qubits:
                q._register = reg
            return outcome, reg

        reg._qubits = []
        reg.density_matrix = np.array([[1.0]], dtype=complex)
        return outcome, None


class State(Register):
    """Backwards-compatible density-matrix State backed by Register."""

    def __init__(self, density_matrix):
        super().__init__(density_matrix)

    def depolarizing_channel(self, p):
        if np.shape(self.density_matrix)[0] == 4:
            self.density_matrix = (1 - 4 * p / 3) * self.density_matrix + (
                (4 * p / 3) * ((1 / 4) * np.identity(4))
            )
        elif np.shape(self.density_matrix)[0] == 2:
            rho = self.density_matrix
            self.density_matrix = (1 - p) * rho + (p / 3) * (
                x_operator @ rho @ x_operator
                + y_operator @ rho @ y_operator
                + z_operator @ rho @ z_operator
            )

    def loss_channel(self):
        if np.shape(self.density_matrix)[0] == 4:
            self.density_matrix = 0.5 * np.identity(2)


class Qubit:
    def __init__(self, id, state):
        self.id = id
        self._register = None
        self.state = state

    @property
    def register(self):
        return self._register

    @register.setter
    def register(self, reg):
        self.state = reg

    @property
    def state(self):
        return self._register

    def _detach_from_register(self):
        old = self._register
        if isinstance(old, Register) and self in old._qubits:
            if old.num_qubits == len(old._qubits):
                old.trace_out(self)
            else:
                old._qubits.remove(self)
                self._register = None
        else:
            self._register = None

    @state.setter
    def state(self, value):
        if value is self._register:
            return
        if isinstance(value, Register) and self not in value._qubits:
            if len(value._qubits) >= value.num_qubits:
                raise ValueError(
                    f"Register already has {len(value._qubits)} qubit(s) for a {value.num_qubits}-qubit state."
                )
        self._detach_from_register()
        if value is None:
            self._register = None
        elif isinstance(value, Register):
            value.attach(self)
        else:
            self._register = value

    @staticmethod
    def bell_state(id_1, id_2, state):
        qubit_1 = Qubit(id_1, state)
        qubit_2 = Qubit(id_2, state)
        return (qubit_1, qubit_2)

    def depolarize(self, p):
        if self._register is not None:
            self._register.depolarize(self, p)

    def apply_unitary(self, unitary):
        if self._register is not None:
            self._register.apply_unitary(self, unitary)

    def loss(self, loss_p, rng=None):
        if _draw(rng) < loss_p:
            if self._register is not None:
                self._register.trace_out(self)
            self._register = None
