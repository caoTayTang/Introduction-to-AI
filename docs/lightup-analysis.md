# Light Up (Akari) as a search problem

This analysis describes the Light Up solver merged from the standalone
`lightup` project into `light_up_problem/` for the Introduction to AI course.
Algorithm behavior follows
[`algorithms/search.py`](../light_up_problem/algorithms/search.py); rules follow
[`core/rules.py`](../light_up_problem/core/rules.py) and
[`core/model.py`](../light_up_problem/core/model.py).

## 1. Task and environment

Given a square board of white cells, unnumbered black walls and numbered walls
(0–4), place bulbs on white cells so that:

1. Every white cell is illuminated. A bulb shines in the four orthogonal
   directions until a wall or the board edge.
2. No two bulbs see each other along an unobstructed row or column.
3. Every numbered wall has exactly its count of orthogonally adjacent bulbs.

Rules reference: [Puzzle Light Up](https://www.puzzle-light-up.com/). This is a
single-agent, deterministic, fully observable, discrete, static satisfaction
task. Unlike Pipes, this implementation also defines a path cost (one per bulb)
and the A* solver optimizes it: among valid solutions it returns one with the
minimum number of bulbs.

## 2. Formal problem formulation

| Component | Definition in this implementation |
|---|---|
| Input | Board rows: `None` (white), `-1` (wall), `0..4` (clue) |
| Search state | Set of bulb cells, encoded as an integer bitmask over white cells |
| Initial state | Empty bulb set (mask 0) |
| Action | Place a bulb on an eligible white cell |
| Transition | Add the cell bit; reject if it conflicts with rules or reachability |
| Goal test | All white cells lit, all clues exact, no bulb conflicts |
| Path cost | One per placed bulb (A* objective) |
| Solution | A goal bulb set, with its placement order as the path |

The bitmask is the key representation decision: a board with $W$ white cells
maps to a $W$-bit integer, so visited-set membership, successor generation and
lit-cell computation are integer operations.

## 3. Branching policy and pruning

Both solvers branch on the \textbf{first unlit white cell} in row-major order
(`_View.branch_cell`) and place only bulbs that are currently legal. Before
accepting a child, `_View.feasible` runs sound checks:

1. No line-of-sight bulb conflict and no numbered wall overfilled.
2. Every numbered wall can still reach its remaining count with legal cells
   adjacent to it.
3. No unlit cell has zero possible legal illuminators.

These checks only discard states that cannot reach a goal, preserving
completeness. The row-major branch choice is deterministic; it is not a
heuristic priority — the same branching feeds both solvers, keeping their
comparison fair.

## 4. Blind search: DFS

Depth-first search keeps a LIFO stack of masks plus a visited set, expands the
first unlit cell, and returns the first complete solution (not minimum-cost).
Worst-case time is $O(2^W)$ states with per-state visibility and feasibility
work; retained memory is the visited set plus the stack, exponential in the
worst case. Resource limits (timeout, node limit, estimated memory) produce
distinct `TIMEOUT` / `NODE_LIMIT` / `MEMORY_LIMIT` statuses, separate from
exhausted `UNSOLVABLE`.

## 5. Heuristic search: A*

A* uses a binary heap ordered by $f(n) = g(n) + h(n)$ with unit bulb cost, and a
`best_g` table to skip rediscoveries. The admissible heuristic is the maximum of
three lower bounds on the bulbs still needed:

1. $\lceil \text{dark cells} / \text{max cells one legal bulb can light} \rceil$
2. the largest single numbered-wall deficit
3. $\lceil \text{total wall deficits} / \text{max wall adjacencies one legal bulb can satisfy} \rceil$

Each component is a lower bound, so their maximum is admissible; with unit costs
and completed search, A* returns a minimum-bulb solution. The price is the
frontier and duplicate table in memory, and per-expansion bound computation.

## 6. Step-by-step demonstration

The pygame interface (`ui/app.py`, backed by a spawn-safe `worker.py` process)
plays manually and runs solvers live: Run / Pause / Step / Stop with sampled
`SearchEvent` streaming (expand/placement counters, current bulbs, focused
cell), then replays the returned solution placement by placement. A
"Compare DFS and A*" action runs both solvers once on the current puzzle.

## 7. Input generation and provenance

`generator/generate.py` builds puzzles from a seed: it constructs a cyclic
witness with one bulb per row and column, proposes walls away from witness
bulbs, derives clue values from adjacent witness bulbs, and keeps a wall only if
the witness remains valid. The witness is verified with `is_goal_state` before
the puzzle is returned but is not stored in the player-facing board. Sample
seeds cover all 4 sizes × 3 difficulties (12 combinations). Wall density targets
are 16% / 10.5% / 5.5% of board area for easy/normal/hard. Uniqueness of the
solution is **not** checked and difficulty labels are structural, not
solve-time-calibrated — the report says so explicitly.

## 8. Measurement notes

`benchmark/runner.py` wraps each solver call with `tracemalloc` and reports
`execution_time_seconds` (the solver's own `perf_counter` measurement),
`peak_python_memory_bytes` (peak Python allocations, not process RSS),
expanded/generated nodes and status. Every repeat is a CSV row; medians are
computed per puzzle. Evidence: [2026-10-25-lightup.csv](2026-10-25-lightup.csv)
and [2026-10-25-lightup.md](2026-10-25-lightup.md).

## 9. References

- Akari rules: [Puzzle Light Up](https://www.puzzle-light-up.com/).
- Russell, S. J., and Norvig, P. *Artificial Intelligence: A Modern Approach*,
  4th ed. (2021), Chapters 3 and 6.
- Python 3 standard library: `tracemalloc`, `time`, `multiprocessing`, `heapq`.
- pygame-ce and pygame_gui documentation.
