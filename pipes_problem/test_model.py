import unittest

from .model import E, N, Puzzle, S, W, inspect_board, rotate


class PuzzleTests(unittest.TestCase):
    def test_rotation_preserves_shape(self):
        for mask in range(1, 16):
            self.assertEqual(rotate(mask, 4), mask)
            self.assertEqual(rotate(rotate(mask), -1), mask)
            self.assertEqual(rotate(mask).bit_count(), mask.bit_count())

    def test_generator_produces_trees_and_unsolved_starts(self):
        for size in (4, 5, 7):
            for seed in range(100):
                puzzle = Puzzle(size, seed)
                self.assertTrue(
                    inspect_board(puzzle.solution, size, puzzle.source).solved
                )
                self.assertFalse(puzzle.status.solved)
                self.assertTrue(all(puzzle.solution))
                self.assertEqual(
                    sum(x.bit_count() for x in puzzle.solution), 2 * (size * size - 1)
                )
                self.assertEqual(
                    [x.bit_count() for x in puzzle.solution],
                    [x.bit_count() for x in puzzle.masks],
                )

    def test_goal_rejects_loops_and_disconnected_networks(self):
        loop = [E | S, W | S, N | E, N | W]
        status = inspect_board(loop, 2, 0)
        self.assertTrue(status.cycle)
        self.assertFalse(status.solved)
        separate = [E, W, E, W]
        self.assertFalse(inspect_board(separate, 2, 0).solved)
        self.assertEqual(len(inspect_board(separate, 2, 0).connected), 2)

    def test_loose_ends_include_board_boundary(self):
        status = inspect_board([N], 1, 0)
        self.assertEqual(status.mismatches, ((0, N),))
        self.assertFalse(status.solved)

    def test_lock_undo_reset_and_determinism(self):
        puzzle = Puzzle(5, 261)
        self.assertEqual(puzzle.initial, Puzzle(5, 261).initial)
        index = next(i for i, m in enumerate(puzzle.masks) if rotate(m) != m)
        original = puzzle.masks[index]
        puzzle.toggle_lock(index)
        self.assertFalse(puzzle.turn(index))
        puzzle.undo()
        self.assertTrue(puzzle.turn(index))
        self.assertEqual(puzzle.moves, 1)
        puzzle.undo()
        self.assertEqual(puzzle.moves, 0)
        self.assertEqual(puzzle.masks[index], original)
        puzzle.turn(index)
        puzzle.toggle_lock(index)
        puzzle.reset()
        self.assertEqual(puzzle.masks, puzzle.initial)
        self.assertFalse(puzzle.locked)
        self.assertFalse(puzzle.history)

    def test_alternative_solution_is_accepted(self):
        # The goal validator takes actual board structure, not the stored answer.
        tree = [E | S, W, N | E, W]
        self.assertTrue(inspect_board(tree, 2, 0).solved)


if __name__ == "__main__":
    unittest.main()
