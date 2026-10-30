"""Reproducible paired DFS/CSP benchmarks over five distinct seeds per configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import platform
import queue
import statistics
import subprocess
import sys
import traceback
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from light_up_problem.algorithms.search import SearchLimits, SearchStatus
from light_up_problem.benchmark.runner import BenchmarkRow, _row, _run_one, write_csv
from light_up_problem.core.model import Puzzle
from light_up_problem.core.rules import is_goal_state
from light_up_problem.generator import DIFFICULTIES, SIZES, generate_puzzle

ROOT = Path(__file__).resolve().parents[2]


def make_inputs(seeds_per_config: int = 5) -> list[Puzzle]:
    if seeds_per_config < 1:
        raise ValueError("seeds_per_config must be positive")
    return [
        generate_puzzle(size, difficulty, size * 10_000 + (level + 1) * 97 + offset)
        for size in SIZES
        for level, difficulty in enumerate(DIFFICULTIES)
        for offset in range(seeds_per_config)
    ]


def _measure(puzzle: Puzzle, algorithm: str, limits: SearchLimits, messages: Any) -> None:
    try:
        result, peak = _run_one(puzzle, algorithm, limits)
        if result.status == SearchStatus.SOLVED and not is_goal_state(puzzle, result.solution):
            raise RuntimeError(f"Invalid {algorithm} solution: {puzzle.puzzle_id}")
        messages.put(("row", _row(puzzle, algorithm.upper(), 1, 1, result, peak)))
    except Exception:
        messages.put(("error", traceback.format_exc()))


def measure_isolated(puzzle: Puzzle, algorithm: str, limits: SearchLimits) -> BenchmarkRow:
    context = mp.get_context("spawn")
    messages = context.Queue(maxsize=1)
    process = context.Process(target=_measure, args=(puzzle, algorithm, limits, messages))
    process.start()
    try:
        while True:
            try:
                kind, payload = messages.get(timeout=0.5)
                break
            except queue.Empty:
                if not process.is_alive():
                    # Flush and recheck before declaring a missing result.
                    process.join()
                    try:
                        kind, payload = messages.get_nowait()
                        break
                    except queue.Empty as exc:
                        raise RuntimeError(f"Benchmark worker exited with code {process.exitcode}") from exc
        process.join()
        if process.exitcode != 0 or kind == "error":
            raise RuntimeError(f"Benchmark failed: {payload}")
        return payload
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
        messages.close()


def summarize(rows: list[BenchmarkRow]) -> list[dict[str, Any]]:
    summaries = []
    for size in SIZES:
        for difficulty in DIFFICULTIES:
            for algorithm in ("DFS", "CSP"):
                group = [r for r in rows if (r.size, r.difficulty, r.algorithm) == (size, difficulty, algorithm)]
                if not group:
                    continue
                solved = [r for r in group if r.status == "SOLVED"]
                summaries.append({
                    "size": size, "difficulty": difficulty, "algorithm": algorithm, "runs": len(group),
                    "statuses": dict(Counter(r.status for r in group)),
                    "seeds": sorted(r.seed for r in group),
                    "median_attempt_seconds": statistics.median(r.execution_time_seconds for r in group),
                    "median_peak_python_memory_bytes": statistics.median(r.peak_python_memory_bytes for r in group),
                    "median_nodes_expanded": statistics.median(r.nodes_expanded for r in group),
                    "median_solved_seconds": statistics.median(r.execution_time_seconds for r in solved)
                    if solved else None,
                    "median_solution_cost": statistics.median(r.solution_cost for r in solved) if solved else None,
                })
    return summaries


def run_suite(output_prefix: Path, limits: SearchLimits, seeds_per_config: int = 5) -> None:
    inputs = make_inputs(seeds_per_config)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    source_paths = [
        "light_up_problem/algorithms/search.py", "light_up_problem/generator/generate.py",
        "light_up_problem/core/model.py", "light_up_problem/core/rules.py",
        "light_up_problem/benchmark/runner.py", "light_up_problem/benchmark/suite.py",
    ]
    manifest = {
        "started_at": datetime.now().astimezone().isoformat(), "completed_at": None,
        "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_paths},
        "limits": asdict(limits), "algorithms": ["DFS", "CSP"], "seeds_per_config": seeds_per_config,
        "measurement": "fresh spawned process per run; perf_counter around solver; tracemalloc peak; no trace",
        "order": "paired algorithms alternate order on consecutive input seeds; all runs sequential",
        "seed_formula": "size * 10000 + (difficulty_index + 1) * 97 + offset; offset=0..seeds_per_config-1",
        "repeat_semantics": "one solver run per distinct seed; repeat=1, repeats=1 in each raw row",
        "summary_semantics": "attempt medians include resource-limited runs; solved time and cost exclude them",
        "inputs": [{
            "puzzle": puzzle.to_dict(),
            "sha256": hashlib.sha256(json.dumps(puzzle.to_dict(), sort_keys=True).encode()).hexdigest(),
        } for puzzle in inputs],
    }
    manifest_path = output_prefix.with_name(output_prefix.name + "-manifest.json")
    summary_path = output_prefix.with_name(output_prefix.name + "-summary.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rows = []
    total = 2 * len(inputs)
    for index, puzzle in enumerate(inputs):
        for algorithm in (("dfs", "csp") if index % 2 == 0 else ("csp", "dfs")):
            print(f"[{len(rows) + 1}/{total}] START {puzzle.puzzle_id} {algorithm.upper()}", flush=True)
            row = measure_isolated(puzzle, algorithm, limits)
            rows.append(row)
            write_csv(rows, output_prefix.with_suffix(".csv"))
            summary_path.write_text(json.dumps(summarize(rows), indent=2) + "\n")
            print(f"  {row.status}: {row.execution_time_seconds:.6f}s, "
                  f"{row.peak_python_memory_bytes / 1024:.1f} KiB, {row.nodes_expanded} nodes", flush=True)
    manifest["completed_at"] = datetime.now().astimezone().isoformat()
    manifest["runs"] = len(rows)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"complete": len(rows), "statuses": dict(Counter(r.status for r in rows))}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--seeds-per-config", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--node-limit", type=int, default=500_000)
    parser.add_argument("--memory-limit-mb", type=float, default=512.0)
    args = parser.parse_args()
    run_suite(
        args.output_prefix, SearchLimits(args.timeout, args.node_limit, args.memory_limit_mb), args.seeds_per_config,
    )


if __name__ == "__main__":
    main()
