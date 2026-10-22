"""Saved inputs, solver correctness, budgets, and reproducible results."""

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .benchmark import run_batch
from .model import Puzzle
from .search import ALGORITHMS, Search, measure, orientations, solve, validate_solution
from .storage import (
    CSV_FIELDS,
    load_game_config,
    map_hash,
    puzzle_from_dict,
    puzzle_to_dict,
    save_map,
)


class SolverTests(unittest.TestCase):
    def test_saved_maps_solve_without_generator_answer(self):
        for size in (4, 5, 7):
            for seed in (261, 262, 263):
                puzzle = puzzle_from_dict(puzzle_to_dict(Puzzle(size, seed)))
                self.assertFalse(hasattr(puzzle, "solution"))
                initial = puzzle.initial.copy()
                for algorithm in ALGORITHMS:
                    result = solve(puzzle, algorithm)
                    self.assertEqual(result.status, "solved")
                    self.assertTrue(validate_solution(puzzle, result.board))
                    self.assertEqual(puzzle.initial, initial)

    def test_pruning_preserves_known_solution_prefixes(self):
        for seed in range(10):
            puzzle = Puzzle(4, seed)
            search = Search(puzzle)
            for depth in range(17):
                self.assertIsNotNone(
                    search.compatible(tuple(puzzle.solution[:depth]))[0]
                )

    def test_unsolvable_and_budget_and_cancel(self):
        data = puzzle_to_dict(Puzzle(4, 261))
        data["tiles"] = [["N"] * 4 for _ in range(4)]
        puzzle = puzzle_from_dict(data)
        for algorithm in ALGORITHMS:
            self.assertEqual(solve(puzzle, algorithm).status, "unsolvable")
            self.assertEqual(
                solve(Puzzle(4, 261), algorithm, max_expansions=1).status,
                "limit_reached",
            )
        search = Search(Puzzle(4, 261))
        search.advance()
        search.cancel()
        self.assertEqual(search.result.status, "cancelled")
        self.assertIsNone(search.advance())

    def test_trace_and_measure_agree(self):
        for algorithm in ALGORITHMS:
            puzzle = Puzzle(4, 261)
            search = Search(puzzle, algorithm)
            kinds = set()
            while search.result.status == "running":
                step = search.advance()
                if step:
                    kinds.add(step.kind)
            result = measure(puzzle, algorithm)
            self.assertEqual(result.board, search.result.board)
            self.assertEqual(result.expanded, search.result.expanded)
            self.assertGreater(result.peak_memory_kib, 0)
            self.assertIn("expand", kinds)
            self.assertIn("reject", kinds)

    def test_symmetry_and_independent_validation(self):
        self.assertEqual(len(orientations(15)), 1)
        self.assertEqual(len(orientations(5)), 2)
        puzzle = Puzzle(4, 261)
        self.assertFalse(validate_solution(puzzle, [15] * 16))
        self.assertFalse(validate_solution(puzzle, puzzle.solution[:-1]))


class StorageTests(unittest.TestCase):
    def test_map_roundtrip_without_generation_metadata(self):
        puzzle = Puzzle(5, 261)
        data = puzzle_to_dict(puzzle)
        self.assertEqual(set(data), {"size", "source", "tiles"})
        loaded = puzzle_from_dict(data)
        self.assertIsNone(loaded.seed)
        self.assertEqual(map_hash(puzzle), map_hash(loaded))
        loaded.turn(0)
        loaded.reset()
        self.assertEqual(loaded.masks, puzzle.initial)

    def test_loaded_identity_comes_from_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "my-board.json"
            save_map(Puzzle(4, 261), path)
            from .storage import load_map

            self.assertEqual(load_map(path).id, "my-board")
            self.assertEqual(
                set(json.loads(path.read_text())), {"size", "source", "tiles"}
            )

    def test_invalid_maps(self):
        good = puzzle_to_dict(Puzzle(4, 261))
        for field, value in [
            ("size", 6),
            ("source", [4, 0]),
            ("tiles", [["NN"] * 4] * 4),
            ("tiles", [["X"] * 4] * 4),
        ]:
            data = copy.deepcopy(good)
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                puzzle_from_dict(data)

    def test_config_paths_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"version": 1, "startup_map": "maps/a.json"}))
            self.assertEqual(
                load_game_config(path)["startup_map"],
                (Path(directory) / "maps/a.json").resolve(),
            )
            path.write_text(
                json.dumps({"version": 1, "startup_map": "a.json", "animation_ms": -1})
            )
            with self.assertRaises(ValueError):
                load_game_config(path)

    def test_batch_preserves_failures_and_exact_csv_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_map(Puzzle(4, 261), root / "maps" / "a.json")
            bad = puzzle_to_dict(Puzzle(4, 262))
            bad["tiles"] = [["N"] * 4 for _ in range(4)]
            (root / "maps" / "b.json").write_text(json.dumps(bad))
            config = root / "benchmark.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "maps": ["maps/*.json"],
                        "algorithms": list(ALGORITHMS),
                        "repetitions": 2,
                        "output_directory": "results",
                    }
                )
            )
            with patch("builtins.print"):
                output = run_batch(config)
            with (output / "benchmark.csv").open(newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, list(CSV_FIELDS))
            self.assertEqual(len(rows), 8)
            self.assertEqual(sum(row["status"] == "unsolvable" for row in rows), 4)
            self.assertTrue(all(row["seed"] == "" for row in rows))
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(len(manifest["runs"]), 8)
            self.assertEqual(len(manifest["maps"]), 2)
            self.assertIn("source_sha256", manifest["environment"])


if __name__ == "__main__":
    unittest.main()
