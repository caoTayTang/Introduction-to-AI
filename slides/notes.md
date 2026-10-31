# Presentation notes

Suggested duration: approximately 12-15 minutes including both puzzles,
excluding live demonstrations. The decks (VI/EN) share the same frame order.

## Part 1 — Pipes (DFS + Greedy Best-First)

1. **Pipes.** Introduce the puzzle and the comparison: a depth-first baseline
   and Greedy Best-First, both under the same constraints.
2. **Goal.** Each tile becomes a graph vertex. Ports pair into edges. All ports
   must match, and the final graph must be a tree. The source anchors the water
   animation. It does not make the solved-state criterion depend on one tile.
3. **Formulation.** The initial search state is the empty assignment. All tile
   shapes are already known. Assignment depth and manual-click count measure
   different things.
4. **Successors.** The example is the top-left corner: N and W leave the board,
   so an elbow can only open E and S. Assigned-neighbor agreement restricts
   later choices, including absence of ports. A candidate still needs the
   remaining feasibility checks.
5. **Search space.** Symmetric rotations collapse: a cross contributes one
   choice, a straight two. The 268,435,456 count is the exact product of
   distinct rotations for the shipped example before boundaries/pruning, not
   its actual expansions. Fixed assignment order gives each prefix exactly one
   parent.
6. **Pruning.** Explain the port-count check, local matching, cycle rejection
   and possible-connectivity graph. Possible edges may require conflicting
   choices, so connectivity in the optimistic graph is necessary, not
   sufficient. Both algorithms use these same checks.
7. **DFS.** Follow the first feasible orientation, recurse and backtrack. The
   numbered tree is schematic. Python copies prefix tuples, so path storage
   differs from the simplest textbook stack.
8. **Heuristic.** The score is the log of the product of remaining domain
   sizes. It estimates unresolved choices while ignoring unassigned-neighbor
   dependency. It is not claimed to estimate the minimum number of clicks.
9. **Greedy.** A heap ordered by h, negative depth and insertion number. On
   this finite prefix tree, retaining every feasible candidate makes it
   complete with enough resources. Retained tuples can consume exponential
   space.
10. **Evaluation.** Compare identical inputs and limits. Timing and memory use
    separate passes; tracemalloc reports Python allocations rather than RSS.
    Five repeats do not turn three maps into fifteen independent puzzle inputs.
11. **Results (25 Oct, Linux).** Read units carefully: milliseconds and KiB of
    peak allocation. DFS wins at 5×5 and two of three 7×7 maps; Greedy takes
    the hardest map (38.2 vs 40.8 ms) and holds 4-5× less traced memory. Easy,
    well-pruned inputs explain why heuristic ordering need not be faster.
12. **Next experiments.** Harder and unsolvable inputs, a pruning ablation, and
    keeping exhausted search distinct from a stopped search.

## Part 2 — Light Up / Akari (DFS + Backtracking/MRV/CP)

- Show the current seed 70097 board and a validated CSP solution. The old cyclic
  witness picture is replaced by the walls-first generator's actual board.
- A state contains bulb, illuminated and legal-location masks. DFS uses the first
  dark cell and row-major options. It accepts the first feasible bulb and descends
  immediately, trying siblings only after backtracking.
- CSP propagates satisfied-wall exclusions, forced wall neighbors, sole
  illuminators and diagonal conflicts to a fixed point. It then compares wall
  combination counts with dark-cell illuminator counts (MRV), preferring walls
  on ties and high lighting gain for value ordering.
- A checkpoint restores both bulbs and legal domains. One CSP search node can
  contain multiple forced bulbs; node counts do not measure equal work.
- The new experiment has 4 sizes × 3 difficulties × 5 different seeds × 2
  algorithms = 120 runs on 60 boards. Each board is run once per solver. Do not
  describe this as five repeat timings of one map.
- Limits stay at 30 s, 500,000 expanded nodes and 512 MiB estimated memory. Keep
  TIMEOUT, NODE_LIMIT and MEMORY_LIMIT distinct from UNSOLVABLE. No automatic
  extension to 600 s is part of the new experiment.
- Read the two results slides together: SOLVED/5, median duration of all attempts,
  and median traced peak KiB for every configuration. Limited durations are not
  completed solve times. The summary JSON contains solved-only medians as well.
- Fresh spawned processes and sequential execution isolate each measurement.
  Algorithm order alternates by seed. Solver time includes tracemalloc overhead;
  generation/startup/animation are excluded. Every SOLVED output is validated.
- Describe the observed tradeoff, not a universal speed claim: propagation can
  reduce branching substantially while costing more on already easy boards.
  Check the current CSV for totals; older results are historical and use
  the old generator. Neither DFS nor CSP promises minimum bulb count.
- Five seeds are a small sample; uniqueness is unchecked; allocation is not RSS
  or the estimate used for MEMORY_LIMIT. Next: more seeds and CP/MRV ablations.

## Live demonstrations

**Pipes:** run `uv run main.py`. Load a saved 4×4 map, select DFS and use Next
to show an expansion, a rejection and a feasible assignment. Use Run/Pause and
then Show solution. Repeat with Greedy and explain queue selection. Show an
unsolvable input's message (`uv run main.py pipes --map
pipes_problem/maps/custom/cdai.json`).

**Light Up:** run `uv run main.py lightup`. Pick the 7×7 easy sample, place a
few bulbs manually (watch conflicts turn red), then Solve with DFS, Pause and
use > to advance, then Resume Search. Repeat with CSP (MRV + CP): point out
individual forced bulbs, forbidden-cell marks and checkpoint restoration. The
Compare DFS and CSP on the same board, then use the benchmark suite for the
published multi-seed DFS/CSP comparison.

Choose demo inputs in advance and rehearse their event sequences.

## References

- Game rules: https://www.puzzle-pipes.com/ and https://www.puzzle-light-up.com/
- Search and CSP terminology: Russell and Norvig, *Artificial Intelligence:
  A Modern Approach*, 4th edition, Chapters 3 and 6, https://aima.cs.berkeley.edu/
- Pipes formulation and pseudocode: `pipes_problem/search.py`, `model.py`,
  `docs/pipes-analysis.md`.
- Light Up formulation, bound and pseudocode: `light_up_problem/algorithms/search.py`,
  `docs/lightup-analysis.md`.
- Measurements: `docs/benchmarks/2026-10-25-pipes.md` and
  `docs/benchmarks/2026-10-31-lightup-dfs-csp.md` with their raw CSVs and manifest.
