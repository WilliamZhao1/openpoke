"""Regression checks for evaluation-owned background task draining."""

import asyncio
import unittest

from evals.agent_overload.engine import capture_tasks, drain


class EvaluationTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_background_child_does_not_abort_worker_and_callback_drain(self):
        completed = []

        async def callback():
            await asyncio.sleep(0)
            completed.append("callback")

        async def worker():
            await asyncio.sleep(0)
            completed.append("worker")
            asyncio.create_task(callback())

        async with capture_tasks() as tasks:
            connection_attempt = asyncio.create_task(asyncio.sleep(0))
            connection_attempt.cancel()
            await asyncio.gather(connection_attempt, return_exceptions=True)
            asyncio.create_task(worker())
            await drain(tasks)

        self.assertTrue(connection_attempt.cancelled())
        self.assertEqual(completed, ["worker", "callback"])

    async def test_real_background_failure_is_preserved_alongside_cancelled_child(self):
        failure = RuntimeError("synthetic background failure")

        async def fail():
            raise failure

        async with capture_tasks() as tasks:
            cancelled = asyncio.create_task(asyncio.sleep(0))
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            asyncio.create_task(fail())
            with self.assertRaises(RuntimeError) as caught:
                await drain(tasks)

        self.assertIs(caught.exception, failure)

    async def test_cancelling_the_drain_still_propagates_and_cleans_up_pending_work(self):
        started = asyncio.Event()
        released = asyncio.Event()

        async def worker():
            started.set()
            await released.wait()

        async with capture_tasks() as tasks:
            pending = asyncio.create_task(worker())
            draining = asyncio.create_task(drain(tasks))
            await started.wait()
            await asyncio.sleep(0)
            draining.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await draining
            self.assertTrue(pending.cancelled())

    async def test_case_deadline_still_times_out_and_cancels_pending_work(self):
        released = asyncio.Event()
        async with capture_tasks() as tasks:
            pending = asyncio.create_task(released.wait())
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(drain(tasks), timeout=0.01)
            self.assertTrue(pending.cancelled())

    async def test_exception_return_value_is_not_mistaken_for_a_task_failure(self):
        async def complete():
            return RuntimeError("a returned value, not a raised error")

        async with capture_tasks() as tasks:
            completed = asyncio.create_task(complete())
            await drain(tasks)

        self.assertIsInstance(completed.result(), RuntimeError)


if __name__ == "__main__":
    unittest.main()
