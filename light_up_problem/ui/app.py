"""Pygame and pygame_gui application for manual play and solver playback."""

from __future__ import annotations

import multiprocessing as mp
import queue
import time
from typing import Any

import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UIDropDownMenu, UILabel, UITextEntryLine

from light_up_problem.algorithms.search import SearchLimits, SearchResult, SearchStatus
from light_up_problem.benchmark.runner import BenchmarkRow
from light_up_problem.benchmark.worker import benchmark_worker
from light_up_problem.core.model import Cell
from light_up_problem.core.rules import (
    get_adjacent_bulbs,
    get_illuminated_cells,
    has_bulb_conflicts,
    is_goal_state,
)
from light_up_problem.generator import DIFFICULTIES, generate_puzzle, get_sample_puzzle
from light_up_problem.worker import solver_worker

BG = (16, 22, 33)
PANEL = (26, 34, 49)
PANEL_EDGE = (53, 66, 88)
TEXT = (231, 237, 247)
MUTED = (153, 167, 188)
GOLD = (255, 207, 87)
LIT = (74, 87, 92)
UNLIT = (48, 62, 79)
WALL = (21, 27, 38)
ERROR = (243, 94, 105)
FOCUS = (77, 190, 255)
ALGORITHM_OPTIONS = {"DFS": "DFS", "A*": "A*", "CSP (MRV + CP)": "CSP"}


