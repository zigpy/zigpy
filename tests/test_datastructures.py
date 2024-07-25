import asyncio
from unittest.mock import Mock, patch

import pytest

from zigpy import datastructures


async def test_dynamic_bounded_semaphore_simple_locking():
    """Test simple, serial locking/unlocking."""
    sem = datastructures.PriorityDynamicBoundedSemaphore()

    assert "unlocked" not in repr(sem) and "locked" in repr(sem)

    assert sem.value == 0
    assert sem.max_value == 0
    assert sem.locked()

    # Invalid max value
    with pytest.raises(ValueError):
        sem.max_value = -1

    assert sem.value == 0
    assert sem.max_value == 0
    assert sem.locked()

    # Max value is now specified
    sem.max_value = 1
    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    assert "unlocked" in repr(sem)

    # Semaphore can now be acquired
    async with sem:
        assert sem.value == 0
        assert sem.locked()

    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    await sem.acquire()
    assert sem.value == 0
    assert sem.locked()
    sem.release()

    assert not sem.locked()
    assert sem.max_value == 1
    assert sem.value == 1

    with pytest.raises(ValueError):
        sem.release()


async def test_dynamic_bounded_semaphore_multiple_locking():
    """Test multiple locking/unlocking."""
    sem = datastructures.PriorityDynamicBoundedSemaphore(5)

    assert sem.value == 5
    assert not sem.locked()

    async with sem:
        assert sem.value == 4
        assert not sem.locked()

        async with sem, sem, sem:
            assert sem.value == 1
            assert not sem.locked()

            async with sem:
                assert sem.locked()
                assert sem.value == 0

            assert not sem.locked()
            assert sem.value == 1

        assert sem.value == 4
        assert not sem.locked()

    assert sem.value == 5
    assert not sem.locked()


async def test_dynamic_bounded_semaphore_runtime_limit_increase(event_loop):
    """Test changing the max_value at runtime."""

    sem = datastructures.PriorityDynamicBoundedSemaphore(2)

    def set_limit(n):
        sem.max_value = n

    event_loop.call_later(0.1, set_limit, 3)

    async with sem:
        # Play with the value, testing edge cases
        sem.max_value = 100
        assert sem.value == 99
        assert not sem.locked()

        sem.max_value = 2
        assert sem.value == 1
        assert not sem.locked()

        sem.max_value = 1
        assert sem.value == 0
        assert sem.locked()

        # Setting it to `0` seems undefined but we keep track of locks so it works
        sem.max_value = 0
        assert sem.value == -1
        assert sem.locked()

        sem.max_value = 2
        assert sem.value == 1
        assert not sem.locked()

        async with sem:
            assert sem.locked()
            assert sem.value == 0
            assert sem.max_value == 2

            async with sem:
                # We're now locked until the limit is increased
                pass

            assert not sem.locked()
            assert sem.value == 1
            assert sem.max_value == 3

        assert sem.value == 2
        assert sem.max_value == 3

    assert sem.value == 3
    assert sem.max_value == 3


async def test_dynamic_bounded_semaphore_errors(event_loop):
    """Test semaphore handling errors and cancellation."""

    sem = datastructures.PriorityDynamicBoundedSemaphore(1)

    def set_limit(n):
        sem.max_value = n

    async def acquire():
        async with sem:
            await asyncio.sleep(60)

    # The first acquire call will succeed
    acquire1 = asyncio.create_task(acquire())

    # The remaining two will stall
    acquire2 = asyncio.create_task(acquire())
    acquire3 = asyncio.create_task(acquire())
    await asyncio.sleep(0.1)

    # Cancel the first one, which holds the lock
    acquire1.cancel()

    # But also cancel the second one, which was waiting
    acquire2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await acquire1

    with pytest.raises(asyncio.CancelledError):
        await acquire2

    await asyncio.sleep(0.1)

    # The third one will have succeeded
    assert sem.locked()
    assert sem.value == 0
    assert sem.max_value == 1

    acquire3.cancel()
    with pytest.raises(asyncio.CancelledError):
        await acquire3

    assert not sem.locked()
    assert sem.value == 1
    assert sem.max_value == 1


