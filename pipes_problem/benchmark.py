"""Headless, paired benchmarks. Results are written automatically."""

import argparse
import csv
import glob
import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .search import ALGORITHMS, HEURISTIC, measure
from .storage import (
    ROOT,
    append_result,
    integer,
    load_map,
    map_hash,
    puzzle_to_dict,
    read_json,
)


def environment():
    return {
        "python": sys.version,
        "os": platform.platform(),
        "cpu": platform.processor(),
        "pygame_ce": importlib.metadata.version("pygame-ce"),
        "source_sha256": hashlib.sha256(
            b"".join(
                p.name.encode() + p.read_bytes()
                for p in sorted(ROOT.glob("*.py"))
                if not p.name.startswith("test_")
            )
        ).hexdigest(),
    }


def manifest(puzzles, settings):
    return {
        "version": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "environment": environment(),
        "settings": settings,
        "algorithms": {
            "dfs": {
                "order": "row-major",
                "pruning": "boundary, forward checking, cycle, potential connectivity",
            },
            "greedy_best_first": {
                "order": "row-major",
                "heuristic": HEURISTIC,
                "pruning": "same as DFS",
            },
        },
        "measurement": {
            "time": "perf_counter, headless, no trace",
            "memory": "separate tracemalloc replay with same expansion count; not process RSS",
            "unavailable_memory": "blank if replay differs",
        },
        "maps": [
            {"puzzle_id": p.id, "sha256": map_hash(p), "map": puzzle_to_dict(p)}
            for p in puzzles
        ],
    }


def record_interactive(puzzle, result, settings, directory=None):
    directory = Path(directory or ROOT.parent / "results")
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "interactive.csv"
    row = 1
    if csv_path.exists():
        with csv_path.open(newline="") as handle:
            row = max(1, sum(1 for _ in csv.reader(handle)))
    document = manifest([puzzle], settings)
    document["csv_row"] = row
    document["status"] = result.status
    document["error"] = result.error
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    location = directory / "interactive" / f"{stamp}.json"
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_text(json.dumps(document, indent=2) + "\n")
    append_result(csv_path, puzzle, result)


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    if (
        not isinstance(config, dict)
        or type(config.get("version")) is not int
        or config.get("version") != 1
    ):
        raise ValueError("Benchmark config must have version 1")
    patterns = config.get("maps")
    algorithms = config.get("algorithms")
    if (
        not isinstance(patterns, list)
        or not patterns
        or any(not isinstance(p, str) for p in patterns)
    ):
        raise ValueError("maps must be a nonempty list of file patterns")
    if (
        not isinstance(algorithms, list)
        or not algorithms
        or any(a not in ALGORITHMS for a in algorithms)
    ):
        raise ValueError(f"algorithms must select from {ALGORITHMS}")
    if len(set(algorithms)) != len(algorithms):
        raise ValueError("Duplicate algorithm names")
    reps = integer(config.get("repetitions", 5), "repetitions", 1)
    limit = config.get("time_limit_seconds", 30)
    if (
        isinstance(limit, bool)
        or not isinstance(limit, (int, float))
        or not math.isfinite(limit)
        or limit <= 0
    ):
        raise ValueError("time_limit_seconds must be a positive finite number")
    budget = integer(config.get("max_expansions", 200000), "max_expansions", 1)
    paths = sorted(
        {
            Path(p).resolve()
            for pattern in patterns
            for p in glob.glob(str(path.parent / pattern))
        }
    )
    if not paths:
        raise ValueError("No maps matched benchmark config")
    puzzles = [load_map(p) for p in paths]
    if len({p.id for p in puzzles}) != len(puzzles):
        raise ValueError("Map ids must be unique in a benchmark batch")
    output = config.get("output_directory", "../results")
    if not isinstance(output, str) or not output:
        raise ValueError("output_directory must be a file path")
    resolved = dict(
        config,
        repetitions=reps,
        time_limit_seconds=limit,
        max_expansions=budget,
        maps=[str(p) for p in paths],
        output_directory=str((path.parent / output).resolve()),
    )
    return puzzles, resolved


def run_batch(config_path):
    puzzles, config = load_config(config_path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(config["output_directory"]) / f"benchmark-{stamp}"
    output.mkdir(parents=True)
    document = manifest(puzzles, config)
    document["runs"] = []
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(document, indent=2) + "\n")
    grouped = {}
    for puzzle in puzzles:
        for algorithm in config["algorithms"]:
            for repetition in range(config["repetitions"]):
                result = measure(
                    puzzle,
                    algorithm,
                    time_limit=config["time_limit_seconds"],
                    max_expansions=config["max_expansions"],
                )
                append_result(output / "benchmark.csv", puzzle, result)
                grouped.setdefault((puzzle.size, algorithm), []).append(result)
                document["runs"].append(
                    {
                        "csv_row": len(document["runs"]) + 1,
                        "repetition": repetition + 1,
                        "expanded": result.expanded,
                        "error": result.error,
                    }
                )
                manifest_path.write_text(json.dumps(document, indent=2) + "\n")
                print(
                    f"{puzzle.id}  {algorithm}  {repetition + 1}/{config['repetitions']}  {result.status}  {result.time_ms:.2f} ms",
                    flush=True,
                )
    summary = [
        "# Pipes benchmark",
        "",
        "Timings below summarize successful runs only. All outcomes remain in CSV.",
        "",
        "| Size | Algorithm | Solved / runs | Median time (ms) | Median peak allocation (KiB) | Other outcomes |",
        "|---|---|---:|---:|---:|---|",
    ]
    for (size, algorithm), results in sorted(grouped.items()):
        solved = [r for r in results if r.status == "solved"]
        memory = [r.peak_memory_kib for r in solved if r.peak_memory_kib is not None]
        median_time = (
            f"{statistics.median(r.time_ms for r in solved):.3f}" if solved else "—"
        )
        median_memory = f"{statistics.median(memory):.3f}" if memory else "—"
        other = dict(Counter(r.status for r in results if r.status != "solved"))
        summary.append(
            f"| {size}×{size} | {algorithm} | {len(solved)}/{len(results)} | {median_time} | {median_memory} | {other or '—'} |"
        )
    (output / "summary.md").write_text("\n".join(summary) + "\n")
    print(f"Results: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Benchmark saved Pipes maps")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.json")
    args = parser.parse_args()
    try:
        run_batch(args.config)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
