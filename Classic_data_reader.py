from collections import deque

from Emitter import *
from Qubits import *


class Classic_data_reader:
    """Joint Outcome Counter: pairs two classical outcome streams.

    Two distinct metrics are maintained so dark counts and other untagged clicks
    never inflate pair-ID-matched quantum outcomes:

    1. **Pair-ID-matched outcomes** (`count_00`, `count_01`, `count_10`, `count_11`):
       Only outcomes carrying a non-None `pair_id` are paired by `pair_id` (even
       if they arrive out of order). Untagged arrivals (including dark counts)
       are never added to these counts.
    2. **Windowed physical coincidences** (`coincidence_00`, `coincidence_01`,
       `coincidence_10`, `coincidence_11`, `true_pair_coincidences`,
       `accidental_coincidences`):
       All clicks (real detections and dark counts) on both inputs are matched
       chronologically iff `|t_1 - t_2| <= coincidence_window`. Coincidences
       where both clicks share the same non-None `pair_id` and neither is a dark
       count increment `true_pair_coincidences`; all other windowed coincidences
       increment `accidental_coincidences`.
    """

    def __init__(self, id, sim=None, coincidence_window=0.0):
        if coincidence_window < 0:
            raise ValueError(f"coincidence_window must be >= 0, got {coincidence_window}")
        self.id = id
        self.sim = sim
        self.coincidence_window = float(coincidence_window)
        self.input_1 = Handler(self.result_1, sim=self.sim, kind="classical", max_connections=1)
        self.input_2 = Handler(self.result_2, sim=self.sim, kind="classical", max_connections=1)
        self._by_pair_1 = {}
        self._by_pair_2 = {}
        self._coinc_q1 = deque()
        self._coinc_q2 = deque()
        self.count_success = 0
        self.count_fail = 0
        self.count_11 = 0
        self.count_10 = 0
        self.count_01 = 0
        self.count_00 = 0
        self.coincidence_11 = 0
        self.coincidence_10 = 0
        self.coincidence_01 = 0
        self.coincidence_00 = 0
        self.true_pair_coincidences = 0
        self.accidental_coincidences = 0
        self.untagged_1 = 0
        self.untagged_2 = 0
        self.dark_clicks_1 = 0
        self.dark_clicks_2 = 0

    @property
    def unmatched_1(self):
        return len(self._by_pair_1)

    @property
    def unmatched_2(self):
        return len(self._by_pair_2)

    def _now(self):
        return self.sim.time if self.sim is not None else 0.0

    def _tally(self, b1, b2):
        if b1 == "0" and b2 == "0":
            self.count_00 += 1
        elif b1 == "1" and b2 == "1":
            self.count_11 += 1
        elif b1 == "0" and b2 == "1":
            self.count_01 += 1
        elif b1 == "1" and b2 == "0":
            self.count_10 += 1

    def _tally_coincidence(self, b1, b2, is_true_pair):
        if b1 == "0" and b2 == "0":
            self.coincidence_00 += 1
        elif b1 == "1" and b2 == "1":
            self.coincidence_11 += 1
        elif b1 == "0" and b2 == "1":
            self.coincidence_01 += 1
        elif b1 == "1" and b2 == "0":
            self.coincidence_10 += 1
        if is_true_pair:
            self.true_pair_coincidences += 1
        else:
            self.accidental_coincidences += 1

    def _record_coincidence(self, side, outcome, pid, is_dark):
        now = self._now()
        w = self.coincidence_window
        if side == 1:
            own_q, other_q = self._coinc_q1, self._coinc_q2
        else:
            own_q, other_q = self._coinc_q2, self._coinc_q1

        # Drop clicks on both sides that are already older than the window:
        # monotonic time guarantees they can never match any future click.
        while other_q and (now - other_q[0][0]) > w:
            other_q.popleft()
        while own_q and (now - own_q[0][0]) > w:
            own_q.popleft()

        if other_q and abs(now - other_q[0][0]) <= w:
            _t_other, b_other, pid_other, dark_other = other_q.popleft()
            is_true = (
                (not is_dark)
                and (not dark_other)
                and (pid is not None)
                and (pid == pid_other)
            )
            if side == 1:
                self._tally_coincidence(outcome, b_other, is_true)
            else:
                self._tally_coincidence(b_other, outcome, is_true)
        else:
            own_q.append((now, outcome, pid, is_dark))

    def result_1(self, outcome):
        pid = getattr(outcome, "pair_id", None)
        is_dark = bool(getattr(outcome, "is_dark_count", False))
        if is_dark:
            self.dark_clicks_1 += 1
        if pid is not None:
            if pid in self._by_pair_2:
                self._tally(outcome, self._by_pair_2.pop(pid))
            else:
                self._by_pair_1[pid] = outcome
        else:
            self.untagged_1 += 1
        self._record_coincidence(1, outcome, pid, is_dark)

    def result_2(self, outcome):
        pid = getattr(outcome, "pair_id", None)
        is_dark = bool(getattr(outcome, "is_dark_count", False))
        if is_dark:
            self.dark_clicks_2 += 1
        if pid is not None:
            if pid in self._by_pair_1:
                self._tally(self._by_pair_1.pop(pid), outcome)
            else:
                self._by_pair_2[pid] = outcome
        else:
            self.untagged_2 += 1
        self._record_coincidence(2, outcome, pid, is_dark)

    def coincidence_summary(self):
        return {
            "window": self.coincidence_window,
            "00": self.coincidence_00,
            "01": self.coincidence_01,
            "10": self.coincidence_10,
            "11": self.coincidence_11,
            "total": self.coincidence_00 + self.coincidence_01 + self.coincidence_10 + self.coincidence_11,
            "true_pair_coincidences": self.true_pair_coincidences,
            "accidental_coincidences": self.accidental_coincidences,
            "untagged_1": self.untagged_1,
            "untagged_2": self.untagged_2,
            "dark_clicks_1": self.dark_clicks_1,
            "dark_clicks_2": self.dark_clicks_2,
        }
