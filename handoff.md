# Project handoff

Updated: 25 October 2026.

## Status

This repository now contains both required puzzles of the Introduction to AI
assignment. Pipes keeps DFS and Greedy Best-First. Light Up was merged from the
standalone `lightup` project into `light_up_problem/` with DFS and A* (minimum
bulbs). Both puzzles have pygame demos with step-by-step search playback, CSV
benchmarks and unittest suites (33 + 17 tests). Report and slide sources for
both languages live under `report/` and `slides/`, built with tectonic into four
PDFs. Remaining: fill in group member names on the title pages and rehearse.

The repository uses one environment and a separate package per puzzle.
`light_up_problem/` preserves the upstream subpackage layout (`core/`,
`algorithms/`, `generator/`, `benchmark/`, `ui/`); its JSON format string
`lightup-puzzle-v1` is unchanged for data compatibility. Avoid extracting shared
code before both games need it.

## Run and checks

```sh
uv sync --frozen
uv run main.py              # Pipes
uv run main.py lightup      # Light Up
uv run python -m unittest discover -s pipes_problem -t .
uv run python -m unittest discover -s light_up_problem -t .
uv run ruff check main.py pipes_problem light_up_problem
uv run python -m pipes_problem.benchmark
uv run python -m light_up_problem.benchmark --size 7 --difficulty easy
```

Requires Python 3.13 and uv. Runtime dependencies: pygame-ce, pygame-gui
(imported as `pygame`, `pygame_gui`). The locked dev dependency provides Ruff.
GitHub Actions runs headless tests and lint for both packages. Local
verification on 25 October: 50 tests pass, lint passes, and fresh benchmark
batches for both puzzles are recorded under `docs/benchmarks/2026-10-25-*`.

## Code map

| File | Responsibility |
|---|---|
| `main.py` | Launcher for both puzzles (`pipes` default, `lightup`) |
| `pipes_problem/app.py` | Pipes UI, input, animation, search playback, workers |
| `pipes_problem/rendering.py` | Native high-DPI canvas and antialiased drawing |
| `pipes_problem/model.py` | Pipes rules, validation, generation and manual state |
| `pipes_problem/search.py` | Pipes DFS/Greedy, pruning, timing and memory |
| `pipes_problem/storage.py` | Map/config loading, formatting, hashing and CSV |
| `pipes_problem/worker.py` | Isolated headless measurement process (Pipes) |
| `pipes_problem/benchmark.py` | Pipes batch runner, manifests and summary tables |
| `light_up_problem/algorithms/search.py` | Bitmask DFS and A* with admissible bound |
| `light_up_problem/core/` | Light Up puzzle model, rules, JSON serialization |
| `light_up_problem/generator/` | Seeded, witness-checked puzzle construction |
| `light_up_problem/benchmark/` | Light Up benchmark CLI, runner and worker |
| `light_up_problem/ui/app.py` | Light Up pygame/pygame_gui app |
| `pipes_problem/test_*.py`, `light_up_problem/test_*.py` | Tests |

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

- [README](README.md): setup, controls for both puzzles and repository layout.
- [Pipes analysis](docs/pipes-analysis.md): goals, actions, search space,
  pseudocode, complexity and evaluation.
- [Light Up analysis](docs/lightup-analysis.md): bitmask formulation, DFS, A*
  lower bound, generation methodology and measurement notes.
- [Implementation details](docs/pipes-plan.md): JSON, algorithms and recording.
- [Report sources](report/): `main-vi.tex` and `main-en.tex`, each importing a
  per-puzzle section file; build with tectonic.
- [Slides](slides/README.md): `main-vi.tex` / `main-en.tex` Beamer decks with
  per-puzzle frame files, editable TikZ diagrams and notes.
- Baselines: [Pipes 25 Oct](docs/benchmarks/2026-10-25-pipes.md),
  [Light Up 25 Oct](docs/benchmarks/2026-10-25-lightup.md),
  [Pipes 22 Oct (macOS)](docs/benchmarks/2026-10-22.md).

Generated logs, caches, played maps and old screenshots are ignored by Git.
Original Sudoku/Chess Ranger work and assignment review files remain local and
are excluded from this source repository. The merged Light Up project remains
at `../lightup/` untouched as the original standalone reference. User-created
maps under `maps/custom/` remain preserved. Do not delete local references or
historical outputs.

## Remaining work

1. Fill in group member names, student IDs and class on the report and slide
   title pages (placeholders are marked with square brackets).
2. Rehearse the presentation; the decks cover both puzzles and the measured
   comparison.
3. Optional extensions: harder and provably unsolvable inputs for both puzzles,
   a pruning ablation, and uniqueness checking for Light Up.
