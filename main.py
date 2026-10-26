"""Launcher for both assignment puzzles: Pipes (default) and Light Up."""

import sys

GAMES = ("pipes", "lightup")


def main() -> None:
    args = sys.argv[1:]
    game = "pipes"
    if args and args[0] in GAMES:
        game, args = args[0], args[1:]
    sys.argv = [sys.argv[0], *args]
    if game == "lightup":
        from light_up_problem import main as run_light_up

        run_light_up()
    else:
        from pipes_problem.app import main as run_pipes

        run_pipes()


if __name__ == "__main__":
    main()
