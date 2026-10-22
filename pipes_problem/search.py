"""DFS and Greedy Best-First over fixed-order partial tile assignments."""

import heapq
import math
import time
import tracemalloc
from dataclasses import dataclass
from itertools import count

from .model import DIRECTIONS, inspect_board, rotate

ALGORITHMS = ("dfs", "greedy_best_first")
HEURISTIC = "sum(log2(remaining orientation-domain size)); deeper states break ties"


@dataclass(frozen=True)
class Step:
    kind: str
    state: tuple[int, ...]
    index: int | None = None
    reason: str = ""


@dataclass
class Result:
    algorithm: str
    status: str = "running"
    board: tuple[int, ...] | None = None
    time_ms: float = 0.0
    peak_memory_kib: float | None = None
    expanded: int = 0
    error: str = ""


def orientations(mask):
    return tuple(dict.fromkeys(rotate(mask, turns) for turns in range(4)))


def validate_solution(puzzle, board):
    return (
        board is not None
        and len(board) == len(puzzle.initial)
        and all(
            value in orientations(initial)
            for value, initial in zip(board, puzzle.initial)
        )
        and inspect_board(list(board), puzzle.size, puzzle.source).solved
    )


class Search:
    def __init__(
        self,
        puzzle,
        algorithm="dfs",
        *,
        trace=True,
        time_limit=30.0,
        max_expansions=200000,
    ):
        if algorithm not in ALGORITHMS:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        if time_limit <= 0 or max_expansions < 1:
            raise ValueError("Search limits must be positive")
        # Read only the initial board, never the generator's solution or manual locks.
        self.initial = tuple(puzzle.initial)
        self.size, self.source = puzzle.size, puzzle.source
        self.algorithm, self.trace = algorithm, trace
        self.time_limit, self.max_expansions = time_limit, max_expansions
        self.elapsed = 0.0
        self.result = Result(algorithm)
        self.domains = self.boundary_domains()
        edge_count_ok = sum(mask.bit_count() for mask in self.initial) == 2 * (
            len(self.initial) - 1
        )
        if not edge_count_ok or self.compatible(())[0] is None:
            self.result.status = "unsolvable"
            self.iterator = iter(())
        else:
            self.iterator = self.explore()

    def boundary_domains(self):
        domains = []
        for i, initial in enumerate(self.initial):
            r, c = divmod(i, self.size)
            forbidden = sum(
                bit
                for dr, dc, bit, _ in DIRECTIONS
                if not (0 <= r + dr < self.size and 0 <= c + dc < self.size)
            )
            domains.append(
                tuple(mask for mask in orientations(initial) if not mask & forbidden)
            )
        return tuple(domains)

    def compatible(self, state):
        """Shared sound pruning, without changing the fixed assignment order."""
        n, depth = len(self.initial), len(state)
        domains = [((state[i],) if i < depth else self.domains[i]) for i in range(n)]
        if any(not domain for domain in domains):
            return None, "No legal orientation"
        # Forward checking: all ports, including absent ports, must match assigned neighbors.
        for i in range(n):
            r, c = divmod(i, self.size)
            for dr, dc, bit, opposite in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.size and 0 <= nc < self.size):
                    continue
                j = nr * self.size + nc
                if j < depth:
                    domains[i] = tuple(
                        mask
                        for mask in domains[i]
                        if bool(mask & bit) == bool(state[j] & opposite)
                    )
            if not domains[i]:
                return None, "Neighbor cannot match"
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        potential = [[] for _ in range(n)]
        for i in range(n):
            r, c = divmod(i, self.size)
            for dr, dc, bit, opposite in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.size and 0 <= nc < self.size):
                    continue
                j = nr * self.size + nc
                if j <= i:
                    continue
                possible = any(m & bit for m in domains[i]) and any(
                    m & opposite for m in domains[j]
                )
                if possible:
                    potential[i].append(j)
                    potential[j].append(i)
                if i < depth and j < depth and state[i] & bit and state[j] & opposite:
                    a, b = find(i), find(j)
                    if a == b:
                        return None, "Closed loop"
                    parent[a] = b
        visited, pending = {self.source}, [self.source]
        while pending:
            for j in potential[pending.pop()]:
                if j not in visited:
                    visited.add(j)
                    pending.append(j)
        if len(visited) != n:
            return None, "Cannot connect all tiles"
        return domains, ""

    def budget(self):
        if (
            self.elapsed >= self.time_limit
            or self.result.expanded >= self.max_expansions
        ):
            self.result.status = "limit_reached"
            return False
        return True

    def accept_goal(self, state):
        if len(state) != len(self.initial):
            return False
        if inspect_board(list(state), self.size, self.source).solved:
            self.result.status = "solved"
            self.result.board = state
            return True
        return False

    def dfs(self, state):
        if not self.budget():
            return
        self.result.expanded += 1
        yield Step("expand", state) if self.trace else None
        if self.accept_goal(state):
            return
        if len(state) == len(self.initial):
            return
        index = len(state)
        for mask in self.domains[index]:
            child = state + (mask,)
            domains, reason = self.compatible(child)
            if domains is None:
                if self.trace:
                    yield Step("reject", child, index, reason)
                continue
            if self.trace:
                yield Step("assign", child, index)
            yield from self.dfs(child)
            if self.result.status != "running":
                return
            if self.trace:
                yield Step("backtrack", state, index)

    def greedy(self):
        serial = count()
        queue = [(0.0, 0, next(serial), ())]
        while queue and self.budget():
            _, _, _, state = heapq.heappop(queue)
            self.result.expanded += 1
            yield Step("expand", state) if self.trace else None
            if self.accept_goal(state):
                return
            if len(state) == len(self.initial):
                continue
            index = len(state)
            for mask in self.domains[index]:
                child = state + (mask,)
                domains, reason = self.compatible(child)
                if domains is None:
                    if self.trace:
                        yield Step("reject", child, index, reason)
                    continue
                score = sum(math.log2(len(domain)) for domain in domains[len(child) :])
                heapq.heappush(queue, (score, -len(child), next(serial), child))
                if self.trace:
                    yield Step("queue", child, index)

    def explore(self):
        # A loop-free network on n tiles has n-1 edges and two ports per edge.
        if sum(mask.bit_count() for mask in self.initial) != 2 * (
            len(self.initial) - 1
        ):
            self.result.status = "unsolvable"
            return
        domains, _ = self.compatible(())
        if domains is None:
            self.result.status = "unsolvable"
            return
        yield from (self.dfs(()) if self.algorithm == "dfs" else self.greedy())
        if self.result.status == "running":
            self.result.status = "unsolvable"

    def advance(self):
        if self.result.status != "running":
            return None
        started = time.perf_counter()
        try:
            step = next(self.iterator)
        except StopIteration:
            step = None
        except (ValueError, IndexError, RuntimeError, MemoryError) as exc:
            self.result.status = "error"
            self.result.error = str(exc)
            step = None
        finally:
            self.elapsed += time.perf_counter() - started
            self.result.time_ms = self.elapsed * 1000
        return step

    def cancel(self):
        if self.result.status == "running":
            self.result.status = "cancelled"
            self.iterator.close()