async def test_priority_lock(event_loop):
    """Test priority lock."""

    lock = datastructures.PriorityLock()

    with pytest.raises(ValueError):
        lock.max_value = 2

    assert lock.max_value == 1

    # Default priority of 0
    async with lock:
        pass

    # Overridden priority of 100
    async with lock(priority=100):
        pass

    run_order = []

    async def test_priority(priority: int, item: str):
        assert lock.locked()

        async with lock(priority=priority):
            run_order.append(item)

    # Lock first
    async with lock:
        assert lock.locked()

        names = {
            "1: first": 1,
            "5: first": 5,
            "1: second": 1,
            "1: third": 1,
            "5: second": 5,
            "-5: only": -5,
            "1: fourth": 1,
            "2: only": 2,
        }

        tasks = {
            name: asyncio.create_task(test_priority(priority + 0, name + ""))
            for name, priority in names.items()
        }

        await asyncio.sleep(0)
        tasks["1: second"].cancel()
        await asyncio.sleep(0)

    await asyncio.gather(*tasks.values(), return_exceptions=True)

    assert run_order == [
        "5: first",
        "5: second",
        "2: only",
        "1: first",
        # "1: second",
        "1: third",
        "1: fourth",
        "-5: only",
    ]


async def test_reschedulable_timeout():
    callback = Mock()
    timeout = datastructures.ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.09)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 1


async def test_reschedulable_timeout_reschedule():
    callback = Mock()
    timeout = datastructures.ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    timeout.reschedule(0.2)
    await asyncio.sleep(0.19)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 1


async def test_reschedulable_timeout_cancel():
    callback = Mock()
    timeout = datastructures.ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.09)
    timeout.cancel()
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 0


async def test_debouncer():
    """Test debouncer."""

    debouncer = datastructures.Debouncer()
    debouncer.clean()
    assert repr(debouncer) == "<Debouncer [tracked:0]>"

    obj1 = object()
    assert not debouncer.is_filtered(obj1)
    assert not debouncer.filter(obj1, expire_in=0.1)
    assert debouncer.is_filtered(obj1)

    assert debouncer.filter(obj1, expire_in=1)
    assert debouncer.filter(obj1, expire_in=0.1)
    assert debouncer.filter(obj1, expire_in=1)
    assert debouncer.is_filtered(obj1)
    assert repr(debouncer) == "<Debouncer [tracked:1]>"

    obj2 = object()
    assert not debouncer.is_filtered(obj2)
    assert not debouncer.filter(obj2, expire_in=0.2)
    assert debouncer.filter(obj1, expire_in=1)
    assert debouncer.filter(obj2, expire_in=1)
    assert debouncer.filter(obj1, expire_in=1)
    assert debouncer.filter(obj2, expire_in=1)

    assert debouncer.is_filtered(obj1)
    assert debouncer.is_filtered(obj2)
    assert repr(debouncer) == "<Debouncer [tracked:2]>"

    await asyncio.sleep(0.1)
    assert not debouncer.is_filtered(obj1)
    assert debouncer.is_filtered(obj2)
    assert repr(debouncer) == "<Debouncer [tracked:1]>"

    await asyncio.sleep(0.1)
    assert not debouncer.is_filtered(obj1)
    assert not debouncer.is_filtered(obj2)
    assert repr(debouncer) == "<Debouncer [tracked:0]>"


async def test_debouncer_low_resolution_clock():
    """Test debouncer with a low resolution clock."""

    loop = asyncio.get_running_loop()
    now = loop.time()

    # Make sure we can debounce on a low resolution clock
    with patch.object(loop, "time", return_value=now):
        debouncer = datastructures.Debouncer()

        obj1 = object()
        debouncer.filter(obj1, expire_in=0.1)
        assert debouncer.is_filtered(obj1)

        obj2 = object()
        debouncer.filter(obj2, expire_in=0.1)
        assert debouncer.is_filtered(obj2)

        # The two objects cannot be compared
        with pytest.raises(TypeError):
            obj1 < obj2  # noqa: B015
