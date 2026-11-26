from Emitter import*
from Qubits import*


class Classic_data_reader:
    """Joint Outcome Counter: pairs two classical outcome streams.

    When outcomes carry `pair_id` (via `MeasurementResult`), sides are matched
    by `pair_id` even if outcomes arrive out of order. Untagged `"0"`/`"1"`
    strings fall back to arrival-order pairing. Unmatched outcomes remain
    visible via `unmatched_1` and `unmatched_2`.
    """

    def __init__(self, id, sim=None):
        self.id = id
        self.sim = sim
        self.input_1 = Handler(self.result_1, sim=self.sim, kind="classical", max_connections=1)
        self.input_2 = Handler(self.result_2, sim=self.sim, kind="classical", max_connections=1)
        self.list_1 = []
        self.list_2 = []
        self._by_pair_1 = {}
        self._by_pair_2 = {}
        self.count_success = 0
        self.count_fail = 0
        self.count_11 = 0
        self.count_10 = 0
        self.count_01 = 0
        self.count_00 = 0

    @property
    def unmatched_1(self):
        return len(self.list_1) + len(self._by_pair_1)

    @property
    def unmatched_2(self):
        return len(self.list_2) + len(self._by_pair_2)

    def _tally(self, b1, b2):
        if b1 == "0" and b2 == "0":
            self.count_00 += 1
        elif b1 == "1" and b2 == "1":
            self.count_11 += 1
        elif b1 == "0" and b2 == "1":
            self.count_01 += 1
        elif b1 == "1" and b2 == "0":
            self.count_10 += 1

    def result_1(self, outcome):
        pid = getattr(outcome, "pair_id", None)
        if pid is not None:
            if pid in self._by_pair_2:
                self._tally(outcome, self._by_pair_2.pop(pid))
            else:
                self._by_pair_1[pid] = outcome
            return
        self.list_1.append(outcome)
        self.checker(len(self.list_1))

    def result_2(self, outcome):
        pid = getattr(outcome, "pair_id", None)
        if pid is not None:
            if pid in self._by_pair_1:
                self._tally(self._by_pair_1.pop(pid), outcome)
            else:
                self._by_pair_2[pid] = outcome
            return
        self.list_2.append(outcome)
        self.checker(len(self.list_2))

    def checker(self, length):
        if len(self.list_1) >= length and len(self.list_2) >= length:
            self._tally(self.list_1[length - 1], self.list_2[length - 1])
            del self.list_1[length - 1]
            del self.list_2[length - 1]
