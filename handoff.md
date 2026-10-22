# Project handoff

Updated: 22 October 2026.

## Status

This repository contains the Pipes portion of the Introduction to AI assignment.
The Python game, DFS, Greedy Best-First, visual playback and automatic benchmark
recording are implemented. Light Up is the intended second puzzle and has not
been implemented. The full two-puzzle report and presentation remain unfinished.

The repository uses one environment and a separate package per puzzle. Keep
`pipes_problem/` and add `light_up_problem/` when it has real implementation.
Avoid extracting shared code before both games need it.

## Run and checks

```sh
uv sync --frozen
uv run main.py
uv run python -m unittest discover -s pipes_problem -t .
uv run ruff check main.py pipes_problem
uv run python -m pipes_problem.benchmark
```

Requires Python 3.13 and uv. Runtime dependency: pygame-ce, imported as `pygame`.
The locked development dependency provides Ruff. GitHub Actions runs headless
tests and lint. Local verification on 22 October: 33 tests pass, lint passes,
and the default benchmark solves all 90 runs. See [baseline evidence](docs/benchmarks/2026-10-22.md).

## Code map

| File | Responsibility |
|---|---|
| `main.py`, `pipes_problem/__main__.py` | Entry points |
| `pipes_problem/app.py` | UI, input, animation, search playback, worker lifecycle |
| `pipes_problem/rendering.py` | Native high-DPI canvas and antialiased drawing |
| `pipes_problem/model.py` | Rules, validation, generation and manual state |
| `pipes_problem/search.py` | Search, pruning, validation, timing and memory |
| `pipes_problem/storage.py` | Map/config loading, formatting, hashing and CSV |
| `pipes_problem/worker.py` | Isolated headless measurement process |
| `pipes_problem/benchmark.py` | Batch runner, manifests and summary tables |
| `pipes_problem/test_*.py` | Tests |

## Decisions to preserve

- Light gray/white UI with blue accents. Keep Help and Inspect Connections
  removed. Keep copy short and omit unnecessary controls or dashboards.
- Connected pipes contain blue water with subtle animated highlights. Empty
  pipes remain gray. Motion Off stops animation while retaining water color.
- Preserve high-DPI rendering and antialiased joins. Cross tiles acknowledge
  every click. Rapid rotations remain queued and undoable.
- Map JSON stores `size`, `source` and `tiles`, with optional `reference`.
  No map `version`, `id` or `generation_seed`. Filename stem supplies the ID.
  Format one top-level key per line and one tile row per line.
- Source is zero-based `[row, column]` and anchors visualization. A 5×5 board
  accepts coordinates 0 through 4. It does not restrict complete valid networks.
- Runtime map generation remains available. Loaded maps use saved tiles and
  never call the generator. No solution is stored in map JSON.
- Automatically store results with seven columns. No export button, no live
  memory chart. Keep solved, unsolvable, limits and cancellation distinct.

## Search model

Both solvers assign orientations in fixed row-major order, using an empty prefix
as the root. They deduplicate symmetric rotations and share boundary, neighbor,
cycle and possible-connectivity pruning. Every solution passes independent
validation. Neither solver reads the generated answer or optimizes manual clicks.

Greedy uses `sum(log2(domain_size))` over unassigned domains, breaking ties by
greater depth and then insertion order. This ranks remaining choices rather than
estimating minimum clicks. Defaults are 30 seconds and 200,000 expansions.
See [academic analysis](docs/pipes-analysis.md) for formulation and pseudocode.

Run/Pause, Next and Speed control events. Show solution replays the final
assignment separately. Reset and algorithm/input changes clear the trace and
stop the owned measurement worker. Solvers start from the initial saved board,
ignoring manual moves and locks.

## Recording

Interactive CSV: `results/interactive.csv`. Per-run JSON: `results/interactive/`.
Played maps: `pipes_problem/maps/played/`. Each batch writes a new directory
containing `benchmark.csv`, `manifest.json` and `summary.md`.

The seven CSV columns are:

```text
puzzle_id,grid_size,algorithm,seed,status,time_ms,peak_memory_kib
```

The solver seed is blank for these deterministic algorithms. It does not refer
to map generation. Missing memory remains blank. Manifests carry exact maps,
hashes, settings, expansions, environment and source hash.

Timing is headless and memory is a separate matching tracemalloc replay.
Interactive measurements run in an isolated process to exclude UI allocations.
Live trace time excludes playback delays. After completion a matching headless
measurement replaces it. Immediate root rejection may show zero trace time until
the measurement finishes. Tracemalloc measures Python allocations rather than RSS.

## Documentation and presentation

- [README](README.md): setup, controls and repository layout.
- [Implementation details](docs/pipes-plan.md): JSON, algorithms and recording.
- [Course analysis](docs/pipes-analysis.md): goals, actions, search space,
  pseudocode, complexity and evaluation.
- [Slides](slides/README.md): 12-slide Beamer PDF, editable TikZ source and notes.
- [Baseline](docs/benchmarks/2026-10-22.md): fresh paired measurements and raw rows.

Generated logs, caches, played maps and old screenshots are ignored by Git.
Original Sudoku/Chess Ranger work and assignment review files remain local and
are excluded from this source repository. User-created maps under `maps/custom/`
remain preserved. Do not delete local references or historical outputs.

## Remaining work

1. Implement the second puzzle with both required search categories.
2. Add harder and unsolvable maps. Explain generated/reference-derived input
   provenance and measure pruning separately before generalizing results.
3. Finish the full report, two-puzzle slides and presentation rehearsal. This
   deck is the Pipes section only, not the completed assignment presentation.
4. Re-run paired benchmarks after solver changes and update the slide result
   table and evidence together.

The exhausted-search unsolvable message has been fixed and has a UI regression
test. Root-detected impossibility also displays an explanatory message. Some
ignored screenshots predate those fixes; regenerate them before presenting.
