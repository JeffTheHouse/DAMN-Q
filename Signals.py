"""Typed control and outcome messages between DAMN-Q components.

- `Ready(slot_id, memory_id)`: memory announces a confirmed slot.
- `Release(slot_id, memory_id)`: controller requests readout of that exact slot.
- `BellOutcome(bits, swap_id)`: `str` subclass (`"00"`..`"11"`) carrying swap ID.
- `MeasurementResult(bit, pair_id, basis, measurement_id)`: `str` subclass
  (`"0"` or `"1"`) carrying pair identity and measurement basis.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Ready:
    slot_id: int
    memory_id: Optional[Any] = None


@dataclass(frozen=True)
class Release:
    slot_id: int
    memory_id: Optional[Any] = None


class BellOutcome(str):
    """Classical Bell-state measurement outcome (`"00"`, `"01"`, `"10"`, `"11"`)."""

    def __new__(cls, bits, swap_id=None):
        obj = super().__new__(cls, bits)
        obj.swap_id = swap_id
        return obj


class MeasurementResult(str):
    """Classical single-qubit measurement outcome (`"0"` or `"1"`)."""

    def __new__(cls, bit, pair_id=None, basis=None, measurement_id=None):
        obj = super().__new__(cls, bit)
        obj.pair_id = pair_id
        obj.basis = basis
        obj.measurement_id = measurement_id
        return obj


def enqueue_ready(queue, message):
    """Queue `(slot_id, memory_id)` pairs from Ready or legacy int count."""
    if isinstance(message, Ready):
        queue.append((message.slot_id, message.memory_id))
    else:
        for _ in range(int(message)):
            queue.append((None, None))


def release_request(entry):
    """Tagged Release for a known slot, or legacy untagged request otherwise."""
    if isinstance(entry, tuple):
        slot_id, memory_id = entry
    else:
        slot_id, memory_id = entry, None
    return Release(slot_id, memory_id=memory_id) if slot_id is not None else 1
