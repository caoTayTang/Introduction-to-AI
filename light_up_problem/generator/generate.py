"""Deterministic puzzle generation with a constructive witness.

The generator chooses walls first, then places bulbs on randomly chosen dark
cells until every white cell is lit. It derives numbered clues from that witness
and leaves some walls unnumbered. This guarantees at least one solution without
storing an answer in the puzzle file.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from light_up_problem.core.model import Cell, Puzzle
from light_up_problem.core.rules import get_illuminated_cells, is_goal_state

SIZES = (7, 10, 14, 25)
DIFFICULTIES = ("easy", "normal", "hard")
_WALL_DENSITY = {"easy": 0.16, "normal": 0.105, "hard": 0.055}
_SAMPLE_SEEDS = {
    (size, difficulty): size * 10_000 + (index + 1) * 97
    for size in SIZES
    for index, difficulty in enumerate(DIFFICULTIES)
}


@dataclass(frozen=True, slots=True)
class DifficultyMetrics:
    clue_density: float
    constrained_white_fraction: float
    mean_clue_extremity: float


def difficulty_metrics(puzzle: Puzzle) -> DifficultyMetrics:
    whites = sum(value is None for row in puzzle.rows for value in row)
    clues = puzzle.numbered_walls()
    adjacent_whites = {
        (r + dr, c + dc)
        for r, c in clues
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if puzzle.is_white((r + dr, c + dc))
    }
    extremities: list[float] = []
    for r, c in clues:
        degree = sum(puzzle.is_white((r + dr, c + dc)) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        target = puzzle.rows[r][c]
        if degree:
            # 0 or degree is a stronger local requirement than a split clue.
            extremities.append(1.0 - (2.0 * min(target, degree - target) / degree))
    return DifficultyMetrics(
        clue_density=len(clues) / max(1, whites),
        constrained_white_fraction=len(adjacent_whites) / max(1, whites),
        mean_clue_extremity=sum(extremities) / max(1, len(extremities)),
    )


def generate_puzzle(size: int, difficulty: str, seed: int) -> Puzzle:
    """Create a seed-reproducible puzzle and independently verify its witness."""
    if size not in SIZES:
        raise ValueError(f"Board size must be one of {SIZES}")
    difficulty = difficulty.lower()
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Difficulty must be one of {DIFFICULTIES}")

    rng = random.Random(seed)
    target_walls = round(size * size * _WALL_DENSITY[difficulty])
    cells = [(row, col) for row in range(size) for col in range(size)]
    walls = rng.sample(cells, target_walls)
    grid: list[list[int | None]] = [[None for _ in range(size)] for _ in range(size)]
    for row, col in walls:
        grid[row][col] = -1

    layout = Puzzle(tuple(tuple(row) for row in grid))
    dark = {cell for cell in cells if layout.is_white(cell)}
    bulbs: list[Cell] = []
    while dark:
        bulb = rng.choice(sorted(dark))
        bulbs.append(bulb)
        dark.difference_update(get_illuminated_cells(layout, (bulb,)))
    witness = tuple(bulbs)

    unnumbered_count = min(target_walls - 1, max(1, round(target_walls * 0.25)))
    unnumbered = frozenset(rng.sample(walls, unnumbered_count))
    puzzle_id = f"akari-{size}-{difficulty}-{seed}"
    puzzle = _with_clues(grid, witness, size, seed, difficulty, puzzle_id, unnumbered_walls=unnumbered)
    if not is_goal_state(puzzle, witness):
        raise RuntimeError("Generator produced a board whose constructive witness is invalid")
    metrics = difficulty_metrics(puzzle)
    metadata = {
        "generator": "walls-first-witness-v2",
        "witness_verified": True,
        "uniqueness": "not_checked",
        "wall_count": target_walls,
        "numbered_wall_count": target_walls - unnumbered_count,
        "unnumbered_wall_count": unnumbered_count,
        "target_wall_count": target_walls,
        "difficulty_method": "seeded total wall density; easy has more walls, hard has fewer",
        "difficulty_metrics": {
            "clue_density": round(metrics.clue_density, 5),
            "constrained_white_fraction": round(metrics.constrained_white_fraction, 5),
            "mean_clue_extremity": round(metrics.mean_clue_extremity, 5),
        },
    }
    return Puzzle(puzzle.rows, puzzle_id, difficulty, seed, metadata)


def _with_clues(
    grid: list[list[int | None]],
    witness: tuple[Cell, ...],
    size: int,
    seed: int,
    difficulty: str,
    puzzle_id: str,
    *,
    unnumbered_walls: frozenset[Cell] = frozenset(),
) -> Puzzle:
    bulbs = set(witness)
    rows = [row.copy() for row in grid]
    for row in range(size):
        for col in range(size):
            if rows[row][col] == -1 and (row, col) not in unnumbered_walls:
                rows[row][col] = sum((row + dr, col + dc) in bulbs for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
    return Puzzle(tuple(tuple(row) for row in rows), puzzle_id, difficulty, seed)


def get_sample_puzzle(size: int, difficulty: str) -> Puzzle:
    """Return the deterministic, validated sample for one of the 12 modes."""
    try:
        seed = _SAMPLE_SEEDS[(size, difficulty.lower())]
    except KeyError as exc:
        raise ValueError("No sample exists for that size and difficulty") from exc
    return generate_puzzle(size, difficulty, seed)


def all_sample_modes() -> tuple[tuple[int, str], ...]:
    return tuple((size, difficulty) for size in SIZES for difficulty in DIFFICULTIES)
