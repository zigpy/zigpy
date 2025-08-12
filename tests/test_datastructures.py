import asyncio
from unittest.mock import Mock, patch

import pytest

from zigpy import datastructures
from zigpy.datastructures import RequestLimiter


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


async def test_dynamic_bounded_semaphore_hanging_bug():
    """Test semaphore hanging bug."""
    sem = datastructures.PriorityDynamicBoundedSemaphore(1)

    async def c1():
        async with sem:
            await asyncio.sleep(0)
        t2.cancel()

    async def c2():
        async with sem:
            pytest.fail("Should never get here")

    t1 = asyncio.create_task(c1())
    t2 = asyncio.create_task(c2())

    r1, r2 = await asyncio.gather(t1, t2, return_exceptions=True)
    assert r1 is None
    assert isinstance(r2, asyncio.CancelledError)

    assert not sem.locked()

    async with sem:
        assert True


def test_dynamic_bounded_semaphore_multiple_event_loops():
    """Test semaphore detecting multiple loops."""

    async def test_semaphore(sem):
        async with sem:
            await asyncio.sleep(0.1)

    async def make_semaphore():
        sem = datastructures.PriorityDynamicBoundedSemaphore(1)

        # The loop reference is lazily created so we need to actually lock the semaphore
        await asyncio.gather(test_semaphore(sem), test_semaphore(sem))

        return sem

    loop1 = asyncio.new_event_loop()
    sem = loop1.run_until_complete(make_semaphore())

    async def inner():
        await asyncio.gather(test_semaphore(sem), test_semaphore(sem))

    loop2 = asyncio.new_event_loop()

    with pytest.raises(RuntimeError):
        loop2.run_until_complete(inner())


async def test_dynamic_bounded_semaphore_runtime_limit_increase():
    """Test changing the max_value at runtime."""

    sem = datastructures.PriorityDynamicBoundedSemaphore(2)

    def set_limit(n):
        sem.max_value = n

    asyncio.get_running_loop().call_later(0.1, set_limit, 3)

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


async def test_dynamic_bounded_semaphore_errors():
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


async def test_dynamic_bounded_semaphore_cancellation():
    """Test semaphore handling errors and cancellation."""

    sem = datastructures.PriorityDynamicBoundedSemaphore(2)

    async def acquire():
        async with sem:
            await asyncio.sleep(0.2)

    tasks = []

    # First two lock up the semaphore but succeed
    tasks.append(asyncio.create_task(acquire()))
    tasks.append(asyncio.create_task(acquire()))

    # Next two get in line, will be cancelled
    tasks.append(asyncio.create_task(acquire()))
    tasks.append(asyncio.create_task(acquire()))

    await asyncio.sleep(0)
    exc = RuntimeError("Uh oh :(")
    sem.cancel_waiting(exc)

    # Last one makes it through
    tasks.append(asyncio.create_task(acquire()))

    assert (await asyncio.gather(*tasks, return_exceptions=True)) == [
        None,
        None,
        exc,
        exc,
        None,
    ]

    assert not sem.locked()


async def test_priority_lock():
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


async def test_debouncer_cleaning_bug():
    """Test debouncer bug when using heapq improperly."""
    debouncer = datastructures.Debouncer()

    obj1 = object()
    obj2 = object()
    obj3 = object()

    # Filter obj1 with an expiration of 0.3 seconds
    debouncer.filter(obj1, expire_in=0.3)

    # Slight delay to ensure different expiration times
    await asyncio.sleep(0.05)

    # Filter obj2 with an expiration of 0.1 seconds
    debouncer.filter(obj2, expire_in=0.1)

    # Another slight delay
    await asyncio.sleep(0.05)

    # Filter obj3 with an expiration of 0.2 seconds
    debouncer.filter(obj3, expire_in=0.2)

    assert debouncer.is_filtered(obj1)
    assert debouncer.is_filtered(obj2)
    assert debouncer.is_filtered(obj3)

    # Wait until after obj2 should have expired
    await asyncio.sleep(0.11)  # Total elapsed time ~0.21 seconds from start

    # Clean up expired items
    debouncer.clean()

    # obj2 should have expired, but due to the bug, it might still be filtered
    assert not debouncer.is_filtered(obj2)

    # obj1 and obj3 should still be filtered
    assert debouncer.is_filtered(obj1)
    assert debouncer.is_filtered(obj3)

    # Wait until after obj1 and obj3 should have expired
    await asyncio.sleep(0.1)  # Total elapsed time ~0.31 seconds from start

    # Clean up expired items
    debouncer.clean()

    # Now all objects should have expired
    assert not debouncer.is_filtered(obj1)
    assert not debouncer.is_filtered(obj3)

    # The queue should be empty
    assert len(debouncer._queue) == 0


