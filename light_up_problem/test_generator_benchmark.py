"""Seeded generation, JSON round trip and paired benchmark recording."""

import random
import tempfile
import unittest
from pathlib import Path

from .algorithms.search import SearchLimits
from .benchmark.runner import benchmark
from .core.model import Puzzle
from .core.rules import is_goal_state, validate_numbered_walls
from .core.serialization import load_puzzle, save_puzzle
from .generator import DIFFICULTIES, SIZES, get_sample_puzzle


class GeneratorBenchmarkTests(unittest.TestCase):
    def test_all_twelve_sample_modes_are_seeded_and_have_valid_constructive_witnesses(self):
        for size in SIZES:
            for difficulty in DIFFICULTIES:
                with self.subTest(size=size, difficulty=difficulty):
                    puzzle = get_sample_puzzle(size, difficulty)
                    self.assertEqual(puzzle.size, size)
                    self.assertEqual(puzzle.difficulty, difficulty)
                    self.assertTrue(puzzle.metadata["witness_verified"])
                    self.assertEqual(puzzle.metadata["uniqueness"], "not_checked")
                    self.assertEqual(len(puzzle.numbered_walls()), puzzle.metadata["wall_count"])
                    offset = random.Random(puzzle.seed).randrange(size)
                    witness = {(row, (row + offset) % size) for row in range(size)}
                    self.assertTrue(is_goal_state(puzzle, witness))
                    self.assertTrue(validate_numbered_walls(puzzle, witness))
                    self.assertEqual(get_sample_puzzle(size, difficulty).rows, puzzle.rows)

    def test_more_easy_clues_than_hard_clues_for_sample_mode(self):
        easy = get_sample_puzzle(10, "easy")
        hard = get_sample_puzzle(10, "hard")
        easy_clues = sum(value is not None for row in easy.rows for value in row)
        hard_clues = sum(value is not None for row in hard.rows for value in row)
        self.assertGreater(easy_clues, hard_clues)

    def test_puzzle_json_round_trip(self):
        puzzle = get_sample_puzzle(7, "normal")
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "puzzle.json"
            save_puzzle(puzzle, file_path)
            loaded = load_puzzle(file_path)
        self.assertEqual(loaded.rows, puzzle.rows)
        self.assertEqual(loaded.seed, puzzle.seed)
        self.assertEqual(loaded.puzzle_id, puzzle.puzzle_id)

    def test_benchmark_records_same_puzzle_and_real_solver_metrics(self):
        puzzle = Puzzle(((None, None), (None, None)), "same-input", "test", 12)
        rows = benchmark(puzzle, ("dfs", "astar"), repeats=1, limits=SearchLimits())
        self.assertEqual([row.algorithm for row in rows], ["DFS", "ASTAR"])
        self.assertTrue(all(row.puzzle_id == "same-input" and row.seed == 12 for row in rows))
        self.assertTrue(all(row.status == "SOLVED" and row.execution_time_seconds >= 0 for row in rows))
        self.assertTrue(all(row.peak_python_memory_bytes > 0 and row.nodes_expanded > 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
