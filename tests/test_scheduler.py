import pytest

from Emitter import scheduler
from Scheduler import Scheduler


def test_events_execute_in_time_order():
    fired = []
    scheduler.add(5, lambda: fired.append(("second", scheduler._time)))
    scheduler.add(2, lambda: fired.append(("first", scheduler._time)))

    scheduler.run(10)

    assert fired == [("first", 2), ("second", 5)]


@pytest.mark.xfail(
    strict=True,
    reason="Scheduler.run pops and discards the first event beyond the run horizon.",
)
def test_event_beyond_horizon_is_preserved():
    fired = []
    scheduler.add(10, lambda: fired.append(scheduler._time))

    scheduler.run(5)
    assert fired == []

    scheduler.run(11)
    assert fired == [10]


@pytest.mark.xfail(
    strict=True,
    reason="Scheduler is currently a process-wide singleton sharing clock and queue.",
)
def test_scheduler_instances_are_isolated():
    s1 = Scheduler()
    s2 = Scheduler()
    assert s1 is not s2
