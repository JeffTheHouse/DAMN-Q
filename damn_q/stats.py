"""O(1)-memory streaming statistics with optional full sample tracing."""

import math


class StreamingStats:
    """Online Welford mean/std/min/max accumulator; keeps samples only if `trace=True`."""

    def __init__(self, *, trace=False):
        self.trace = bool(trace)
        self.count = 0
        self._mean = 0.0
        self._m2 = 0.0
        self.min_val = None
        self.max_val = None
        self.samples = []

    def add(self, value):
        x = float(value)
        self.count += 1
        delta = x - self._mean
        self._mean += delta / self.count
        delta2 = x - self._mean
        self._m2 += delta * delta2
        if self.min_val is None or x < self.min_val:
            self.min_val = x
        if self.max_val is None or x > self.max_val:
            self.max_val = x
        if self.trace:
            self.samples.append(x)

    @property
    def mean(self):
        return self._mean if self.count > 0 else None

    @property
    def std(self):
        if self.count == 0:
            return None
        return math.sqrt(max(0.0, self._m2 / self.count))

    def to_dict(self):
        if self.count == 0:
            return None
        out = {
            "count": self.count,
            "mean": self.mean,
            "std": self.std,
            "min": self.min_val,
            "max": self.max_val,
        }
        if self.trace:
            out["samples"] = list(self.samples)
        return out
