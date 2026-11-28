"""Processing-node quantum repeater chain for cross-simulator benchmarking (Delft-Eindhoven).

Models a 3-node (2-link) processing-node repeater (e.g. NV-center / trapped-ion
architecture in Avis et al., npj Quantum Information 9, 100, 2023):
  - Two end nodes (Alice, Bob) and one central processing-node repeater (R)
  - Four published fibre segments (Alice -> H1 <- R -> H2 <- Bob)
  - Single communication qubit + single storage qubit at R (sequential link
    generation with timed local MOVE/SWAP gate)
  - Attempt-induced dephasing on the storage qubit during link-2 retries
  - Continuous elapsed-time T1/T2 storage decoherence
  - Configurable cutoff policy (maximum storage time and/or link-2 attempts)
  - Exact density-matrix `Register` evolution and O(1) `StreamingStats`
"""

from dataclasses import dataclass
import math
import time

import numpy as np

from Hardware_models import (
    DEFAULT_FIBRE_ATTENUATION_DB_PER_KM,
    FIBRE_SPEED_KM_PER_S,
    fibre_loss_p,
    phase_damping_kraus,
    storage_decoherence_kraus,
    validate_storage_times,
    werner_bell_density,
)
from Operators import x_operator, z_operator
from Qubits import Qubit, Register, State
from Simulation import Simulation
from States import phi_plus
from damn_q.stats import StreamingStats


@dataclass
class ProcessingNodeConfig:
    # Published Delft-Eindhoven rounded segment lengths (km): 83, 19, 75, 50
    seg_a_left_km: float = 83.0
    seg_a_right_km: float = 19.0
    seg_b_left_km: float = 75.0
    seg_b_right_km: float = 50.0
    attenuation_db_per_km: float = DEFAULT_FIBRE_ATTENUATION_DB_PER_KM
    coupling_loss_db: float = 0.0
    # Elementary heralding efficiency factor (detector/collection/protocol prefactor)
    herald_prefactor: float = 1.0
    elementary_fidelity: float = 1.0
    # Processing-node gate & memory parameters (in seconds)
    move_gate_duration_s: float = 1e-3
    swap_gate_duration_s: float = 1e-3
    gate_depol_p: float = 0.0
    attempt_dephasing_p: float = 0.0  # pure dephasing lambda per link-2 attempt on stored qubit
    storage_t1_s: float = 0.0
    storage_t2_s: float = 0.0
    bsm_visibility: float = 1.0
    # Cutoff policies (0 = disabled)
    memory_cutoff_s: float = 0.0
    max_attempts_cutoff: int = 0
    # Simulation horizon (seconds) and RNG seed
    until_s: float = 10.0
    seed: int = 42
    trace: bool = False


