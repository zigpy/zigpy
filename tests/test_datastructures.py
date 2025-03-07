import asyncio
from unittest.mock import Mock, call

import pytest

from zigpy.datastructures import (
    LimitedSizeDict,
    PacketReorder,
    PriorityDynamicBoundedSemaphore,
    PriorityLock,
    ReschedulableTimeout,
)


async def test_dynamic_bounded_semaphore_simple_locking():
    """Test simple, serial locking/unlocking."""
    sem = PriorityDynamicBoundedSemaphore()

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
    sem = PriorityDynamicBoundedSemaphore(5)

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
    sem = PriorityDynamicBoundedSemaphore(1)

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
        sem = PriorityDynamicBoundedSemaphore(1)

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

    sem = PriorityDynamicBoundedSemaphore(2)

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

    sem = PriorityDynamicBoundedSemaphore(1)

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

    sem = PriorityDynamicBoundedSemaphore(2)

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

    lock = PriorityLock()

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
    timeout = ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.09)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 1


async def test_reschedulable_timeout_reschedule():
    callback = Mock()
    timeout = ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    timeout.reschedule(0.2)
    await asyncio.sleep(0.19)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 1


async def test_reschedulable_timeout_cancel():
    callback = Mock()
    timeout = ReschedulableTimeout(callback)

    timeout.reschedule(0.1)
    assert len(callback.mock_calls) == 0
    await asyncio.sleep(0.09)
    timeout.cancel()
    await asyncio.sleep(0.02)
    assert len(callback.mock_calls) == 0


def test_limited_size_dict_insert_retrieve() -> None:
    d: LimitedSizeDict[str, int] = LimitedSizeDict(maxlen=2)
    d["a"] = 1
    d["b"] = 2
    assert len(d) == 2
    assert d["a"] == 1
    assert d["b"] == 2


def test_limited_size_dict_overflow() -> None:
    d: LimitedSizeDict[str, int] = LimitedSizeDict(maxlen=2)
    d["a"] = 1
    d["b"] = 2
    d["c"] = 3  # should pop "a"
    assert len(d) == 2
    assert "a" not in d
    assert d["b"] == 2
    assert d["c"] == 3


def test_limited_size_dict_update_moves_key_to_end() -> None:
    d: LimitedSizeDict[str, int] = LimitedSizeDict(maxlen=2)
    d["x"] = 10
    d["y"] = 20
    d["x"] = 100  # "x" now most recently updated
    d["z"] = 300  # should pop "y"
    assert len(d) == 2
    assert "y" not in d
    assert d["x"] == 100
    assert d["z"] == 300


def test_limited_size_dict_delete() -> None:
    d: LimitedSizeDict[str, int] = LimitedSizeDict(maxlen=2)
    d["a"] = 1
    d["b"] = 2
    del d["a"]
    assert len(d) == 1
    assert "a" not in d
    assert d["b"] == 2


def test_packet_reorder_in_order() -> None:
    callback = Mock()
    reorder = PacketReorder(
        window=3,
        reordering_timeout=1.0,
        packet_callback=callback,
        packet_comparison_func=lambda old, new: old == new,
    )

    reorder.handle_packet(0, "packet 0")
    reorder.handle_packet(1, "packet 1")
    assert callback.mock_calls == [call("packet 0"), call("packet 1")]
    assert reorder.expected_tsn == 2


def test_packet_reorder_huge_skip() -> None:
    callback = Mock()
    reorder = PacketReorder(
        window=20,
        reordering_timeout=1.0,
        packet_callback=callback,
        packet_comparison_func=lambda old, new: old == new,
    )

    reorder.handle_packet(200, "packet 200")
    assert callback.mock_calls == [call("packet 200")]
    assert reorder.expected_tsn == 201

    # We skip so far ahead that it exceeds the reordering window
    reorder.handle_packet(10, "packet 10")
    assert callback.mock_calls == [call("packet 200"), call("packet 10")]
    assert reorder.expected_tsn == 11


async def test_packet_reorder_out_of_order() -> None:
    callback = Mock()
    reorder = PacketReorder(
        window=10,
        reordering_timeout=0.1,
        packet_callback=callback,
        packet_comparison_func=lambda old, new: old == new,
    )
    reorder.expected_tsn = 0

    # Send over packets 5, 4, 3, 2, 1, skipping 0
    for i in range(5, 0, -1):
        reorder.handle_packet(i, f"packet {i}")
        assert callback.mock_calls == []
        assert reorder.expected_tsn == 0

    # Now TSN=0 arrives and we emit both packets
    reorder.handle_packet(0, "packet 0")
    assert callback.mock_calls == [
        call("packet 0"),
        call("packet 1"),
        call("packet 2"),
        call("packet 3"),
        call("packet 4"),
        call("packet 5"),
    ]
    assert reorder.expected_tsn == 6


async def test_packet_reorder_timeout() -> None:
    callback = Mock()
    reorder = PacketReorder(
        window=10,
        reordering_timeout=0.1,
        packet_callback=callback,
        packet_comparison_func=lambda old, new: old == new,
    )

    # Start: TSN=0 arrives -> immediate emit
    reorder.handle_packet(0, "packet 0")
    assert callback.mock_calls == [call("packet 0")]
    assert reorder.expected_tsn == 1

    # Next we skip packet 1 and receive TSN=2
    reorder.handle_packet(2, "packet 2")
    assert callback.mock_calls == [call("packet 0")]
    assert reorder.expected_tsn == 1

    # Do nothing for a bit
    await asyncio.sleep(0.2)

    # The buffered packet will be emitted
    assert callback.mock_calls == [call("packet 0"), call("packet 2")]
    assert reorder.expected_tsn == 3
