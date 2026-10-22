"""Isolated measurement process: Pygame/UI allocations cannot enter its peak."""

import json
import sys
from dataclasses import asdict

from .search import measure
from .storage import puzzle_from_dict


def main():
    request = json.load(sys.stdin)
    puzzle = puzzle_from_dict(request["map"], request["puzzle_id"])
    result = measure(
        puzzle,
        request["algorithm"],
        time_limit=request.get("time_limit", 30),
        max_expansions=request.get("max_expansions", 200000),
    )
    print(json.dumps(asdict(result)), flush=True)


if __name__ == "__main__":
    main()
