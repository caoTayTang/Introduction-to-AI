"""JSON puzzle/config files and the small shared CSV result format."""

import csv
import hashlib
import json
import re
from pathlib import Path

from .model import Puzzle

ROOT = Path(__file__).resolve().parent
PORTS = ((1, "N"), (2, "E"), (4, "S"), (8, "W"))
CSV_FIELDS = (
    "puzzle_id",
    "grid_size",
    "algorithm",
    "seed",
    "status",
    "time_ms",
    "peak_memory_kib",
)


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def puzzle_to_dict(puzzle):
    result = {
        "size": puzzle.size,
        "source": list(divmod(puzzle.source, puzzle.size)),
        "tiles": [
            [
                "".join(name for bit, name in PORTS if mask & bit)
                for mask in puzzle.initial[r * puzzle.size : (r + 1) * puzzle.size]
            ]
            for r in range(puzzle.size)
        ],
    }
    if getattr(puzzle, "reference", None):
        result["reference"] = puzzle.reference
    return result


def puzzle_from_dict(data, identity="map"):
    if not isinstance(data, dict):
        raise ValueError("Map must be an object")  # noqa: TRY004 -- invalid JSON input
    size = integer(data.get("size"), "size", 1)
    if size not in (4, 5, 7):
        raise ValueError("Map size must be 4, 5 or 7")
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", identity
    ):
        raise ValueError(
            "Map filename must use letters, numbers, dots, underscores or hyphens"
        )
    source = data.get("source")
    if not isinstance(source, list) or len(source) != 2:
        raise ValueError("source must be [row, column]")
    if any(integer(v, "source coordinate") >= size for v in source):
        raise ValueError("source is outside the board")
    rows = data.get("tiles")
    if not isinstance(rows, list) or len(rows) != size:
        raise ValueError("tiles must have size rows")
    masks = []
    for row in rows:
        if not isinstance(row, list) or len(row) != size:
            raise ValueError("Every tiles row must have size columns")
        for tile in row:
            if (
                not isinstance(tile, str)
                or not tile
                or any(p not in "NESW" for p in tile)
                or len(set(tile)) != len(tile)
            ):
                raise ValueError(f"Invalid tile ports: {tile!r}")
            masks.append(sum(bit for bit, name in PORTS if name in tile))
    reference = data.get("reference")
    if reference is not None and not isinstance(reference, str):
        raise ValueError("reference must be a string")
    # Loading never invokes the generator, and no solution is stored on the map.
    puzzle = Puzzle.__new__(Puzzle)
    puzzle.size, puzzle.seed, puzzle.id = size, None, identity
    puzzle.source = source[0] * size + source[1]
    puzzle.reference = reference
    puzzle.initial = masks
    puzzle.reset()
    return puzzle


def load_map(path):
    path = Path(path)
    return puzzle_from_dict(read_json(path), path.stem)


def format_map(data):
    """Keep top-level fields readable and each board row on one line."""
    fields = []
    for key, value in data.items():
        if key == "tiles":
            rows = ",\n".join("    " + json.dumps(row) for row in value)
            encoded = "[\n" + rows + "\n  ]"
        else:
            encoded = json.dumps(value)
        fields.append("  " + json.dumps(key) + ": " + encoded)
    return "{\n" + ",\n".join(fields) + "\n}\n"


def save_map(puzzle, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_map(puzzle_to_dict(puzzle)))


def map_hash(puzzle):
    data = {"size": puzzle.size, "source": puzzle.source, "tiles": puzzle.initial}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def load_game_config(path):
    path = Path(path).resolve()
    data = read_json(path)
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data.get("version") != 1
    ):
        raise ValueError("Game config must have version 1")
    result = dict(data)
    for name, default, low, high in (
        ("animation_ms", 260, 0, 2000),
        ("playback_steps_per_second", 8, 1, 120),
    ):
        value = integer(data.get(name, default), name, low)
        if value > high:
            raise ValueError(f"{name} must be <= {high}")
        result[name] = value
    startup = data.get("startup_map")
    if not isinstance(startup, str) or not startup:
        raise ValueError("startup_map must be a file path")
    result["startup_map"] = (path.parent / startup).resolve()
    return result


def append_result(path, puzzle, result):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(newline="") as handle:
            if next(csv.reader(handle), None) != list(CSV_FIELDS):
                raise ValueError(f"Unexpected CSV header in {path}")
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "puzzle_id": puzzle.id,
                "grid_size": puzzle.size,
                "algorithm": result.algorithm,
                "seed": "",
                "status": result.status,
                "time_ms": f"{result.time_ms:.4f}",
                "peak_memory_kib": ""
                if result.peak_memory_kib is None
                else f"{result.peak_memory_kib:.3f}",
            }
        )
