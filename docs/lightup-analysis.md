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

DFS branches on the first unlit white cell in row-major order
(`_View.branch_first_dark`). A* uses a forced wall move or the dark cell with the
fewest legal illuminators (`_View.branch_mrv`). Both place only bulbs that are
currently legal and prune children using sound checks:

1. No line-of-sight bulb conflict and no numbered wall overfilled.
2. Every numbered wall can still reach its remaining count with legal cells
   adjacent to it.
3. No unlit cell has zero possible legal illuminators.

These checks only discard states that cannot reach a goal, preserving
completeness. DFS tries candidate illuminators in row-major order. A* uses its
branching policy and heuristic to prioritize search.

## 4. Blind search: DFS

Depth-first search keeps an explicit stack of frames containing the current
bulbs, lit and legal masks, candidate actions, and the next untried action. It
accepts the first feasible candidate and descends immediately, keeping that bulb
placed while exploring the next dark cell. Only after that subtree fails does
it remove the bulb, return to the parent frame, and try the next candidate.
Later sibling branches exclude earlier options to avoid rediscovering the same
bulb sets in different placement orders. The solver retains parent links for
solution reconstruction and returns the first complete solution (not minimum-cost).
Worst-case time is $O(2^W)$ states with per-state visibility and feasibility
work; retained memory is the parent table plus the stack, exponential in the
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

## 6. Backtracking + MRV + Constraint Propagation

`backtracking_mrv_cp` (also exported as `csp_search`, result code `csp`) keeps an
explicit stack of branch checkpoints. Fixed-point propagation removes neighbors
of satisfied walls, places all remaining neighbors when a wall requires them,
places the sole legal illuminator of a dark cell, and removes diagonal candidates
that would leave too few neighbors for a numbered wall. A new bulb also excludes
all cells it illuminates from holding another bulb. Contradictions reject a branch.

After propagation, dynamic constraint-level MRV compares the number of choices
for each unsatisfied wall (`comb(available neighbors, remaining bulbs)`) and each
dark cell (number of legal illuminators). Wall constraints win ties. Candidate
branches are ordered by the number of dark cells illuminated. The first branch
whose propagation succeeds is explored immediately; failed subtrees restore the
parent checkpoint before trying another choice. This solver returns the first
valid solution and does not promise minimum bulb count.

## 7. Step-by-step demonstration

The pygame interface (`ui/app.py`, backed by a spawn-safe `worker.py` process)
plays manually and runs solvers live: Start Search (Resume Search while paused),
Pause, and Reset with complete `SearchEvent` streaming. All three solvers accept
`trace_steps=True` to emit expansions, candidate bulb placements, rejected branches,
DFS acceptances/backtracks or A* frontier insertions/state selections, and a validated
goal. The default `trace_steps=False` preserves sampled expansion callbacks for
other callers. Trial A* placements have no `h` or `f` until their heuristic has
been evaluated; the UI shows these unevaluated values as a dash.

The menu maps **CSP (MRV + CP)** to `backtracking_mrv_cp`; the choice survives
widget rebuilding. Its propagation observer emits `propagate` for each forced
bulb and `prune` for each domain-reduction rule, including deductions at the root
before any node is expanded. No-op rules emit no event. Each event contains a
`forbidden` snapshot (an empty tuple by default for other solvers). The board marks
forbidden dark cells with `×`, separately from manual notes, and can highlight a
numbered wall as well as a white cell. MRV events identify the actual constraint
and choice count. Contradictions show the actual partially propagated state;
backtracking restores both bulbs and domains. Only A* displays `g/h/f`.

DFS emits `assign → accept → expand` as soon as a candidate is feasible, with
the accepted bulb preserved in the next state. It defers sibling attempts until
backtracking. Its generated-node count includes only accepted children created
during traversal, and its frontier statistic counts active DFS frames. A* continues
to generate all legal successors before selecting the lowest `f = g + h` from
the entire frontier; accepting the first legal successor would change A*.

