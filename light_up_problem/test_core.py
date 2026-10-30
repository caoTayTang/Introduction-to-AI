"""Rule checks: light propagation, conflicts, clues, goal and board validation."""

import unittest

from .core.model import Puzzle
from .core.rules import (
    get_adjacent_bulbs,
    get_illuminated_cells,
    get_legal_actions,
    has_bulb_conflicts,
    is_goal_state,
    is_valid_partial_state,
    validate_numbered_walls,
)


class RuleTests(unittest.TestCase):
    def test_light_travels_in_four_directions_and_stops_at_walls(self):
        puzzle = Puzzle(
            (
                (None, None, -1, None),
                (None, None, None, None),
                (None, 2, None, None),
                (None, None, None, None),
            )
        )
        lit = get_illuminated_cells(puzzle, {(1, 1)})
        self.assertLessEqual({(1, 1), (0, 1), (1, 0), (1, 2), (1, 3)}, lit)
        self.assertNotIn((0, 0), lit)
        self.assertNotIn((3, 1), lit)  # The numbered wall blocks light.

    def test_bulb_conflict_requires_unobstructed_line_of_sight(self):
        open_board = Puzzle(tuple(tuple(None for _ in range(3)) for _ in range(3)))
        blocked_board = Puzzle(((None, None, None), (None, -1, None), (None, None, None)))
        self.assertTrue(has_bulb_conflicts(open_board, {(1, 0), (1, 2)}))
        self.assertFalse(has_bulb_conflicts(blocked_board, {(1, 0), (1, 2)}))
        self.assertFalse(has_bulb_conflicts(open_board, {(0, 0), (1, 1)}))

    def test_numbered_wall_counts_exactly(self):
        cases = [
            (0, set(), True),
            (1, {(0, 1)}, True),
            (2, {(0, 1), (2, 1)}, True),
            (3, {(0, 1), (2, 1)}, False),
            (4, {(0, 1), (2, 1), (1, 0), (1, 2)}, True),
        ]
        for clue, bulbs, expected in cases:
            with self.subTest(clue=clue, bulbs=sorted(bulbs)):
                puzzle = Puzzle(((None, None, None), (None, clue, None), (None, None, None)))
                self.assertIs(validate_numbered_walls(puzzle, bulbs), expected)
                self.assertEqual(len(get_adjacent_bulbs(puzzle, (1, 1), bulbs)), len(bulbs))

    def test_partial_state_rejects_conflicts_and_overfilled_clues(self):
        puzzle = Puzzle(((None, 1, None), (None, None, None), (None, None, None)))
        self.assertTrue(is_valid_partial_state(puzzle, {(0, 0)}))
        self.assertFalse(is_valid_partial_state(puzzle, {(0, 0), (0, 2)}))
        self.assertNotIn((0, 2), get_legal_actions(puzzle, {(0, 0)}))

    def test_diagonal_bulbs_do_not_count_toward_numbered_wall(self):
        puzzle = Puzzle(((None, None, None), (None, 1, None), (None, None, None)))
        diagonal = {(0, 0)}
        self.assertEqual(get_adjacent_bulbs(puzzle, (1, 1), diagonal), set())
        self.assertFalse(validate_numbered_walls(puzzle, diagonal))
        self.assertTrue(validate_numbered_walls(puzzle, diagonal | {(2, 1)}))

    def test_goal_requires_lighting_and_clues_and_bulbs_must_be_on_white_cells(self):
        puzzle = Puzzle(((None, None), (None, None)))
        solution = {(0, 0), (1, 1)}
        self.assertTrue(is_goal_state(puzzle, solution))
        self.assertFalse(is_goal_state(puzzle, set()))
        self.assertEqual(get_illuminated_cells(puzzle, solution), {(0, 0), (0, 1), (1, 0), (1, 1)})
        with self.assertRaises(ValueError):
            get_illuminated_cells(puzzle, {(0, 0), (1, 1), (3, 3)})

    def test_lighting_every_white_cell_does_not_override_an_unsatisfied_clue(self):
        puzzle = Puzzle(((None, -1, -1), (None, 1, -1), (-1, -1, -1)))
        bulbs = {(0, 0)}
        self.assertEqual(len(get_illuminated_cells(puzzle, bulbs)), 2)
        self.assertFalse(validate_numbered_walls(puzzle, bulbs))
        self.assertFalse(is_goal_state(puzzle, bulbs))

    def test_puzzle_rejects_empty_non_square_and_invalid_clues(self):
        with self.assertRaises(ValueError):
            Puzzle(())
        with self.assertRaises(ValueError):
            Puzzle(((None, None), (None,)))
        with self.assertRaises(ValueError):
            Puzzle(((5,),))


if __name__ == "__main__":
    unittest.main()
