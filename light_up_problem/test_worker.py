"""Isolated worker processes: pause/step streaming and paired benchmark rows."""

import multiprocessing as mp
import queue
import unittest
from dataclasses import asdict
from threading import Event
from unittest.mock import Mock, patch

from .algorithms.search import (
    SearchEvent,
    SearchLimits,
    SearchResult,
    SearchStatus,
    astar,
    backtracking_mrv_cp,
    depth_first_search,
)
from .benchmark.runner import BenchmarkRow
from .benchmark.worker import benchmark_worker
from .core.model import Puzzle
from .worker import solver_worker


class WorkerTests(unittest.TestCase):
    def test_spawn_stream_matches_full_trace_through_single_slot_queue(self):
        puzzle = Puzzle(((None, None), (None, None)))
        for algorithm, solver in (("DFS", depth_first_search), ("A*", astar), ("CSP", backtracking_mrv_cp)):
            with self.subTest(algorithm=algorithm):
                if algorithm == "CSP":
                    puzzle = Puzzle(((None, None, None), (None, 0, None), (None, None, None)))
                expected = []
                solver(puzzle, on_event=expected.append, trace_steps=True)
                context = mp.get_context("spawn")
                messages = context.Queue(maxsize=1)
                stop, pause, step = context.Event(), context.Event(), context.Event()
                process = context.Process(target=solver_worker, args=(
                    puzzle, algorithm, SearchLimits(timeout_seconds=0), messages, stop, pause, step,
                ))
                # Keep the queue full until after the worker has started producing trace.
                messages.put(("prefilled", None))
                process.start()
                try:
                    self.assertFalse(stop.wait(0.2))
                    self.assertEqual(messages.get(timeout=5), ("prefilled", None))
                    received = []
                    while True:
                        kind, payload = messages.get(timeout=5)
                        if kind == "result":
                            self.assertEqual(payload.status, SearchStatus.SOLVED)
                            break
                        self.assertEqual(kind, "progress")
                        received.append(payload)
                    for event in received:
                        event.pop("elapsed_seconds")
                    expected_payloads = [asdict(event) for event in expected]
                    for event in expected_payloads:
                        event.pop("elapsed_seconds")
                    self.assertEqual(received, expected_payloads)
                    process.join(timeout=5)
                    self.assertEqual(process.exitcode, 0)
                finally:
                    stop.set()
                    pause.clear()
                    step.set()
                    process.join(timeout=2)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=1)
                    messages.close()
                    messages.join_thread()

    def test_csp_worker_can_pause_step_resume_or_stop_during_initial_propagation(self):
        for finish in ("resume", "stop"):
            with self.subTest(finish=finish):
                context = mp.get_context("spawn")
                messages = context.Queue(maxsize=1)
                stop, pause, step = context.Event(), context.Event(), context.Event()
                pause.set()
                process = context.Process(target=solver_worker, args=(
                    Puzzle(((None, -1, None), (-1, -1, -1), (None, -1, None))), "CSP",
                    SearchLimits(timeout_seconds=0), messages, stop, pause, step,
                ))
                process.start()
                try:
                    kind, first = messages.get(timeout=5)
                    self.assertEqual((kind, first["kind"], len(first["bulbs"])), ("progress", "propagate", 1))
                    self.assertEqual(first["expanded"], 0)
                    step.set()
                    kind, second = messages.get(timeout=5)
                    self.assertEqual((kind, second["kind"], len(second["bulbs"])), ("progress", "propagate", 2))
                    with self.assertRaises(queue.Empty):
                        messages.get(timeout=0.15)
                    if finish == "stop":
                        stop.set()
                    pause.clear()
                    step.set()
                    if finish == "resume":
                        while True:
                            kind, payload = messages.get(timeout=5)
                            if kind == "result":
                                self.assertEqual(payload.algorithm, "csp")
                                self.assertIs(payload.status, SearchStatus.SOLVED)
                                break
                            self.assertEqual(kind, "progress")
                    process.join(timeout=5)
                    self.assertEqual(process.exitcode, 0)
                finally:
                    stop.set()
                    pause.clear()
                    step.set()
                    process.join(timeout=1)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=1)
                    messages.close()

    def test_unknown_algorithm_reports_error_without_running_astar(self):
        messages = Mock()
        with patch("light_up_problem.worker.astar") as search:
            solver_worker(Puzzle(((None,),)), "unknown", SearchLimits(), messages, Event(), Event(), Event())
        search.assert_not_called()
        kind, payload = messages.put.call_args.args[0]
        self.assertEqual(kind, "error")
        self.assertIn("Unknown search algorithm: unknown", payload)

    def test_full_queue_retries_progress_result_and_errors_until_delivered(self):
        puzzle = Puzzle(((None,),))
        event = SearchEvent("expand", (), 1, 0, 0, 0, 0, 0, 0)
        result = SearchResult("dfs", SearchStatus.SOLVED)
        for fail in (False, True):
            with self.subTest(solver_error=fail):
                calls = []
                delivered = []
                messages = Mock()

                def put(message, timeout):
                    calls.append(message[0])
                    if calls.count(message[0]) <= 2:
                        raise queue.Full
                    delivered.append(message)

                def solver(*args, on_event, **kwargs):
                    on_event(event)
                    if fail:
                        raise ValueError("solver failed")
                    return result

                messages.put.side_effect = put
                with patch("light_up_problem.worker.depth_first_search", side_effect=solver) as search:
                    solver_worker(puzzle, "DFS", SearchLimits(), messages, Event(), Event(), Event())
                self.assertTrue(search.call_args.kwargs["trace_steps"])
                self.assertEqual([kind for kind, _ in delivered], ["progress", "error" if fail else "result"])

    def test_stop_releases_worker_waiting_for_queue_space(self):
        stop = Event()
        messages = Mock()

        def put(*args, **kwargs):
            stop.set()
            raise queue.Full

        messages.put.side_effect = put
        solver_worker(Puzzle(((None,),)), "DFS", SearchLimits(), messages, stop, Event(), Event())
        messages.put.assert_called_once()

    def test_spawn_worker_pauses_steps_and_returns_solution(self):
        context = mp.get_context("spawn")
        messages = context.Queue(maxsize=64)
        stop_event = context.Event()
        pause_event = context.Event()
        step_event = context.Event()
        pause_event.set()
        process = context.Process(
            target=solver_worker,
            args=(
                Puzzle(((None, None), (None, None))),
                "A*",
                SearchLimits(timeout_seconds=5, node_limit=100, progress_interval=1),
                messages,
                stop_event,
                pause_event,
                step_event,
            ),
        )
        process.start()
        try:
            kind, progress = messages.get(timeout=5)
            self.assertEqual(kind, "progress")
            self.assertEqual(progress["kind"], "expand")
            self.assertTrue(process.is_alive())  # The worker is waiting while paused.
            step_event.set()
            kind, next_progress = messages.get(timeout=5)
            self.assertEqual(kind, "progress")
            self.assertNotEqual(next_progress, progress)
            with self.assertRaises(queue.Empty):
                messages.get(timeout=0.2)  # One click must produce exactly one new state.
            pause_event.clear()
            deadline_messages = 0
            result = None
            while deadline_messages < 20:
                kind, payload = messages.get(timeout=5)
                if kind == "result":
                    result = payload
                    break
                deadline_messages += 1
            self.assertIsInstance(result, SearchResult)
            self.assertIs(result.status, SearchStatus.SOLVED)
        finally:
            stop_event.set()
            pause_event.clear()
            step_event.set()
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            messages.close()

    def test_spawn_benchmark_worker_compares_both_algorithms_on_one_input(self):
        context = mp.get_context("spawn")
        messages = context.Queue(maxsize=64)
        stop_event = context.Event()
        process = context.Process(
            target=benchmark_worker,
            args=(
                Puzzle(((None, None), (None, None)), "benchmark-fixture", "test", 9),
                SearchLimits(timeout_seconds=5, node_limit=100),
                messages,
                stop_event,
            ),
        )
        process.start()
        try:
            kind, rows = messages.get(timeout=10)
            self.assertEqual(kind, "benchmark")
            self.assertEqual([row.algorithm for row in rows], ["DFS", "ASTAR"])
            self.assertTrue(all(isinstance(row, BenchmarkRow) for row in rows))
            self.assertTrue(all(row.puzzle_id == "benchmark-fixture" for row in rows))
        finally:
            stop_event.set()
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            messages.close()


if __name__ == "__main__":
    unittest.main()
