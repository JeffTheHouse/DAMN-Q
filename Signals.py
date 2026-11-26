"""Slot-tagged control messages between memories and their controllers.

A memory announces a confirmed slot with `Ready(slot_id)`. A controller that
wants that exact qubit replies with `Release(slot_id)`. Bare integers are the
legacy untagged protocol: a bare `1` releases the oldest (FIFO) or newest
(LIFO) confirmed slot, as configured on the memory.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ready:
    slot_id: int


@dataclass(frozen=True)
class Release:
    slot_id: int


def enqueue_ready(queue, message):
    """Queue slot IDs from a readiness message (Ready) or legacy count (int)."""
    if isinstance(message, Ready):
        queue.append(message.slot_id)
    else:
        for _ in range(int(message)):
            queue.append(None)


def release_request(slot_id):
    """Tagged release for a known slot, or the legacy untagged request otherwise."""
    return Release(slot_id) if slot_id is not None else 1
