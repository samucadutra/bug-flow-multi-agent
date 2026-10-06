import threading

import pytest

from bugflow.services.background import Lane


def make():
    lane = Lane("test-lane")
    return lane


def test_items_run_in_submission_order_and_never_overlap():
    lane = make()
    order, active, overlap = [], [0], []

    def task(n):
        def run():
            active[0] += 1
            if active[0] > 1:
                overlap.append(n)
            order.append(n)
            threading.Event().wait(0.01)
            active[0] -= 1

        return run

    for n in range(5):
        lane.submit(task(n))
    assert lane.wait_idle(5)
    assert order == [0, 1, 2, 3, 4] and overlap == []
    lane.shutdown(2)


def test_a_failing_task_does_not_stop_the_lane_and_reports_once():
    lane = make()
    seen, ran = [], []

    def boom():
        raise RuntimeError("boom")

    lane.submit(boom, lambda exc: seen.append(str(exc)))
    lane.submit(lambda: ran.append(1))
    assert lane.wait_idle(5)
    assert seen == ["boom"] and ran == [1]
    lane.shutdown(2)


def test_a_failing_callback_is_swallowed():
    lane = make()
    ran = []

    def bad(exc):
        raise ValueError("cleanup")

    lane.submit(lambda: 1 / 0, bad)
    lane.submit(lambda: ran.append(1))
    assert lane.wait_idle(5) and ran == [1]
    lane.shutdown(2)


def test_thread_starts_lazily_and_is_a_daemon():
    lane = make()
    assert lane.thread is None
    lane.submit(lambda: None)
    assert lane.thread is not None and lane.thread.daemon
    assert lane.thread.name == "test-lane"
    lane.shutdown(2)


def test_wait_idle_is_true_only_when_empty_and_idle():
    lane = make()
    assert lane.wait_idle(0.01) is True
    gate = threading.Event()
    lane.submit(gate.wait)
    assert lane.wait_idle(0.05) is False
    gate.set()
    assert lane.wait_idle(5) is True
    lane.shutdown(2)


def test_shutdown_drops_queued_items_and_joins():
    lane = make()
    gate, ran = threading.Event(), []
    started = threading.Event()

    def first():
        started.set()
        gate.wait()
        ran.append("first")

    lane.submit(first)
    started.wait(2)
    lane.submit(lambda: ran.append("second"))
    threading.Timer(0.1, gate.set).start()
    lane.shutdown(5)
    assert ran == ["first"]
    assert lane.thread is not None and not lane.thread.is_alive()
    assert lane.wait_idle(0.1)


def test_submit_after_shutdown_raises():
    lane = make()
    lane.shutdown(1)
    with pytest.raises(RuntimeError):
        lane.submit(lambda: None)