class ProcessingNodeRepeater:
    """Discrete-event processing-node repeater with exact `Register` state tracking."""

    def __init__(self, config: ProcessingNodeConfig):
        for name in (
            "seg_a_left_km",
            "seg_a_right_km",
            "seg_b_left_km",
            "seg_b_right_km",
            "attenuation_db_per_km",
            "coupling_loss_db",
            "move_gate_duration_s",
            "swap_gate_duration_s",
            "storage_t1_s",
            "storage_t2_s",
            "memory_cutoff_s",
        ):
            val = getattr(config, name)
            if not math.isfinite(val) or val < 0.0:
                raise ValueError(f"{name} must be finite and >= 0, got {val}")
        if not math.isfinite(config.until_s) or config.until_s <= 0.0:
            raise ValueError(f"until_s must be finite and > 0, got {config.until_s}")
        if config.max_attempts_cutoff < 0:
            raise ValueError(f"max_attempts_cutoff must be >= 0, got {config.max_attempts_cutoff}")
        for name in ("gate_depol_p", "attempt_dephasing_p", "bsm_visibility"):
            val = getattr(config, name)
            if not math.isfinite(val) or not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {val}")
        if not math.isfinite(config.herald_prefactor) or not (0.0 < config.herald_prefactor <= 1.0):
            raise ValueError(f"herald_prefactor must be in (0, 1], got {config.herald_prefactor}")
        if not math.isfinite(config.elementary_fidelity) or not (0.25 <= config.elementary_fidelity <= 1.0):
            raise ValueError(f"elementary_fidelity must be in [0.25, 1], got {config.elementary_fidelity}")
        validate_storage_times(config.storage_t1_s, config.storage_t2_s)

        self.cfg = config
        self.sim = Simulation(seed=config.seed)

        # Link round-trip durations (seconds): max(L_left, L_right) * 2 / c_fibre
        self.t_round_1 = 2.0 * max(config.seg_a_left_km, config.seg_a_right_km) / FIBRE_SPEED_KM_PER_S
        self.t_round_2 = 2.0 * max(config.seg_b_left_km, config.seg_b_right_km) / FIBRE_SPEED_KM_PER_S
        self.t_ff = (config.seg_b_left_km + config.seg_b_right_km) / FIBRE_SPEED_KM_PER_S

        # Link heralding probabilities from total segment fibre attenuation + coupling
        t_link_1 = 1.0 - fibre_loss_p(
            config.seg_a_left_km + config.seg_a_right_km,
            config.attenuation_db_per_km,
            config.coupling_loss_db,
        )
        t_link_2 = 1.0 - fibre_loss_p(
            config.seg_b_left_km + config.seg_b_right_km,
            config.attenuation_db_per_km,
            config.coupling_loss_db,
        )
        self.p_link_1 = min(1.0, config.herald_prefactor * t_link_1)
        self.p_link_2 = min(1.0, config.herald_prefactor * t_link_2)

        self._init_rho = (
            phi_plus if config.elementary_fidelity == 1.0 else werner_bell_density(config.elementary_fidelity)
        )
        self._attempt_pd_ops = (
            phase_damping_kraus(config.attempt_dephasing_p) if config.attempt_dephasing_p > 0.0 else []
        )

        # Active protocol state
        self._cycle_start_s = 0.0
        self._stored_at_s = 0.0
        self._q_alice = None
        self._q_storage = None
        self._link2_attempts_this_cycle = 0

        # Metrics
        self.link1_attempts = 0
        self.link2_attempts = 0
        self.cutoffs = 0
        self.swaps_completed = 0
        self.fidelity_stats = StreamingStats(trace=config.trace)
        self.latency_stats = StreamingStats(trace=config.trace)

        # Start first link-1 attempt at t=0
        self.sim.add(0.0, self._start_cycle)

    def _start_cycle(self):
        self._cycle_start_s = self.sim.time
        self._link2_attempts_this_cycle = 0
        self._attempt_link_1()

    def _attempt_link_1(self):
        self.link1_attempts += 1
        self.sim.add(self.t_round_1, self._on_link_1_result)

    def _on_link_1_result(self):
        if self.sim.rng.random() >= self.p_link_1:
            self._attempt_link_1()
            return
        # Link 1 heralded: create Bell pair (Alice, Repeater comm qubit) and MOVE to storage
        self._q_alice, self._q_storage = Qubit.bell_state(1, 2, State(self._init_rho.copy()))
        self._stored_at_s = self.sim.time
        self.sim.add(self.cfg.move_gate_duration_s, self._on_move_complete)

    def _on_move_complete(self):
        if self.cfg.gate_depol_p > 0.0:
            self._q_storage.depolarize(self.cfg.gate_depol_p)
        self._attempt_link_2()

    def _discard_stored_and_restart(self):
        self.cutoffs += 1
        if self._q_alice is not None:
            self._q_alice.state = None
        if self._q_storage is not None:
            self._q_storage.state = None
        self._q_alice = None
        self._q_storage = None
        self._start_cycle()

    def _attempt_link_2(self):
        # Enforce cutoff policies before starting another link-2 attempt
        if self.cfg.max_attempts_cutoff > 0 and self._link2_attempts_this_cycle >= self.cfg.max_attempts_cutoff:
            self._discard_stored_and_restart()
            return
        if self.cfg.memory_cutoff_s > 0.0 and (self.sim.time - self._stored_at_s) >= self.cfg.memory_cutoff_s:
            self._discard_stored_and_restart()
            return

        self.link2_attempts += 1
        self._link2_attempts_this_cycle += 1
        # Attempt-induced dephasing on the stored qubit
        if self._attempt_pd_ops:
            self._q_storage.apply_kraus(self._attempt_pd_ops)
        self.sim.add(self.t_round_2, self._on_link_2_result)

    def _on_link_2_result(self):
        if self.sim.rng.random() >= self.p_link_2:
            self._attempt_link_2()
            return

        # Link 2 heralded: create Bell pair (Repeater comm qubit, Bob)
        q_comm, q_bob = Qubit.bell_state(3, 4, State(self._init_rho.copy()))
        self.sim.add(
            self.cfg.swap_gate_duration_s,
            lambda qc=q_comm, qb=q_bob: self._on_swap_complete(qc, qb),
        )

    def _apply_t1_t2(self, qubit, elapsed_s):
        if elapsed_s <= 0.0 or (self.cfg.storage_t1_s == 0.0 and self.cfg.storage_t2_s == 0.0):
            return
        ad_ops, pd_ops = storage_decoherence_kraus(elapsed_s, self.cfg.storage_t1_s, self.cfg.storage_t2_s)
        if ad_ops:
            qubit.apply_kraus(ad_ops)
        if pd_ops:
            qubit.apply_kraus(pd_ops)

    def _on_swap_complete(self, q_comm, q_bob):
        # Accrue elapsed-time T1/T2 on stored qubit and Alice's qubit up to swap
        elapsed_storage = self.sim.time - self._stored_at_s
        self._apply_t1_t2(self._q_storage, elapsed_storage)
        self._apply_t1_t2(self._q_alice, elapsed_storage)
        if self.cfg.gate_depol_p > 0.0:
            self._q_storage.depolarize(self.cfg.gate_depol_p)
            q_comm.depolarize(self.cfg.gate_depol_p)

        outcome, _ = Register.bell_measure_imperfect(
            self._q_storage, q_comm, visibility=self.cfg.bsm_visibility, rng=self.sim.rng
        )
        self.swaps_completed += 1

        qa = self._q_alice
        self._q_alice = None
        self._q_storage = None
        swap_time = self.sim.time

        self.sim.add(
            self.t_ff,
            lambda a=qa, b=q_bob, out=outcome, st=swap_time: self._on_delivery(a, b, out, st),
        )

    def _on_delivery(self, q_alice, q_bob, outcome, swap_time):
        # Accrue T1/T2 during classical feed-forward
        ff_elapsed = self.sim.time - swap_time
        self._apply_t1_t2(q_alice, ff_elapsed)
        self._apply_t1_t2(q_bob, ff_elapsed)

        if q_bob.register is not None:
            if outcome[1] == "1":
                q_bob.apply_unitary(x_operator)
            if outcome[0] == "1":
                q_bob.apply_unitary(z_operator)
        if q_alice.register is not None and q_alice.register is q_bob.register:
            joint = q_alice.register.reduced_density_matrix([q_alice, q_bob])
            fidelity = float(np.real(np.trace(phi_plus @ joint)))
        else:
            fidelity = 0.0

        q_alice.state = None
        q_bob.state = None

        self.fidelity_stats.add(fidelity)
        self.latency_stats.add(self.sim.time - self._cycle_start_s)
        self._start_cycle()

    def analytic_ideal_rate_hz(self):
        """Exact expected delivery rate (Hz) when no cutoffs are active."""
        e_t1 = self.t_round_1 / self.p_link_1
        e_t2 = self.t_round_2 / self.p_link_2
        mean_cycle_s = e_t1 + self.cfg.move_gate_duration_s + e_t2 + self.cfg.swap_gate_duration_s + self.t_ff
        return 1.0 / mean_cycle_s

    def run(self):
        t0 = time.perf_counter()
        self.sim.run(self.cfg.until_s)
        wall_s = time.perf_counter() - t0
        n_pairs = self.fidelity_stats.count
        rate_hz = n_pairs / self.sim.time if self.sim.time > 0 else 0.0
        return {
            "seed": self.cfg.seed,
            "until_s": self.cfg.until_s,
            "p_link_1": self.p_link_1,
            "p_link_2": self.p_link_2,
            "t_round_1_s": self.t_round_1,
            "t_round_2_s": self.t_round_2,
            "analytic_no_cutoff_rate_hz": self.analytic_ideal_rate_hz(),
            "delivered_pairs": n_pairs,
            "delivered_pairs_per_s": rate_hz,
            "link1_attempts": self.link1_attempts,
            "link2_attempts": self.link2_attempts,
            "cutoffs": self.cutoffs,
            "swaps_completed": self.swaps_completed,
            "fidelity": self.fidelity_stats.to_dict(),
            "latency_s": self.latency_stats.to_dict(),
            "wall_time_s": wall_s,
        }


def run_processing_node(config: ProcessingNodeConfig):
    """Build and run a Delft-Eindhoven processing-node repeater simulation."""
    return ProcessingNodeRepeater(config).run()
