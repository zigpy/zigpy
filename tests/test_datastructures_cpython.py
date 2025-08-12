"""CPython semaphore unit tests minimally modified to work with RequestLimiter."""

# ruff: noqa: PT009, PT027

import asyncio
import collections
import re
import sys
import unittest
from unittest import mock

STR_RGX_REPR = (
    r"^<(?P<class>.*?) object at (?P<address>.*?)"
    r"\[(?P<extras>"
    r"(set|unset|locked|unlocked|filling|draining|resetting|broken)"
    r"(, value:\d)?"
    r"(, waiters:\d+)?"
    r"(, waiters:\d+\/\d+)?"  # barrier
    r")\]>\Z"
)
RGX_REPR = re.compile(STR_RGX_REPR)


class SemaphoreTests(unittest.IsolatedAsyncioTestCase):
    def test_initial_value_zero(self):
        sem = asyncio.Semaphore(0)
        self.assertTrue(sem.locked())

    async def test_repr(self):
        sem = asyncio.Semaphore()
        self.assertTrue(repr(sem).endswith("[unlocked, value:1]>"))
        self.assertTrue(RGX_REPR.match(repr(sem)))

        await sem.acquire()
        self.assertTrue(repr(sem).endswith("[locked]>"))
        self.assertTrue("waiters" not in repr(sem))
        self.assertTrue(RGX_REPR.match(repr(sem)))

        if sem._waiters is None:
            sem._waiters = collections.deque()

        sem._waiters.append(mock.Mock())
        self.assertTrue("waiters:1" in repr(sem))
        self.assertTrue(RGX_REPR.match(repr(sem)))

        sem._waiters.append(mock.Mock())
        self.assertTrue("waiters:2" in repr(sem))
        self.assertTrue(RGX_REPR.match(repr(sem)))

    async def test_semaphore(self):
        sem = asyncio.Semaphore()
        self.assertEqual(1, sem._value)

        with self.assertRaisesRegex(
            TypeError,
            "object Semaphore can't be used in 'await' expression",
        ):
            await sem

        self.assertFalse(sem.locked())
        self.assertEqual(1, sem._value)

    def test_semaphore_value(self):
        self.assertRaises(ValueError, asyncio.Semaphore, -1)

    async def test_acquire(self):
        sem = asyncio.Semaphore(3)
        result = []

        self.assertTrue(await sem.acquire())
        self.assertTrue(await sem.acquire())
        self.assertFalse(sem.locked())

        async def c1(result):
            await sem.acquire()
            result.append(1)
            return True

        async def c2(result):
            await sem.acquire()
            result.append(2)
            return True

        async def c3(result):
            await sem.acquire()
            result.append(3)
            return True

        async def c4(result):
            await sem.acquire()
            result.append(4)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)
        self.assertEqual([1], result)
        self.assertTrue(sem.locked())
        self.assertEqual(2, len(sem._waiters))
        self.assertEqual(0, sem._value)

        t4 = asyncio.create_task(c4(result))

        sem.release()
        sem.release()
        self.assertEqual(0, sem._value)

        await asyncio.sleep(0)
        self.assertEqual(0, sem._value)
        self.assertEqual(3, len(result))
        self.assertTrue(sem.locked())
        self.assertEqual(1, len(sem._waiters))
        self.assertEqual(0, sem._value)

        self.assertTrue(t1.done())
        self.assertTrue(t1.result())
        race_tasks = [t2, t3, t4]
        done_tasks = [t for t in race_tasks if t.done() and t.result()]
        self.assertEqual(2, len(done_tasks))

        # cleanup locked semaphore
        sem.release()
        await asyncio.gather(*race_tasks)

    async def test_acquire_cancel(self):
        sem = asyncio.Semaphore()
        await sem.acquire()

        acquire = asyncio.create_task(sem.acquire())
        asyncio.get_running_loop().call_soon(acquire.cancel)
        with self.assertRaises(asyncio.CancelledError):
            await acquire
        self.assertTrue(
            (not sem._waiters) or all(waiter.done() for waiter in sem._waiters)
        )

    async def test_acquire_cancel_before_awoken(self):
        sem = asyncio.Semaphore(value=0)

        t1 = asyncio.create_task(sem.acquire())
        t2 = asyncio.create_task(sem.acquire())
        t3 = asyncio.create_task(sem.acquire())
        t4 = asyncio.create_task(sem.acquire())

        await asyncio.sleep(0)

        t1.cancel()
        t2.cancel()
        sem.release()

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        num_done = sum(t.done() for t in [t3, t4])
        self.assertEqual(num_done, 1)
        self.assertTrue(t3.done())
        self.assertFalse(t4.done())

        t3.cancel()
        t4.cancel()
        await asyncio.sleep(0)

    async def test_acquire_hang(self):
        sem = asyncio.Semaphore(value=0)

        t1 = asyncio.create_task(sem.acquire())
        t2 = asyncio.create_task(sem.acquire())
        await asyncio.sleep(0)

        t1.cancel()
        sem.release()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(sem.locked())
        self.assertTrue(t2.done())

    async def test_acquire_no_hang(self):
        sem = asyncio.Semaphore(1)

        async def c1():
            async with sem:
                await asyncio.sleep(0)
            t2.cancel()

        async def c2():
            async with sem:
                self.assertFalse(True)

        t1 = asyncio.create_task(c1())
        t2 = asyncio.create_task(c2())

        r1, r2 = await asyncio.gather(t1, t2, return_exceptions=True)
        self.assertTrue(r1 is None)
        self.assertTrue(isinstance(r2, asyncio.CancelledError))

        await asyncio.wait_for(sem.acquire(), timeout=1.0)

    def test_release_not_acquired(self):
        sem = asyncio.BoundedSemaphore()

        self.assertRaises(ValueError, sem.release)

    async def test_release_no_waiters(self):
        sem = asyncio.Semaphore()
        await sem.acquire()
        self.assertTrue(sem.locked())

        sem.release()
        self.assertFalse(sem.locked())

    async def test_acquire_fifo_order(self):
        sem = asyncio.Semaphore(1)
        result = []

        async def coro(tag):
            await sem.acquire()
            result.append(f"{tag}_1")
            await asyncio.sleep(0.01)
            sem.release()

            await sem.acquire()
            result.append(f"{tag}_2")
            await asyncio.sleep(0.01)
            sem.release()

        async with asyncio.TaskGroup() as tg:
            tg.create_task(coro("c1"))
            tg.create_task(coro("c2"))
            tg.create_task(coro("c3"))

        self.assertEqual(["c1_1", "c2_1", "c3_1", "c1_2", "c2_2", "c3_2"], result)

    async def test_acquire_fifo_order_2(self):
        sem = asyncio.Semaphore(1)
        result = []

        async def c1(result):
            await sem.acquire()
            result.append(1)
            return True

        async def c2(result):
            await sem.acquire()
            result.append(2)
            sem.release()
            await sem.acquire()
            result.append(4)
            return True

        async def c3(result):
            await sem.acquire()
            result.append(3)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)

        sem.release()
        sem.release()

        tasks = [t1, t2, t3]
        await asyncio.gather(*tasks)
        self.assertEqual([1, 2, 3, 4], result)

    async def test_acquire_fifo_order_3(self):
        sem = asyncio.Semaphore(0)
        result = []

        async def c1(result):
            await sem.acquire()
            result.append(1)
            return True

        async def c2(result):
            await sem.acquire()
            result.append(2)
            return True

        async def c3(result):
            await sem.acquire()
            result.append(3)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)

        t1.cancel()

        await asyncio.sleep(0)

        sem.release()
        sem.release()

        tasks = [t1, t2, t3]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual([2, 3], result)

    # Skip for Python < 3.13
    @unittest.skipIf(
        sys.version_info < (3, 13),
        "This test requires Python 3.13 or later",
    )
    async def test_acquire_fifo_order_4(self):
        # Test that a successful `acquire()` will wake up multiple Tasks
        # that were waiting in the Semaphore queue due to FIFO rules.
        sem = asyncio.Semaphore(0)
        result = []
        count = 0  # noqa: F841

        async def c1(result):
            # First task immediately waits for semaphore.  It will be awoken by c2.
            self.assertEqual(sem._value, 0)
            await sem.acquire()
            # We should have woken up all waiting tasks now.
            self.assertEqual(sem._value, 0)
            # Create a fourth task.  It should run after c3, not c2.
            nonlocal t4
            t4 = asyncio.create_task(c4(result))
            result.append(1)
            return True

        async def c2(result):
            # The second task begins by releasing semaphore three times,
            # for c1, c2, and c3.
            sem.release()
            sem.release()
            sem.release()
            self.assertEqual(sem._value, 2)
            # It is locked, because c1 hasn't woken up yet.
            self.assertTrue(sem.locked())
            await sem.acquire()
            result.append(2)
            return True

        async def c3(result):
            await sem.acquire()
            self.assertTrue(sem.locked())
            result.append(3)
            return True

        async def c4(result):
            result.append(4)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))
        t4 = None

        await asyncio.sleep(0)
        # Three tasks are in the queue, the first hasn't woken up yet.
        self.assertEqual(sem._value, 2)
        self.assertEqual(len(sem._waiters), 3)
        await asyncio.sleep(0)

        assert t4 is not None
        tasks = [t1, t2, t3, t4]
        await asyncio.gather(*tasks)
        self.assertEqual([1, 2, 3, 4], result)
