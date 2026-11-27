"""Configurable N-hop linear quantum repeater chain with swap-asap and memory cutoff.

Uses the exact multi-qubit density-matrix `Register` and per-run `Simulation`
event queue. Supports:
  - Arbitrary chain length `num_hops >= 1` (N+1 nodes: Alice, N-1 repeaters, Bob)
  - Periodic elementary link attempts with retries when adjacent slots are free
  - Swap-as-soon-as-both-links-are-ready (swap-asap) at every repeater node,
    respecting classical notification delay (`swap_delay + hop_distance * link_delay`)
    before a downstream repeater may swap a newly formed segment
  - Configurable `memory_cutoff` (simulation ticks; 0 disables cutoff), enforced
    **through delivery**: any segment whose oldest surviving endpoint qubit reaches
    storage age `memory_cutoff` is discarded, whether waiting for a swap or waiting
    for end-to-end classical feed-forward
  - O(1)-memory `StreamingStats` by default, with optional `trace=True`
  - Optional lightweight phase timing (`profile=True`) separating register ops,
    event scheduling, and diagnostics for scaling benchmarks.
"""

from dataclasses import dataclass
import math
import time
import numpy as np

from Memory import _composed_depolarization_p
from Operators import x_operator, z_operator
from Qubits import Qubit, Register, State
from Simulation import Simulation
from States import phi_plus
from damn_q.stats import StreamingStats


@dataclass
class ChainConfig:
    num_hops: int = 2
    until: float = 40000
    seed: int = 101
    tick_duration_s: float = 1e-6
    attempt_period: float = 200
    link_delay: float = 50
    swap_delay: float = 1
    loss_p: float = 0.2
    channel_depolarization_p: float = 0.005
    memory_depolarization_p: float = 0.0005
    memory_cutoff: float = 0.0  # 0 = no cutoff
    trace: bool = False
    profile: bool = False


class _Segment:
    """An active entangled segment between node `left_node` and node `right_node`."""

    __slots__ = (
        "seg_id",
        "left_node",
        "right_node",
        "q_left",
        "q_right",
        "left_arrival",
        "right_arrival",
        "created_at",
        "left_ready",
        "right_ready",
        "pending_x",
        "pending_z",
        "alive",
        "cutoff_handles",
    )

    def __init__(
        self,
        seg_id,
        left_node,
        right_node,
        q_left,
        q_right,
        left_arrival,
        right_arrival,
        created_at,
        *,
        left_ready=True,
        right_ready=True,
    ):
        self.seg_id = seg_id
        self.left_node = left_node
        self.right_node = right_node
        self.q_left = q_left
        self.q_right = q_right
        self.left_arrival = left_arrival
        self.right_arrival = right_arrival
        self.created_at = created_at
        self.left_ready = left_ready
        self.right_ready = right_ready
        self.pending_x = False
        self.pending_z = False
        self.alive = True
        self.cutoff_handles = []