The worker uses a bounded queue and waits for space without dropping events.
The UI displays at most one event per monotonic-clock interval at **2, 8, or 30
steps/s**, defaulting to **8**, matching Pipes. Slow frames do not trigger a
catch-up burst. Playback remains active after the worker exits and consumes the
final result only after all preceding steps have been displayed.

The `<` and `>` controls pause the live search to review recorded states;
`>` at the latest state displays exactly one new event. Pause freezes the board,
and Resume Search first replays any recorded states ahead of the current position.
After solving, these arrows review the solution placement by placement. Speed
changes apply during playback and survive resize, reset, and puzzle changes.
Reset stops any active worker and clears placements and queued events without
changing the puzzle. Visualization disables the search timeout while retaining
node and memory limits; worker elapsed time includes waits for queue space and pauses. A
"Compare DFS and A*" action runs both solvers once on the current puzzle without
trace or visualization waits, retaining its own benchmark time limits.

## 8. Input generation and provenance

`generator/generate.py` (`walls-first-witness-v2`) builds puzzles from a seed:
it chooses the wall layout first, then repeatedly places a bulb on a random dark
white cell until all white cells are lit. This allows multiple bulbs in a row or
column when separated by walls, and numbered clues from 0 through 4. Clues count
only orthogonally adjacent witness bulbs; about 25% of walls remain unnumbered
(`-1`), with at least one numbered and one unnumbered wall. The witness is verified
with `is_goal_state` before the puzzle is returned but is not stored in the
player-facing board. Sample
seeds cover all 4 sizes × 3 difficulties (12 combinations). Wall density targets
are 16% / 10.5% / 5.5% of board area for easy/normal/hard, rounded to the nearest
integer and counting both numbered and unnumbered walls. Metadata records both
counts separately; clue metrics count only numbered walls. The sample seed formula
is unchanged, but the layouts for those seeds differ from the previous cyclic
generator. Historical benchmark data describes the old generator. Uniqueness of the
solution is **not** checked and difficulty labels are structural, not
solve-time-calibrated — the report says so explicitly.

## 9. Measurement notes

`benchmark/runner.py` wraps each solver call with `tracemalloc` and reports
`execution_time_seconds` (the solver's own `perf_counter` measurement),
`peak_python_memory_bytes` (peak Python allocations, not process RSS),
expanded/generated nodes and status. Every repeat is a CSV row; medians are
computed per puzzle when using `--repeats`.

The current published experiment is
[31 October DFS/CSP](benchmarks/2026-10-31-lightup-dfs-csp.md): 4 sizes × 3
difficulties × 5 distinct seeds × 2 algorithms = 120 runs on 60 boards. Each map
is measured once per solver in a fresh spawned process, with algorithm order
alternating across consecutive seeds. Limits remain 30 s / 500,000 nodes / 512 MiB
estimated memory. DFS solved 52/60 with 8 TIMEOUT; CSP solved 60/60. No NODE_LIMIT
or MEMORY_LIMIT occurred; both remain enabled and tested. All SOLVED outputs
were independently validated. Attempt medians include stopped runs, with solved-only
medians reported separately. Neither solver promises a minimum-bulb result.

Reproduce with `python -m light_up_problem.benchmark.suite --output-prefix
results/lightup-dfs-csp --seeds-per-config 5`. The CSV, summary and manifest
store raw measurements, exact JSON maps, hashes, environment and limits.
Historical DFS/A* data remain at
[25 October CSV](benchmarks/2026-10-25-lightup.csv) and
[historical analysis](benchmarks/2026-10-25-lightup.md), using the older generator.

## 10. References

- Akari rules: [Puzzle Light Up](https://www.puzzle-light-up.com/).
- Russell, S. J., and Norvig, P. *Artificial Intelligence: A Modern Approach*,
  4th ed. (2021), Chapters 3 and 6.
- Python 3 standard library: `tracemalloc`, `time`, `multiprocessing`, `heapq`.
- pygame-ce and pygame_gui documentation.
