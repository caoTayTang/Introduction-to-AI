"""Pure puzzle rules and reproducible, guaranteed-solvable puzzle generation."""

import random
from dataclasses import dataclass

N, E, S, W = 1, 2, 4, 8
DIRECTIONS = ((-1, 0, N, S), (0, 1, E, W), (1, 0, S, N), (0, -1, W, E))


def rotate(mask: int, turns: int = 1) -> int:
    for _ in range(turns % 4):
        mask = ((mask << 1) & 15) | (mask >> 3)
    return mask


@dataclass(frozen=True)
class BoardStatus:
    connected: frozenset[int]
    mismatches: tuple[tuple[int, int], ...]
    cycle: bool
    solved: bool


def inspect_board(masks: list[int], size: int, source: int) -> BoardStatus:
    """Count each unmatched port and traverse only reciprocal connections."""
    adjacency = [set() for _ in masks]
    mismatches = []
    for i, mask in enumerate(masks):
        r, c = divmod(i, size)
        for dr, dc, bit, opposite in DIRECTIONS:
            if not mask & bit:
                continue
            nr, nc = r + dr, c + dc
            if not (0 <= nr < size and 0 <= nc < size):
                mismatches.append((i, bit))
            else:
                j = nr * size + nc
                if masks[j] & opposite:
                    adjacency[i].add(j)
                else:
                    mismatches.append((i, bit))
    connected, pending = {source}, [source]
    while pending:
        for j in adjacency[pending.pop()]:
            if j not in connected:
                connected.add(j)
                pending.append(j)
    seen, cycle = set(), False
    for start in range(len(masks)):
        if start in seen:
            continue
        stack = [(start, -1)]
        while stack:
            node, parent = stack.pop()
            if node in seen:
                cycle = True
                continue
            seen.add(node)
            stack.extend((j, node) for j in adjacency[node] if j != parent)
    solved = not mismatches and len(connected) == len(masks) and not cycle
    return BoardStatus(frozenset(connected), tuple(mismatches), cycle, solved)


class Puzzle:
    def __init__(self, size: int = 5, seed: int = 261):
        if size not in (4, 5, 7):
            raise ValueError("Supported sizes are 4, 5 and 7")
        self.size, self.seed = size, seed
        self.id = f"pipes-{size}x{size}-{seed}"
        self.source = (size // 2) * size + size // 2
        rng = random.Random(seed)
        self.solution = [0] * (size * size)
        visited = {self.source}
        frontier = []

        def add_edges(i):
            r, c = divmod(i, size)
            for dr, dc, bit, opposite in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < size and 0 <= nc < size:
                    j = nr * size + nc
                    if j not in visited:
                        frontier.append((i, j, bit, opposite))

        add_edges(self.source)
        while frontier:
            index = rng.randrange(len(frontier))
            i, j, bit, opposite = frontier.pop(index)
            if j in visited:
                continue
            self.solution[i] |= bit
            self.solution[j] |= opposite
            visited.add(j)
            add_edges(j)
        self.initial = [rotate(mask, rng.randrange(4)) for mask in self.solution]
        # Avoid an accidentally solved starting board.
        if inspect_board(self.initial, size, self.source).solved:
            i = next(i for i, mask in enumerate(self.initial) if rotate(mask) != mask)
            self.initial[i] = rotate(self.initial[i])
        self.reset()

    def reset(self):
        self.masks = self.initial.copy()
        self.locked: set[int] = set()
        self.history: list[tuple[str, int, int | bool]] = []
        self.moves = 0

    @property
    def status(self):
        return inspect_board(self.masks, self.size, self.source)

    def turn(self, index: int, turns: int = 1) -> bool:
        if not 0 <= index < len(self.masks) or index in self.locked:
            return False
        old = self.masks[index]
        new = rotate(old, turns)
        if turns % 4 == 0:
            return False
        self.history.append(("rotate", index, old))
        self.masks[index] = new
        self.moves += 1
        return True

    def toggle_lock(self, index: int):
        if not 0 <= index < len(self.masks):
            return
        was_locked = index in self.locked
        self.history.append(("lock", index, was_locked))
        if was_locked:
            self.locked.remove(index)
        else:
            self.locked.add(index)

    def undo(self):
        if not self.history:
            return None
        action, index, old = self.history.pop()
        if action == "rotate":
            self.masks[index] = old
            self.moves -= 1
        elif old:
            self.locked.add(index)
        else:
            self.locked.discard(index)
        return action, index
