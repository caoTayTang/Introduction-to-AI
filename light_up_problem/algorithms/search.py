"""Constraint-pruned DFS, CSP (Backtracking + MRV + Propagation), and optimal A* over bulb configurations."""

from __future__ import annotations

import heapq
import itertools
import math
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from light_up_problem.core.model import Cell, Puzzle
from light_up_problem.core.rules import is_goal_state

AlgorithmName = Literal["dfs", "astar", "csp"]


class SearchStatus(StrEnum):
    SOLVED = "SOLVED"
    UNSOLVABLE = "UNSOLVABLE"
    TIMEOUT = "TIMEOUT"
    NODE_LIMIT = "NODE_LIMIT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class SearchLimits:
    timeout_seconds: float = 30.0
    node_limit: int = 500_000
    memory_limit_mb: float = 512.0
    progress_interval: int = 100


@dataclass(frozen=True, slots=True)
class SearchEvent:
    kind: str
    bulbs: tuple[Cell, ...]
    expanded: int
    generated: int
    frontier_size: int
    depth: int
    g: int
    h: int | None
    f: int | None
    focus: Cell | None = None
    detail: str = ""
    elapsed_seconds: float = 0.0
    forbidden: tuple[Cell, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchResult:
    algorithm: AlgorithmName
    status: SearchStatus
    solution: tuple[Cell, ...] = ()
    solution_path: tuple[tuple[Cell, ...], ...] = ()
    expanded: int = 0
    generated: int = 0
    max_frontier: int = 0
    elapsed_seconds: float = 0.0
    peak_memory_bytes: int = 0
    solution_cost: int | None = None
    message: str = ""


def _iter_bits(mask: int) -> tuple[int, ...]:
    """Extract set bit indices in ascending order."""
    indices: list[int] = []
    while mask:
        bit = mask & -mask
        indices.append(bit.bit_length() - 1)
        mask ^= bit
    return tuple(indices)


def _record_transition(
    parents: dict[int, tuple[int, int] | None], prev_state: int, next_state: int
) -> None:
    """Chain individual bulb additions so _path_from_parents reconstructs multi-bulb propagation steps."""
    added = next_state & ~prev_state
    cursor = prev_state
    while added:
        bit = added & -added
        action = bit.bit_length() - 1
        added ^= bit
        step_state = cursor | bit
        if step_state not in parents:
            parents[step_state] = (cursor, action)
        cursor = step_state


@dataclass(slots=True)
class _View:
    puzzle: Puzzle
    cells: tuple[Cell, ...]
    index: dict[Cell, int]
    white_mask: int
    covers: tuple[int, ...]
    conflicts: tuple[int, ...]
    wall_neighbors: tuple[tuple[int, int], ...]
    illuminators: tuple[tuple[int, ...], ...]
    reach_masks: tuple[int, ...]

    @classmethod
    def build(cls, puzzle: Puzzle) -> _View:
        cells = tuple(
            (row, col) for row in range(puzzle.size) for col in range(puzzle.size) if puzzle.is_white((row, col))
        )
        index = {cell: i for i, cell in enumerate(cells)}
        covers: list[int] = []
        for row, col in cells:
            mask = 1 << index[(row, col)]
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                r, c = row + dr, col + dc
                while puzzle.is_white((r, c)):
                    mask |= 1 << index[(r, c)]
                    r += dr
                    c += dc
            covers.append(mask)
        conflicts = tuple(cover & ~(1 << i) for i, cover in enumerate(covers))
        walls: list[tuple[int, int]] = []
        for row, col in puzzle.numbered_walls():
            neighbors = tuple(
                index[(row + dr, col + dc)]
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                if (row + dr, col + dc) in index
            )
            walls.append((puzzle.rows[row][col], sum(1 << i for i in neighbors)))
        illuminators = tuple(
            tuple(i for i, cover in enumerate(covers) if cover & (1 << target)) for target in range(len(cells))
        )
        # Precompute 2-hop reachability mask for each cell to accelerate independent set heuristic
        reach_masks: list[int] = []
        for target in range(len(cells)):
            reach = 0
            for b in illuminators[target]:
                reach |= covers[b]
            reach_masks.append(reach)

        return cls(
            puzzle,
            cells,
            index,
            (1 << len(cells)) - 1,
            tuple(covers),
            conflicts,
            tuple(walls),
            illuminators,
            tuple(reach_masks),
        )

    def bulb_cells(self, mask: int) -> tuple[Cell, ...]:
        return tuple(self.cells[i] for i in range(len(self.cells)) if mask & (1 << i))

    def lit_mask(self, bulbs: int) -> int:
        lit = 0
        while bulbs:
            bit = bulbs & -bulbs
            lit |= self.covers[bit.bit_length() - 1]
            bulbs ^= bit
        return lit

    def can_place(self, bulb: int, bulbs: int) -> bool:
        bit = 1 << bulb
        if bulbs & bit or self.conflicts[bulb] & bulbs:
            return False
        for target, neighbors in self.wall_neighbors:
            if neighbors & bit and (neighbors & bulbs).bit_count() >= target:
                return False
        return True

    def propagate(
        self, bulbs: int, lit: int, legal: int, *,
        on_step: Callable[[str, int, int, Cell | None, str], None] | None = None,
    ) -> tuple[int, int, int, bool]:
        """Fixed-point Constraint Propagation combining Numbered Wall, Illumination, and Bulb Conflict rules.

        Domain mapping per white cell i:
        - bit i in `bulbs` == 1             -> D(x_i) = {1} (bulb placed)
        - bit i in `legal` == 1             -> D(x_i) = {0, 1} (undecided)
        - bit i in `bulbs` == 0 & `legal`==0 -> D(x_i) = {0} (forbidden)
        """
        def notify(kind: str, focus: Cell | None, detail: str) -> None:
            if on_step is not None:
                on_step(kind, bulbs, legal, focus, detail)

        wall_cells = self.puzzle.numbered_walls() if on_step is not None else ()
        # Rule 3 consistency: any already-illuminated cell cannot hold a new bulb
        previously_legal_lit = legal & lit
        legal &= ~lit
        if previously_legal_lit:
            notify("prune", None, "Lit cells cannot hold another bulb")

        changed = True
        while changed:
            changed = False

            # Rule 1: Numbered Wall Propagation
            for wall_index, (target, neighbors) in enumerate(self.wall_neighbors):
                wall = wall_cells[wall_index] if on_step is not None else None
                b = (neighbors & bulbs).bit_count()
                r = target - b
                undecided = neighbors & legal
                u = undecided.bit_count()

                # Case 1: Placed too many bulbs or not enough undecided neighbors left
                if r < 0 or r > u:
                    notify("reject", wall, "Numbered wall has too many bulbs or too few available neighbors")
                    return bulbs, lit, legal, False

                # Case 2: Wall is satisfied (r == 0) -> all remaining undecided neighbors get x_i = 0
                if r == 0:
                    if undecided:
                        legal &= ~undecided
                        changed = True
                        notify("prune", wall, f"Wall {wall} is satisfied; forbid its remaining neighbors")
                    continue

                # Case 3: All remaining undecided neighbors must have bulbs (r == u)
                if r == u:
                    temp = undecided
                    while temp:
                        bit = temp & -temp
                        idx = bit.bit_length() - 1
                        temp ^= bit
                        # Check conflict with existing bulbs or if removed from legal by an earlier neighbor
                        if (bulbs & self.conflicts[idx]) or not (legal & bit):
                            notify("reject", self.cells[idx], f"Forced bulb for wall {wall} conflicts with a bulb")
                            return bulbs, lit, legal, False
                        bulbs |= bit
                        lit |= self.covers[idx]
                        legal &= ~self.covers[idx]
                        notify("propagate", self.cells[idx], f"Wall {wall} requires a bulb at every remaining neighbor")
                    changed = True
                    continue

                # Local deduction (Rule 4 - Diagonal Conflict): if u - r == 1, any legal cell that
                # illuminates 2+ undecided neighbors of this wall cannot be a bulb (would leave u - 2 < r).
                if u - r == 1:
                    previous_legal = legal
                    u_list = _iter_bits(undecided)
                    for i_idx in range(len(u_list)):
                        c1 = self.covers[u_list[i_idx]]
                        for j_idx in range(i_idx + 1, len(u_list)):
                            shared = c1 & self.covers[u_list[j_idx]] & legal
                            if shared:
                                legal &= ~shared
                                changed = True
                    if legal != previous_legal:
                        notify("prune", wall, f"Diagonal conflict at wall {wall}; preserve enough eligible neighbors")

            # Rule 2: Illumination Propagation
            dark = self.white_mask & ~lit
            while dark:
                bit = dark & -dark
                cell_idx = bit.bit_length() - 1
                dark ^= bit

                # C(i) = {j in V(i) | 1 in D(x_j)}
                candidates = self.covers[cell_idx] & legal

                # Case 1: |C(i)| == 0 -> Unlit cell has no valid illuminator (Contradiction)
                if candidates == 0:
                    notify("reject", self.cells[cell_idx], "Dark cell has no legal illuminator")
                    return bulbs, lit, legal, False

                # Case 2: |C(i)| == 1 -> Single valid illuminator j must have a bulb (x_j = 1)
                if (candidates & (candidates - 1)) == 0:
                    bulb_idx = candidates.bit_length() - 1
                    if bulbs & self.conflicts[bulb_idx]:
                        notify("reject", self.cells[bulb_idx], "The only illuminator conflicts with another bulb")
                        return bulbs, lit, legal, False
                    bulbs |= candidates
                    new_lit = self.covers[bulb_idx]
                    lit |= new_lit
                    # Rule 3: Bulb Conflict Propagation removes all cells in V(j) from legal
                    legal &= ~new_lit
                    dark &= ~new_lit
                    changed = True
                    notify("propagate", self.cells[bulb_idx], f"Only illuminator for dark cell {self.cells[cell_idx]}")

        return bulbs, lit, legal, True

    def select_mrv_choices(
        self, bulbs: int, lit: int, legal: int, *,
        on_select: Callable[[Cell, int, str], None] | None = None,
    ) -> tuple[int | None, tuple[tuple[int, int, int, int], ...]]:
        """Dynamic Constraint-Level MRV across numbered walls and unlit white cells (Section 3).

        Returns:
            (focus_cell_index, tuple of (child_bulbs, child_lit, child_legal, representative_action))
        """
        dark = self.white_mask & ~lit
        if not dark:
            return None, ()

        best_score = sys.maxsize
        best_kind: Literal["wall", "light"] | None = None
        best_wall_data: tuple[int, int] | None = None  # (r, undecided_mask)
        best_cell: int | None = None
        best_cell_candidates: int = 0
        best_wall_index = 0

        # 3.2. MRV on numbered walls: m_wall = comb(u, r)
        for wall_index, (target, neighbors) in enumerate(self.wall_neighbors):
            r = target - (neighbors & bulbs).bit_count()
            if r <= 0:
                continue
            undecided = neighbors & legal
            u = undecided.bit_count()
            if u < r:
                return None, ()
            score = math.comb(u, r)
            if score < best_score:
                best_score = score
                best_kind = "wall"
                best_wall_data = (r, undecided)
                best_wall_index = wall_index

        # 3.1. MRV on unlit white cells: m_light(i) = |C(i)|
        temp_dark = dark
        while temp_dark:
            bit = temp_dark & -temp_dark
            cell_idx = bit.bit_length() - 1
            temp_dark ^= bit

            candidates = self.covers[cell_idx] & legal
            count = candidates.bit_count()
            if count == 0:
                return cell_idx, ()
            # 3.3. Combine both MRVs (on ties, numbered walls are preferred for stronger cascade)
            if count < best_score:
                best_score = count
                best_kind = "light"
                best_cell = cell_idx
                best_cell_candidates = candidates

        # Generate branching choices for a numbered-wall constraint
        if best_kind == "wall" and best_wall_data is not None:
            if on_select is not None:
                on_select(self.puzzle.numbered_walls()[best_wall_index], best_score, "wall")
            r, undecided = best_wall_data
            u_cells = _iter_bits(undecided)
            focus = u_cells[0] if u_cells else None
            # Unchosen neighbors around this wall get x_i = 0
            base_legal = legal & ~undecided
            scored_choices: list[tuple[int, int, int, int, int]] = []
            for comb in itertools.combinations(u_cells, r):
                c_bulbs = bulbs
                c_lit = lit
                c_legal = base_legal
                valid = True
                for idx in comb:
                    bit = 1 << idx
                    if (c_bulbs & self.conflicts[idx]) or (c_bulbs & bit):
                        valid = False
                        break
                    c_bulbs |= bit
                    c_lit |= self.covers[idx]
                    c_legal &= ~self.covers[idx]
                if valid:
                    gain = (c_lit & dark).bit_count()
                    scored_choices.append((gain, c_bulbs, c_lit, c_legal, comb[0]))
            scored_choices.sort(key=lambda item: item[0], reverse=True)
            return focus, tuple((bulbs, lit, legal, act) for _, bulbs, lit, legal, act in scored_choices)

        # Generate disjoint branching choices for an unlit white-cell constraint
        if best_kind == "light" and best_cell is not None:
            if on_select is not None:
                on_select(self.cells[best_cell], best_score, "dark cell")
            cand_indices = list(_iter_bits(best_cell_candidates))
            # Value ordering: try candidates that illuminate the most dark cells first
            cand_indices.sort(key=lambda idx: (self.covers[idx] & dark).bit_count(), reverse=True)
            choices: list[tuple[int, int, int, int]] = []
            running_legal = legal
            for idx in cand_indices:
                bit = 1 << idx
                c_bulbs = bulbs | bit
                c_lit = lit | self.covers[idx]
                c_legal = running_legal & ~self.covers[idx]
                choices.append((c_bulbs, c_lit, c_legal, idx))
                # Disjoint branching: set x_{p_k} = 0 for all subsequent branches
                running_legal &= ~bit
            return best_cell, tuple(choices)

        return None, ()

    def legal_mask_and_check(self, bulbs: int, lit: int) -> tuple[int, bool, int | None]:
        """Compute bitmask of all valid bulb placements and check wall feasibility.

        Returns:
            (legal_mask, is_feasible, forced_cell_index)
        """
        legal = self.white_mask & ~lit
        for target, neighbors in self.wall_neighbors:
            current = (neighbors & bulbs).bit_count()
            if current > target:
                return 0, False, None
            if current == target:
                legal &= ~neighbors

        forced_cell: int | None = None
        for target, neighbors in self.wall_neighbors:
            deficit = target - (neighbors & bulbs).bit_count()
            if deficit > 0:
                eligible = neighbors & legal
                eligible_count = eligible.bit_count()
                if eligible_count < deficit:
                    return 0, False, None
                if forced_cell is None and eligible_count == deficit:
                    # All remaining eligible neighbors around this wall MUST have bulbs
                    forced_cell = (eligible & -eligible).bit_length() - 1

        return legal, True, forced_cell

    def feasible(self, bulbs: int, lit: int) -> bool:
        """Safe upper-bound checks for numbered clues and uncovered cells."""
        legal, ok, _ = self.legal_mask_and_check(bulbs, lit)
        if not ok:
            return False
        dark = self.white_mask & ~lit
        while dark:
            bit = dark & -dark
            target_index = bit.bit_length() - 1
            if (self.covers[target_index] & legal) == 0:
                return False
            dark ^= bit
        return True

    def branch_cell(self, lit: int, bulbs: int) -> tuple[int | None, tuple[int, ...]]:
        """Pick the first uncovered cell; this fixed order keeps DFS blind."""
        dark = self.white_mask & ~lit
        if not dark:
            return None, ()
        bit = dark & -dark
        target = bit.bit_length() - 1
        options = tuple(i for i in self.illuminators[target] if self.can_place(i, bulbs))
        return target, options

    def branch_mrv(self, lit: int, legal: int, forced_cell: int | None) -> tuple[int | None, tuple[int, ...]]:
        """MRV branching for A* with instant dead-end detection and forced wall moves."""
        dark = self.white_mask & ~lit
        if not dark:
            return None, ()

        best_target: int | None = None
        best_mask = 0
        best_count = sys.maxsize

        temp_dark = dark
        while temp_dark:
            bit = temp_dark & -temp_dark
            target = bit.bit_length() - 1
            temp_dark ^= bit

            options_mask = self.covers[target] & legal
            if not options_mask:
                # An unlit cell has 0 legal illuminators -> immediate dead end
                return target, ()
            count = options_mask.bit_count()
            if count < best_count:
                best_count = count
                best_target = target
                best_mask = options_mask
                if count == 1:
                    break

        if forced_cell is not None:
            return forced_cell, (forced_cell,)

        return best_target, _iter_bits(best_mask)

    def lower_bound(self, bulbs: int, lit: int, legal: int | None = None) -> int:
        """Admissible lower bound combining independent dark cells, max-gain coverage, and wall deficits."""
        if legal is None:
            legal, ok, _ = self.legal_mask_and_check(bulbs, lit)
            if not ok:
                return math.inf  # type: ignore[return-value]

        dark = self.white_mask & ~lit
        if not dark:
            coverage_bound = 0
        else:
            # 1. Independent dark cells bound: no single legal bulb can cover two chosen dark cells
            indep_bound = 0
            rem_dark = dark
            while rem_dark:
                bit = rem_dark & -rem_dark
                u = bit.bit_length() - 1
                opts = self.covers[u] & legal
                if not opts:
                    return math.inf  # type: ignore[return-value]
                indep_bound += 1
                # Any bulb covering `u` can only light cells within the union of covers[b] for b in opts
                reach = 0
                temp_opts = opts
                while temp_opts:
                    b_bit = temp_opts & -temp_opts
                    reach |= self.covers[b_bit.bit_length() - 1]
                    temp_opts ^= b_bit
                rem_dark &= ~reach

            # 2. Max-gain bound over remaining legal candidates
            max_gain = 0
            temp_legal = legal
            while temp_legal:
                b_bit = temp_legal & -temp_legal
                b = b_bit.bit_length() - 1
                temp_legal ^= b_bit
                gain = (self.covers[b] & dark).bit_count()
                if gain > max_gain:
                    max_gain = gain
            if max_gain == 0:
                return math.inf  # type: ignore[return-value]
            coverage_bound = max(indep_bound, math.ceil(dark.bit_count() / max_gain))

        # 3. Wall clue deficit bound
        total_deficit = 0
        max_deficit = 0
        active_walls: list[int] = []
        for target, neighbors in self.wall_neighbors:
            deficit = target - (neighbors & bulbs).bit_count()
            if deficit > 0:
                if (neighbors & legal).bit_count() < deficit:
                    return math.inf  # type: ignore[return-value]
                total_deficit += deficit
                if deficit > max_deficit:
                    max_deficit = deficit
                active_walls.append(neighbors)

        if not active_walls:
            clue_bound = 0
        else:
            max_help = 0
            temp_legal = legal
            while temp_legal:
                b_bit = temp_legal & -temp_legal
                temp_legal ^= b_bit
                help_count = sum(1 for neighbors in active_walls if neighbors & b_bit)
                if help_count > max_help:
                    max_help = help_count
            if max_help == 0:
                return math.inf  # type: ignore[return-value]
            clue_bound = max(max_deficit, math.ceil(total_deficit / max_help))

        return max(coverage_bound, clue_bound)

    def branch_first_dark(self, lit: int, legal: int) -> tuple[int | None, tuple[int, ...]]:
        """Pick the first uncovered cell in row-major order using bitmask legal candidates."""
        dark = self.white_mask & ~lit
        if not dark:
            return None, ()
        bit = dark & -dark
        target = bit.bit_length() - 1
        options_mask = self.covers[target] & legal
        return target, _iter_bits(options_mask)

    def feasible_with_legal(self, bulbs: int, lit: int, legal: int) -> tuple[int, bool]:
        """Update legal_mask with saturated walls and verify no wall or dark cell is starved."""
        # 1. Remove neighbors of walls that have reached their target count
        for target, neighbors in self.wall_neighbors:
            current = (neighbors & bulbs).bit_count()
            if current > target:
                return 0, False
            if current == target:
                legal &= ~neighbors

        # 2. Check if any wall no longer has enough eligible neighbors
        for target, neighbors in self.wall_neighbors:
            deficit = target - (neighbors & bulbs).bit_count()
            if deficit > 0 and (neighbors & legal).bit_count() < deficit:
                return 0, False

        # 3. Check if every remaining dark cell still has at least one legal illuminator
        dark = self.white_mask & ~lit
        while dark:
            bit = dark & -dark
            if (self.covers[bit.bit_length() - 1] & legal) == 0:
                return 0, False
            dark ^= bit

        return legal, True


def _path_from_parents(
    view: _View, goal: int, parents: dict[int, tuple[int, int] | None]
) -> tuple[tuple[Cell, ...], ...]:
    actions: list[int] = []
    cursor = goal
    while parents[cursor] is not None:
        parent, action = parents[cursor]  # type: ignore[misc]
        actions.append(action)
        cursor = parent
    actions.reverse()
    state = 0
    path = [tuple()]
    for action in actions:
        state |= 1 << action
        path.append(view.bulb_cells(state))
    return tuple(path)


def _finish(
    algorithm: AlgorithmName,
    status: SearchStatus,
    start: float,
    expanded: int,
    generated: int,
    max_frontier: int,
    peak_bytes: int,
    goal: int | None = None,
    parents: dict[int, tuple[int, int] | None] | None = None,
    view: _View | None = None,
    message: str = "",
) -> SearchResult:
    solution = view.bulb_cells(goal) if goal is not None and view is not None else ()
    path = _path_from_parents(view, goal, parents) if goal is not None and parents is not None and view else ()
    return SearchResult(
        algorithm=algorithm,
        status=status,
        solution=solution,
        solution_path=path,
        expanded=expanded,
        generated=generated,
        max_frontier=max_frontier,
        elapsed_seconds=time.perf_counter() - start,
        peak_memory_bytes=peak_bytes,
        solution_cost=len(solution) if goal is not None else None,
        message=message,
    )


def _memory_estimate_bytes(visited: int, frontier: int, bit_count: int) -> int:
    mask_bytes = sys.getsizeof(1 << bit_count)
    return visited * (88 + mask_bytes) + frontier * (64 + mask_bytes)


def _resource_status(
    start: float,
    limits: SearchLimits,
    expanded: int,
    estimated_bytes: int,
    cancelled: Callable[[], bool] | None,
    *,
    check_node_limit: bool = True,
) -> SearchStatus | None:
    if cancelled is not None and cancelled():
        return SearchStatus.CANCELLED
    if limits.timeout_seconds > 0 and time.perf_counter() - start >= limits.timeout_seconds:
        return SearchStatus.TIMEOUT
    if check_node_limit and limits.node_limit > 0 and expanded >= limits.node_limit:
        return SearchStatus.NODE_LIMIT
    if limits.memory_limit_mb > 0 and estimated_bytes > limits.memory_limit_mb * 1024 * 1024:
        return SearchStatus.MEMORY_LIMIT
    return None


def _emit_step(
    on_event: Callable[[SearchEvent], None] | None,
    view: _View,
    start: float,
    kind: str,
    state: int,
    expanded: int,
    generated: int,
    frontier_size: int,
    focus: int | None = None,
    detail: str = "",
    h: int | None = 0,
) -> None:
    if on_event is None:
        return
    depth = state.bit_count()
    on_event(SearchEvent(
        kind, view.bulb_cells(state), expanded, generated, frontier_size,
        depth, depth, h, depth + h if h is not None else None,
        view.cells[focus] if focus is not None else None, detail,
        time.perf_counter() - start,
    ))


@dataclass(slots=True)
class _DFSFrame:
    """Keep the next untried action while exploring an accepted child's subtree."""

    state: int
    lit: int
    legal: int
    options: tuple[int, ...] | None = None
    next_option: int = 0


@dataclass(slots=True)
class _CSPFrame:
    """Checkpoint state for Backtracking + Dynamic Constraint-Level MRV + Constraint Propagation."""

    state: int
    lit: int
    legal: int
    focus: int | None = None
    choices: tuple[tuple[int, int, int, int], ...] | None = None
    next_choice: int = 0
    last_action: int | None = None


class _CSPInterrupted(Exception):
    def __init__(self, status: SearchStatus) -> None:
        super().__init__(status)
        self.status = status


def backtracking_mrv_cp(
    puzzle: Puzzle,
    limits: SearchLimits | None = None,
    *,
    on_event: Callable[[SearchEvent], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    trace_steps: bool = False,
    algorithm_label: AlgorithmName = "csp",
) -> SearchResult:
    """Solve Akari using Backtracking + Dynamic Constraint-Level MRV + Fixed-Point Constraint Propagation."""
    limits = limits or SearchLimits()
    start = time.perf_counter()
    view = _View.build(puzzle)
    parents: dict[int, tuple[int, int] | None] = {0: None}
    stack: list[_CSPFrame] = []
    expanded = generated = max_frontier = peak_bytes = 0

    def trace(kind: str, mask: int, legal: int, focus: Cell | None = None, detail: str = "") -> None:
        if trace_steps and on_event is not None:
            depth = mask.bit_count()
            on_event(SearchEvent(
                kind, view.bulb_cells(mask), expanded, generated, len(stack), depth, depth, None, None,
                focus, detail, time.perf_counter() - start,
                forbidden=view.bulb_cells(view.white_mask & ~(mask | legal)),
            ))

    def observe(kind: str, mask: int, legal: int, focus: Cell | None, detail: str) -> None:
        # Root propagation can itself produce a long, paused trace before a search frame exists.
        def check_limits() -> None:
            estimated = _memory_estimate_bytes(len(parents), len(stack), len(view.cells))
            status = _resource_status(start, limits, expanded, estimated, cancelled, check_node_limit=False)
            if status is not None:
                raise _CSPInterrupted(status)

        check_limits()
        trace(kind, mask, legal, focus, detail)
        check_limits()

    # 1. Initial Fixed-Point Constraint Propagation at the root
    try:
        root_bulbs, root_lit, root_legal, ok = view.propagate(
            0, 0, view.white_mask, on_step=observe if trace_steps else None,
        )
    except _CSPInterrupted as exc:
        return _finish(algorithm_label, exc.status, start, 0, 0, 0, 0, view=view)
    if not ok:
        return _finish(
            algorithm_label,
            SearchStatus.UNSOLVABLE,
            start,
            0,
            0,
            0,
            0,
            view=view,
            message="Initial constraints are inconsistent",
        )

    _record_transition(parents, 0, root_bulbs)
    stack.append(_CSPFrame(root_bulbs, root_lit, root_legal))
    max_frontier = 1
    interval = max(1, limits.progress_interval)
    peak_bytes = _memory_estimate_bytes(len(parents), 1, len(view.cells))

    while stack:
        frame = stack[-1]
        estimated = _memory_estimate_bytes(len(parents), len(stack), len(view.cells))
        peak_bytes = max(peak_bytes, estimated)
        status = _resource_status(
            start, limits, expanded, estimated, cancelled, check_node_limit=frame.choices is None
        )
        if status:
            return _finish(
                algorithm_label, status, start, expanded, generated, max_frontier, peak_bytes, view=view
            )

        state, lit, legal = frame.state, frame.lit, frame.legal

        # 2. Check termination or select MRV constraint on first visit to this node
        if frame.choices is None:
            expanded += 1
            if (view.white_mask & ~lit) == 0 and is_goal_state(puzzle, view.bulb_cells(state)):
                trace("expand", state, legal, detail="Visit goal state after Constraint Propagation")
                trace("solution", state, legal, detail="All cells are lit and all numbered walls are satisfied")
                return _finish(
                    algorithm_label,
                    SearchStatus.SOLVED,
                    start,
                    expanded,
                    generated,
                    max_frontier,
                    peak_bytes,
                    state,
                    parents,
                    view,
                )

            # 3 & 4. Select constraint with fewest valid choices (MRV) and generate branching options
            selection: list[tuple[Cell, int, str]] = []
            frame.focus, frame.choices = view.select_mrv_choices(
                state, lit, legal,
                on_select=(lambda cell, score, kind: selection.append((cell, score, kind))) if trace_steps else None,
            )
            focus = view.cells[frame.focus] if frame.focus is not None else None
            detail = "Select most constrained wall or unlit cell via MRV"
            if selection:
                focus, score, kind = selection[0]
                detail = f"MRV {kind} {focus}: {score} candidate choices, {len(frame.choices)} legal branches"
            trace("expand", state, legal, focus, detail)
            if frame.focus is None or not frame.choices:
                trace("reject", state, legal, focus, "Selected constraint has 0 valid choices")
            elif not trace_steps and on_event and (expanded == 1 or expanded % interval == 0):
                _emit_step(on_event, view, start, "expand", state, expanded, generated, len(stack), frame.focus)

        # 6. All choices for this constraint failed -> restore state & backtrack
        if frame.next_choice >= len(frame.choices):
            stack.pop()
            if stack:
                trace(
                    "backtrack",
                    stack[-1].state,
                    stack[-1].legal,
                    view.cells[frame.last_action] if frame.last_action is not None else None,
                    "All MRV choices exhausted; restore checkpoint and backtrack",
                )
            continue

        # 5. Try the next choice and immediately run Fixed-Point Constraint Propagation
        choice_bulbs, choice_lit, choice_legal, action = frame.choices[frame.next_choice]
        frame.next_choice += 1
        trace("assign", choice_bulbs, choice_legal, view.cells[action], "Apply MRV branch choice; begin propagation")

        try:
            prop_bulbs, prop_lit, prop_legal, prop_ok = view.propagate(
                choice_bulbs, choice_lit, choice_legal, on_step=observe if trace_steps else None,
            )
        except _CSPInterrupted as exc:
            return _finish(
                algorithm_label, exc.status, start, expanded, generated, max_frontier, peak_bytes, view=view,
            )
        if not prop_ok:
            trace("backtrack", state, legal, view.cells[action], "Contradiction; restore checkpoint before next choice")
            continue

        _record_transition(parents, state, prop_bulbs)
        generated += 1
        stack.append(_CSPFrame(prop_bulbs, prop_lit, prop_legal, last_action=action))
        max_frontier = max(max_frontier, len(stack))
        trace("accept", prop_bulbs, prop_legal, view.cells[action], "Propagation succeeded; descend to next level")

    return _finish(
        algorithm_label, SearchStatus.UNSOLVABLE, start, expanded, generated, max_frontier, peak_bytes, view=view
    )


# Alias for convenience
csp_search = backtracking_mrv_cp


def depth_first_search(
    puzzle: Puzzle,
    limits: SearchLimits | None = None,
    *,
    on_event: Callable[[SearchEvent], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    trace_steps: bool = False,
) -> SearchResult:
    """Try one action at a time and descend immediately, retaining siblings in explicit DFS frames."""
    limits = limits or SearchLimits()
    start = time.perf_counter()
    view = _View.build(puzzle)
    parents: dict[int, tuple[int, int] | None] = {0: None}

    root_legal, ok = view.feasible_with_legal(0, 0, view.white_mask)
    if not ok:
        if trace_steps:
            _emit_step(on_event, view, start, "reject", 0, 0, 0, 0,
                       detail="Initial clues or lighting constraints are inconsistent")
        return _finish(
            "dfs", SearchStatus.UNSOLVABLE, start, 0, 0, 0, 0, view=view, message="Initial constraints are inconsistent"
        )

    # Suspended parent frames replace recursion, including on boards deeper than Python's recursion limit.
    stack = [_DFSFrame(0, 0, root_legal)]
    expanded = generated = 0
    max_frontier = 1
    interval = max(1, limits.progress_interval)
    peak_bytes = _memory_estimate_bytes(1, 1, len(view.cells))

    def trace(kind: str, mask: int, focus: int | None = None, detail: str = "") -> None:
        if trace_steps:
            _emit_step(on_event, view, start, kind, mask, expanded, generated, len(stack), focus, detail)

    while stack:
        frame = stack[-1]
        estimated = _memory_estimate_bytes(len(parents), len(stack), len(view.cells))
        peak_bytes = max(peak_bytes, estimated)
        status = _resource_status(
            start, limits, expanded, estimated, cancelled, check_node_limit=frame.options is None,
        )
        if status:
            return _finish(
                "dfs", status, start, expanded, generated, max_frontier, max(peak_bytes, estimated), view=view
            )

        state, lit = frame.state, frame.lit
        if frame.options is None:
            expanded += 1
            if (view.white_mask & ~lit) == 0 and is_goal_state(puzzle, view.bulb_cells(state)):
                trace("expand", state, detail="Visit goal state")
                trace("solution", state, detail="All cells are lit and all clues match")
                return _finish(
                    "dfs", SearchStatus.SOLVED, start, expanded, generated, max_frontier,
                    peak_bytes, state, parents, view,
                )

            target, frame.options = view.branch_first_dark(lit, frame.legal)
            trace("expand", state, target, "Visit DFS state; find the first dark cell")
            if target is None or not frame.options:
                trace("reject", state, target, "No legal bulb can illuminate the remaining dark cells")
            elif not trace_steps and on_event and (expanded == 1 or expanded % interval == 0):
                _emit_step(on_event, view, start, "expand", state, expanded, generated, len(stack), target)

        if frame.next_option >= len(frame.options):
            stack.pop()
            if stack:
                _, action = parents[state]
                trace("backtrack", stack[-1].state, action, "Remove the bulb; return to try the next DFS candidate")
            continue

        action = frame.options[frame.next_option]
        frame.next_option += 1
        action_bit = 1 << action
        child = state | action_bit
        child_lit = lit | view.covers[action]
        trace("assign", child, action, "Try placing a bulb")
        candidate_legal = frame.legal & ~view.covers[action]
        child_legal, child_ok = view.feasible_with_legal(child, child_lit, candidate_legal)

        # Subsequent siblings exclude all earlier options, including after returning from a child.
        frame.legal &= ~action_bit
        if not child_ok:
            trace("reject", child, action, "Placement leaves an unsatisfied clue or an unlightable cell")
            continue

        parents[child] = (state, action)
        generated += 1
        stack.append(_DFSFrame(child, child_lit, child_legal))
        max_frontier = max(max_frontier, len(stack))
        trace("accept", child, action, "Accept bulb; descend immediately to the next dark cell")

    return _finish("dfs", SearchStatus.UNSOLVABLE, start, expanded, generated, max_frontier, peak_bytes, view=view)


def astar(
    puzzle: Puzzle,
    limits: SearchLimits | None = None,
    *,
    on_event: Callable[[SearchEvent], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    trace_steps: bool = False,
) -> SearchResult:
    """Optimal A* over bulb sets using bitmask legal pruning, MRV branching, and independent-set lower bounds."""
    limits = limits or SearchLimits()
    start = time.perf_counter()
    view = _View.build(puzzle)
    if is_goal_state(puzzle, ()):
        if trace_steps:
            _emit_step(on_event, view, start, "expand", 0, 1, 0, 0)
            _emit_step(on_event, view, start, "solution", 0, 1, 0, 0, detail="The empty board is solved")
        return _finish("astar", SearchStatus.SOLVED, start, 1, 0, 1, 0, 0, {0: None}, view)

    root_legal, ok, root_forced = view.legal_mask_and_check(0, 0)
    if not ok:
        if trace_steps:
            _emit_step(on_event, view, start, "reject", 0, 0, 0, 0,
                       detail="Initial numbered-wall constraints are inconsistent", h=None)
        return _finish(
            "astar",
            SearchStatus.UNSOLVABLE,
            start,
            0,
            0,
            0,
            0,
            view=view,
            message="Initial constraints are inconsistent",
        )
    root_h = view.lower_bound(0, 0, root_legal)
    if math.isinf(root_h):
        if trace_steps:
            _emit_step(on_event, view, start, "reject", 0, 0, 0, 0,
                       detail="No legal bulbs can satisfy the initial state", h=None)
        return _finish(
            "astar",
            SearchStatus.UNSOLVABLE,
            start,
            0,
            0,
            0,
            0,
            view=view,
            message="No legal bulb can satisfy the initial state",
        )

    # Heap entries: (f_score, -g_score, tie, state, lit_mask, legal_mask, forced_cell)
    frontier: list[tuple[int, int, int, int, int, int, int | None]] = [
        (int(root_h), 0, 0, 0, 0, root_legal, root_forced)
    ]
    parents: dict[int, tuple[int, int] | None] = {0: None}
    seen: set[int] = {0}
    tie = 1
    expanded = generated = 0
    max_frontier = 1
    interval = max(1, limits.progress_interval)
    peak_bytes = _memory_estimate_bytes(1, 1, len(view.cells))

    def trace(
        kind: str, mask: int, focus: int | None = None, detail: str = "", h: int | None = None,
    ) -> None:
        if trace_steps:
            _emit_step(on_event, view, start, kind, mask, expanded, generated, len(frontier), focus, detail, h)

    while frontier:
        estimated = _memory_estimate_bytes(len(seen), len(frontier), len(view.cells))
        status = _resource_status(start, limits, expanded, estimated, cancelled)
        if status:
            return _finish(
                "astar", status, start, expanded, generated, max_frontier, max(peak_bytes, estimated), view=view
            )

        f_score, neg_g, _, state, lit, legal, forced_cell = heapq.heappop(frontier)
        queued_g = -neg_g
        expanded += 1
        peak_bytes = max(peak_bytes, estimated)
        h = f_score - queued_g
        if expanded > 1:
            trace("select", state, detail="Select the state with lowest f from A* frontier", h=h)

        if (view.white_mask & ~lit) == 0:
            bulbs = view.bulb_cells(state)
            if is_goal_state(puzzle, bulbs):
                trace("expand", state, detail="Expand goal state", h=h)
                trace("solution", state, detail="All cells are lit and all clues match", h=h)
                return _finish(
                    "astar",
                    SearchStatus.SOLVED,
                    start,
                    expanded,
                    generated,
                    max_frontier,
                    peak_bytes,
                    state,
                    parents,
                    view,
                )
            continue

        target, options = view.branch_mrv(lit, legal, forced_cell)
        trace("expand", state, target, "Expand state; choose a forced move or the most constrained dark cell", h)
        if target is None or not options:
            trace("reject", state, target, "No legal bulb can illuminate the remaining dark cells", h)
            continue

        if not trace_steps and on_event and (expanded == 1 or expanded % interval == 0):
            bulbs = view.bulb_cells(state)
            h = f_score - queued_g
            on_event(
                SearchEvent(
                    "expand",
                    bulbs,
                    expanded,
                    generated,
                    len(frontier),
                    queued_g,
                    queued_g,
                    h,
                    f_score,
                    view.cells[target],
                    elapsed_seconds=time.perf_counter() - start,
                )
            )

        child_g = queued_g + 1
        for action in options:
            child = state | (1 << action)
            trace("assign", child, action, "Try placing a bulb; heuristic not evaluated yet")
            if child in seen:
                trace("reject", child, action, "This bulb configuration is already in the visited set")
                continue
            child_lit = lit | view.covers[action]
            child_legal, child_ok, child_forced = view.legal_mask_and_check(child, child_lit)
            if not child_ok:
                trace("reject", child, action, "A numbered wall cannot be satisfied")
                continue
            child_h = view.lower_bound(child, child_lit, child_legal)
            if math.isinf(child_h):
                trace("reject", child, action, "No legal bulbs can illuminate all remaining dark cells")
                continue
            seen.add(child)
            parents[child] = (state, action)
            heapq.heappush(
                frontier,
                (child_g + int(child_h), -child_g, tie, child, child_lit, child_legal, child_forced),
            )
            tie += 1
            generated += 1
            trace("queue", child, action, "Add legal state to A* frontier", int(child_h))

        max_frontier = max(max_frontier, len(frontier))

    return _finish("astar", SearchStatus.UNSOLVABLE, start, expanded, generated, max_frontier, peak_bytes, view=view)
