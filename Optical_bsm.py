"""Time-gated optical Bell-State Measurement (BSM) driven by detector clicks.

Models a two-photon optical Bell analyser with:
  - Coincidence time gate `coincidence_window` (simulation ticks)
  - Per-photon Gaussian detector/arrival timing jitter `jitter_std` (ticks)
  - Detector efficiency `detector_efficiency` in (0, 1]
  - Per-tick dark-count rate `dark_count_rate` in [0, 1] on each detector arm
  - Two-photon Hong-Ou-Mandel interference visibility `visibility` in [0, 1]
  - Linear-optical BSM success probability `linear_optical_efficiency` in (0, 1]
    (0.5 for a standard linear-optical BSM distinguishing 2 of 4 Bell states;
    1.0 for a full 4-outcome Bell analyser).

Clicks on both arms are buffered in bounded chronological queues (expired clicks
older than `coincidence_window` are pruned and any associated photon is traced
out). When two clicks fall within `|t_1 - t_2| <= coincidence_window`:
  - **True coincidence (photon + photon):** succeeds with probability
    `linear_optical_efficiency`, applies `Register.bell_measure_imperfect` with
    `visibility`, and emits a `SwapOutcome` herald on `ch_out_c_1` and `ch_out_c_2`.
  - **False / accidental coincidence (photon + dark, or dark + dark):** any
    participating photon is traced out (leaving its remote partner maximally
    mixed), and a spurious `SwapOutcome` herald is emitted.
"""

from collections import deque

from Emitter import Emitter, Handler, scheduler
from Hardware_models import geometric_gap
from Qubits import Register
from Signals import BellOutcome

_BELL_LABELS = ("00", "01", "10", "11")