async def test_request_limiter_simple_tier():
    """Test the limiter behaving like a simple semaphore with one tier."""
    limiter = datastructures.RequestLimiter(2, {0: 1})
    results = []
    order = []

    async def worker(uid):
        nonlocal order
        order.append(f"trying-{uid}")
        async with limiter(priority=0):
            order.append(f"acquired-{uid}")
            results.append(f"start-{uid}")
            await asyncio.sleep(0.05)
            results.append(f"end-{uid}")

    tasks = [asyncio.create_task(worker(i)) for i in range(3)]

    # The first two should start immediately
    await asyncio.sleep(0)
    assert limiter.active_requests == 2
    assert limiter.waiting_requests == 1
    assert "active=2, waiting=1" in repr(limiter)

    # Wait for all to complete
    await asyncio.gather(*tasks)

    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 0
    # The exact end order depends on scheduling, but the start order is what matters.
    assert results[:2] == ["start-0", "start-1"]
    assert results[2:4] == ["end-0", "end-1"]
    assert results[4] == "start-2"
    assert results[5] == "end-2"


async def test_request_limiter_cascading_priority():
    """Test the core cascading priority logic."""
    # 2 slots for low priority, 1 extra for high priority (total 3)
    limiter = datastructures.RequestLimiter(3, {0: 2 / 3, 10: 1 / 3})
    events = []

    async def worker(uid, priority, delay):
        nonlocal events
        async with limiter(priority=priority):
            events.append(f"start-{uid}(p={priority})")
            await asyncio.sleep(delay)
            events.append(f"end-{uid}(p={priority})")

    # These two should take the low-priority slots
    t1 = asyncio.create_task(worker(1, 0, 0.1))
    t2 = asyncio.create_task(worker(2, 0, 0.1))

    # This one should have to wait
    t3 = asyncio.create_task(worker(3, 0, 0.1))

    await asyncio.sleep(0)
    assert limiter.active_requests == 2
    assert limiter.waiting_requests == 1
    assert events == ["start-1(p=0)", "start-2(p=0)"]

    # This high-priority one should be able to acquire the reserved slot
    t4 = asyncio.create_task(worker(4, 10, 0.1))
    await asyncio.sleep(0)
    assert limiter.active_requests == 3
    assert limiter.waiting_requests == 1
    assert "start-4(p=10)" in events

    # No more slots available for anyone
    t5 = asyncio.create_task(worker(5, 10, 0.1))
    await asyncio.sleep(0)
    assert limiter.active_requests == 3
    assert limiter.waiting_requests == 2

    await asyncio.gather(t1, t2, t3, t4, t5)

    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 0


async def test_request_limiter_priority_queueing():
    """Test that waiters are woken up according to their priority."""
    limiter = datastructures.RequestLimiter(1, {0: 1})
    events = []

    async def worker(uid, priority):
        nonlocal events
        async with limiter(priority=priority):
            events.append(uid)
            await asyncio.sleep(0.1)  # Hold the lock long enough for others to queue

    # First task takes the only slot
    t1 = asyncio.create_task(worker(1, 0))
    await asyncio.sleep(0)  # Ensure t1 acquires the lock
    assert limiter.active_requests == 1

    # Queue up waiters with different priorities
    t2 = asyncio.create_task(worker(2, 5))  # medium
    t3 = asyncio.create_task(worker(3, 0))  # low
    t4 = asyncio.create_task(worker(4, 10))  # high

    await asyncio.sleep(0)  # Ensure all waiters have tried to acquire
    assert limiter.waiting_requests == 3

    # Wait for all tasks to complete
    await asyncio.gather(t1, t2, t3, t4)

    # The waiters should have run in priority order, not submission order
    assert events == [1, 4, 2, 3]


async def test_request_limiter_cancellation():
    """Test cancelling tasks that are waiting for or holding a slot."""
    limiter = datastructures.RequestLimiter(1, {0: 1})

    async def holder():
        async with limiter(priority=0):
            await asyncio.sleep(60)

    async def waiter():
        async with limiter(priority=0):
            pytest.fail("Waiter should not acquire the slot")

    # t1 acquires the only slot
    t1 = asyncio.create_task(holder())
    await asyncio.sleep(0)
    assert limiter.active_requests == 1

    # t2 waits in line
    t2 = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    assert limiter.waiting_requests == 1

    # Cancel the waiting task
    t2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t2

    assert limiter.waiting_requests == 0
    assert limiter.active_requests == 1

    # Now, cancel the holder task
    t1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t1

    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 0

    # The limiter should be usable again
    async with limiter(priority=0):
        assert limiter.active_requests == 1


