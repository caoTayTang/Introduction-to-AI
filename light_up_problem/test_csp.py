"""CSP trace preserves search and exposes individual propagation deductions and checkpoints."""

import unittest
from dataclasses import asdict
from threading import Event

from .algorithms import backtracking_mrv_cp
from .algorithms.search import SearchLimits, SearchStatus
from .core.model import Puzzle
from .core.rules import is_goal_state
from .generator import get_sample_puzzle

ISOLATED_CELLS = Puzzle(((None, -1, None), (-1, -1, -1), (None, -1, None)))


class CSPTests(unittest.TestCase):
    def test_tracing_preserves_solution_path_counters_and_memory_estimate(self):
        fixtures = [
            ISOLATED_CELLS, Puzzle(((0,),)), Puzzle(((1,),)),
            Puzzle(((None, None), (None, None))),
            *(Puzzle(((None, None, None), (None, clue, None), (None, None, None))) for clue in range(5)),
            *(get_sample_puzzle(7, difficulty) for difficulty in ("easy", "normal", "hard")),
        ]
        for puzzle in fixtures:
            with self.subTest(board=puzzle.rows):
                baseline = asdict(backtracking_mrv_cp(puzzle))
                events = []
                result = backtracking_mrv_cp(puzzle, on_event=events.append, trace_steps=True)
                actual = asdict(result)
                baseline.pop("elapsed_seconds")
                actual.pop("elapsed_seconds")
                self.assertEqual(actual, baseline)
                self.assertEqual(result.algorithm, "csp")
                for event in events:
                    self.assertFalse(set(event.bulbs) & set(event.forbidden))
                    self.assertEqual(event.depth, len(event.bulbs))
                    self.assertIsNone(event.h)
                    self.assertIsNone(event.f)
                if result.status == SearchStatus.SOLVED:
                    self.assertTrue(is_goal_state(puzzle, result.solution))
                    self.assertEqual(events[-1].kind, "solution")
                    self.assertEqual(events[-1].bulbs, result.solution)
                    self.assertEqual(len(result.solution_path), len(result.solution) + 1)
                    for parent, child in zip(result.solution_path, result.solution_path[1:]):
                        self.assertEqual(len(set(child) - set(parent)), 1)

    def test_root_propagation_displays_each_forced_illuminator_before_goal(self):
        events = []
        result = backtracking_mrv_cp(ISOLATED_CELLS, on_event=events.append, trace_steps=True)
        self.assertIs(result.status, SearchStatus.SOLVED)
        self.assertEqual([event.kind for event in events], ["propagate"] * 4 + ["expand", "solution"])
        for count, event in enumerate(events[:4], 1):
            self.assertEqual(len(event.bulbs), count)
            self.assertEqual(event.expanded, 0)
            self.assertIn(event.focus, event.bulbs)
            self.assertIn("Only illuminator", event.detail)

    def test_numbered_wall_places_each_forced_neighbor_in_a_separate_step(self):
        puzzle = Puzzle(((None, -1, None), (None, 2, None), (-1, -1, -1)))
        events = []
        backtracking_mrv_cp(puzzle, on_event=events.append, trace_steps=True)
        forced = [event for event in events if event.kind == "propagate"]
        self.assertEqual([len(event.bulbs) for event in forced], [1, 2])
        self.assertTrue(all("Wall (1, 1)" in event.detail for event in forced))

    def test_domain_pruning_marks_wall_neighbors_and_diagonal_conflicts(self):
        for clue, reason in ((0, "is satisfied"), (1, "Diagonal conflict")):
            with self.subTest(clue=clue):
                events = []
                puzzle = Puzzle(((None, None, None), (None, clue, None), (None, None, None)))
                backtracking_mrv_cp(puzzle, on_event=events.append, trace_steps=True)
                matching = [event for event in events if event.kind == "prune" and reason in event.detail]
                self.assertTrue(matching)
                self.assertTrue(all(event.focus == (1, 1) for event in matching))
                if clue == 0:
                    self.assertEqual(set(events[0].forbidden), {(0, 1), (1, 0), (1, 2), (2, 1)})
                previous_bulbs = previous_forbidden = set()
                for event in events:
                    if event.kind == "prune":
                        self.assertEqual(set(event.bulbs), previous_bulbs)
                        self.assertTrue(set(event.forbidden) > previous_forbidden)  # No no-op deductions.
                    previous_bulbs, previous_forbidden = set(event.bulbs), set(event.forbidden)

    def test_failed_propagation_shows_actual_contradiction_then_restores_checkpoint(self):
        puzzle = Puzzle(((None, None, None), (None, 1, None), (None, None, None)))
        events = []
        result = backtracking_mrv_cp(puzzle, on_event=events.append, trace_steps=True)
        self.assertIs(result.status, SearchStatus.UNSOLVABLE)
        failures = [i for i, event in enumerate(events) if event.kind == "reject"]
        self.assertTrue(failures)
        for index in failures:
            self.assertGreaterEqual(len(events[index].bulbs), 2)  # Includes bulbs inferred after the trial.
            restored = events[index + 1]
            self.assertEqual(restored.kind, "backtrack")
            self.assertEqual(restored.bulbs, ())
            self.assertEqual(restored.forbidden, ())

    def test_mrv_wall_focus_identifies_the_actual_numbered_wall(self):
        puzzle = get_sample_puzzle(7, "easy")
        events = []
        backtracking_mrv_cp(puzzle, on_event=events.append, trace_steps=True)
        choices = [event for event in events if event.kind == "expand" and "MRV wall" in event.detail]
        self.assertTrue(choices)
        for event in choices:
            self.assertIn(event.focus, puzzle.numbered_walls())
            self.assertIn("candidate choices", event.detail)
            self.assertIn("legal branches", event.detail)

    def test_cancel_during_root_propagation_stops_before_remaining_deductions(self):
        cancelled = Event()
        events = []

        def on_event(event):
            events.append(event)
            cancelled.set()

        result = backtracking_mrv_cp(
            ISOLATED_CELLS, on_event=on_event, cancelled=cancelled.is_set, trace_steps=True,
        )
        self.assertIs(result.status, SearchStatus.CANCELLED)
        self.assertEqual([event.kind for event in events], ["propagate"])
        self.assertEqual(result.expanded, 0)

    def test_trace_limits_have_distinct_statuses(self):
        for limits, status in (
            (SearchLimits(timeout_seconds=1e-10), SearchStatus.TIMEOUT),
            (SearchLimits(memory_limit_mb=1e-9), SearchStatus.MEMORY_LIMIT),
        ):
            with self.subTest(status=status):
                result = backtracking_mrv_cp(ISOLATED_CELLS, limits, trace_steps=True)
                self.assertIs(result.status, status)
        result = backtracking_mrv_cp(
            Puzzle(((None, None), (None, None))), SearchLimits(node_limit=1), trace_steps=True,
        )
        self.assertIs(result.status, SearchStatus.NODE_LIMIT)
        self.assertEqual(result.expanded, 1)

    def test_default_callback_keeps_sampled_expand_events(self):
        events = []
        backtracking_mrv_cp(get_sample_puzzle(7, "easy"), on_event=events.append)
        self.assertEqual([event.kind for event in events], ["expand"])
