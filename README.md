# Introduction to AI — BTL1

Search algorithms for two logic puzzles, implemented in Python 3 with visual
step-by-step demos. This repository contains **Pipes**
([puzzle-pipes.com](https://www.puzzle-pipes.com/), DFS + Greedy Best-First) and
**Light Up / Akari** ([puzzle-light-up.com](https://www.puzzle-light-up.com/),
DFS, A*, and Backtracking + MRV + Constraint Propagation). Each puzzle ships a
pygame game, automated benchmarks and tests.

![Pipes with a solved network and animated water](docs/images/pipes.png)

## Run

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/). From the repository
root:

```sh
uv sync
uv run main.py          # Pipes (default)
uv run main.py lightup  # Light Up
```

Equivalent module entry points:

```sh
uv run python -m pipes_problem
uv run python -m light_up_problem
```

### Pipes

Rotate tiles to connect every pipe into one network, with no open ends or
cycles. Connected pipes carry animated blue water from the source.

| Control | Action |
|---|---|
| Click / Shift-click | Rotate clockwise / counterclockwise |
| Right-click | Lock or unlock a tile for manual play |
| Undo / Reset | Undo a manual move / restore the starting map |
| DFS / Greedy | Select the algorithm |
| Run / Pause / Next | Play, pause or advance search events |
| Speed / Show solution | Change playback rate / replay a returned solution |
| Motion | Toggle rotation and water animation |

Supported boards are 4×4, 5×5 and 7×7. Run starts from the saved board and
ignores manual moves and locks. An unsolvable map produces an explicit message.

```sh
uv run main.py pipes --map pipes_problem/maps/pipes-4x4-261.json
uv run main.py pipes --size 7 --seed 262
```

### Light Up (Akari)

Place bulbs on white cells so every white cell is illuminated, no two bulbs see
each other along an unobstructed row or column, and every numbered wall has
exactly its count of immediately adjacent bulbs above, below, left and right
(diagonals do not count).

| Control | Action |
|---|---|
| Click | Place or remove a bulb |
| Puzzle picker | Choose size (7/10/14/25), difficulty and seed |
| Play manually / Solve | Switch between manual mode and the solver |
| DFS / A* / CSP (MRV + CP) | Select the algorithm (A* returns a minimum-bulb solution) |
| Start Search / Resume Search, Pause, Reset | Start or resume search, pause it, or stop and clear the board |
| Compare DFS and CSP | Run both solvers on the current puzzle once |
| `<` / `>` | Pause and review search states; `>` advances the paused worker at the latest state. After solving, review solution placements |
| Speed: 2 / 8 / 30 steps/s | Cycle playback speed; default is 8 steps/s |

Visualization shows each expansion, bulb attempt, rejected branch, stack/frontier
insertion, DFS backtrack or A* state selection, and the final goal. Each event
stays visible for one playback interval; slow frames do not skip steps. Pause
freezes the displayed step, and Resume Search replays forward from the current
history position before showing new events. The final result appears after the
trace has been displayed in order.

DFS accepts the first valid candidate and immediately explores the next dark
cell with that bulb kept in place. It tries another candidate only after the
current branch fails and backtracks. A* evaluates and queues legal successors
before selecting the next state with the lowest `f = g + h`.

CSP runs `backtracking_mrv_cp`: it selects the most constrained wall or dark
cell, tries a branch, and propagates forced decisions before descending. Each
forced bulb and each domain-pruning deduction has its own playback step, with a
reason shown below the board. Dark cells marked `×` are forbidden by the solver;
these marks are separate from manual notes and restore with the branch checkpoint
when backtracking. Initial propagation is animated too. Only A* shows `g/h/f`.
The Compare button continues to compare DFS and A*. The benchmark CLI also accepts CSP.

Visualization has no time limit; node and memory limits still apply. Worker
runtime includes waits for queue space and pauses. Benchmarks keep their own time
limits and run without visualization waits for solver performance measurements.

The puzzle picker in the UI selects size, difficulty and seed; puzzles can also
be imported as JSON by the benchmark CLI (`--puzzle-json`, format
`lightup-puzzle-v1`).

```sh
uv run main.py lightup
```

## Benchmarks

Both puzzles record time, peak Python memory (tracemalloc), node counts and
status to CSV. Interactive runs write under `results/` (git-ignored).

```sh
uv run python -m pipes_problem.benchmark        # 9 maps × DFS/Greedy × 5 runs
uv run python -m light_up_problem.benchmark \
  --size 7 --difficulty easy --algorithms dfs csp \
  --repeats 3 --timeout 30 --csv results/benchmark.csv
uv run python -m light_up_problem.benchmark.suite \
  --output-prefix results/lightup-dfs-csp --seeds-per-config 5 \
  --timeout 30 --node-limit 500000 --memory-limit-mb 512
```

`light_up_problem.benchmark` accepts `--size 7|10|14|25`,
`--difficulty easy|normal|hard`, `--seed`, `--puzzle-json`, `--algorithms`,
`--repeats`, `--timeout`, `--node-limit`, `--memory-limit-mb` and `--csv`.
Algorithms are `dfs`, `astar`, and `csp`. The suite runs DFS/CSP once on each of
five distinct seeds per size/difficulty (60 boards, 120 runs), using fresh
processes and unchanged resource limits. This differs from `--repeats`, which
reruns the same board. It saves raw CSV, summary JSON and an input/source manifest.
Published evidence (CSV + summary) lives under
[`docs/benchmarks/`](docs/benchmarks/): `2026-10-25-pipes.*` and
`2026-10-25-lightup.*` are historical baselines. The current DFS/CSP experiment
is [2026-10-31-lightup-dfs-csp.md](docs/benchmarks/2026-10-31-lightup-dfs-csp.md):
DFS solves 52/60 (8 TIMEOUT), CSP 60/60. NODE_LIMIT and MEMORY_LIMIT remain enabled;
neither occurred in these runs. Both reports and slide decks use this new evidence.

## Report and slides

LaTeX sources build with [tectonic](https://tectonic-typesetting.github.io/)
(one command per file; Vietnamese versions use DejaVu fonts):

```sh
tectonic report/main-vi.tex   # report/main-vi.pdf (tiếng Việt)
tectonic report/main-en.tex   # report/main-en.pdf (English)
tectonic slides/main-vi.tex   # slides/main-vi.pdf (tiếng Việt)
tectonic slides/main-en.tex   # slides/main-en.pdf (English)
```

`slides/main-*.tex` inputs the per-puzzle frame files (`pipes-vi/en.tex`,
`lightup-vi/en.tex`) and `results-table.tex`. Speaker notes are in
[slides/notes.md](slides/notes.md).

## Course material

- [Pipes as a search problem](docs/pipes-analysis.md): formulation, pruning,
  pseudocode, complexity and evaluation design.
- [Light Up as a search problem](docs/lightup-analysis.md): bitmask formulation,
  DFS and the A* lower bound, generation methodology, measurement notes.
- [Implementation notes](docs/pipes-plan.md): Pipes JSON, playback and recording.
- [Project handoff](handoff.md): code map, decisions and remaining work.

## Repository layout

```text
main.py               Launcher: uv run main.py [pipes|lightup]
pipes_problem/        Pipes game, solvers, tests, maps and configuration
light_up_problem/     Light Up game, bitmask DFS / A* / CSP solvers, tests, UI
docs/                 Algorithm analyses, benchmark evidence, images
report/               LaTeX sources of the course report (VI + EN)
slides/               LaTeX sources of the slides (VI + EN)
results/              Local benchmark output (git-ignored)
```

Use one repository for the assignment, with a separate package per puzzle. Keep
puzzle rules and solvers inside their package; extract shared code only when
both games actually need it.

## Checks

```sh
uv sync --frozen
uv run python -m unittest discover -s pipes_problem -t .
uv run python -m unittest discover -s light_up_problem -t .
uv run ruff check main.py pipes_problem light_up_problem
```

The default benchmark inputs are generated examples, not transcriptions of
website puzzles. `maps/custom/cdai.json` is a manually edited unsolvable Pipes
map; Light Up puzzles are generated from seeds with a verified constructive
witness (uniqueness is not checked). Rules references:
[Pipes](https://www.puzzle-pipes.com/) and
[Light Up](https://www.puzzle-light-up.com/).
Bundled font: Figtree under the [SIL Open Font License](pipes_problem/assets/OFL.txt).

The current Light Up generator chooses walls first, places bulbs on dark cells
until all white cells are lit, then derives numbered clues (0–4). About 25% of
walls remain unnumbered (`-1`). Easy/Normal/Hard use total wall densities of
16%/10.5%/5.5%, including unnumbered walls; these labels are not calibrated to
solve times. Seeds remain reproducible with the new generator, but produce
different boards from the old cyclic generator used for historical benchmarks.