async def test_request_limiter_invalid_priority():
    """Test that using a priority with no allocated tier raises an error."""
    limiter = datastructures.RequestLimiter(1, {10: 1})

    with pytest.raises(
        ValueError,
        match="Priority 5 is lower than the lowest known priority 10 and has no allocated capacity",
    ):
        async with limiter(priority=5):
            pytest.fail("This code should not be reached")


async def test_request_limiter_highest_priority():
    """Test that the highest priority task is always allowed to run."""
    limiter = datastructures.RequestLimiter(1, {100: 1})

    async with limiter(priority=100 + 1):
        assert limiter.active_requests == 1

        assert limiter.locked(priority=100)


async def test_limiter_initial_value_zero():
    """Tests that a limiter with zero capacity starts off locked."""
    # A limiter with 0 capacity should not allow any requests through.
    limiter = RequestLimiter(max_concurrency=0, capacities={0: 1.0})
    assert limiter.locked(priority=0)


async def test_limiter_repr():
    """Tests the string representation of the limiter in various states."""
    limiter = RequestLimiter(max_concurrency=1, capacities={0: 1.0})
    # Initial state
    assert "active=0, waiting=0" in repr(limiter)
    assert "max_concurrency=1" in repr(limiter)

    # State with one active request
    async with limiter(priority=0):
        assert "active=1, waiting=0" in repr(limiter)

        # Define a coroutine for a task that will wait
        async def waiter():
            async with limiter(priority=0):
                pass  # This part won't be reached in this test

        # Create a waiting task and let it run until it blocks
        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0)

        # State with one active and one waiting request
        assert "active=1, waiting=1" in repr(limiter)

        # Clean up the waiter task
        waiter_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter_task

    # Back to initial state after the context is exited
    assert "active=0, waiting=0" in repr(limiter)


async def test_limiter_invalid_config():
    """Tests that the limiter raises errors for invalid configurations."""
    # Test that max_concurrency must result in integer capacities for each tier.
    with pytest.raises(ValueError, match="is not an integer"):
        RequestLimiter(max_concurrency=3, capacities={0: 0.5})

    # Test that a negative max_concurrency raises a ValueError.
    with pytest.raises(ValueError):
        RequestLimiter(max_concurrency=-1, capacities={0: 1.0})


async def test_limiter_acquire_flow():
    """Tests the complete flow of acquiring, waiting, and releasing slots,
    using only the public API.
    """
    limiter = RequestLimiter(3, {0: 1.0})
    results = []

    # Use an asyncio.Event to control a "holder" task that takes up one slot.
    # This simulates a long-running request.
    holder_event = asyncio.Event()

    async def holder():
        async with limiter(priority=0):
            await holder_event.wait()
        results.append("holder_released")

    async def worker(uid):
        async with limiter(priority=0):
            results.append(uid)
        return True

    # The holder task acquires the first slot.
    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0)  # Ensure holder task runs and acquires the slot.
    assert limiter.active_requests == 1

    # Create tasks that will compete for the remaining 2 slots.
    tasks = [asyncio.create_task(worker(i)) for i in range(1, 5)]

    await asyncio.sleep(0)  # Let worker tasks run.

    # Two workers should have acquired the remaining slots. Two should be waiting.
    assert limiter.active_requests == 3  # 1 holder + 2 workers
    assert limiter.waiting_requests == 2
    assert limiter.locked(priority=0)
    assert len(results) == 2  # Only the first two workers finished their block.

    # Release the holder's slot by setting the event. This should wake up the next waiter.
    holder_event.set()
    await asyncio.sleep(0)  # Allow the awakened task to run.

    # The holder has released, and one waiting task has now acquired a slot.
    assert "holder_released" in results
    assert limiter.active_requests == 3  # 2 original workers + 1 newly awakened worker.
    assert limiter.waiting_requests == 1

    # Wait for all tasks to complete.
    await asyncio.gather(holder_task, *tasks)

    # All tasks should have run and completed.
    assert len(results) == 5  # 4 workers + "holder_released"
    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 0


async def test_limiter_acquire_cancel_waiting_task():
    """Tests cancelling a task that is waiting to acquire a slot."""
    limiter = RequestLimiter(1, {0: 1.0})

    # Task to hold the only slot and keep it busy.
    holder_task = asyncio.create_task(limiter(priority=0).__aenter__())
    await asyncio.sleep(0)
    assert limiter.active_requests == 1

    # This task will wait for the slot.
    async def waiter():
        async with limiter(priority=0):
            pytest.fail("Waiter should not acquire the slot")

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)  # Let the waiter get into the queue.
    assert limiter.waiting_requests == 1

    # Cancel the waiting task.
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    # The waiter should be removed from the queue, holder is unaffected.
    assert limiter.waiting_requests == 0
    assert limiter.active_requests == 1

    # Clean up the holder task.
    holder_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder_task

    # The slot should have been released upon cancellation of the holder.
    assert limiter.active_requests == 0


