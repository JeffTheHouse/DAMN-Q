"""Slot-tagged control messages between memories and their controllers.

A memory announces a confirmed slot with `Ready(slot_id, memory_id)`.
A controller that wants that exact qubit replies with
`Release(slot_id, memory_id)`. A memory ignores any `Release` whose
`memory_id` is set and does not match its own `id`.

Bare integers remain supported as the legacy untagged protocol: a bare `1`
releases the oldest (FIFO) or newest (LIFO) confirmed slot on the receiving
memory.
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
