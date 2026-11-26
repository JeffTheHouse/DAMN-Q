import pytest

from Emitter import scheduler
from Scheduler import Scheduler


def test_events_execute_in_time_order():
    fired = []
    scheduler.add(5, lambda: fired.append(("second", scheduler._time)))
    scheduler.add(2, lambda: fired.append(("first", scheduler._time)))

    scheduler.run(10)

    assert fired == [("first", 2), ("second", 5)]


def test_event_beyond_horizon_is_preserved():
    fired = []
    scheduler.add(10, lambda: fired.append(scheduler._time))

    scheduler.run(5)
    assert fired == []

    scheduler.run(11)
    assert fired == [10]


def test_scheduler_instances_are_isolated():
    s1 = Scheduler()
    s2 = Scheduler()
    assert s1 is not s2

    fired_1 = []
    fired_2 = []
    s1.add(3, lambda: fired_1.append(s1.time))
    s2.add(5, lambda: fired_2.append(s2.time))

    s1.run(10)
    assert fired_1 == [3]
    assert fired_2 == []
    assert s2.time == 0

    s2.run(10)
    assert fired_2 == [5]


def test_same_time_events_preserve_fifo_order():
    s = Scheduler()
    order = []
    s.add(2, lambda: order.append("a"))
    s.add(2, lambda: order.append("b"))
    s.add(2, lambda: order.append("c"))

    s.run(5)
    assert order == ["a", "b", "c"]


def test_step_and_cancellation():
    s = Scheduler()
    fired = []
    h1 = s.add(1, lambda: fired.append("e1"))
    h2 = s.add(2, lambda: fired.append("e2"))
    s.add(3, lambda: fired.append("e3"))

    s.cancel(h2)
    assert h2.cancelled
    assert not h1.cancelled

    assert s.step(until=0.5) is False
    assert fired == []

    assert s.step() is True
    assert fired == ["e1"]
    assert s.time == 1

    assert s.step() is True
    assert fired == ["e1", "e3"]
    assert s.time == 3

    assert s.step() is False


def test_negative_delay_raises():
    s = Scheduler()
    with pytest.raises(ValueError):
        s.add(-1, lambda: None)


def test_cancel_rejects_foreign_handle():
    s1 = Scheduler()
    s2 = Scheduler()
    fired = []
    handle_a = s1.add(2, lambda: fired.append("a"))

    with pytest.raises(ValueError):
        s2.cancel(handle_a)

    assert not handle_a.cancelled
    s1.run(5)
    assert fired == ["a"]
