"""Headless checks for visualization controls and solver configuration."""

import os
import queue
import unittest
from dataclasses import asdict
from threading import Event
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pygame_gui

from .algorithms.search import SearchResult, SearchStatus, backtracking_mrv_cp
from .core.model import Puzzle
from .ui.app import ERROR, FOCUS, LightUpApp


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = LightUpApp()

    def tearDown(self):
        pygame.quit()

    def prepare_trace(self):
        app = self.app
        app.search_active = True
        app.worker_kind = "search"
        app.search_status = "Running"
        app.pause_event, app.step_event, app.stop_event = Event(), Event(), Event()
        app.process = Mock()
        app.process.is_alive.return_value = False  # Trace must outlive the producing process.
        app.messages = queue.Queue()
        for expanded, bulbs in enumerate(((), ((0, 0),), ((0, 0), (1, 1))), 1):
            app.messages.put(("progress", {
                "kind": "expand", "bulbs": bulbs, "focus": (1, 1), "depth": len(bulbs),
                "expanded": expanded, "generated": expanded, "frontier_size": 1,
                "g": len(bulbs), "h": 0, "f": len(bulbs), "detail": "Expand state",
            }))
        result = SearchResult(
            "dfs", SearchStatus.SOLVED, solution=((0, 0), (1, 1)),
            solution_path=((), ((0, 0),), ((0, 0), (1, 1))), expanded=3, solution_cost=2,
        )
        app.messages.put(("result", result))
        return result

    def test_csp_selection_survives_widget_rebuild_and_starts_the_csp_worker(self):
        app = self.app
        label = "CSP (MRV + CP)"
        self.assertIn((label, label), app.algorithm_menu.options_list)
        app.algorithm_menu.selected_option = (label, label)
        app._rebuild_widgets()
        self.assertEqual(app.algorithm_menu.selected_option, (label, label))
        context = Mock()
        with patch("light_up_problem.ui.app.mp.get_context", return_value=context):
            app._start_search()
        self.assertEqual(context.Process.call_args.kwargs["args"][1], "CSP")
        self.assertEqual(app.search_stats["algorithm"], "CSP")
        self.assertEqual(app.buttons["benchmark"].text, "Compare DFS and CSP")
        self.assertNotIn(("A*", "A*"), app.algorithm_menu.options_list)

    def test_csp_history_restores_forbidden_cells_without_changing_manual_notes(self):
        app = self.app
        self.prepare_trace()
        app.puzzle = Puzzle(((None, None, None), (None, 0, None), (None, None, None)))
        app.search_stats["algorithm"] = "CSP"
        app.notes = {(0, 2)}
        events = []
        result = backtracking_mrv_cp(app.puzzle, on_event=events.append, trace_steps=True)
        app.messages = queue.Queue()
        for event in events:
            app.messages.put(("progress", asdict(event)))
        app.messages.put(("result", result))
        with patch("light_up_problem.ui.app.time.monotonic", return_value=0.0) as clock:
            app._poll_worker()
            self.assertEqual(app.search_forbidden, {(0, 1), (1, 0), (1, 2), (2, 1)})
            app._button_action("pause")
            app._button_action("forward")
            app._poll_worker()  # MRV selection retains the pruned domain.
            app._button_action("forward")
            app._poll_worker()  # First branch adds further forbidden cells.
            branch_forbidden = app.search_forbidden.copy()
            self.assertGreater(len(branch_forbidden), 4)
            app._button_action("back")
            self.assertEqual(app.search_forbidden, {(0, 1), (1, 0), (1, 2), (2, 1)})
            app._button_action("forward")
            self.assertEqual(app.search_forbidden, branch_forbidden)
            self.assertEqual(app.notes, {(0, 2)})
            app._button_action("solve")
            while app.search_active:
                clock.return_value += 1 / 8
                app._poll_worker()
            self.assertFalse(app.search_forbidden)
            self.assertEqual(app.notes, {(0, 2)})
            app._button_action("back")
            self.assertFalse(app.search_forbidden)

    def test_csp_render_shows_domain_marks_and_focus_on_numbered_walls(self):
        app = self.app
        self.prepare_trace()
        app.puzzle = Puzzle(((None, None, None), (None, 0, None), (None, None, None)))
        app.notes = {(0, 0)}
        app._show_search_state({
            "kind": "prune", "bulbs": (), "focus": (1, 1), "depth": 0,
            "forbidden": ((0, 1), (1, 0), (1, 2), (2, 1)), "detail": "Wall is satisfied",
        })
        with patch.object(app, "_draw_text", wraps=app._draw_text) as draw_text:
            app._draw_board()
        marks = [call for call in draw_text.call_args_list if call.args[0] == "×"]
        self.assertEqual(len(marks), 4)  # Manual note is hidden during search.
        board, cell = app._geometry()
        pixel = (board.x + cell + max(1, cell // 40) + 1, board.y + cell + cell // 2)
        self.assertEqual(app.screen.get_at(pixel)[:3], FOCUS)
        app.search_stats["kind"] = "reject"
        app._draw_board()
        self.assertEqual(app.screen.get_at(pixel)[:3], ERROR)
        self.assertEqual(app.notes, {(0, 0)})

    def test_reset_and_new_game_discard_csp_domains_and_keep_algorithm_selection(self):
        app = self.app
        label = "CSP (MRV + CP)"
        app.algorithm_menu.selected_option = (label, label)
        app.search_forbidden = {(0, 0)}
        app._button_action("reset")
        self.assertFalse(app.search_forbidden)
        app.search_forbidden = {(0, 0)}
        app.seed_entry.set_text("123")
        app._button_action("new")
        self.assertFalse(app.search_forbidden)
        self.assertEqual(app.algorithm_menu.selected_option, (label, label))

    def test_visualizer_algorithm_menu_only_offers_dfs_and_csp(self):
        options = {option[0] for option in self.app.algorithm_menu.options_list}
        self.assertEqual(options, {"DFS", "CSP (MRV + CP)"})

    def test_each_rate_shows_one_event_per_tick_and_holds_result_until_next_tick(self):
        for rate in (2, 8, 30):
            with self.subTest(rate=rate):
                app = self.app
                result = self.prepare_trace()
                app.search_result = None
                app.search_history.clear()
                app.history_index = -1
                app.last_search_step = float("-inf")
                app.playback_steps_per_second = rate
                with patch("light_up_problem.ui.app.time.monotonic", return_value=0.0) as clock:
                    app._poll_worker()
                    self.assertEqual(len(app.search_history), 1)
                    self.assertEqual(app.search_bulbs, set())
                    clock.return_value = 0.5 / rate
                    app._poll_worker()
                    self.assertEqual(len(app.search_history), 1)
                    clock.return_value = 1 / rate
                    app._poll_worker()
                    self.assertEqual(len(app.search_history), 2)
                    self.assertEqual(app.search_bulbs, {(0, 0)})
                    # A delayed frame must show just one step, with no catch-up loop.
                    clock.return_value = 100.0
                    app._poll_worker()
                    app._poll_worker()
                    self.assertEqual(len(app.search_history), 3)
                    self.assertIsNone(app.search_result)
                    self.assertTrue(app.search_active)
                    self.assertEqual(app.search_status, "Running")
                    clock.return_value = 100.0 + 0.5 / rate
                    app._poll_worker()
                    self.assertIsNone(app.search_result)
                    clock.return_value = 100.0 + 1 / rate + 1e-9
                    app._poll_worker()
                    self.assertIs(app.search_result, result)
                    self.assertFalse(app.search_active)
                    self.assertEqual(app.search_status, "SOLVED")

    def test_pause_single_step_and_resume_replay_history_even_after_worker_exits(self):
        app = self.app
        self.prepare_trace()
        with patch("light_up_problem.ui.app.time.monotonic", return_value=0.0) as clock:
            app._poll_worker()
            app._button_action("pause")
            clock.return_value = 100.0
            app._poll_worker()
            self.assertEqual(len(app.search_history), 1)
            self.assertEqual(app.messages.qsize(), 3)
            app._button_action("forward")
            app._poll_worker()
            app._poll_worker()
            self.assertEqual(len(app.search_history), 2)
            self.assertEqual(app.search_bulbs, {(0, 0)})
            self.assertFalse(app.single_step_pending)
            self.assertTrue(app.pause_event.is_set())
            app._button_action("back")
            self.assertEqual(app.search_bulbs, set())
            with patch("light_up_problem.ui.app.mp.get_context") as context:
                app._button_action("solve")
            context.assert_not_called()
            self.assertFalse(app.pause_event.is_set())
            clock.return_value += 1 / 8
            app._poll_worker()
            self.assertEqual(app.history_index, 1)
            self.assertEqual(app.search_bulbs, {(0, 0)})
            self.assertEqual(app.messages.qsize(), 2)  # Replayed history before reading more trace.
            clock.return_value += 1 / 8
            app._poll_worker()
            self.assertEqual(app.history_index, 2)
            self.assertIsNone(app.search_result)
            clock.return_value += 1 / 8
            app._poll_worker()
            self.assertFalse(app.search_active)

    def test_speed_changes_apply_during_playback_and_survive_rebuild_reset_and_new_game(self):
        app = self.app
        self.assertEqual(app.playback_steps_per_second, 8)
        self.prepare_trace()
        with patch("light_up_problem.ui.app.time.monotonic", return_value=0.0) as clock:
            app._poll_worker()
            app._button_action("speed")
            self.assertEqual(app.playback_steps_per_second, 30)
            clock.return_value = 1 / 30
            app._poll_worker()
            self.assertEqual(len(app.search_history), 2)
            app._button_action("speed")
            self.assertEqual(app.playback_steps_per_second, 2)
            clock.return_value += 1 / 30
            app._poll_worker()
            self.assertEqual(len(app.search_history), 2)
        app._rebuild_widgets()
        self.assertEqual(app.buttons["speed"].text, "Speed: 2 steps/s")
        # Match multiprocessing queue cleanup methods for this UI-only test.
        app.messages = Mock()
        app._button_action("reset")
        self.assertEqual(app.playback_steps_per_second, 2)
        app.seed_entry.set_text("123")
        app._button_action("new")
        self.assertEqual(app.buttons["speed"].text, "Speed: 2 steps/s")
        app._button_action("speed")
        self.assertEqual(app.playback_steps_per_second, 8)

    def test_worker_failure_and_unexpected_exit_are_reported(self):
        app = self.app
        self.prepare_trace()
        app.messages = queue.Queue()
        app.messages.put(("error", "Solver failed\nTraceback details"))
        app._poll_worker()
        self.assertFalse(app.search_active)
        self.assertEqual(app.search_status, "Worker error")
        self.assertEqual(app.message, "Solver failed")
        self.prepare_trace()
        app.messages = queue.Queue()
        app.last_search_step = float("-inf")
        app._poll_worker()
        self.assertFalse(app.search_active)
        self.assertEqual(app.message, "Worker exited without a result.")

    def test_controls_and_search_without_timeout(self):
        self.assertTrue({"back", "forward", "solve", "pause", "reset"} <= self.app.buttons.keys())
        self.assertFalse({"undo", "redo", "step", "play", "stop", "hint"} & self.app.buttons.keys())
        context = Mock()
        with patch("light_up_problem.ui.app.mp.get_context", return_value=context):
            self.app._start_search()
        limits = context.Process.call_args.kwargs["args"][2]
        self.assertEqual(limits.timeout_seconds, 0)
        self.assertGreater(limits.node_limit, 0)

    def test_pause_is_idempotent_and_start_resumes_same_worker(self):
        app = self.app
        process = app.process = Mock()
        process.is_alive.return_value = True
        app.worker_kind = "search"
        app.search_active = True
        app.pause_event, app.step_event = Event(), Event()
        app.search_bulbs = {(0, 0)}
        app._button_action("pause")
        app._button_action("pause")
        self.assertTrue(app.pause_event.is_set())
        self.assertEqual(app.buttons["pause"].text, "Pause")
        self.assertEqual(app.buttons["solve"].text, "Resume Search")
        app._rebuild_widgets()
        self.assertEqual(app.buttons["solve"].text, "Resume Search")
        app.step_event.set()
        with patch("light_up_problem.ui.app.mp.get_context") as context:
            app._button_action("solve")
        context.assert_not_called()
        self.assertIs(app.process, process)
        self.assertFalse(app.pause_event.is_set())
        self.assertFalse(app.step_event.is_set())
        self.assertEqual(app.search_bulbs, {(0, 0)})
        self.assertEqual(app.buttons["solve"].text, "Start Search")
        app.process = None

    def test_reset_stops_paused_worker_and_discards_pending_results(self):
        app = self.app
        puzzle = app.puzzle
        app.process = Mock()
        app.process.is_alive.return_value = True
        app.worker_kind = "search"
        app.search_active = True
        app.pause_event, app.step_event, app.stop_event = Event(), Event(), Event()
        app.pause_event.set()
        messages = app.messages = Mock()
        app.bulbs = {(0, 0)}
        app.search_bulbs = {(0, 0)}
        app.playback_index = 5
        with patch.object(app, "_stop_worker", wraps=app._stop_worker) as stop:
            app._button_action("reset")
        stop.assert_called_once()
        messages.close.assert_called_once()
        self.assertIsNone(app.process)
        self.assertIsNone(app.messages)
        self.assertIsNone(app.pause_event)
        self.assertIs(app.puzzle, puzzle)
        self.assertEqual(app.bulbs, set())
        self.assertEqual(app.search_bulbs, set())
        self.assertEqual(app.playback_index, 0)
        self.assertEqual(app.buttons["solve"].text, "Start Search")
        app._poll_worker()
        self.assertEqual(app.search_status, "Idle")

    def test_size_change_loads_board_immediately(self):
        app = self.app
        app.seed_entry.set_text("123")
        app.size_menu.selected_option = "10×10"
        changed = pygame.event.Event(
            pygame_gui.UI_DROP_DOWN_MENU_CHANGED, ui_element=app.size_menu, text="10×10",
        )
        with patch("pygame.event.get", return_value=[changed, pygame.event.Event(pygame.QUIT)]):
            app.run()
        self.assertEqual(app.puzzle.size, 10)
        self.assertEqual(app.puzzle.difficulty, "easy")
        self.assertEqual(app.puzzle.seed, 123)

    def test_difficulty_change_loads_board_and_new_game_applies_seed(self):
        app = self.app
        app.seed_entry.set_text("123")
        app.difficulty_menu.selected_option = "Hard"
        changed = pygame.event.Event(
            pygame_gui.UI_DROP_DOWN_MENU_CHANGED, ui_element=app.difficulty_menu, text="Hard",
        )
        with patch("pygame.event.get", return_value=[changed, pygame.event.Event(pygame.QUIT)]):
            # Keep pygame available for the subsequent New Game button action.
            with patch("light_up_problem.ui.app.pygame.quit"):
                app.run()
        self.assertEqual(app.puzzle.size, 7)
        self.assertEqual(app.puzzle.difficulty, "hard")
        app.seed_entry.set_text("456")
        app._button_action("new")
        self.assertEqual(app.puzzle.seed, 456)
        self.assertEqual(app.puzzle.difficulty, "hard")

    def test_new_game_discards_old_worker_updates(self):
        app = self.app
        messages = app.messages = Mock()
        app.process = Mock()
        app.process.is_alive.return_value = True
        app.pause_event = Mock()
        app.playback_index = 20
        app._new_game()
        app.process = None
        messages.close.assert_called_once()
        self.assertIsNone(app.messages)
        self.assertIsNone(app.pause_event)
        self.assertEqual(app.playback_index, 0)

    def test_arrows_review_live_history_and_step_at_its_end(self):
        app = self.app
        app.worker_kind = "search"
        app.search_active = True
        app.process = Mock()
        app.process.is_alive.return_value = True
        app.pause_event = Mock()
        app.pause_event.is_set.return_value = True
        app.step_event = Mock()
        app.search_history = [
            {"bulbs": [], "focus": [0, 0], "depth": 0, "kind": "expand"},
            {"bulbs": [[0, 0]], "focus": [1, 1], "depth": 1, "kind": "expand"},
        ]
        app.history_index = 1
        app._button_action("back")
        self.assertEqual(app.history_index, 0)
        self.assertEqual(app.search_bulbs, set())
        app._button_action("forward")
        self.assertEqual(app.search_bulbs, {(0, 0)})
        app.step_event.set.assert_not_called()
        app._button_action("forward")
        app.step_event.set.assert_called_once()
        self.assertTrue(app.single_step_pending)
        app.process = None

    def test_solution_arrows_survive_window_rebuild(self):
        app = self.app
        app.search_result = SearchResult(
            "dfs", SearchStatus.SOLVED,
            solution=((0, 0), (1, 1)), solution_path=((), ((0, 0),), ((0, 0), (1, 1))),
        )
        app.playback_index = 2
        app._rebuild_widgets()
        app._button_action("back")
        self.assertEqual(app.search_bulbs, {(0, 0)})
        app._button_action("forward")
        self.assertEqual(app.search_bulbs, {(0, 0), (1, 1)})
        app._button_action("forward")
        self.assertEqual(app.playback_index, 0)
        self.assertEqual(app.search_bulbs, set())
        self.assertEqual(app.message, "Solution step 0/2.")
        app._button_action("back")
        self.assertEqual(app.playback_index, 0)
        app._button_action("forward")
        self.assertEqual(app.playback_index, 1)
        self.assertEqual(app.search_bulbs, {(0, 0)})
