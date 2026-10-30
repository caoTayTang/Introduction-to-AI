"""Seeded generation, JSON round trip and paired benchmark recording."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .algorithms.search import SearchLimits
from .benchmark.runner import benchmark
from .core.model import Puzzle
from .core.rules import get_illuminated_cells, is_goal_state, validate_numbered_walls
from .core.serialization import load_puzzle, save_puzzle
from .generator import DIFFICULTIES, SIZES, generate_puzzle, get_sample_puzzle
from .generator.generate import _with_clues, difficulty_metrics


class GeneratorBenchmarkTests(unittest.TestCase):
    def test_all_twelve_sample_modes_are_seeded_and_have_valid_constructive_witnesses(self):
        for size in SIZES:
            for difficulty in DIFFICULTIES:
                with self.subTest(size=size, difficulty=difficulty):
                    with patch("light_up_problem.generator.generate._with_clues", wraps=_with_clues) as build:
                        puzzle = get_sample_puzzle(size, difficulty)
                    witness = build.call_args.args[1]
                    self.assertEqual(puzzle.size, size)
                    self.assertEqual(puzzle.difficulty, difficulty)
                    self.assertTrue(puzzle.metadata["witness_verified"])
                    self.assertEqual(puzzle.metadata["uniqueness"], "not_checked")
                    wall_count = sum(value is not None for row in puzzle.rows for value in row)
                    unnumbered_count = sum(value == -1 for row in puzzle.rows for value in row)
                    density = {"easy": 0.16, "normal": 0.105, "hard": 0.055}[difficulty]
                    self.assertEqual(wall_count, round(size * size * density))
                    self.assertEqual(wall_count, puzzle.metadata["wall_count"])
                    self.assertEqual(wall_count, puzzle.metadata["target_wall_count"])
                    self.assertEqual(len(puzzle.numbered_walls()), puzzle.metadata["numbered_wall_count"])
                    self.assertEqual(unnumbered_count, puzzle.metadata["unnumbered_wall_count"])
                    self.assertEqual(unnumbered_count, max(1, round(wall_count * 0.25)))
                    self.assertGreater(len(puzzle.numbered_walls()), 0)
                    self.assertNotIn("witness", puzzle.metadata)
                    self.assertTrue(is_goal_state(puzzle, witness))
                    self.assertTrue(validate_numbered_walls(puzzle, witness))
                    self.assertEqual(get_sample_puzzle(size, difficulty).to_dict(), puzzle.to_dict())

    def test_more_easy_walls_than_hard_walls_for_sample_mode(self):
        easy = get_sample_puzzle(10, "easy")
        hard = get_sample_puzzle(10, "hard")
        easy_walls = sum(value is not None for row in easy.rows for value in row)
        hard_walls = sum(value is not None for row in hard.rows for value in row)
        self.assertGreater(easy_walls, hard_walls)

    def test_fixed_seeds_cover_three_four_and_unnumbered_walls(self):
        for value, seed in ((-1, 0), (3, 1), (4, 16)):
            with self.subTest(value=value, seed=seed):
                with patch("light_up_problem.generator.generate._with_clues", wraps=_with_clues) as build:
                    puzzle = generate_puzzle(7, "easy", seed)
                self.assertIn(value, {cell for row in puzzle.rows for cell in row})
                self.assertTrue(is_goal_state(puzzle, build.call_args.args[1]))

    def test_clues_count_three_and_four_and_preserve_unnumbered_wall(self):
        grid = [[None, None, None], [None, -1, None], [None, None, None]]
        neighbors = ((0, 1), (1, 0), (1, 2), (2, 1))
        for count in (3, 4):
            with self.subTest(count=count):
                puzzle = _with_clues(grid, neighbors[:count], 3, 0, "easy", "fixture")
                self.assertEqual(puzzle.rows[1][1], count)
                self.assertTrue(validate_numbered_walls(puzzle, neighbors[:count]))
        unnumbered = _with_clues(
            grid, neighbors, 3, 0, "easy", "fixture", unnumbered_walls=frozenset({(1, 1)}),
        )
        self.assertEqual(unnumbered.rows[1][1], -1)
        self.assertTrue(is_goal_state(unnumbered, neighbors))
        self.assertEqual(grid[1][1], -1)  # Clue conversion must not mutate its input.

    def test_generated_wall_types_block_light(self):
        for seed in (0, 1, 16):
            puzzle = generate_puzzle(7, "easy", seed)
            for row in range(puzzle.size):
                for col in range(puzzle.size):
                    if puzzle.rows[row][col] is None:
                        continue
                    for dr, dc in ((1, 0), (0, 1)):
                        before, after = (row - dr, col - dc), (row + dr, col + dc)
                        if puzzle.is_white(before) and puzzle.is_white(after):
                            self.assertNotIn(after, get_illuminated_cells(puzzle, (before,)))

    def test_metrics_ignore_unnumbered_walls(self):
        puzzle = Puzzle(((None, -1, None), (None, 0, None), (None, None, None)))
        metrics = difficulty_metrics(puzzle)
        self.assertAlmostEqual(metrics.clue_density, 1 / 7)
        self.assertAlmostEqual(metrics.constrained_white_fraction, 3 / 7)
        self.assertEqual(metrics.mean_clue_extremity, 1.0)

    def test_puzzle_json_round_trip(self):
        puzzle = get_sample_puzzle(7, "normal")
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "puzzle.json"
            save_puzzle(puzzle, file_path)
            loaded = load_puzzle(file_path)
        self.assertEqual(loaded.rows, puzzle.rows)
        self.assertEqual(loaded.seed, puzzle.seed)
        self.assertEqual(loaded.puzzle_id, puzzle.puzzle_id)
        self.assertEqual(loaded.metadata, puzzle.metadata)
        self.assertTrue(any(value == -1 for row in loaded.rows for value in row))

    def test_benchmark_records_same_puzzle_and_real_solver_metrics(self):
        puzzle = Puzzle(((None, None), (None, None)), "same-input", "test", 12)
        rows = benchmark(puzzle, ("dfs", "astar"), repeats=1, limits=SearchLimits())
        self.assertEqual([row.algorithm for row in rows], ["DFS", "ASTAR"])
        self.assertTrue(all(row.puzzle_id == "same-input" and row.seed == 12 for row in rows))
        self.assertTrue(all(row.status == "SOLVED" and row.execution_time_seconds >= 0 for row in rows))
        self.assertTrue(all(row.peak_python_memory_bytes > 0 and row.nodes_expanded > 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
