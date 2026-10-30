"""Spawn-safe multiprocessing entry point used by the Pygame interface."""

from __future__ import annotations

import queue
import traceback
from dataclasses import asdict
from multiprocessing.queues import Queue
from typing import Any

from light_up_problem.algorithms.search import SearchEvent, SearchLimits, astar, backtracking_mrv_cp, depth_first_search
from light_up_problem.core.model import Puzzle


def solver_worker(
    puzzle: Puzzle,
    algorithm: str,
    limits: SearchLimits,
    messages: Queue,
    stop_event: Any,
    pause_event: Any,
    step_event: Any,
) -> None:
    """Stream every trace event, waiting for queue space instead of dropping steps."""

    def send(kind: str, payload: Any) -> None:
        while not stop_event.is_set():
            try:
                messages.put((kind, payload), timeout=0.1)
                return
            except queue.Full:
                continue

    def emit(event: SearchEvent) -> None:
        if stop_event.is_set():
            return
        send("progress", asdict(event))
        while pause_event.is_set() and not stop_event.is_set():
            if step_event.wait(0.1):
                step_event.clear()
                break

    try:
        solvers = {"DFS": depth_first_search, "A*": astar, "CSP": backtracking_mrv_cp}
        if algorithm.upper() not in solvers:
            raise ValueError(f"Unknown search algorithm: {algorithm}")
        solver = solvers[algorithm.upper()]
        result = solver(puzzle, limits, on_event=emit, cancelled=stop_event.is_set, trace_steps=True)
        send("result", result)
    except Exception as exc:  # Send a readable failure to the owning UI process.
        send("error", f"{exc}\n{traceback.format_exc()}")
