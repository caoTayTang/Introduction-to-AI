# Pipes as a search problem

This analysis describes the implemented solver for an Introduction to AI course.
It connects problem formulation, uninformed search, heuristic search and
constraint propagation. Algorithm behavior below follows
[`search.py`](../pipes_problem/search.py); board validity follows
[`model.py`](../pipes_problem/model.py).

## 1. Task and environment

Rotate the pipes of an m×m board until every tile belongs to one connected,
loop-free network. Every open port must meet a reciprocal port on an adjacent
tile. Ports cannot leave the board. The implementation uses ordinary boundaries,
without wraparound. These rules follow the [Pipes reference game][pipes].

This is a single-agent, deterministic, fully observable, discrete, static task.
It is a satisfaction problem: return any valid orientation assignment. The code
does not minimize the number of manual rotations.

The source coordinate marks where the UI displays water. Once the entire board
is connected, any source tile reaches every tile. Changing the source therefore
changes the visual anchor but does not change which complete boards are valid.

## 2. Formal problem formulation

Let n=m². Number tiles 0 to n−1 in row-major order. Tile i has a fixed shape and
an orientation domain R_i containing its distinct rotations. An orientation is
a set of ports from {N,E,S,W}.

| Component | Definition in this implementation |
|---|---|
| Input | Saved tile shapes/orientations, grid size and source |
| Search state | Prefix s=(a_0,…,a_{k−1}) of assigned orientations |
| Initial search state | Empty prefix () with all shapes known |
| Next variable | Tile k, using fixed row-major order |
| Action | Choose a distinct boundary-valid orientation for tile k |
| Transition | Append the orientation: s′=s+(a_k) |
| Accepted successor | Transition passes all shared feasibility checks |
| Goal test | k=n and the complete network satisfies every rule |
| Step cost | Conceptually 1 per assignment; neither solver ranks by cost |
| Solution | A complete valid orientation tuple |

The saved scrambled board supplies tile domains and rotation enumeration order.
It is distinct from the empty initial search state. During playback, the UI
draws unassigned tiles in their saved orientations for context.

### Manual moves and solver steps

A manual move rotates any selected unlocked tile by 90 degrees. A solver step
assigns an absolute orientation to the next tile. One assignment may correspond
to zero, one, two or three clockwise clicks. Reject, queue and backtrack events
are explanatory events, not additional physical rotations. Both solvers use the
same assignment model, making their comparison consistent.

## 3. Goal test

For a complete assignment a:

1. Every a_i is a rotation of the original shape of tile i.
2. No port points beyond the board.
3. Adjacent ports agree in both presence and absence. An east port exists iff
   the neighboring tile has a west port, and likewise north/south.
4. A graph traversal from the source reaches all n tiles.
5. The undirected graph contains no cycle.

Tiles form vertices. Each reciprocal pipe connection forms one undirected edge.
A connected acyclic graph with n vertices has n−1 edges, hence 2(n−1) ports.
Rotation preserves port count, so a different total proves impossibility at the
root. Passing this count alone does not establish solvability.

`validate_solution()` independently checks shape preservation and the goal.
Neither algorithm reads the generator's stored solution. Loaded maps have no
solution attached.

## 4. Viable moves and shared pruning

Before search, remove orientations whose ports leave the board. For a proposed
child, the shared `compatible()` routine then:

1. Restricts each domain to agree with all assigned neighbors. A missing port
   must agree too. Reject if any domain becomes empty.
2. Rejects cycles already formed by assigned tiles, using disjoint sets.
3. Builds a possible-connectivity graph. An edge exists if each endpoint has
   some remaining orientation that could open toward the other. Reject if this
   optimistic graph cannot connect every tile.

Example: tile 0 is the top-left corner, with shape NE. Its distinct rotations
are NE, ES, SW and NW. Only ES survives the boundary test. If the next tile must
match an east port from tile 0, its chosen orientation needs a west port.

The possible-connectivity graph is an optimistic relaxation: its edges may rely
on incompatible choices for the same tile. Connectivity in that graph is only
a necessary condition. Search must still resolve the remaining choices.

Pruning is sound because a rejected state cannot extend to a valid solution.
It does not select the next variable by MRV and does not perform full arc
consistency between every pair of unassigned domains. Both algorithms receive
the same checks. DFS remains uninformed in its traversal order, although it is
a constraint-pruned baseline rather than an unpruned rotation enumerator.

## 5. Search space

Let r_i=|R_i|. An end, elbow or T-junction has four rotations, a straight has two,
and a cross has one. The unpruned number of complete assignments is

```text
U = product(r_i) <= 4^n
```

The assignment tree has maximum depth n and branching factor at most four.
An upper bound on all prefix nodes is:

```text
T = sum from k=0 to n of product from i=0 to k-1 of r_i
  <= (4^(n+1) - 1) / 3
```

The empty product is 1. Boundary filtering and shared pruning reduce the visited
tree, sometimes sharply. The naive leaf bound is 4^16≈4.29×10^9 for a 4×4 board,
4^25≈1.13×10^15 for 5×5, and 4^49≈3.17×10^29 for 7×7. These are upper bounds,
not measured expansion counts.

There is a unique parent for each prefix. Fixed assignment order avoids repeated
states caused by rotating tiles in different orders, so this solver needs no
closed set for duplicate detection. Every complete assignment has depth n.

Worst-case exploration remains exponential. Textbook DFS retains a path and
pending alternatives; this Python implementation additionally stores copied
prefix tuples and generator frames, allowing O(n²) retained prefix storage on
one branch. Greedy can retain exponentially many prefixes in its priority
queue, with each tuple taking up to O(n) space. Each successor also pays the
polynomial cost of feasibility checks. Heap operations add queue-management cost.

