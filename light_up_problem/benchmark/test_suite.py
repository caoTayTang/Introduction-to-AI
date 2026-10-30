"""Seed diversity, paired measurement and resource status reporting for the published suite."""

import unittest
from dataclasses import replace

from light_up_problem.algorithms.search import SearchLimits
from light_up_problem.benchmark.runner import benchmark
from light_up_problem.benchmark.suite import make_inputs, measure_isolated, summarize
from light_up_problem.core.model import Puzzle


class SuiteTests(unittest.TestCase):
    def test_five_distinct_seeds_per_size_and_difficulty(self):
        inputs = make_inputs()
        self.assertEqual(len(inputs), 60)
        configs = {(p.size, p.difficulty) for p in inputs}
        self.assertEqual(len(configs), 12)
        for config in configs:
            group = [p for p in inputs if (p.size, p.difficulty) == config]
            self.assertEqual(len({p.seed for p in group}), 5)
            self.assertEqual(len({p.rows for p in group}), 5)
            self.assertTrue(all(p.metadata["witness_verified"] for p in group))

    def test_csp_dispatch_returns_csp_metrics_on_the_same_input(self):
        puzzle = Puzzle(((None, None), (None, None)), "paired", "easy", 12)
        rows = benchmark(puzzle, ("dfs", "csp"), limits=SearchLimits())
        self.assertEqual([r.algorithm for r in rows], ["DFS", "CSP"])
        self.assertEqual([r.nodes_expanded for r in rows], [3, 2])
        self.assertTrue(all(r.puzzle_id == "paired" and r.seed == 12 for r in rows))
        self.assertTrue(all(r.status == "SOLVED" and r.peak_python_memory_bytes > 0 for r in rows))

    def test_both_algorithms_preserve_the_three_distinct_resource_limits(self):
        puzzle = Puzzle(tuple((None,) * 5 for _ in range(5)))
        for limits, status in (
            (SearchLimits(timeout_seconds=1e-10), "TIMEOUT"),
            (SearchLimits(node_limit=1), "NODE_LIMIT"),
            (SearchLimits(memory_limit_mb=1e-9), "MEMORY_LIMIT"),
        ):
            with self.subTest(status=status):
                rows = benchmark(puzzle, ("dfs", "csp"), limits=limits)
                self.assertEqual([row.status for row in rows], [status, status])
                self.assertTrue(all(row.solution_cost is None for row in rows))

    def test_summary_separates_censored_attempts_from_solved_times(self):
        base = benchmark(Puzzle(((None,),), "summary", "easy", 1), ("dfs",))[0]
        base = replace(base, size=7, execution_time_seconds=1.0, solution_cost=1)
        rows = [base, replace(base, seed=2, status="TIMEOUT", execution_time_seconds=30.0, solution_cost=None)]
        summary = summarize(rows)[0]
        self.assertEqual(summary["statuses"], {"SOLVED": 1, "TIMEOUT": 1})
        self.assertEqual(summary["median_attempt_seconds"], 15.5)
        self.assertEqual(summary["median_solved_seconds"], 1.0)
        self.assertEqual(summary["median_solution_cost"], 1)

    def test_isolated_process_returns_real_csp_result(self):
        row = measure_isolated(Puzzle(((None,),), "isolated", "easy", 1), "csp", SearchLimits())
        self.assertEqual((row.algorithm, row.status, row.solution_cost), ("CSP", "SOLVED", 1))
        self.assertGreater(row.peak_python_memory_bytes, 0)