class Optical_bsm:
    """Click-driven, time-gated optical Bell-state measurement."""

    def __init__(
        self,
        id,
        delay=1,
        coincidence_window=1.0,
        jitter_std=0.0,
        detector_efficiency=1.0,
        dark_count_rate=0.0,
        visibility=1.0,
        linear_optical_efficiency=0.5,
        sim=None,
    ):
        if delay < 0:
            raise ValueError(f"delay must be >= 0, got {delay}")
        if coincidence_window < 0:
            raise ValueError(f"coincidence_window must be >= 0, got {coincidence_window}")
        if jitter_std < 0:
            raise ValueError(f"jitter_std must be >= 0, got {jitter_std}")
        if not (0.0 < detector_efficiency <= 1.0):
            raise ValueError(f"detector_efficiency must be in (0, 1], got {detector_efficiency}")
        if not (0.0 <= dark_count_rate <= 1.0):
            raise ValueError(f"dark_count_rate must be in [0, 1], got {dark_count_rate}")
        if not (0.0 <= visibility <= 1.0):
            raise ValueError(f"visibility must be in [0, 1], got {visibility}")
        if not (0.0 < linear_optical_efficiency <= 1.0):
            raise ValueError(
                f"linear_optical_efficiency must be in (0, 1], got {linear_optical_efficiency}"
            )

        self.id = id
        self.delay = delay
        self.coincidence_window = float(coincidence_window)
        self.jitter_std = float(jitter_std)
        self.detector_efficiency = float(detector_efficiency)
        self.dark_count_rate = float(dark_count_rate)
        self.visibility = float(visibility)
        self.linear_optical_efficiency = float(linear_optical_efficiency)
        self.sim = sim if sim is not None else scheduler

        self.ch_in_q_1 = Handler(self.handle_qubit_1, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_in_q_2 = Handler(self.handle_qubit_2, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_out_c_1 = Emitter(sim=self.sim, kind="classical")
        self.ch_out_c_2 = Emitter(sim=self.sim, kind="classical")

        # Bounded chronological buffers: (detect_time, qubit_or_None, is_dark)
        self._buf_1 = deque()
        self._buf_2 = deque()

        # Metrics
        self.counter = 0
        self.true_heralds = 0
        self.false_heralds = 0
        self.signal_dark_heralds = 0
        self.dark_dark_heralds = 0
        self.ambiguous_patterns = 0
        self.missed_detections = 0
        self.expired_photons = 0
        self.dark_clicks_1 = 0
        self.dark_clicks_2 = 0

        if self.dark_count_rate > 0.0:
            self._schedule_dark_click(1)
            self._schedule_dark_click(2)

    def _schedule_dark_click(self, side):
        gap = geometric_gap(self.dark_count_rate, self.sim.rng)
        self.sim.add(gap, lambda s=side: self._on_dark_click(s))

    def _on_dark_click(self, side):
        if side == 1:
            self.dark_clicks_1 += 1
        else:
            self.dark_clicks_2 += 1
        self._ingest_click(side, self.sim.time, None, is_dark=True)
        self._schedule_dark_click(side)

    def _discard_qubit(self, q):
        if q is not None and q.state is not None:
            q.state = None

    def _prune_buffer(self, buf, now):
        w = self.coincidence_window
        while buf and (now - buf[0][0]) > w:
            _t, q, is_dark = buf.popleft()
            if not is_dark and q is not None:
                self._discard_qubit(q)
                self.expired_photons += 1

    def _handle_arrival(self, side, qubit):
        if qubit.state is None:
            return
        if self.detector_efficiency < 1.0:
            qubit.loss(1.0 - self.detector_efficiency, rng=self.sim.rng)
            if qubit.state is None:
                self.missed_detections += 1
                return
        t_det = self.sim.time
        if self.jitter_std > 0.0:
            t_det = t_det + self.sim.rng.gauss(0.0, self.jitter_std)
        self._ingest_click(side, t_det, qubit, is_dark=False)

    def handle_qubit_1(self, qubit):
        self._handle_arrival(1, qubit)

    def handle_qubit_2(self, qubit):
        self._handle_arrival(2, qubit)

    def _ingest_click(self, side, t_det, qubit, *, is_dark):
        now = self.sim.time
        own_buf, other_buf = (self._buf_1, self._buf_2) if side == 1 else (self._buf_2, self._buf_1)
        # Prune expired entries on both arms (also keeps one-sided traffic bounded).
        self._prune_buffer(other_buf, now)
        self._prune_buffer(own_buf, now)

        # Find the earliest partner click in other_buf within the coincidence window.
        match_idx = None
        for idx, (t_other, _q_other, _d_other) in enumerate(other_buf):
            if abs(t_det - t_other) <= self.coincidence_window:
                match_idx = idx
                break

        if match_idx is None:
            own_buf.append((t_det, qubit, is_dark))
            return

        # Pop matched entry
        _t_other, q_other, dark_other = other_buf[match_idx]
        del other_buf[match_idx]

        if side == 1:
            q1, d1, q2, d2 = qubit, is_dark, q_other, dark_other
        else:
            q1, d1, q2, d2 = q_other, dark_other, qubit, is_dark

        self._resolve_coincidence(q1, d1, q2, d2)

    def _emit_herald(self, outcome):
        swap_id = self.sim.next_swap_id()
        msg = BellOutcome(outcome, swap_id=swap_id)
        self.counter += 1
        self.sim.add(self.delay, lambda m=msg: self.ch_out_c_1.emit(m))
        self.sim.add(self.delay, lambda m=msg: self.ch_out_c_2.emit(m))

    def _resolve_coincidence(self, q1, d1, q2, d2):
        if (not d1) and (not d2) and (q1 is not None) and (q2 is not None) and (q1.state is not None) and (q2.state is not None):
            # True two-photon coincidence: linear-optical Bell analyser succeeds with probability linear_optical_efficiency.
            if self.linear_optical_efficiency < 1.0 and self.sim.rng.random() >= self.linear_optical_efficiency:
                self.ambiguous_patterns += 1
                self._discard_qubit(q1)
                self._discard_qubit(q2)
                return

            outcome, _ = Register.bell_measure_imperfect(
                q1, q2, visibility=self.visibility, rng=self.sim.rng
            )
            self.true_heralds += 1
            self._emit_herald(outcome)
            return

        # Accidental / false herald (signal+dark or dark+dark)
        self._discard_qubit(q1)
        self._discard_qubit(q2)
        self.false_heralds += 1
        if d1 and d2:
            self.dark_dark_heralds += 1
        else:
            self.signal_dark_heralds += 1
        idx = min(int(self.sim.rng.random() * 4), 3)
        self._emit_herald(_BELL_LABELS[idx])
