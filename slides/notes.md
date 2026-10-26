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

## Part 2 — Light Up / Akari (DFS + A*)

13. **Light Up.** Show the real 7×7 sample (akari-7-easy-70097) with its
    7-bulb solution. Bulbs illuminate along rows/columns until walls; no two
    bulbs may see each other; numbered walls count their adjacent bulbs.
    Emphasize the new axis versus Pipes: A* optimizes the bulb count while DFS
    returns the first solution.
14. **Formulation.** A state is a W-bit bitmask over white cells — placement,
    conflict checks and illumination are integer operations. Both solvers
    branch on the first unlit white cell in row-major order, so the comparison
    is fair. One parent per state; no heavy duplicate machinery.
15. **Shared pruning.** Feasibility: no sight-line conflicts, no overfilled
    clues, every clue still reachable, no dark cell without a possible
    illuminator. Sound checks only — completeness is preserved. This is why
    "blind" DFS is fast on small boards.
16. **DFS.** LIFO stack plus visited set; first unlit cell branching; returns
    the first solution. TIMEOUT/NODE_LIMIT/MEMORY_LIMIT stay distinct from
    UNSOLVABLE — a timed-out run proves nothing about solvability.
17. **A\* lower bound.** Walk through the three components: dark cells divided
    by the best single-bulb coverage, the largest wall deficit, and the total
    deficit divided by the best simultaneous adjacencies. Max of lower bounds
    is admissible; unit costs give a minimum-bulb guarantee on completion.
18. **A\* mechanics.** The heap keeps the whole frontier; best_g fights
    rediscovery; every expansion recomputes the bounds over big bitmasks. These
    are exactly the measured cost sources.
19. **Inputs.** Seeded generator with a cyclic witness (one bulb per row and
    column); walls kept only while the witness stays valid; clue numbers
    derived from the witness; 12 sample sets across 4 sizes and 3 densities.
    State openly: uniqueness is not checked and difficulty labels are
    structural, not calibrated against solve times.
20. **Demo.** Manual play with live lit/conflict feedback; Run/Pause/Step/Stop
    with sampled search events and counters; Compare DFS and A* on one board;
    solution replay. Solvers run in a spawn-safe worker process.
21. **Results (25 Oct, Linux).** DFS solved 12/12 with 7-35 expansions on most
    boards (248 on 10-easy) — the first-unlit policy plus pruning barely
    backtracks. A* completed 5/12, 9-250× slower, peaking at 3621 KiB before
    timing out on 10-hard. Where both finished, A* proved fewer bulbs:
    8→7, 11→10 and most strikingly 12→9 on 10-normal (DFS overshoots 33%).
    At 25×25, A* expands only 15-37 states in 30 s (near a second per
    expansion) while DFS finishes in 7-10 s. If asked about the 26.7 s A* run
    on 10-normal: all three repeats landed at 25.4-28.0 s with exactly 5,464
    nodes — deterministic search, stable ~5 ms per node, simply 8.8× more
    nodes than 10-easy because fewer clues weaken the bounds. The 30 s budget
    is our protocol choice (the brief mandates none): a 600 s A* rerun on the
    seven over-limit inputs still timed out on all of them (10-hard reached
    151,546 nodes and ~70 MiB in ten minutes), so TIMEOUT marks genuine
    resource exhaustion, not unsolvability and not a tight budget.
22. **Limitations.** Structural difficulty labels, unverified uniqueness,
    tracemalloc ≠ RSS, and stronger (matching-based) lower bounds left as
    future work.

## Live demonstrations

**Pipes:** run `uv run main.py`. Load a saved 4×4 map, select DFS and use Next
to show an expansion, a rejection and a feasible assignment. Use Run/Pause and
then Show solution. Repeat with Greedy and explain queue selection. Show an
unsolvable input's message (`uv run main.py pipes --map
pipes_problem/maps/custom/cdai.json`).

**Light Up:** run `uv run main.py lightup`. Pick the 7×7 easy sample, place a
few bulbs manually (watch conflicts turn red), then Solve with DFS, Pause and
Step through the live search, and finish with Play solution. Repeat with A* and
point at the expanded/frontier counters. The Compare action shows both solvers
on one board.

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
  `docs/benchmarks/2026-10-25-lightup.md` with their raw CSVs.
