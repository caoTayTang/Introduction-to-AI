"""Exercise real Pygame input handlers without opening a desktop window."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import unittest
from unittest.mock import patch

import pygame

from .app import App
from .model import E, W, rotate
from .rendering import Canvas
from .search import Result, Search


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.app = App(5, 261)
        self.app.reduce_motion = True
        self.app.draw()

    def tearDown(self):
        pygame.quit()

    def send(self, event):
        with patch.object(pygame.event, "get", return_value=[event]):
            self.app.events()

    def key(self, key):
        self.send(pygame.event.Event(pygame.KEYDOWN, key=key))

    def click(self, pos, button=1):
        self.send(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))

    def tile_center(self, index):
        r, c = divmod(index, self.app.puzzle.size)
        b = self.app.board_rect
        s = self.app.cell
        return b.x + c * s + s // 2, b.y + r * s + s // 2

    def test_solver_next_and_solution_playback(self):
        self.app.search = Search(self.app.puzzle, "greedy_best_first")
        self.app.search_paused = True
        with patch.object(self.app, "record_search"):
            self.app.action("next")
            self.assertEqual(self.app.search.result.expanded, 1)
            self.assertTrue(self.app.search_paused)
            while self.app.search.result.status == "running":
                self.app.action("next")
            self.assertTrue(self.app.puzzle.status.solved)
            self.app.action("solution")
            while self.app.solution_playback:
                self.app.last_search_step = 0
                self.app.update_search()
            self.assertTrue(self.app.puzzle.status.solved)
        self.app.draw()
        self.assertTrue(any(widget[0] == "solution" for widget in self.app.widgets))

    def test_cancel_records_actual_status_once(self):
        self.app.search = Search(self.app.puzzle)
        self.app.search.advance()
        self.app.measured_result = Result("dfs", status="solved")
        with patch("pipes_problem.benchmark.record_interactive") as record:
            self.app.clear_search()
            self.app.clear_search()
            record.assert_called_once()
            self.assertEqual(record.call_args.args[1].status, "cancelled")
        self.assertIsNone(self.app.search)

    def test_exhaustive_unsolvable_sets_explanatory_message(self):
        class ExhaustedSearch:
            def __init__(self):
                self.result = Result("dfs")

            def advance(self):
                self.result.status = "unsolvable"

        self.app.search = ExhaustedSearch()
        with patch.object(self.app, "record_search"):
            self.app.advance_search()
        self.assertTrue(self.app.search_paused)
        self.assertEqual(
            self.app.result_text,
            "This map is unsolvable with the current pipe layout.",
        )

    def test_mouse_rotate_lock_and_undo(self):
        i = next(i for i, m in enumerate(self.app.puzzle.masks) if rotate(m) != m)
        pos = self.tile_center(i)
        old = self.app.puzzle.masks[i]
        self.click(pos)
        self.assertEqual(self.app.puzzle.masks[i], rotate(old))
        self.click(pos, 3)
        self.click(pos)
        self.assertEqual(self.app.puzzle.moves, 1)
        self.key(pygame.K_z)
        self.assertNotIn(i, self.app.puzzle.locked)
        self.key(pygame.K_z)
        self.assertEqual(self.app.puzzle.masks[i], old)
        self.assertEqual(self.app.puzzle.moves, 0)

    def test_reverse_rotation_and_keyboard_navigation(self):
        i = next(i for i, m in enumerate(self.app.puzzle.masks) if rotate(m) != m)
        old = self.app.puzzle.masks[i]
        with patch.object(pygame.key, "get_mods", return_value=pygame.KMOD_SHIFT):
            self.click(self.tile_center(i))
        self.assertEqual(self.app.puzzle.masks[i], rotate(old, -1))
        self.app.selected = None
        self.key(pygame.K_RIGHT)
        self.assertEqual(self.app.selected, self.app.puzzle.source)
        self.key(pygame.K_l)
        self.assertIn(self.app.selected, self.app.puzzle.locked)

    def test_reset_confirmation_preserves_progress_until_confirmed(self):
        i = next(i for i, m in enumerate(self.app.puzzle.masks) if rotate(m) != m)
        self.click(self.tile_center(i))
        self.key(pygame.K_r)
        self.assertEqual(self.app.modal, ("confirm", "reset"))
        self.key(pygame.K_ESCAPE)
        self.assertEqual(self.app.puzzle.moves, 1)
        self.key(pygame.K_r)
        self.app.draw()
        self.key(pygame.K_RETURN)
        self.assertEqual(self.app.puzzle.masks, self.app.puzzle.initial)
        self.assertEqual(self.app.puzzle.moves, 0)
        self.assertIsNone(self.app.modal)

    def test_new_puzzle_and_size_changes_clear_old_state(self):
        self.app.new_puzzle(7)
        self.assertEqual(len(self.app.puzzle.masks), 49)
        self.assertFalse(self.app.puzzle.history)
        self.assertFalse(self.app.animations)
        self.assertEqual(self.app.elapsed, 0)
        self.app.draw()

    def test_minimum_layout_and_boundary_input(self):
        self.send(pygame.event.Event(pygame.VIDEORESIZE, w=600, h=400))
        self.assertEqual(self.app.screen.get_size(), (1000, 720))
        self.app.draw()
        self.assertTrue(self.app.board_card.contains(self.app.board_rect))
        for key, rect in self.app.widgets:
            if key in ("undo", "reset") or key.startswith("size_"):
                self.assertTrue(self.app.side_card.contains(rect), key)
        self.click((self.app.board_rect.right, self.app.board_rect.bottom))
        self.assertEqual(self.app.puzzle.moves, 0)

    def test_solved_state_blocks_accidental_rotations_and_allows_undo(self):
        self.app.puzzle.masks = self.app.puzzle.solution.copy()
        self.assertTrue(self.app.puzzle.status.solved)
        before = self.app.puzzle.masks.copy()
        self.click(self.tile_center(0))
        self.assertEqual(self.app.puzzle.masks, before)
        self.app.draw()

    def test_rotation_animation_finishes(self):
        self.app.reduce_motion = False
        i = next(i for i, m in enumerate(self.app.puzzle.masks) if rotate(m) != m)
        self.click(self.tile_center(i))
        self.assertIn(i, self.app.animations)
        old, turn, started = self.app.animations[i]
        self.app.animations[i] = (old, turn, started - 1)
        self.app.draw()
        self.assertNotIn(i, self.app.animations)

    def test_cross_tile_acknowledges_click_and_can_be_undone(self):
        self.app.reduce_motion = False
        i = next(i for i, mask in enumerate(self.app.puzzle.masks) if mask == 15)
        self.click(self.tile_center(i))
        self.assertEqual(self.app.puzzle.masks[i], 15)
        self.assertEqual(self.app.puzzle.moves, 1)
        self.assertIn(i, self.app.animations)
        self.assertIn(i, self.app.click_feedback)
        self.key(pygame.K_z)
        self.assertEqual(self.app.puzzle.moves, 0)
        self.assertFalse(self.app.animations)

    def test_rapid_clicks_are_queued_instead_of_dropped(self):
        self.app.reduce_motion = False
        i = next(
            i for i, mask in enumerate(self.app.puzzle.masks) if rotate(mask) != mask
        )
        old = self.app.puzzle.masks[i]
        for _ in range(3):
            self.click(self.tile_center(i))
        self.assertEqual(self.app.puzzle.moves, 3)
        self.assertEqual(self.app.puzzle.masks[i], rotate(old, 3))
        self.assertEqual(len(self.app.rotation_queue[i]), 2)
        for _ in range(3):
            old_mask, direction, started = self.app.animations[i]
            self.app.animations[i] = (old_mask, direction, started - 1)
            self.app.draw()
        self.assertNotIn(i, self.app.animations)
        self.assertNotIn(i, self.app.rotation_queue)

    def test_reduced_motion_still_shows_click_feedback(self):
        i = next(i for i, mask in enumerate(self.app.puzzle.masks) if mask == 15)
        self.click(self.tile_center(i))
        self.assertIn(i, self.app.click_feedback)
        self.assertFalse(self.app.animations)

    def test_quit_event_stops_loop(self):
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_high_dpi_keeps_input_coordinates_logical(self):
        self.app.screen = Canvas((1280, 860), 2)
        self.app.layout()
        self.assertEqual(self.app.screen.pixels.get_size(), (2560, 1720))
        i = next(i for i, m in enumerate(self.app.puzzle.masks) if rotate(m) != m)
        old = self.app.puzzle.masks[i]
        self.click(self.tile_center(i))
        self.assertEqual(self.app.puzzle.masks[i], rotate(old))
        self.app.draw()

    def test_straight_pipe_has_no_spike_at_its_center(self):
        self.app.cell = 100
        image = self.app.pipe_surface(E | W, "#16786B")
        # Every column has the same alpha profile for a straight horizontal pipe.
        reference = [image.get_at((10, y)).a for y in range(image.get_height())]
        for x in (49, 50, 51, 90):
            self.assertEqual(
                reference, [image.get_at((x, y)).a for y in range(image.get_height())]
            )

    def test_animated_pipe_is_not_replaced_by_cached_static_image(self):
        self.app.cell = 100
        still = self.app.pipe_surface(E | W, "#16786B")
        rotated = self.app.pipe_surface(E | W, "#16786B", 45)
        self.assertGreater(rotated.get_width(), still.get_width())


if __name__ == "__main__":
    unittest.main()