## 6. Depth-first search

DFS follows the first feasible child until it reaches a goal or a dead end, then
backtracks. It enumerates distinct rotations in saved-orientation order.

```text
SEARCH_DFS(input):
    construct boundary-valid domains
    if root feasibility fails: return UNSOLVABLE
    return VISIT(())

VISIT(s):
    if budget exhausted: return LIMIT_REACHED
    count one expansion
    if GOAL(s): return SOLVED(s)
    for a in boundary-valid rotations of tile |s|:
        child = s + (a)
        if FEASIBLE(child):
            result = VISIT(child)
            if result is SOLVED or LIMIT_REACHED: return result
    return UNSOLVABLE
```

Cancellation is an external stop signal and propagates as `cancelled`.
Completeness holds for this finite tree with sound pruning if search receives
enough resources. The first solution need not minimize manual clicks.

## 7. Greedy Best-First search

Greedy selects the queued prefix with the smallest remaining-choice score:

```text
h(s) = sum(log2(|D_i(s)|)) over unassigned tiles i
priority(s) = (h(s), -depth(s), insertion_order)
```

`D_i(s)` is the boundary-valid domain after matching assigned neighbors. All
domains are nonempty for an accepted state. The sum is the logarithm of the
product of remaining domain sizes. It estimates unresolved orientation choices
while ignoring dependencies between unassigned tiles.

For example, domain sizes (1,2,4) give h=3, while (1,1,2) give h=1. Greedy prefers
the latter. This ranking often favors deeper assignments. Equal h values prefer
greater depth, then earlier insertion. The code inserts the unique root with
priority zero; root priority cannot change selection because it is alone.

The score is an uncertainty heuristic rather than an admissible estimate of
remaining action cost. Every solution in this formulation needs n assignments,
so the exact remaining assignment count n−k would give no preference between
states at equal depth. The code uses h alone and no accumulated path cost g.

```text
SEARCH_GREEDY(input):
    construct boundary-valid domains
    if root feasibility fails: return UNSOLVABLE
    push () into a min-priority queue
    while queue is not empty:
        if budget exhausted: return LIMIT_REACHED
        s = pop the state of minimum priority
        count one expansion
        if GOAL(s): return SOLVED(s)
        for a in boundary-valid rotations of tile |s|:
            child = s + (a)
            domains = FEASIBLE(child)
            if domains exist:
                push child with (h(child), -|child|, next_serial)
    return UNSOLVABLE
```

On this finite, acyclic prefix space, retaining all feasible candidates makes
Greedy complete given enough time and memory. This does not imply completeness
for arbitrary Greedy graph searches. It provides no minimum-click guarantee.

## 8. Step-by-step demonstration

| Event | Meaning |
|---|---|
| expand | DFS visits or Greedy pops a prefix |
| assign | DFS chooses a feasible child |
| queue | Greedy inserts a feasible child |
| reject | Feasibility check discards an orientation |
| backtrack | DFS returns to the parent prefix |

Use Next to distinguish expansion from successor generation. A red outline and
reason explain rejected orientations. Greedy's displayed board can jump between
branches. Show solution replays only the returned assignment. An unsolvable
outcome means all candidates were excluded or exhausted. A limit means search
stopped before deciding. Those outcomes must remain distinct in the demonstration.

## 9. Evaluation design

Both algorithms receive identical saved maps, fixed tile order, pruning and
limits. This controls most implementation differences. It measures the value
and overhead of queue-based heuristic ordering under shared pruning.

Default experiment: nine generated maps across sizes 4, 5 and 7, five runs per
algorithm, 30 seconds of computation and 200,000 expansions per run. Repetitions
measure runtime variation, not independent puzzle diversity. Only three distinct
maps per size are present in the default batch.

Time uses a headless `perf_counter` pass including construction. A separate
`tracemalloc` replay measures peak Python allocation. Combine the passes only
when status, returned board and expanded count agree. UI drawing and playback
delays are excluded. Tracemalloc does not measure total process memory. See
[implementation details](pipes-plan.md) for the seven-column CSV schema.

Report solved/run counts with medians for successful runs. Retain failures and
limits. Expansion counts are in the manifest, while the CSV keeps the requested
minimal schema. For broader conclusions, add harder and genuinely unsolvable
inputs, disclose their provenance and consider a pruning ablation. A fast result
on generated maps does not establish superior behavior on all Pipes instances.

## 10. Code and references

| Concept | Implementation |
|---|---|
| State, successors, pruning | `Search`, `orientations`, `compatible` in `search.py` |
| DFS / Greedy | `dfs` / `greedy` in `search.py` |
| Goal test | `inspect_board` in `model.py`, `validate_solution` in `search.py` |
| Timing and memory | `solve`, `measure` in `search.py`, `worker.py` |
| Visualization | `advance_search`, `draw_board`, `draw_sidebar` in `app.py` |
| Repeatable evaluation | `benchmark.py`, `benchmark.json` |

Reference rules: [Pipes][pipes]. Search vocabulary and CSP background:
Russell and Norvig, [Artificial Intelligence: A Modern Approach][aima],
4th edition, Chapters 3 and 6. The formulation, heuristic, complexity discussion
and pseudocode here describe this repository's implementation and analysis.
Generated input files are project examples, not official website puzzle IDs.

[pipes]: https://www.puzzle-pipes.com/
[aima]: https://aima.cs.berkeley.edu/
