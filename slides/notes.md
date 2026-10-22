# Presentation notes

Suggested duration: approximately 7-9 minutes, excluding the live demonstration.
These notes explain the 12-slide Pipes section; they are not a full two-puzzle
assignment presentation.

1. **Pipes.** Introduce the puzzle and the comparison: a depth-first baseline
   and Greedy Best-First, both under the same constraints.
2. **Goal.** Each tile becomes a graph vertex. Ports pair into edges. All ports
   must match, and the final graph must be a tree. The source anchors the water
   animation. It does not make the solved-state criterion depend on one tile.
3. **Formulation.** The initial search state is the empty assignment. All tile
   shapes are already known. The board seen in the UI includes saved orientations
   for unassigned tiles. Explain that assignment depth and manual-click count
   measure different things.
4. **Successors.** The example is the top-left corner. N and W leave the board,
   so an elbow can only open E and S. Assigned-neighbor agreement restricts later
   choices, including absence of ports. A candidate still needs the remaining
   feasibility checks. The diagram shows the top/left boundary.
5. **Search space.** Symmetric rotations collapse: a cross contributes one choice,
   a straight two. The 268,435,456 count is the exact product of distinct rotations
   for the shipped example before boundaries/pruning, not its actual expansions.
   Fixed assignment order gives each prefix exactly one parent.
6. **Pruning.** Explain the port-count check, local matching, cycle rejection and
   possible-connectivity graph. Possible edges may require conflicting choices,
   so connectivity in the optimistic graph is necessary, not sufficient.
   Both algorithms use these same checks. This is constraint-pruned DFS.
7. **DFS.** Follow the first feasible orientation, recurse and backtrack.
   The numbered tree is schematic rather than a measured trace. Stop conditions
   propagate through recursion. Finite-tree completeness assumes sufficient
   resources. Python copies prefix tuples, so path storage differs from the
   simplest textbook stack representation.
8. **Heuristic.** The score is the log of the product of remaining domain sizes.
   It estimates unresolved choices while ignoring unassigned-neighbor dependency.
   It tends to favor deeper states and uses depth again to break ties. It is not
   claimed to estimate the minimum number of clicks. The numerical example is
   hypothetical.
9. **Greedy.** Use a heap ordered by h, negative depth and insertion number.
   A child waits in the queue rather than being immediately explored recursively.
   The actual implementation puts the unique root at priority zero, which has
   no effect because no other state exists yet. On this finite prefix tree,
   retaining every feasible candidate makes it complete with enough resources.
   Retained tuples can consume exponential space.
10. **Evaluation.** Compare identical inputs and limits. Timing and memory use
    separate passes. Tracemalloc reports Python allocations rather than RSS.
    Five repeats do not turn three maps into fifteen independent puzzle inputs.
11. **Results.** Read units carefully: milliseconds and KiB of peak allocation.
    Use the table as baseline evidence only. Queue overhead and an easy/pruned
    input set help explain why heuristic ordering need not be faster. All raw
    rows are linked from the benchmark documentation.
12. **Next experiments.** Use harder and unsolvable inputs and a pruning ablation
    before generalizing. Distinguish exhausted search from a stopped search.
    Mention the remaining second puzzle/report deliverables if presenting
    project status rather than a finished assignment.

## Live demonstration

Run `uv run main.py`. Load a saved 4×4 map, select DFS and use Next to show an
expansion, a rejection and a feasible assignment. Use Run/Pause and then Show
solution. Repeat with Greedy and explain queue selection. Finish by showing
an unsolvable input's message and the automatic result files. The existing
`pipes_problem/maps/custom/cdai.json` is an unsolvable example, loadable with
`uv run main.py --map pipes_problem/maps/custom/cdai.json`. Choose the demo input
in advance and rehearse its event sequence.

## References

- Game rules: https://www.puzzle-pipes.com/
- Search and CSP terminology: Russell and Norvig, *Artificial Intelligence:
  A Modern Approach*, 4th edition, Chapters 3 and 6, https://aima.cs.berkeley.edu/
- The formulation, heuristic, pseudocode and complexity qualifications describe
  this repository's `pipes_problem/search.py` and `model.py`.
- Measurements: `docs/benchmarks/2026-10-22.md` and its raw CSV.
