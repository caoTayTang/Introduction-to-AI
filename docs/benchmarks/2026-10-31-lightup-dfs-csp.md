# Light Up DFS / CSP: five distinct seeds per configuration (31 October 2026)

## Reproduce

```sh
.venv/bin/python -m light_up_problem.benchmark.suite \
  --output-prefix docs/benchmarks/2026-10-31-lightup-dfs-csp \
  --seeds-per-config 5 --timeout 30 --node-limit 500000 --memory-limit-mb 512
```

120 sequential measurements: 4 sizes × 3 difficulty labels × 5 different seeds × 2 algorithms. Each exact map is run once per algorithm in a fresh spawned process; algorithm order alternates across consecutive seeds. The raw `repeat=1,repeats=1` fields describe one run on a particular seed, not five repeats on the same board.

[Raw CSV](2026-10-31-lightup-dfs-csp.csv), [exact inputs/environment/source manifest](2026-10-31-lightup-dfs-csp-manifest.json), [machine-readable summary](2026-10-31-lightup-dfs-csp-summary.json).

Started: 2026-10-31T04:08:07.482658+07:00. Completed: 2026-10-31T04:13:34.280820+07:00.
Environment: `Linux-6.8.0-138-generic-x86_64-with-glibc2.35`, Python `3.13.14`.

**Limits:** 30 seconds, 500,000 expanded nodes, 512 MiB estimated solver memory. TIMEOUT, NODE_LIMIT, MEMORY_LIMIT and UNSOLVABLE are distinct. No automatic extension or fallback run was used. Checkpoints are cooperative, so the measured duration can slightly overshoot the limit.

**Measurement:** solver perf_counter with tracemalloc active, excluding generation/process startup/rendering and external solution validation. Peak traced Python allocation is not RSS and is not the memory estimate used by the limit. Full visualization trace is off. All SOLVED results were independently validated after timing.

## Seed ranges

| Size | easy | normal | hard |
|---|---|---|---|
| 7 | 70097–70101 | 70194–70198 | 70291–70295 |
| 10 | 100097–100101 | 100194–100198 | 100291–100295 |
| 14 | 140097–140101 | 140194–140198 | 140291–140295 |
| 25 | 250097–250101 | 250194–250198 | 250291–250295 |

## Medians across distinct seeds

All attempt time/memory/node medians below include limited runs. Their durations are censored attempts, not solved-time estimates. The JSON summary separately reports solved-only time and solution-cost medians.

| Size | Difficulty | Algorithm | SOLVED | TIMEOUT | NODE_LIMIT | MEMORY_LIMIT | Median attempt (s) | Median peak (KiB) | Median expanded |
|---|---|---|---|---|---|---|---|---|---|
| 7 | easy | DFS | 5/5 | 0 | 0 | 0 | 0.0075 | 24.9 | 11 |
| 7 | easy | CSP | 5/5 | 0 | 0 | 0 | 0.0066 | 25.2 | 4 |
| 7 | normal | DFS | 5/5 | 0 | 0 | 0 | 0.0066 | 26.8 | 9 |
| 7 | normal | CSP | 5/5 | 0 | 0 | 0 | 0.0103 | 29.0 | 6 |
| 7 | hard | DFS | 5/5 | 0 | 0 | 0 | 0.0074 | 27.3 | 8 |
| 7 | hard | CSP | 5/5 | 0 | 0 | 0 | 0.0107 | 30.5 | 6 |
| 10 | easy | DFS | 5/5 | 0 | 0 | 0 | 0.0229 | 55.9 | 27 |
| 10 | easy | CSP | 5/5 | 0 | 0 | 0 | 0.0288 | 56.2 | 9 |
| 10 | normal | DFS | 5/5 | 0 | 0 | 0 | 0.0218 | 60.0 | 15 |
| 10 | normal | CSP | 5/5 | 0 | 0 | 0 | 0.0309 | 61.8 | 8 |
| 10 | hard | DFS | 5/5 | 0 | 0 | 0 | 0.0229 | 62.4 | 12 |
| 10 | hard | CSP | 5/5 | 0 | 0 | 0 | 0.0314 | 67.8 | 10 |
| 14 | easy | DFS | 5/5 | 0 | 0 | 0 | 0.2330 | 135.3 | 261 |
| 14 | easy | CSP | 5/5 | 0 | 0 | 0 | 0.0801 | 109.1 | 12 |
| 14 | normal | DFS | 5/5 | 0 | 0 | 0 | 0.0724 | 117.3 | 34 |
| 14 | normal | CSP | 5/5 | 0 | 0 | 0 | 0.1030 | 123.5 | 17 |
| 14 | hard | DFS | 5/5 | 0 | 0 | 0 | 0.0832 | 126.1 | 22 |
| 14 | hard | CSP | 5/5 | 0 | 0 | 0 | 0.1168 | 134.6 | 15 |
| 25 | easy | DFS | 2/5 | 3 | 0 | 0 | 30.0001 | 2237.0 | 9328 |
| 25 | easy | CSP | 5/5 | 0 | 0 | 0 | 0.9558 | 562.1 | 31 |
| 25 | normal | DFS | 1/5 | 4 | 0 | 0 | 30.0004 | 3583.3 | 13886 |
| 25 | normal | CSP | 5/5 | 0 | 0 | 0 | 1.0274 | 696.9 | 33 |
| 25 | hard | DFS | 4/5 | 1 | 0 | 0 | 0.7835 | 870.3 | 46 |
| 25 | hard | CSP | 5/5 | 0 | 0 | 0 | 1.0421 | 868.0 | 34 |

## Interpretation and limits

- DFS: {'SOLVED': 52, 'TIMEOUT': 8}; CSP: {'SOLVED': 60}.
- Among 52 jointly solved pairs, CSP is faster on 15. Median paired time ratio DFS/CSP: 0.7262. This excludes stopped pairs and does not replace solved-rate reporting.
- CSP search nodes can encompass multiple placements and deductions; expanded-node counts are not equal units of work across algorithms. This is a combined MRV/value-ordering/CP comparison, not an ablation of MRV alone.
- On some small maps CP costs more per node; structural wall-density labels do not order solve difficulty monotonically.
- Neither first-solution algorithm guarantees minimum bulb count. Five different seeds per configuration are a small input sample, not repeat-timing variance on one map.
- Current generator: walls-first-witness-v2, with independently validated constructive witnesses, numbered and unnumbered walls, and unchecked uniqueness.
- Older 25 October DFS/A* evidence uses the old generator and remains archived. Its 72-run and 600-second results are not pooled into the new experiment.
