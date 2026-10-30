"""Solver correctness: valid solutions, minimum cost, unsolvable and limit statuses."""

import itertools
import unittest

from .algorithms.search import SearchLimits, SearchStatus, astar, depth_first_search
from .core.model import Puzzle
from .core.rules import is_goal_state


class SearchTests(unittest.TestCase):
    def test_full_trace_preserves_results_and_records_each_expansion_and_attempt(self):
        fixtures = (
            Puzzle(((None, None), (None, None))),
            Puzzle(((None, None, None), (None, 1, None), (None, None, None))),
            Puzzle(((1,),)),
        )
        for solver in (depth_first_search, astar):
            for puzzle in fixtures:
                with self.subTest(solver=solver.__name__, rows=puzzle.rows):
                    baseline = solver(puzzle)
                    events = []
                    # Full trace must ignore the normal expansion sampling interval.
                    result = solver(puzzle, SearchLimits(progress_interval=1000),
                                    on_event=events.append, trace_steps=True)
                    for field in ("status", "solution", "solution_path", "solution_cost",
                                  "expanded", "generated", "max_frontier", "peak_memory_bytes"):
                        self.assertEqual(getattr(result, field), getattr(baseline, field), field)
                    expanded = [event.expanded for event in events if event.kind == "expand"]
                    self.assertEqual(expanded, list(range(1, result.expanded + 1)))
                    attempts = {(event.expanded, event.bulbs) for event in events if event.kind == "assign"}
                    accepted = [event for event in events if event.kind in {"accept", "queue"}]
                    self.assertEqual(len(accepted), result.generated)
                    for event in accepted:
                        self.assertIn((event.expanded, event.bulbs), attempts)
                        self.assertEqual(event.g, len(event.bulbs))
                        self.assertEqual(event.f, event.g + event.h)
                    for event in events:
                        self.assertEqual(event.depth, len(event.bulbs))
                        if event.kind == "assign":
                            self.assertIn(event.focus, event.bulbs)
                        if solver is astar and event.kind == "assign":
                            self.assertIsNone(event.h)  # No invented score before evaluating the candidate.
                            self.assertIsNone(event.f)
                    if result.status == SearchStatus.SOLVED:
                        self.assertEqual(events[-1].kind, "solution")
                        self.assertEqual(events[-1].bulbs, result.solution)
                    else:
                        self.assertIn("reject", [event.kind for event in events])
                        for event in events:
                            if event.kind == "reject":
                                self.assertTrue(event.detail)

    def test_dfs_trace_returns_to_parent_before_expanding_sibling(self):
        puzzle = Puzzle(((None, None, None), (None, 1, None), (None, None, None)))
        events = []
        depth_first_search(puzzle, on_event=events.append, trace_steps=True)
        backtracks = [event for event in events if event.kind == "backtrack"]
        self.assertTrue(backtracks)
        for event in backtracks:
            self.assertNotIn(event.focus, event.bulbs)  # The abandoned placement is removed.
        last_expanded = ()
        returned_to = None
        for event in events:
            if event.kind == "backtrack":
                returned_to = event.bulbs
            if event.kind == "expand":
                if not set(last_expanded) <= set(event.bulbs):
                    self.assertIsNotNone(returned_to)
                    self.assertTrue(set(returned_to) < set(event.bulbs))
                last_expanded = event.bulbs
                returned_to = None

    def test_dfs_descends_after_first_valid_candidate_without_trying_siblings(self):
        events = []
        result = depth_first_search(
            Puzzle(((None, None), (None, None))), on_event=events.append, trace_steps=True,
        )
        self.assertIs(result.status, SearchStatus.SOLVED)
        self.assertEqual([event.kind for event in events], [
            "expand", "assign", "accept", "expand", "assign", "accept", "expand", "solution",
        ])
        self.assertEqual(events[1].focus, (0, 0))
        # Once the first bulb is accepted, it stays placed throughout the successful descent.
        for event in events[2:]:
            self.assertIn((0, 0), event.bulbs)
        self.assertEqual(result.generated, 2)  # No unused siblings generated on a successful path.

    def test_dfs_only_tries_next_sibling_after_backtracking_to_parent(self):
        puzzle = Puzzle(((None, None, None), (None, 1, None), (None, None, None)))
        events = []
        depth_first_search(puzzle, on_event=events.append, trace_steps=True)
        active_states = [()]
        pending_child = None
        for event in events:
            if event.kind == "assign":
                # Every candidate extends the current branch, never an unvisited sibling's parent.
                self.assertEqual(set(event.bulbs) - {event.focus}, set(active_states[-1]))
                pending_child = event.bulbs
            elif event.kind == "accept":
                self.assertEqual(event.bulbs, pending_child)
                active_states.append(event.bulbs)
            elif event.kind == "backtrack":
                removed = active_states.pop()
                self.assertEqual(event.bulbs, active_states[-1])
                self.assertEqual(set(removed) - {event.focus}, set(event.bulbs))

    def test_astar_still_queues_all_root_successors_before_selecting_by_f(self):
        events = []
        astar(Puzzle(((None, None), (None, None))), on_event=events.append, trace_steps=True)
        selection = next(i for i, event in enumerate(events) if event.kind == "select")
        candidates = [event for event in events[:selection] if event.kind == "queue"]
        self.assertEqual({event.focus for event in candidates}, {(0, 0), (0, 1), (1, 0)})
        self.assertEqual(events[selection].f, min(event.f for event in candidates))

    def test_sampled_callback_remains_expand_only_without_full_trace(self):
        for solver in (depth_first_search, astar):
            events = []
            solver(Puzzle(((None, None), (None, None))),
                   SearchLimits(progress_interval=1000), on_event=events.append)
            self.assertEqual([event.kind for event in events], ["expand"])

    def test_empty_solution_has_a_visible_goal_step(self):
        for solver in (depth_first_search, astar):
            events = []
            result = solver(Puzzle(((0,),)), on_event=events.append, trace_steps=True)
            self.assertIs(result.status, SearchStatus.SOLVED)
            self.assertEqual([event.kind for event in events], ["expand", "solution"])
            self.assertEqual(events[-1].bulbs, ())

    def test_dfs_and_astar_find_valid_solutions_on_same_small_puzzle(self):
        puzzle = Puzzle(((None, None), (None, None)))
        dfs_result = depth_first_search(puzzle)
        astar_result = astar(puzzle)
        self.assertIs(dfs_result.status, SearchStatus.SOLVED)
        self.assertIs(astar_result.status, SearchStatus.SOLVED)
        self.assertTrue(is_goal_state(puzzle, dfs_result.solution))
        self.assertTrue(is_goal_state(puzzle, astar_result.solution))
        self.assertEqual(len(dfs_result.solution_path), len(dfs_result.solution) + 1)
        self.assertEqual(len(astar_result.solution_path), len(astar_result.solution) + 1)

    def test_astar_returns_minimum_bulb_count_on_small_board(self):
        puzzle = Puzzle(((None, None), (None, None)))
        white_cells = [(r, c) for r in range(2) for c in range(2)]
        exhaustive_minimum = min(
            len(candidate)
            for count in range(len(white_cells) + 1)
            for candidate in itertools.combinations(white_cells, count)
            if is_goal_state(puzzle, candidate)
        )
        result = astar(puzzle)
        self.assertEqual(result.solution_cost, exhaustive_minimum)

    def test_inconsistent_numbered_wall_is_unsolvable_not_timeout(self):
        puzzle = Puzzle(((1,),))
        self.assertIs(depth_first_search(puzzle).status, SearchStatus.UNSOLVABLE)
        self.assertIs(astar(puzzle).status, SearchStatus.UNSOLVABLE)

    def test_limits_and_cancellation_have_distinct_statuses(self):
        puzzle = Puzzle(tuple(tuple(None for _ in range(5)) for _ in range(5)))
        self.assertIs(
            depth_first_search(puzzle, SearchLimits(timeout_seconds=1e-10)).status,
            SearchStatus.TIMEOUT,
        )
        self.assertIs(
            depth_first_search(puzzle, SearchLimits(node_limit=1)).status,
            SearchStatus.NODE_LIMIT,
        )
        self.assertIs(
            depth_first_search(puzzle, SearchLimits(memory_limit_mb=1e-9)).status,
            SearchStatus.MEMORY_LIMIT,
        )
        self.assertIs(astar(puzzle, cancelled=lambda: True).status, SearchStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
