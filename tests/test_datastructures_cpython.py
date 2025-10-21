"""CPython semaphore unit tests minimally modified to work with RequestLimiter."""

# ruff: noqa: PT009, PT027

import asyncio
import re
import unittest

from zigpy.datastructures import RequestLimiter

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
        sem = RequestLimiter(max_concurrency=0, capacities={1: 1.0})
        self.assertTrue(sem.locked(priority=1))

    async def test_repr(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        # RequestLimiter format: <RequestLimiter(max_concurrency=1, active=0, waiting=0)>
        self.assertIn("max_concurrency=1", repr(sem))
        self.assertIn("active=0", repr(sem))
        self.assertIn("waiting=0", repr(sem))

        await sem._acquire(priority=1)
        self.assertIn("active=1", repr(sem))
        self.assertIn("waiting=0", repr(sem))

        # Start tasks that will wait since semaphore is already acquired
        task1 = asyncio.create_task(sem._acquire(priority=1))
        await asyncio.sleep(0)  # Let task1 start and get queued
        self.assertIn("waiting=1", repr(sem))

        task2 = asyncio.create_task(sem._acquire(priority=1))
        await asyncio.sleep(0)  # Let task2 start and get queued
        self.assertIn("waiting=2", repr(sem))

        # Clean up
        task1.cancel()
        task2.cancel()

        await asyncio.gather(task1, task2, return_exceptions=True)

    async def test_semaphore(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        # self.assertEqual(1, sem.active_requests)

        with self.assertRaisesRegex(
            TypeError,
            "object RequestLimiter can't be used in 'await' expression",
        ):
            await sem

        self.assertFalse(sem.locked(priority=1))
        # self.assertEqual(1, sem.active_requests)

    def test_semaphore_value(self):
        self.assertRaises(ValueError, RequestLimiter, -1, {})

    async def test_acquire(self):
        sem = RequestLimiter(max_concurrency=3, capacities={1: 1.0})
        result = []

        self.assertTrue(await sem._acquire(priority=1))
        self.assertTrue(await sem._acquire(priority=1))
        self.assertFalse(sem.locked(priority=1))

        async def c1(result):
            await sem._acquire(priority=1)
            result.append(1)
            return True

        async def c2(result):
            await sem._acquire(priority=1)
            result.append(2)
            return True

        async def c3(result):
            await sem._acquire(priority=1)
            result.append(3)
            return True

        async def c4(result):
            await sem._acquire(priority=1)
            result.append(4)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)
        self.assertEqual([1], result)
        self.assertTrue(sem.locked(priority=1))
        self.assertEqual(2, sem.waiting_requests)
        # self.assertEqual(0, sem.active_requests)

        t4 = asyncio.create_task(c4(result))

        sem._release(priority=1)
        sem._release(priority=1)
        # self.assertEqual(3, sem.active_requests)

        await asyncio.sleep(0)
        # self.assertEqual(0, sem.active_requests)
        self.assertEqual(3, len(result))
        self.assertTrue(sem.locked(priority=1))
        self.assertEqual(1, sem.waiting_requests)
        # self.assertEqual(0, sem.active_requests)

        self.assertTrue(t1.done())
        self.assertTrue(t1.result())
        race_tasks = [t2, t3, t4]
        done_tasks = [t for t in race_tasks if t.done() and t.result()]
        self.assertEqual(2, len(done_tasks))

        # cleanup locked semaphore
        sem._release(priority=1)
        await asyncio.gather(*race_tasks)

    async def test_acquire_cancel(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        await sem._acquire(priority=1)

        acquire = asyncio.create_task(sem._acquire(priority=1))
        asyncio.get_running_loop().call_soon(acquire.cancel)
        with self.assertRaises(asyncio.CancelledError):
            await acquire
        self.assertTrue(
            (not sem._waiters) or all(waiter.done() for waiter in sem._waiters)
        )

    async def test_acquire_cancel_before_awoken(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})

        t1 = asyncio.create_task(sem._acquire(priority=1))
        t2 = asyncio.create_task(sem._acquire(priority=1))
        t3 = asyncio.create_task(sem._acquire(priority=1))
        t4 = asyncio.create_task(sem._acquire(priority=1))

        await asyncio.sleep(0)

        t1.cancel()
        t2.cancel()
        sem._release(priority=1)

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
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})

        t1 = asyncio.create_task(sem._acquire(priority=1))
        t2 = asyncio.create_task(sem._acquire(priority=1))
        await asyncio.sleep(0)

        t1.cancel()
        sem._release(priority=1)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(sem.locked(priority=1))
        self.assertTrue(t2.done())

    async def test_acquire_no_hang(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})

        async def c1():
            async with sem(priority=1):
                await asyncio.sleep(0)
            t2.cancel()

        async def c2():
            async with sem(priority=1):
                self.assertFalse(True)

        t1 = asyncio.create_task(c1())
        t2 = asyncio.create_task(c2())

        r1, r2 = await asyncio.gather(t1, t2, return_exceptions=True)
        self.assertTrue(r1 is None)
        self.assertTrue(isinstance(r2, asyncio.CancelledError))

        await asyncio.wait_for(sem._acquire(priority=1), timeout=1.0)

    def test_release_not_acquired(self):
        sem = asyncio.BoundedSemaphore()

        self.assertRaises(ValueError, sem.release)

    async def test_release_no_waiters(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        await sem._acquire(priority=1)
        self.assertTrue(sem.locked(priority=1))

        sem._release(priority=1)
        self.assertFalse(sem.locked(priority=1))

    async def test_acquire_fifo_order(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        result = []

        async def coro(tag):
            await sem._acquire(priority=1)
            result.append(f"{tag}_1")
            await asyncio.sleep(0.01)
            sem._release(priority=1)

            await sem._acquire(priority=1)
            result.append(f"{tag}_2")
            await asyncio.sleep(0.01)
            sem._release(priority=1)

        tasks = []
        tasks.append(asyncio.create_task(coro("c1")))
        tasks.append(asyncio.create_task(coro("c2")))
        tasks.append(asyncio.create_task(coro("c3")))
        await asyncio.gather(*tasks, return_exceptions=True)

        self.assertEqual(["c1_1", "c2_1", "c3_1", "c1_2", "c2_2", "c3_2"], result)

    async def test_acquire_fifo_order_2(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        result = []

        async def c1(result):
            await sem._acquire(priority=1)
            result.append(1)
            return True

        async def c2(result):
            await sem._acquire(priority=1)
            result.append(2)
            sem._release(priority=1)
            await sem._acquire(priority=1)
            result.append(4)
            return True

        async def c3(result):
            await sem._acquire(priority=1)
            result.append(3)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)

        sem._release(priority=1)
        sem._release(priority=1)

        tasks = [t1, t2, t3]
        await asyncio.gather(*tasks)
        # self.assertEqual([1, 2, 3, 4], result)
        self.assertEqual([1, 2, 4, 3], result)  # We differ here

    async def test_acquire_fifo_order_3(self):
        sem = RequestLimiter(max_concurrency=1, capacities={1: 1.0})
        result = []

        async def c1(result):
            await sem._acquire(priority=1)
            result.append(1)
            return True

        async def c2(result):
            await sem._acquire(priority=1)
            result.append(2)
            return True

        async def c3(result):
            await sem._acquire(priority=1)
            result.append(3)
            return True

        t1 = asyncio.create_task(c1(result))
        t2 = asyncio.create_task(c2(result))
        t3 = asyncio.create_task(c3(result))

        await asyncio.sleep(0)

        t1.cancel()

        await asyncio.sleep(0)

        sem._release(priority=1)
        sem._release(priority=1)

        tasks = [t1, t2, t3]
        await asyncio.gather(*tasks, return_exceptions=True)
        # self.assertEqual([2, 3], result)
        self.assertEqual([1, 2, 3], result)  # We differ here
