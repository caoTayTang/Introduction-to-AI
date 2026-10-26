"""Solver correctness: valid solutions, minimum cost, unsolvable and limit statuses."""

import itertools
import unittest

from .algorithms.search import SearchLimits, SearchStatus, astar, depth_first_search
from .core.model import Puzzle
from .core.rules import is_goal_state


class SearchTests(unittest.TestCase):
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