class LightUpApp:
    """Own the game loop, widgets, board display and worker lifecycle."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Light Up — AI Search Visualizer")
        self.screen = pygame.display.set_mode((1500, 920), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui,arial", 18)
        self.small_font = pygame.font.SysFont("segoeui,arial", 14)
        self.big_font = pygame.font.SysFont("segoeui,arial", 28, bold=True)
        self.manager = pygame_gui.UIManager(self.screen.get_size())
        self.widgets: list[Any] = []
        self._make_widgets()

        self.puzzle = get_sample_puzzle(7, "easy")
        self.bulbs: set[Cell] = set()
        self.notes: set[Cell] = set()
        self.game_started_at = time.perf_counter()
        self.message = "Ready — place bulbs or start a search."

        self.process: mp.Process | None = None
        self.messages: Any = None
        self.stop_event: Any = None
        self.pause_event: Any = None
        self.step_event: Any = None
        self.search_active = False
        self.single_step_pending = False
        self.playback_steps_per_second = 8
        self.last_search_step = float("-inf")
        self.search_result: SearchResult | None = None
        self.search_status = "Idle"
        self.search_stats: dict[str, Any] = {}
        self.benchmark_rows: list[BenchmarkRow] = []
        self.worker_kind = ""
        self.search_bulbs: set[Cell] = set()
        self.search_forbidden: set[Cell] = set()
        self.manual_edited_after_search = False
        self.focus_cell: Cell | None = None
        self.playback_index = 0
        self.search_history: list[dict[str, Any]] = []
        self.history_index = -1
        self._rebuild_widgets()

    def _make_widgets(self) -> None:
        # Widget references are replaced on window resize so sidebars stay anchored.
        self.size_menu = self.difficulty_menu = self.seed_entry = None
        self.mode_menu = self.algorithm_menu = None
        self.buttons: dict[str, UIButton] = {}
        self.labels: dict[str, UILabel] = {}
        self.widgets.clear()

    def _widget(self, widget: Any) -> Any:
        self.widgets.append(widget)
        return widget

    def _rebuild_widgets(self) -> None:
        selected_algorithm = self.algorithm_menu.selected_option if self.algorithm_menu is not None else "DFS"
        if isinstance(selected_algorithm, tuple):
            selected_algorithm = selected_algorithm[0]
        for widget in self.widgets:
            widget.kill()
        self.widgets.clear()
        self.buttons.clear()
        self.labels.clear()
        width, height = self.screen.get_size()
        manager = self.manager

        def label(name: str, text: str, x: int, y: int, w: int = 220, h: int = 26, font: int | None = None) -> None:
            self.labels[name] = self._widget(
                UILabel(pygame.Rect(x, y, w, h), text, manager, object_id="#lightup_label")
            )

        def button(name: str, text: str, x: int, y: int, w: int, h: int = 38) -> None:
            self.buttons[name] = self._widget(
                UIButton(pygame.Rect(x, y, w, h), text, manager, object_id="#lightup_button")
            )

        left_x, left_w = 20, 230
        right_w, right_x = 250, max(275, width - 270)
        current_size = self.puzzle.size if hasattr(self, "puzzle") else 7
        current_difficulty = self.puzzle.difficulty.title() if hasattr(self, "puzzle") else "Easy"
        self._widget(UILabel(pygame.Rect(left_x, 24, left_w, 42), "", manager, object_id="#lightup_title"))
        label("subtitle", "AI Search Visualizer", left_x + 2, 61, 220)
        label("size_title", "Board size", left_x + 2, 98)
        self.size_menu = self._widget(
            UIDropDownMenu(
                ["7×7", "10×10", "14×14", "25×25"],
                f"{current_size}×{current_size}",
                pygame.Rect(left_x, 124, left_w, 38),
                manager,
            )
        )
        label("difficulty_title", "Difficulty", left_x + 2, 171)
        self.difficulty_menu = self._widget(
            UIDropDownMenu(
                [s.title() for s in DIFFICULTIES], current_difficulty, pygame.Rect(left_x, 197, left_w, 38), manager
            )
        )
        label("seed_title", "Puzzle seed (blank = random)", left_x + 2, 244)
        self.seed_entry = self._widget(UITextEntryLine(pygame.Rect(left_x, 270, left_w, 38), manager))
        self.seed_entry.set_text(
            str(self.puzzle.seed) if hasattr(self, "puzzle") and self.puzzle.seed is not None else ""
        )
        button("new", "New Game", left_x, 316, left_w)

        label("mode_title", "Play mode", left_x + 2, 369)
        self.mode_menu = self._widget(
            UIDropDownMenu(["Manual", "Algorithm"], "Manual", pygame.Rect(left_x, 395, left_w, 38), manager)
        )
        label("algorithm_title", "Search algorithm", left_x + 2, 444)
        self.algorithm_menu = self._widget(
            UIDropDownMenu(list(ALGORITHM_OPTIONS), selected_algorithm, pygame.Rect(left_x, 470, left_w, 38), manager)
        )
        paused = self.search_active and self.pause_event.is_set()
        button("solve", "Resume Search" if paused else "Start Search", left_x, 516, left_w)
        button("pause", "Pause", left_x, 562, left_w)

        button("reset", "Reset", left_x, 615, left_w)
        button("check", "Check Solution", left_x, 660, left_w)
        button("back", "<", left_x, 751, 110)
        button("forward", ">", left_x + 120, 751, 110)
        label("speed_title", "Search playback speed", left_x + 2, 801)
        button("speed", f"Speed: {self.playback_steps_per_second} steps/s", left_x, 827, left_w)

        self._widget(
            UILabel(pygame.Rect(right_x, 24, right_w, 36), "SEARCH STATUS", manager, object_id="#lightup_title")
        )
        for name, text, y in (
            ("status", "Idle", 77),
            ("algorithm", "Algorithm: —", 122),
            ("expanded", "Expanded: 0", 170),
            ("generated", "Generated: 0", 207),
            ("depth", "Depth: 0", 244),
            ("frontier", "Frontier: 0", 281),
            ("runtime", "Runtime: 0.00s", 318),
            ("memory", "Peak memory: —", 355),
            ("cost", "Solution cost: —", 392),
            ("score", "", 429),
            ("timer", "Play time: 00:00", 477),
            ("game_status", "Not checked", 514),
            ("seed_info", "Seed: —", 551),
        ):
            label(name, text, right_x + 2, y, right_w - 8)
        self.buttons["benchmark"] = self._widget(
            UIButton(
                pygame.Rect(right_x + 10, 596, right_w - 20, 38),
                "Compare DFS and A*",
                manager,
                object_id="#lightup_button",
            )
        )
        label("comparison", "Algorithm / seconds / KiB / nodes", right_x + 2, 644, right_w - 8)
        label("comparison_dfs", "DFS —", right_x + 2, 672, right_w - 8)
        label("comparison_astar", "A* —", right_x + 2, 700, right_w - 8)
        label("comparison_status", "", right_x + 2, 728, right_w - 8)
        label(
            "controls",
            "Left click: bulb  •  Right click: X",
            right_x + 2,
            height - 122,
            right_w - 8,
        )
        label(
            "legend",
            "Gold: lit   Slate: dark   Blue: focus",
            right_x + 2,
            height - 66,
            right_w - 8,
        )

    def _geometry(self) -> tuple[pygame.Rect, int]:
        width, height = self.screen.get_size()
        left, right = 265, 270
        available_w = max(240, width - left - right)
        available_h = max(200, height - 80)
        board_px = min(available_w, available_h)
        x = left + (available_w - board_px) // 2
        y = max(28, (height - board_px) // 2)
        return pygame.Rect(x, y, board_px, board_px), board_px // self.puzzle.size

    def _new_game(self) -> None:
        try:
            size_text = (
                self.size_menu.selected_option[0]
                if isinstance(self.size_menu.selected_option, tuple)
                else self.size_menu.selected_option
            )
            size = int(str(size_text).split("×")[0])
            difficulty_text = self.difficulty_menu.selected_option
            difficulty = (difficulty_text[0] if isinstance(difficulty_text, tuple) else difficulty_text).lower()
            seed_text = self.seed_entry.get_text().strip()
            seed = int(seed_text) if seed_text else time.time_ns() % (2**31)
            self._clear_worker()
            self.puzzle = generate_puzzle(size, difficulty, seed)
            self.bulbs.clear()
            self.notes.clear()
            self.search_history.clear()
            self.history_index = -1
            self.playback_index = 0
            self.search_result = None
            self.search_bulbs.clear()
            self.manual_edited_after_search = False
            self.focus_cell = None
            self.search_status = "Idle"
            self.search_stats = {}
            self.benchmark_rows.clear()
            self.labels["comparison"].set_text("Algorithm / seconds / KiB / nodes")
            self.labels["comparison_dfs"].set_text("DFS —")
            self.labels["comparison_astar"].set_text("A* —")
            self.labels["comparison_status"].set_text("")
            self.game_started_at = time.perf_counter()
            self.message = f"Loaded {self.puzzle.puzzle_id}; witness checked, uniqueness not tested."
            self.labels["game_status"].set_text("Not checked")
            self.labels["seed_info"].set_text(f"Seed: {seed}")
            self._rebuild_widgets()
        except (ValueError, RuntimeError) as exc:
            self.message = f"Could not create puzzle: {exc}"

    def _worker_running(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def _new_message_queue(self, context: Any) -> Any:
        if self.messages is not None:
            self.messages.close()
            self.messages.join_thread()
        return context.Queue(maxsize=64)

    def _start_search(self) -> None:
        if self.search_active or self._worker_running():
            if self.search_active and self.pause_event.is_set():
                self.step_event.clear()
                self.single_step_pending = False
                self.pause_event.clear()
                self.search_status = "Running"
                self.last_search_step = time.monotonic()
                self.buttons["solve"].set_text("Start Search")
                self.message = "Search resumed."
            else:
                self.message = "A solver or benchmark is already running."
            return
        algorithm_text = self.algorithm_menu.selected_option
        algorithm = ALGORITHM_OPTIONS[algorithm_text[0] if isinstance(algorithm_text, tuple) else algorithm_text]
        ctx = mp.get_context("spawn")
        self.messages = self._new_message_queue(ctx)
        self.stop_event = ctx.Event()
        self.pause_event = ctx.Event()
        self.step_event = ctx.Event()
        limits = SearchLimits(timeout_seconds=0, node_limit=250_000, memory_limit_mb=384.0)
        self.process = ctx.Process(
            target=solver_worker,
            args=(
                self.puzzle,
                algorithm,
                limits,
                self.messages,
                self.stop_event,
                self.pause_event,
                self.step_event,
            ),
            daemon=True,
        )
        self.process.start()
        self.worker_kind = "search"
        self.search_active = True
        self.single_step_pending = False
        self.last_search_step = float("-inf")
        self.search_result = None
        self.search_bulbs.clear()
        self.search_forbidden.clear()
        self.manual_edited_after_search = False
        self.search_status = "Running"
        self.search_stats = {
            "algorithm": algorithm,
            "expanded": 0,
            "generated": 0,
            "frontier_size": 0,
            "depth": 0,
            "elapsed_seconds": 0.0,
        }
        self.playback_index = 0
        self.search_history.clear()
        self.history_index = -1
        self.focus_cell = None
        self.buttons["pause"].set_text("Pause")
        self.message = f"{algorithm} is exploring states in a worker process."

    def _start_benchmark(self) -> None:
        if self.search_active or self._worker_running():
            self.message = "A solver or benchmark is already running."
            return
        ctx = mp.get_context("spawn")
        self.messages = self._new_message_queue(ctx)
        self.stop_event = ctx.Event()
        self.pause_event = None
        self.step_event = None
        limits = SearchLimits(timeout_seconds=20.0, node_limit=100_000, memory_limit_mb=256.0)
        self.process = ctx.Process(
            target=benchmark_worker,
            args=(self.puzzle, limits, self.messages, self.stop_event),
            daemon=True,
        )
        self.process.start()
        self.worker_kind = "benchmark"
        self.benchmark_rows.clear()
        self.search_status = "Benchmarking"
        self.labels["comparison_dfs"].set_text("DFS running…")
        self.labels["comparison_astar"].set_text("A* queued…")
        self.labels["comparison_status"].set_text("Same puzzle, one run each")
        self.message = "Side-by-side benchmark is running in a worker process."

    def _stop_worker(self) -> None:
        if self.process is None:
            return
        if self.stop_event is not None:
            self.stop_event.set()
        if self.pause_event is not None:
            self.pause_event.clear()
        if self.step_event is not None:
            self.step_event.set()
        self.process.join(timeout=0.5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=0.5)
        self.search_status = "Stopped"

    def _poll_worker(self) -> None:
        if self.search_active:
            self._advance_visualizer()
        elif self.worker_kind != "search" and self.messages is not None:
            for _ in range(30):
                try:
                    kind, payload = self.messages.get_nowait()
                except queue.Empty:
                    break
                self._handle_worker_message(kind, payload)
        if self.process is not None and not self.process.is_alive():
            self.process.join(timeout=0)

    def _advance_visualizer(self) -> None:
        paused = self.pause_event.is_set()
        if paused and not self.single_step_pending:
            return
        if not paused and time.monotonic() - self.last_search_step < 1 / self.playback_steps_per_second:
            return
        if self.history_index < len(self.search_history) - 1:
            self.history_index += 1
            self._show_search_state(self.search_history[self.history_index])
        else:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                if self._worker_running():
                    return
                # A normally exited multiprocessing worker has flushed its queue.
                # Read again after joining to cover an exit during get_nowait().
                self.process.join(timeout=0)
                try:
                    kind, payload = self.messages.get_nowait()
                except queue.Empty:
                    kind, payload = "error", "Worker exited without a result."
            if kind == "progress":
                self.search_history.append(payload)
                self.history_index = len(self.search_history) - 1
                self._show_search_state(payload)
            else:
                self._handle_worker_message(kind, payload)
        self.last_search_step = time.monotonic()
        self.single_step_pending = False

    def _handle_worker_message(self, kind: str, payload: Any) -> None:
        if kind == "result":
            self.search_active = False
            self.search_forbidden.clear()
            self.search_result = payload
            self.search_status = payload.status.value
            self.search_stats.update(
                expanded=payload.expanded,
                generated=payload.generated,
                frontier_size=payload.max_frontier,
                elapsed_seconds=payload.elapsed_seconds,
            )
            self.focus_cell = None
            self.pause_event.clear()
            self.buttons["solve"].set_text("Start Search")
            if payload.status == SearchStatus.SOLVED:
                self.search_bulbs = set(payload.solution)
                self.manual_edited_after_search = False
                self.playback_index = max(0, len(payload.solution_path) - 1)
                self.message = f"Solved with {len(payload.solution)} bulbs. The final state passed the rule validator."
            else:
                self.message = f"Search finished: {payload.status.value}. {payload.message}"
        elif kind == "benchmark":
            self.benchmark_rows = payload
            self.search_status = "Benchmark complete"
            self._show_benchmark_rows(payload)
            self.message = "Benchmark finished. Results use one repetition per algorithm on this board."
        elif kind == "error":
            self.search_active = False
            self.search_forbidden.clear()
            self.single_step_pending = False
            if self.pause_event is not None:
                self.pause_event.clear()
            self.buttons["solve"].set_text("Start Search")
            self.search_status = "Worker error"
            self.message = str(payload).splitlines()[0]

    def _clear_worker(self) -> None:
        if self._worker_running():
            self._stop_worker()
        if self.messages is not None:
            self.messages.close()
            self.messages.join_thread()
            self.messages = None
        self.process = None
        self.worker_kind = ""
        self.search_forbidden.clear()
        self.search_active = False
        self.single_step_pending = False
        self.last_search_step = float("-inf")
        self.pause_event = self.step_event = self.stop_event = None
        self.buttons["solve"].set_text("Start Search")

    def _pause_search(self) -> None:
        if not self.search_active:
            return
        self.pause_event.set()
        self.search_status = "Paused"
        self.step_event.clear()
        self.single_step_pending = False
        self.message = "Search paused; use < and > to review states or advance."
        self.buttons["solve"].set_text("Resume Search")

    def _button_action(self, name: str) -> None:
        if name == "new":
            self._new_game()
        elif name == "solve":
            self._start_search()
        elif name == "benchmark":
            self._start_benchmark()
        elif name == "pause":
            self._pause_search()
        elif name == "speed":
            speeds = (2, 8, 30)
            self.playback_steps_per_second = speeds[(speeds.index(self.playback_steps_per_second) + 1) % len(speeds)]
            self.buttons["speed"].set_text(f"Speed: {self.playback_steps_per_second} steps/s")
        elif name == "reset":
            self._clear_worker()
            self.playback_index = 0
            self.search_history.clear()
            self.history_index = -1
            self.bulbs.clear()
            self.notes.clear()
            self.search_result = None
            self.search_bulbs.clear()
            self.focus_cell = None
            self.manual_edited_after_search = False
            self.search_stats = {}
            self.search_status = "Idle"
            self.labels["game_status"].set_text("Not checked")
            self.message = "Board reset."
        elif name == "check":
            valid = is_goal_state(self.puzzle, self.bulbs)
            self.labels["game_status"].set_text("Solved! ✓" if valid else "Not solved — check clues and dark cells")
            self.message = (
                "Correct solution." if valid else "There are still dark cells, conflicts, or unsatisfied clues."
            )
        elif name == "back":
            self._playback_step(-1)
        elif name == "forward":
            self._playback_step(1)

    def _show_search_state(self, payload: dict[str, Any]) -> None:
        self.search_bulbs = set(tuple(cell) for cell in payload["bulbs"])
        self.search_forbidden = set(tuple(cell) for cell in payload.get("forbidden", ()))
        self.focus_cell = tuple(payload["focus"]) if payload["focus"] else None
        algorithm = self.search_stats.get("algorithm", "—")
        self.search_stats = {**payload, "algorithm": algorithm}
        descriptions = {
            "expand": "Expand state", "assign": "Try bulb", "accept": "Accept bulb", "reject": "Reject branch",
            "queue": "Queue state", "backtrack": "Backtrack", "select": "Select next state",
            "solution": "Solution found",
            "propagate": "Forced bulb", "prune": "Forbid cells",
        }
        description = descriptions.get(payload["kind"], payload["kind"])
        self.message = f"Step {self.history_index + 1}: {description} — {payload.get('detail', '')}"
        if payload["focus"] is not None:
            self.message += f" at {tuple(payload['focus'])}"

    def _playback_step(self, amount: int) -> None:
        if self.search_active:
            if not self.pause_event.is_set():
                self._pause_search()
            if amount > 0 and self.history_index >= len(self.search_history) - 1:
                if not self.single_step_pending:
                    self.single_step_pending = True
                    self.step_event.set()
            elif self.search_history:
                self.single_step_pending = False
                self.history_index = min(len(self.search_history) - 1, max(0, self.history_index + amount))
                self._show_search_state(self.search_history[self.history_index])
                self.last_search_step = time.monotonic()
            return
        if not self.search_result or not self.search_result.solution_path:
            self.message = "Run a solver first to create a solution playback."
            return
        last = len(self.search_result.solution_path) - 1
        self.search_forbidden.clear()
        self.manual_edited_after_search = False
        next_index = self.playback_index + amount
        self.playback_index = 0 if next_index > last else max(0, next_index)
        self.search_bulbs = set(self.search_result.solution_path[self.playback_index])
        self.focus_cell = None
        self.message = f"Solution step {self.playback_index}/{last}."

    def _show_benchmark_rows(self, rows: list[BenchmarkRow]) -> None:
        by_algorithm = {row.algorithm: row for row in rows}
        for key, algorithm in (("comparison_dfs", "DFS"), ("comparison_astar", "ASTAR")):
            row = by_algorithm.get(algorithm)
            if row is None:
                self.labels[key].set_text(f"{algorithm}: cancelled")
            else:
                name = "A*" if algorithm == "ASTAR" else algorithm
                self.labels[key].set_text(
                    f"{name}  {row.execution_time_seconds:.3f}s  "
                    f"{row.peak_python_memory_bytes / 1024:.1f}KiB  {row.nodes_expanded}n"
                )
        statuses = "  ".join(f"{row.algorithm}: {row.status}" for row in rows)
        self.labels["comparison_status"].set_text(statuses or "No completed runs")

    def _board_click(self, pos: tuple[int, int], button: int) -> None:
        if self.search_active or self._worker_running():
            return
        mode = self.mode_menu.selected_option
        mode_text = (mode[0] if isinstance(mode, tuple) else mode).lower()
        if mode_text != "manual":
            return
        if self.search_result is not None and not self.manual_edited_after_search:
            self.bulbs = set(self.search_bulbs)
            self.manual_edited_after_search = True
        board_rect, cell_px = self._geometry()
        if cell_px <= 0 or not board_rect.collidepoint(pos):
            return
        cell = ((pos[1] - board_rect.y) // cell_px, (pos[0] - board_rect.x) // cell_px)
        if not self.puzzle.is_white(cell):
            return
        if button == 1:
            if cell in self.bulbs:
                self.bulbs.remove(cell)
            elif cell not in self.bulbs:
                self.bulbs.add(cell)
                self.notes.discard(cell)
            self.labels["game_status"].set_text("In progress")
            self.message = "Bulb placed. Red bulbs indicate a line-of-sight conflict."
        elif button == 3 and cell not in self.bulbs:
            if cell in self.notes:
                self.notes.remove(cell)
            else:
                self.notes.add(cell)
        if is_goal_state(self.puzzle, self.bulbs):
            self.labels["game_status"].set_text("Solved! ✓")
            self.message = "Puzzle solved — every white cell is lit and all clues match."

    def _draw_board(self) -> None:
        board_rect, cell_px = self._geometry()
        show_search = (
            self.search_active or self._worker_running()
            or (self.search_result is not None and not self.manual_edited_after_search)
        )
        display_bulbs = self.search_bulbs if show_search else self.bulbs
        lit = get_illuminated_cells(self.puzzle, display_bulbs)
        display_notes = self.search_forbidden - lit if show_search else self.notes
        conflicts: set[Cell] = set()
        if has_bulb_conflicts(self.puzzle, display_bulbs):
            for cell in display_bulbs:
                row, col = cell
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    r, c = row + dr, col + dc
                    while self.puzzle.is_white((r, c)):
                        if (r, c) in display_bulbs:
                            conflicts.update((cell, (r, c)))
                        r += dr
                        c += dc

        pygame.draw.rect(self.screen, PANEL, board_rect.inflate(12, 12), border_radius=12)
        for row in range(self.puzzle.size):
            for col in range(self.puzzle.size):
                cell = (row, col)
                rect = pygame.Rect(board_rect.x + col * cell_px, board_rect.y + row * cell_px, cell_px, cell_px)
                value = self.puzzle.rows[row][col]
                if value is not None:
                    pygame.draw.rect(self.screen, WALL, rect)
                    if value >= 0:
                        adjacent = len(get_adjacent_bulbs(self.puzzle, cell, display_bulbs))
                        clue_color = TEXT if adjacent == value else GOLD if adjacent < value else ERROR
                        self._draw_text(str(value), rect.center, clue_color, small=cell_px < 35)
                else:
                    color = LIT if cell in lit else UNLIT
                    pygame.draw.rect(self.screen, color, rect)
                    if cell in display_notes:
                        self._draw_text("×", rect.center, MUTED, small=cell_px < 35)
                    if cell in display_bulbs:
                        bulb_color = ERROR if cell in conflicts else GOLD
                        radius = max(5, int(cell_px * 0.27))
                        pygame.draw.circle(self.screen, bulb_color, rect.center, radius)
                        pygame.draw.circle(self.screen, (255, 242, 191), rect.center, max(2, radius // 3))
                if cell == self.focus_cell:
                    pygame.draw.rect(
                        self.screen, ERROR if self.search_stats.get("kind") == "reject" else FOCUS,
                        rect, max(2, cell_px // 13),
                    )
                pygame.draw.rect(self.screen, PANEL_EDGE, rect, max(1, cell_px // 40))

    def _draw_text(self, text: str, pos: tuple[int, int], color: tuple[int, int, int], small: bool = False) -> None:
        font = self.small_font if small else self.font
        rendered = font.render(text, True, color)
        self.screen.blit(rendered, rendered.get_rect(center=pos))

    def _update_labels(self) -> None:
        stats = self.search_stats
        elapsed = int(time.perf_counter() - self.game_started_at)
        minutes, seconds = divmod(elapsed, 60)
        values = {
            "status": self.search_status,
            "algorithm": f"Algorithm: {stats.get('algorithm', '—')}",
            "expanded": f"Expanded: {stats.get('expanded', 0)}",
            "generated": f"Generated: {stats.get('generated', 0)}",
            "depth": f"Depth: {stats.get('depth', 0)}",
            "frontier": f"Frontier: {stats.get('frontier_size', 0)}",
            "runtime": f"Runtime: {stats.get('elapsed_seconds', 0):.2f}s",
            "memory": f"Peak memory: {self.search_result.peak_memory_bytes / 1024:.1f} KiB est."
            if self.search_result
            else "Peak memory: worker estimate",
            "cost": f"Solution cost: {self.search_result.solution_cost}" if self.search_result else "Solution cost: —",
            "score": "A*: " + "  •  ".join(
                f"{key} {stats.get(key) if stats.get(key) is not None else '—'}" for key in ("g", "h", "f")
            ) if stats.get("algorithm") == "A*" else "",
            "legend": "×: forbidden  •  Blue: focus" if stats.get("algorithm") == "CSP"
            else "Gold: lit   Slate: dark   Blue: focus",
            "timer": f"Play time: {minutes:02d}:{seconds:02d}",
            "seed_info": (
                f"Seed: {self.puzzle.seed}  •  {self.puzzle.size}×{self.puzzle.size} / {self.puzzle.difficulty.title()}"
            ),
        }
        for name, value in values.items():
            if name in self.labels:
                self.labels[name].set_text(value)

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    resized_size = (max(1100, event.w), max(900, event.h))
                    self.screen = pygame.display.set_mode(resized_size, pygame.RESIZABLE)
                    self.manager.set_window_resolution(resized_size)
                    self._rebuild_widgets()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._board_click(event.pos, event.button)

                self.manager.process_events(event)
                if event.type == pygame_gui.UI_BUTTON_PRESSED:
                    for name, widget in self.buttons.items():
                        if event.ui_element == widget:
                            self._button_action(name)
                            break
                elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                    if event.ui_element == self.size_menu or event.ui_element == self.difficulty_menu:
                        self._new_game()
                    elif event.ui_element == self.mode_menu and self.search_result is not None:
                        if event.text.lower() == "manual":
                            self.bulbs = set(self.search_bulbs)
                            self.manual_edited_after_search = True
                        else:
                            self.manual_edited_after_search = False
            self._poll_worker()
            self.manager.update(dt)
            self.screen.fill(BG)
            width, height = self.screen.get_size()
            pygame.draw.rect(self.screen, PANEL, pygame.Rect(10, 10, 250, height - 20), border_radius=14)
            pygame.draw.rect(self.screen, PANEL, pygame.Rect(width - 260, 10, 250, height - 20), border_radius=14)
            self.screen.blit(self.big_font.render("LIGHT UP", True, TEXT), (30, 24))
            self._draw_board()
            # Small status strip under the board area.
            board_rect, _ = self._geometry()
            status_surface = self.small_font.render(self.message[:118], True, MUTED)
            self.screen.blit(status_surface, (board_rect.x, min(self.screen.get_height() - 22, board_rect.bottom + 15)))
            self._update_labels()
            self.manager.draw_ui(self.screen)
            pygame.display.flip()
        self._stop_worker()
        if self.messages is not None:
            self.messages.close()
            self.messages.join_thread()
        pygame.quit()


def run_app() -> None:
    """Start the desktop game from a proper multiprocessing main guard."""
    LightUpApp().run()