def solve(puzzle, algorithm, *, time_limit=30.0, max_expansions=200000):
    session = Search(
        puzzle,
        algorithm,
        trace=False,
        time_limit=time_limit,
        max_expansions=max_expansions,
    )
    while session.result.status == "running":
        session.advance()
    if session.result.status == "solved" and not validate_solution(
        puzzle, session.result.board
    ):
        session.result.status = "error"
        session.result.error = "Independent solution validation failed"
    return session.result


def measure(puzzle, algorithm, *, time_limit=30.0, max_expansions=200000):
    # Start timing before solver construction; no rendering or trace snapshots.
    start = time.perf_counter()
    result = solve(
        puzzle, algorithm, time_limit=time_limit, max_expansions=max_expansions
    )
    result.time_ms = (time.perf_counter() - start) * 1000
    # Replay the exact expansion budget. Profiling overhead must not turn a solved
    # timing run into a timeout; verify both passes agree before combining metrics.
    tracemalloc.start()
    try:
        memory_result = solve(
            puzzle,
            algorithm,
            time_limit=float("inf"),
            max_expansions=max(1, result.expanded),
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if (
        memory_result.status == result.status
        and memory_result.board == result.board
        and memory_result.expanded == result.expanded
    ):
        result.peak_memory_kib = peak / 1024
    return result