async def test_limiter_cancel_before_awoken():
    """Tests that if a waiter is cancelled, the next available waiter is woken up correctly."""
    limiter = RequestLimiter(0, {0: 1.0})
    results = []

    async def worker(uid):
        async with limiter(priority=0):
            results.append(uid)

    # Create waiters. Order matters for FIFO.
    t1 = asyncio.create_task(worker(1))
    t2 = asyncio.create_task(worker(2))
    t3 = asyncio.create_task(worker(3))

    await asyncio.sleep(0)
    assert limiter.waiting_requests == 3

    # Cancel the first waiter in the queue.
    t1.cancel()

    # Release a slot by increasing capacity. This should wake the next waiter (t2).
    limiter.max_concurrency = 1

    # Let the event loop work.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert t1.cancelled()
    assert t2.done()
    assert not t3.done()
    assert results == [2]

    # Clean up remaining tasks.
    limiter.max_concurrency = 2
    await asyncio.gather(t2, t3, return_exceptions=True)
    assert results == [2, 3]


async def test_limiter_acquire_no_hang_on_cancel():
    """Ensures that cancelling a task right as it's being woken up
    doesn't cause a hang or deadlock.
    """
    limiter = RequestLimiter(1, {0: 1.0})

    async def c1(task_to_cancel):
        async with limiter(priority=0):
            await asyncio.sleep(0.01)
            # Cancel c2 just before c1 releases the slot.
            task_to_cancel.cancel()

    async def c2():
        async with limiter(priority=0):
            pytest.fail("c2 should have been cancelled before acquiring slot")

    t2 = asyncio.create_task(c2())
    await asyncio.sleep(0)  # Give t2 a chance to get in the waiting queue.
    assert limiter.waiting_requests == 1

    t1 = asyncio.create_task(c1(t2))

    # Gather results; expect a CancelledError for t2.
    results = await asyncio.gather(t1, t2, return_exceptions=True)
    assert results[0] is None
    assert isinstance(results[1], asyncio.CancelledError)

    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 0

    # The limiter should still be usable.
    async with asyncio.timeout(1):
        async with limiter(priority=0):
            assert limiter.active_requests == 1


async def test_limiter_priority_fifo_order():
    """Tests that waiters are woken up based on priority first,
    and then by FIFO for tasks of the same priority.
    """
    # One total slot, split into two conceptual (but not enforced) tiers.
    limiter = RequestLimiter(1, {0: 1.0, 10: 0.0})
    results = []

    async def worker(uid, priority):
        async with limiter(priority=priority):
            results.append(uid)
            await asyncio.sleep(0.01)

    # Main task acquires the only slot.
    main_task = asyncio.create_task(worker("main", 10))
    await asyncio.sleep(0)
    assert limiter.active_requests == 1

    # Queue up waiters in a mixed order.
    t_low1 = asyncio.create_task(worker("low1", 0))
    t_high1 = asyncio.create_task(worker("high1", 10))
    t_low2 = asyncio.create_task(worker("low2", 0))
    t_high2 = asyncio.create_task(worker("high2", 10))

    await asyncio.sleep(0)
    assert limiter.waiting_requests == 4

    # Wait for all tasks to finish.
    await asyncio.gather(main_task, t_low1, t_high1, t_low2, t_high2)

    # Expected order: main -> high priority (FIFO) -> low priority (FIFO).
    assert results == ["main", "high1", "high2", "low1", "low2"]


async def test_limiter_multi_wake():
    """Tests that a single event (like changing max_concurrency) can wake
    up multiple waiters if enough capacity becomes available.
    """
    limiter = RequestLimiter(0, {0: 1.0})
    results = []

    async def worker(uid):
        async with limiter(priority=0):
            results.append(uid)
            await asyncio.sleep(0.01)

    # All three tasks will wait since capacity is 0.
    tasks = [asyncio.create_task(worker(i)) for i in range(3)]
    await asyncio.sleep(0)

    assert limiter.active_requests == 0
    assert limiter.waiting_requests == 3
    assert not results

    # Increase capacity to allow all waiters to run.
    limiter.max_concurrency = 3

    await asyncio.sleep(0)

    # The _wake_waiters loop should have woken all three tasks.
    assert limiter.active_requests == 3
    assert limiter.waiting_requests == 0

    await asyncio.gather(*tasks)

    # The order isn't guaranteed, so we sort the results for a stable check.
    assert sorted(results) == [0, 1, 2]
