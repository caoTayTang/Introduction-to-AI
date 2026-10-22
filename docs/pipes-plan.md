# Pipes: maps, search and measurements

Implemented: JSON maps/settings, DFS, Greedy Best-First, incremental visual
playback, automatic CSV recording and headless batch benchmarks.

## Assignment coverage

Pipes implements one blind search (DFS) and one heuristic search (Greedy
Best-First), with graphical step-by-step exploration and measured execution
time/peak memory on saved inputs. The assignment also needs the second puzzle,
the written report and presentation; this implementation alone does not complete
those deliverables or guarantee a mark.

## Map JSON

```json
{
  "size": 4,
  "source": [2, 2],
  "tiles": [
    ["E", "NW", "N", "ES"],
    ["S", "NS", "N", "EW"],
    ["ESW", "NSW", "NESW", "NES"],
    ["ES", "S", "E", "S"]
  ]
}
```

N/E/S/W describe open ports: ES is an elbow, NS is straight, NESW is a cross.
Tiles are row-major. Source is a zero-based [row, column], used as the visual
connectivity anchor. The goal is reciprocal ports, no open ends, all tiles
connected, and no cycles. The saved tiles define the input; maps contain no
generation seed. A `reference` string may identify an imported puzzle.
Maps contain no answers. Generated maps are solvable but uniqueness is not
promised. Supported sizes are 4, 5 and 7.

The filename without `.json` is the puzzle ID used in results. No version or ID
is stored inside map JSON. Malformed maps are rejected. Valid but unsolvable
inputs return `unsolvable` and display an explanatory message after detection
or search exhaustion. A limit does not establish unsolvability.
Reset and Run restore saved starting orientations; solvers ignore manual moves
and locks. The loader never invokes the generator.

## Game configuration and controls

[pipes_problem/config.json](../pipes_problem/config.json):

```json
{
  "version": 1,
  "startup_map": "maps/pipes-5x5-261.json",
  "animation_ms": 260,
  "playback_steps_per_second": 8
}
```

Paths are relative to the config file. Animation duration accepts 0–2000 ms;
playback accepts 1–120 steps per second. Zero duration disables rotation motion.

```sh
uv run main.py
uv run main.py --map pipes_problem/maps/pipes-4x4-261.json
uv run main.py --size 7 --seed 262
uv run main.py --config pipes_problem/config.json
```

Select DFS or Greedy, then Run. Run toggles Pause/Resume during a search. Next
starts a paused run or advances one event. Speed cycles 2/8/30 events per second.
Show solution replays the returned tile assignments after success.

The board shows expand, assign/queue, reject and backtrack events. Rejected tiles
have a red outline and a reason below the board. Unassigned tiles retain their
original orientation, so intermediate boards are previews rather than claims
of a complete solution. Greedy can jump between queued branches.

The sidebar shows expanded states, computation time, status and measured peak
allocation. An expansion is a state visited by DFS or popped by Greedy, including
the root and goal. Events are produced incrementally; no full trace is buffered.
Changing the map/algorithm, resetting or closing cancels the current run.

## Algorithms

Both algorithms assign tiles in fixed row-major order. A state is a prefix of
assigned orientations. Each tile has at most four distinct rotations; symmetric
rotations are deduplicated. Shared pruning rejects boundary ports, mismatched
assigned neighbors, empty remaining domains, formed cycles and states whose
possible connections cannot reach all tiles. A tree must have exactly 2(n−1)
ports; incompatible inputs are rejected before exploration. Every reported
solution is independently validated.

DFS traverses this finite assignment tree in depth-first order without a
heuristic ranking. Greedy uses a priority queue ordered by:

`h(state) = sum(log2(|D_i|))` over unassigned tiles.

`D_i` is the remaining domain after boundary restrictions and matching assigned
neighbors. Lower scores favor states with fewer remaining choices. Equal scores
favor deeper assignments, then insertion order. This is an uncertainty ranking,
not an admissible distance estimate. It uses no path-cost term and is not A*.
Neither solver optimizes manual rotation count. Both exhaust the finite search
space if allowed to finish; an interrupted/budget-limited run cannot establish
unsolvability. Greedy may retain more states and is not guaranteed to be faster.

Defaults: 30 seconds of solver computation and 200,000 expansions per run.
The nine shipped maps are a small baseline; include harder and unsolvable inputs
in the report before making general performance claims.

## Automatic CSV

Interactive runs append to `results/interactive.csv`. The exact starting map is
also saved under `pipes_problem/maps/played/`; settings, environment, map hash,
source-code hash and recording details go in `results/interactive/*.json`.
No export button is needed.

The CSV contains exactly seven columns:

| Column | Meaning |
|---|---|
| puzzle_id | Saved input ID; exact map/hash are in the manifest |
| grid_size | Side length |
| algorithm | `dfs` or `greedy_best_first` |
| seed | Solver random seed; blank for these deterministic methods |
| status | `solved`, `unsolvable`, `limit_reached`, `cancelled`, `error` |
| time_ms | Solver computation time in milliseconds |
| peak_memory_kib | Peak traced Python allocation in KiB; blank if unavailable |

One row is appended per run, including cancelled and failed runs. The manifest
uses `csv_row` numbered from 1 for the first data row. The CSV seed is reserved
for a stochastic solver; map generation uses no saved
seed metadata.

## Batch benchmarks

[pipes_problem/benchmark.json](../pipes_problem/benchmark.json):

```json
{
  "version": 1,
  "maps": ["maps/*.json"],
  "algorithms": ["dfs", "greedy_best_first"],
  "repetitions": 5,
  "time_limit_seconds": 30,
  "max_expansions": 200000,
  "output_directory": "../results"
}
```

```sh
uv run python -m pipes_problem.benchmark
uv run python -m pipes_problem.benchmark --config pipes_problem/benchmark.json
```

Each batch writes `benchmark.csv`, `manifest.json` and `summary.md` in a timestamped
folder under results. Both methods receive identical saved inputs and limits.
The manifest stores exact maps/hashes, resolved settings, heuristic/pruning,
Python/OS/package versions, source hash, repetition and expansion counts.
The summary reports solved/runs and medians for successful runs, retaining all
other outcomes in CSV. Duplicate map filenames and malformed configurations are rejected.

## Measurement scope

`perf_counter` measures a headless solve, including solver construction, excluding
map loading, generation, rendering, pauses and visual trace creation. Peak Python
allocation is measured by a separate `tracemalloc` replay. The replay uses the
same expansion budget and must match status, returned board and expansion count;
otherwise peak memory is left blank. This prevents profiling overhead from
changing a timed result. Tracemalloc measures Python allocations, not process RSS.

Interactive measurement runs in a separate process, excluding window/font/UI
allocations. During playback, time reflects trace computation; after completion,
the headless measurement replaces it when the results agree. Cancelled runs use
actual trace computation time and have no peak measurement. If the measurement
worker fails, the trace result is recorded with memory unavailable.

Peak allocation is sufficient as the per-run memory statistic. Across repeated
runs, use medians or means of peaks and times; no additional CSV columns are
required. Do not compare a quick failed run with a successful solve as if both
performed the same work. Discuss the heuristic, pruning, limits and difficult
inputs in the report.