class RepeaterChain:
    """Reusable N-hop linear repeater chain running swap-asap with retries & cutoff."""

    def __init__(self, config: ChainConfig):
        if config.num_hops < 1:
            raise ValueError(f"num_hops must be >= 1, got {config.num_hops}")
        for name in (
            "until",
            "tick_duration_s",
            "attempt_period",
            "link_delay",
            "swap_delay",
            "memory_cutoff",
            "loss_p",
            "channel_depolarization_p",
            "memory_depolarization_p",
        ):
            val = getattr(config, name)
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")
        if config.until <= 0:
            raise ValueError(f"until must be > 0, got {config.until}")
        if config.tick_duration_s <= 0:
            raise ValueError(f"tick_duration_s must be > 0, got {config.tick_duration_s}")
        if config.attempt_period <= 0:
            raise ValueError(f"attempt_period must be > 0, got {config.attempt_period}")
        if config.link_delay < 0:
            raise ValueError(f"link_delay must be >= 0, got {config.link_delay}")
        if config.swap_delay < 0:
            raise ValueError(f"swap_delay must be >= 0, got {config.swap_delay}")
        if config.memory_cutoff < 0:
            raise ValueError(f"memory_cutoff must be >= 0, got {config.memory_cutoff}")
        for name in ("loss_p", "channel_depolarization_p", "memory_depolarization_p"):
            val = getattr(config, name)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {val}")

        self.cfg = config
        self.sim = Simulation(seed=config.seed)
        self.n = config.num_hops

        # Each node i in 0..N has at most one active segment on its left (i-1 side)
        # and one active segment on its right (i side).
        self.left_slot = [None] * (self.n + 1)
        self.right_slot = [None] * (self.n + 1)
        # Elementary link k in 0..N-1 is busy while an attempt is in flight or stored
        self.link_busy = [False] * self.n

        # Metrics
        self.attempts = 0
        self.heralded_elementary = 0
        self.swaps_completed = 0
        self.cutoff_expiries = 0
        self.fidelity_stats = StreamingStats(trace=config.trace)
        self.latency_stats = StreamingStats(trace=config.trace)

        # Optional phase profiling (seconds)
        self._reg_time_s = 0.0
        self._diag_time_s = 0.0
        self._seg_counter = 0

        # Schedule periodic attempt clocks for each elementary link
        for k in range(self.n):
            self.sim.add(self.cfg.attempt_period, lambda idx=k: self._attempt_link(idx))

    def _next_seg_id(self):
        self._seg_counter += 1
        return self._seg_counter

    def _apply_storage_noise(self, qubit, arrival_time):
        if self.cfg.memory_depolarization_p == 0.0 or qubit.state is None:
            return
        ticks = self.sim.time - arrival_time
        if ticks <= 0:
            return
        p_eff = _composed_depolarization_p(self.cfg.memory_depolarization_p, ticks)
        if p_eff != 0.0:
            t0 = time.perf_counter() if self.cfg.profile else 0.0
            qubit.depolarize(p_eff)
            if self.cfg.profile:
                self._reg_time_s += time.perf_counter() - t0

    def _cancel_cutoffs(self, seg):
        for h in seg.cutoff_handles:
            if not h.cancelled:
                self.sim.cancel(h)
        seg.cutoff_handles.clear()

    def _discard_segment(self, seg, *, expired=False):
        if not seg.alive:
            return
        seg.alive = False
        self._cancel_cutoffs(seg)
        if self.right_slot[seg.left_node] is seg:
            self.right_slot[seg.left_node] = None
        if self.left_slot[seg.right_node] is seg:
            self.left_slot[seg.right_node] = None
        # Free elementary link if this was an elementary segment
        if seg.right_node == seg.left_node + 1:
            self.link_busy[seg.left_node] = False
        t0 = time.perf_counter() if self.cfg.profile else 0.0
        if seg.q_left.state is not None:
            seg.q_left.state = None
        if seg.q_right.state is not None:
            seg.q_right.state = None
        if self.cfg.profile:
            self._reg_time_s += time.perf_counter() - t0
        if expired:
            self.cutoff_expiries += 1

    def _schedule_cutoff(self, seg, arrival_time):
        if self.cfg.memory_cutoff <= 0.0:
            return
        remaining = (arrival_time + self.cfg.memory_cutoff) - self.sim.time
        if remaining <= 0:
            self._discard_segment(seg, expired=True)
            return
        handle = self.sim.add(remaining, lambda s=seg: self._discard_segment(s, expired=True))
        seg.cutoff_handles.append(handle)

    def _attempt_link(self, k):
        # Always schedule next attempt tick for link k
        self.sim.add(self.cfg.attempt_period, lambda idx=k: self._attempt_link(idx))

        # Only attempt if both endpoint slots for link k are free and no attempt is in flight
        if self.link_busy[k] or self.right_slot[k] is not None or self.left_slot[k + 1] is not None:
            return

        self.link_busy[k] = True
        self.attempts += 1
        t0_attempt = self.sim.time
        arr_time = t0_attempt + self.cfg.link_delay
        herald_time_delay = self.cfg.link_delay + 1 + self.cfg.link_delay

        t0 = time.perf_counter() if self.cfg.profile else 0.0
        q_l, q_r = Qubit.bell_state(1, 2, State(phi_plus.copy()), created_at=t0_attempt)
        if self.cfg.channel_depolarization_p > 0.0:
            q_l.depolarize(self.cfg.channel_depolarization_p)
            q_r.depolarize(self.cfg.channel_depolarization_p)
        q_l.loss(self.cfg.loss_p, rng=self.sim.rng)
        q_r.loss(self.cfg.loss_p, rng=self.sim.rng)
        if self.cfg.profile:
            self._reg_time_s += time.perf_counter() - t0

        self.sim.add(
            herald_time_delay,
            lambda idx=k, ql=q_l, qr=q_r, ta=arr_time, tc=t0_attempt: self._on_herald(idx, ql, qr, ta, tc),
        )

    def _on_herald(self, k, q_l, q_r, arr_time, created_at):
        if q_l.state is None or q_r.state is None:
            t0 = time.perf_counter() if self.cfg.profile else 0.0
            if q_l.state is not None:
                q_l.state = None
            if q_r.state is not None:
                q_r.state = None
            if self.cfg.profile:
                self._reg_time_s += time.perf_counter() - t0
            self.link_busy[k] = False
            return

        self.heralded_elementary += 1
        seg = _Segment(self._next_seg_id(), k, k + 1, q_l, q_r, arr_time, arr_time, created_at)
        self.right_slot[k] = seg
        self.left_slot[k + 1] = seg

        if self.n == 1:
            # 1-hop chain: already end-to-end!
            self._deliver_end_to_end(seg)
            return

        self._schedule_cutoff(seg, arr_time)
        if k > 0:
            self._try_swap(k)
        if k + 1 < self.n:
            self._try_swap(k + 1)

    def _on_swap_notify(self, seg, side):
        if not seg.alive:
            return
        if side == "left":
            seg.left_ready = True
            if seg.left_node > 0:
                self._try_swap(seg.left_node)
        else:
            seg.right_ready = True
            if seg.right_node < self.n:
                self._try_swap(seg.right_node)

    def _try_swap(self, node):
        seg_l = self.left_slot[node]
        seg_r = self.right_slot[node]
        if (
            seg_l is None
            or seg_r is None
            or not seg_l.alive
            or not seg_r.alive
            or not seg_l.right_ready
            or not seg_r.left_ready
        ):
            return

        # Consume both segments at repeater `node`
        self._cancel_cutoffs(seg_l)
        self._cancel_cutoffs(seg_r)
        seg_l.alive = False
        seg_r.alive = False
        self.left_slot[node] = None
        self.right_slot[node] = None

        # Free elementary links adjacent to `node` so they can retry immediately
        if seg_l.right_node == seg_l.left_node + 1:
            self.link_busy[seg_l.left_node] = False
        if seg_r.right_node == seg_r.left_node + 1:
            self.link_busy[seg_r.left_node] = False

        # Accrue storage noise on the two middle qubits before BSM
        self._apply_storage_noise(seg_l.q_right, seg_l.right_arrival)
        self._apply_storage_noise(seg_r.q_left, seg_r.left_arrival)

        t0 = time.perf_counter() if self.cfg.profile else 0.0
        outcome, _ = Register.bell_measure(seg_l.q_right, seg_r.q_left, rng=self.sim.rng)
        if self.cfg.profile:
            self._reg_time_s += time.perf_counter() - t0
        self.swaps_completed += 1

        new_seg = _Segment(
            self._next_seg_id(),
            seg_l.left_node,
            seg_r.right_node,
            seg_l.q_left,
            seg_r.q_right,
            seg_l.left_arrival,
            seg_r.right_arrival,
            min(seg_l.created_at, seg_r.created_at),
            left_ready=False,
            right_ready=False,
        )
        # Accumulate Pauli frame updates (X and Z commute up to global phase)
        new_seg.pending_x = seg_l.pending_x ^ seg_r.pending_x ^ (outcome[1] == "1")
        new_seg.pending_z = seg_l.pending_z ^ seg_r.pending_z ^ (outcome[0] == "1")

        self.right_slot[new_seg.left_node] = new_seg
        self.left_slot[new_seg.right_node] = new_seg

        # Cutoff applies through delivery (both intermediate and end-to-end segments)
        self._schedule_cutoff(new_seg, min(new_seg.left_arrival, new_seg.right_arrival))
        if not new_seg.alive:
            return

        if new_seg.left_node == 0 and new_seg.right_node == self.n:
            # End-to-end swap completed: schedule classical feed-forward to endpoints
            max_hops = max(node - new_seg.left_node, new_seg.right_node - node)
            ff_delay = self.cfg.swap_delay + max_hops * self.cfg.link_delay
            self.sim.add(ff_delay, lambda s=new_seg: self._deliver_end_to_end(s))
        else:
            # Notify both endpoints after classical propagation delay before downstream swaps
            left_delay = self.cfg.swap_delay + (node - new_seg.left_node) * self.cfg.link_delay
            right_delay = self.cfg.swap_delay + (new_seg.right_node - node) * self.cfg.link_delay
            self.sim.add(left_delay, lambda s=new_seg: self._on_swap_notify(s, "left"))
            self.sim.add(right_delay, lambda s=new_seg: self._on_swap_notify(s, "right"))

    def _deliver_end_to_end(self, seg):
        if not seg.alive:
            return
        if self.cfg.memory_cutoff > 0.0:
            oldest_age = self.sim.time - min(seg.left_arrival, seg.right_arrival)
            if oldest_age >= self.cfg.memory_cutoff:
                self._discard_segment(seg, expired=True)
                return
        seg.alive = False
        self._cancel_cutoffs(seg)
        if self.right_slot[0] is seg:
            self.right_slot[0] = None
        if self.left_slot[self.n] is seg:
            self.left_slot[self.n] = None
        if self.n == 1:
            self.link_busy[0] = False

        # Accrue storage noise on both endpoint qubits up to delivery time
        self._apply_storage_noise(seg.q_left, seg.left_arrival)
        self._apply_storage_noise(seg.q_right, seg.right_arrival)

        t0 = time.perf_counter() if self.cfg.profile else 0.0
        if seg.q_right.register is not None:
            if seg.pending_x:
                seg.q_right.apply_unitary(x_operator)
            if seg.pending_z:
                seg.q_right.apply_unitary(z_operator)
        if seg.q_left.register is not None and seg.q_left.register is seg.q_right.register:
            joint = seg.q_left.register.reduced_density_matrix([seg.q_left, seg.q_right])
            fidelity = float(np.real(np.trace(phi_plus @ joint)))
        else:
            fidelity = 0.0
        # Release delivered qubits so memory stays O(N) bounded
        seg.q_left.state = None
        seg.q_right.state = None
        if self.cfg.profile:
            self._reg_time_s += time.perf_counter() - t0

        td = time.perf_counter() if self.cfg.profile else 0.0
        self.fidelity_stats.add(fidelity)
        self.latency_stats.add(self.sim.time - seg.created_at)
        if self.cfg.profile:
            self._diag_time_s += time.perf_counter() - td

    def run(self):
        t_start = time.perf_counter()
        self.sim.run(self.cfg.until)
        wall_s = time.perf_counter() - t_start

        sim_s = self.sim.time * self.cfg.tick_duration_s
        n_pairs = self.fidelity_stats.count
        rate = (n_pairs / sim_s) if sim_s > 0 else 0.0

        result = {
            "num_hops": self.n,
            "seed": self.cfg.seed,
            "until_ticks": self.cfg.until,
            "tick_duration_s": self.cfg.tick_duration_s,
            "simulated_duration_s": sim_s,
            "memory_cutoff": self.cfg.memory_cutoff,
            "delivered_pairs": n_pairs,
            "delivered_pairs_per_s": rate,
            "attempts": self.attempts,
            "heralded_elementary": self.heralded_elementary,
            "swaps_completed": self.swaps_completed,
            "cutoff_expiries": self.cutoff_expiries,
            "fidelity": self.fidelity_stats.to_dict(),
            "latency_ticks": self.latency_stats.to_dict(),
            "wall_time_s": wall_s,
        }
        if self.cfg.profile:
            events_s = max(0.0, wall_s - self._reg_time_s - self._diag_time_s)
            dominant = max(
                (("registers", self._reg_time_s), ("events", events_s), ("diagnostics", self._diag_time_s)),
                key=lambda kv: kv[1],
            )[0]
            result["profile"] = {
                "registers_s": self._reg_time_s,
                "events_s": events_s,
                "diagnostics_s": self._diag_time_s,
                "dominant": dominant,
            }
        return result


def run_repeater_chain(config: ChainConfig):
    """Convenience entry point to build and run a configurable N-hop repeater chain."""
    return RepeaterChain(config).run()
