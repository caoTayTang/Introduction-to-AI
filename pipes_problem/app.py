"""A small, custom Pygame interface for playing Pipes."""

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from pygame._sdl2.video import Renderer, Texture

from .model import DIRECTIONS, Puzzle
from .rendering import Canvas, draw
from .search import Result, Search, validate_solution
from .storage import ROOT, load_game_config, load_map, puzzle_to_dict, save_map

BG = "#F4F4F4"
PAPER = "#FFFFFF"
INK = "#25282D"
MUTED = "#727780"
LINE = "#D7DADE"
ACCENT = "#285BC2"
ACCENT_BG = "#EAF0FC"
PIPE = "#B8C2CD"
WATER = "#258BD2"
WATER_LIGHT = "#9BDCF7"


class App:
    def __init__(self, size=5, seed=261, *, puzzle=None, settings=None):
        pygame.init()
        self.window = None
        self.renderer = None
        self.texture = None
        if pygame.display.get_driver() == "dummy":
            self.display = pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
        else:
            self.window = pygame.Window(
                "Pipes",
                size=(1280, 860),
                resizable=True,
                allow_high_dpi=True,
            )
            self.window.minimum_size = (1000, 720)
            self.renderer = Renderer(self.window, vsync=True)
        self.configure_canvas((1280, 860))
        self.clock = pygame.time.Clock()
        self.fonts = {}
        self.pipe_cache = {}
        self.puzzle = puzzle or Puzzle(size, seed)
        self.settings = settings or {
            "animation_ms": 260,
            "playback_steps_per_second": 8,
        }
        self.algorithm = "dfs"
        self.search = None
        self.search_step = None
        self.search_paused = False
        self.last_search_step = 0.0
        self.measure_worker = None
        self.measured_result = None
        self.recorded = False
        self.result_text = ""
        self.solution_playback = None
        self.animations = {}
        self.rotation_queue = {}
        self.click_feedback = {}
        self.elapsed = 0.0
        self.modal = None
        self.toast = ""
        self.toast_until = 0
        self.hover_tile = None
        self.selected = None
        self.widgets = []
        self.modal_widgets = []
        self.running = True
        self.reduce_motion = self.settings["animation_ms"] == 0
        self.was_solved = False
        self.layout()

    def configure_canvas(self, size):
        if self.window:
            self.window.size = size
            viewport = self.renderer.get_viewport()
            density = max(1, viewport.w / size[0])
        else:
            density = 1
        self.screen = Canvas(size, density)
        self.texture = None

    def present(self):
        if self.renderer:
            if self.texture is None:
                self.texture = Texture.from_surface(self.renderer, self.screen.pixels)
            else:
                self.texture.update(self.screen.pixels)
            self.texture.draw(dstrect=self.renderer.get_viewport())
            self.renderer.present()
        else:
            self.display.blit(self.screen.pixels, (0, 0))
            pygame.display.flip()

    def font(self, size, bold=False):
        key = size, bold
        if key not in self.fonts:
            face = str(Path(__file__).parent / "assets" / "Figtree.ttf")
            self.fonts[key] = pygame.font.Font(face, size)
            self.fonts[key].set_bold(bold)
        return self.fonts[key]

    def text(self, message, position, size=16, color=INK, bold=False, center=False):
        scale = self.screen.scale
        image = self.font(round(size * scale), bold).render(message, True, color)
        logical_size = tuple(round(v / scale) for v in image.get_size())
        rect = pygame.Rect((0, 0), logical_size)
        if center:
            rect.center = position
        else:
            rect.topleft = position
        self.screen.blit_native(image, rect.topleft)
        return rect

    def wrapped(self, message, x, y, width, size=15, color=MUTED, spacing=6):
        words, line = message.split(), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if line and self.font(size).size(trial)[0] > width:
                self.text(line, (x, y), size, color)
                y += size + spacing
                line = word
            else:
                line = trial
        if line:
            self.text(line, (x, y), size, color)
            y += size + spacing
        return y

    def box(self, rect, color=PAPER, radius=18, border=None):
        draw.rect(self.screen, color, rect, border_radius=radius)
        if border:
            draw.rect(self.screen, border, rect, 1, border_radius=radius)

    def icon(self, name, center, color=INK, size=18):
        x, y = center
        color = pygame.Color(color)
        if name == "lock":
            draw.rect(self.screen, color, (x - 4, y - 1, 8, 7), border_radius=2)
            draw.arc(self.screen, color, (x - 4, y - 7, 8, 10), 0, math.pi, 2)
        elif name == "undo":
            draw.arc(self.screen, color, (x - 7, y - 6, 14, 14), -1.1, 2.5, 2)
            draw.lines(
                self.screen,
                color,
                False,
                [(x - 7, y - 7), (x - 7, y - 1), (x - 1, y - 1)],
                2,
            )
        elif name == "reset":
            draw.arc(self.screen, color, (x - 7, y - 7, 14, 14), -0.4, 4.9, 2)
            draw.polygon(
                self.screen, color, [(x + 7, y - 6), (x + 8, y + 1), (x + 2, y - 2)]
            )
        elif name == "check":
            draw.lines(
                self.screen,
                color,
                False,
                [(x - 6, y), (x - 1, y + 5), (x + 7, y - 5)],
                2,
            )
        elif name == "arrow":
            draw.line(self.screen, color, (x - 7, y), (x + 7, y), 2)
            draw.lines(
                self.screen,
                color,
                False,
                [(x + 2, y - 5), (x + 7, y), (x + 2, y + 5)],
                2,
            )

    def button(
        self, key, label, rect, primary=False, active=False, enabled=True, icon=None
    ):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and self.modal is None and enabled
        fill = (
            ACCENT
            if primary
            else ACCENT_BG
            if active
            else "#F0F1F3"
            if hovered
            else PAPER
        )
        if primary and hovered:
            fill = "#204BA0"
        color = PAPER if primary else ACCENT if active else INK
        if not enabled:
            fill, color = "#FFFFFF", "#B0B4BA"
        self.box(rect, fill, 4, None if primary else LINE)
        if icon:
            self.icon(icon, (rect.x + 23, rect.centery), color)
            self.text(label, (rect.x + 42, rect.centery - 11), 16, color, True)
        else:
            self.text(label, rect.center, 15, color, True, True)
        if enabled:
            self.widgets.append((key, rect))

    def layout(self):
        w, h = self.screen.get_size()
        margin, gap, side = 32, 24, 292
        self.board_card = pygame.Rect(margin, 108, w - margin * 2 - gap - side, h - 158)
        self.side_card = pygame.Rect(w - margin - side, 108, side, h - 158)
        available = min(self.board_card.w - 64, self.board_card.h - 160)
        self.cell = int(available // self.puzzle.size)
        board_size = self.cell * self.puzzle.size
        self.board_rect = pygame.Rect(0, 0, board_size, board_size)
        self.board_rect.center = (
            self.board_card.centerx,
            self.board_card.y + 85 + (self.board_card.h - 155) // 2,
        )

    def tile_at(self, pos):
        if self.board_rect.collidepoint(pos):
            col = (pos[0] - self.board_rect.x) // self.cell
            row = (pos[1] - self.board_rect.y) // self.cell
            return row * self.puzzle.size + col
        return None

    def notify(self, message):
        self.toast = message
        self.toast_until = time.monotonic() + 2.6

    def new_puzzle(self, size=None):
        self.clear_search()
        size = size or self.puzzle.size
        self.puzzle = Puzzle(size, random.SystemRandom().randrange(1, 0xFFFFFF))
        self.animations.clear()
        self.rotation_queue.clear()
        self.click_feedback.clear()
        self.elapsed = 0.0
        self.selected = None
        self.was_solved = False
        self.modal = None
        self.layout()
        self.notify("New puzzle loaded.")

    def reset(self):
        self.clear_search()
        self.puzzle.reset()
        self.animations.clear()
        self.rotation_queue.clear()
        self.click_feedback.clear()
        self.elapsed = 0.0
        self.was_solved = False
        self.modal = None
        self.notify("Puzzle reset.")

    def request_change(self, action):
        if self.puzzle.moves or self.puzzle.locked:
            self.modal = ("confirm", action)
        else:
            self.apply_change(action)

    def apply_change(self, action):
        if action == "reset":
            self.reset()
        elif action == "new":
            self.new_puzzle()
        else:
            self.new_puzzle(int(action.split("_")[1]))

    def turn(self, index, direction=1):
        if self.search is not None:
            return
        if index is None or self.puzzle.status.solved:
            return
        if index in self.puzzle.locked:
            self.notify("Tile locked. Right-click or press L to unlock.")
            return
        old = self.puzzle.masks[index]
        if self.puzzle.turn(index, direction):
            now = time.monotonic()
            self.click_feedback[index] = now
            if not self.reduce_motion:
                if index in self.animations:
                    self.rotation_queue.setdefault(index, []).append((old, direction))
                else:
                    self.animations[index] = (old, direction, now)
            self.selected = index

    def lock(self, index):
        if self.search is not None:
            return
        if index is not None and not self.puzzle.status.solved:
            self.puzzle.toggle_lock(index)
            self.selected = index

    def action(self, key):
        if key in ("new", "reset"):
            self.request_change(key)
        elif key.startswith("size_"):
            if int(key.split("_")[1]) != self.puzzle.size:
                self.request_change(key)
        elif key == "undo":
            if self.search is not None:
                return
            result = self.puzzle.undo()
            if result:
                self.animations.clear()
                self.rotation_queue.clear()
                self.click_feedback.clear()
                self.selected = result[1]
                self.was_solved = False
        elif key == "motion":
            self.reduce_motion = not self.reduce_motion
            self.animations.clear()
            self.rotation_queue.clear()
        elif key.startswith("algo_"):
            self.clear_search()
            self.algorithm = key[5:]
            self.puzzle.reset()
            self.animations.clear()
            self.rotation_queue.clear()
            self.click_feedback.clear()
            self.selected = None
        elif key == "run":
            if self.search is None or self.search.result.status != "running":
                self.start_search()
            else:
                self.search_paused = not self.search_paused
        elif key == "next":
            if self.search is None:
                self.start_search(paused=True)
            self.search_paused = True
            self.advance_search()
        elif key == "speed":
            speeds = (2, 8, 30)
            current = self.settings["playback_steps_per_second"]
            self.settings["playback_steps_per_second"] = next(
                (s for s in speeds if s > current), speeds[0]
            )
        elif key == "solution" and self.search and self.search.result.board:
            board = self.search.result.board
            self.puzzle.masks = self.puzzle.initial.copy()
            self.solution_playback = iter((i, mask) for i, mask in enumerate(board))
            self.search_step = None
            self.last_search_step = time.monotonic()

    def stop_worker(self):
        if self.measure_worker is not None:
            if self.measure_worker.poll() is None:
                self.measure_worker.terminate()
                try:
                    self.measure_worker.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.measure_worker.kill()
                    self.measure_worker.wait()
            self.measure_worker.stdout.close()
            self.measure_worker.stderr.close()
            self.measure_worker = None

    def clear_search(self):
        if self.search and self.search.result.status == "running":
            self.search.cancel()
        if self.search and not self.recorded:
            self.record_search()
        self.stop_worker()
        self.search = None
        self.search_step = None
        self.measured_result = None
        self.recorded = False
        self.result_text = ""
        self.solution_playback = None

    def start_search(self, paused=False):
        self.clear_search()
        self.puzzle.reset()
        self.animations.clear()
        self.rotation_queue.clear()
        self.click_feedback.clear()
        self.selected = None
        self.search = Search(self.puzzle, self.algorithm)
        if self.search.result.status == "unsolvable":
            self.result_text = "This map is unsolvable with the current pipe layout."
            self.search_paused = True
        else:
            self.search_paused = paused
        self.last_search_step = 0.0
        self.was_solved = False
        try:
            save_map(self.puzzle, ROOT / "maps" / "played" / f"{self.puzzle.id}.json")
            self.measure_worker = subprocess.Popen(
                [sys.executable, "-m", "pipes_problem.worker"],
                cwd=ROOT.parent,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            json.dump(
                {
                    "map": puzzle_to_dict(self.puzzle),
                    "puzzle_id": self.puzzle.id,
                    "algorithm": self.algorithm,
                },
                self.measure_worker.stdin,
            )
            self.measure_worker.stdin.close()
        except OSError as exc:
            self.result_text = f"Measurement unavailable: {exc}"
            self.stop_worker()

    def record_search(self):
        if self.recorded or self.search is None:
            return
        from .benchmark import record_interactive

        result = (
            self.search.result
            if self.search.result.status == "cancelled"
            else self.measured_result or self.search.result
        )
        try:
            record_interactive(
                self.puzzle,
                result,
                {
                    "algorithm": self.algorithm,
                    "playback": {
                        "animation_ms": self.settings["animation_ms"],
                        "steps_per_second": self.settings["playback_steps_per_second"],
                    },
                    "time_limit_seconds": 30,
                    "max_expansions": 200000,
                    "measurement_source": "isolated worker"
                    if self.measured_result
                    else "interactive trace; memory unavailable",
                },
            )
            self.recorded = True
        except (OSError, ValueError) as exc:
            self.result_text = f"Recording failed: {exc}"
            self.recorded = True

    def advance_search(self):
        if not self.search or self.search.result.status != "running":
            return
        step = self.search.advance()
        if step is not None:
            self.search_step = step
            self.puzzle.masks = (
                list(step.state) + self.puzzle.initial[len(step.state) :]
            )
            self.selected = step.index
            if step.index is not None:
                self.click_feedback[step.index] = time.monotonic()
        self.last_search_step = time.monotonic()
        if self.search.result.status != "running":
            if self.search.result.status == "solved":
                if not validate_solution(self.puzzle, self.search.result.board):
                    self.search.result.status = "error"
                    self.search.result.error = "Invalid solver result"
                else:
                    self.puzzle.masks = list(self.search.result.board)
                    self.search_step = None
            elif self.search.result.status == "unsolvable":
                self.result_text = (
                    "This map is unsolvable with the current pipe layout."
                )
            self.search_paused = True
            if self.measure_worker is None:
                self.record_search()

    def update_search(self):
        if self.measure_worker and self.measure_worker.poll() is not None:
            output = self.measure_worker.stdout.read()
            diagnostic = self.measure_worker.stderr.read()
            try:
                if self.measure_worker.returncode != 0:
                    raise ValueError(diagnostic.strip() or "Measurement process failed")
                data = json.loads(output)
                if data["board"] is not None:
                    data["board"] = tuple(data["board"])
                self.measured_result = Result(**data)
            except (ValueError, TypeError, KeyError) as exc:
                self.result_text = f"Measurement unavailable: {exc}"
            self.stop_worker()
        if (
            self.search
            and self.search.result.status != "running"
            and self.measure_worker is None
        ):
            if self.measured_result and (
                self.measured_result.status != self.search.result.status
                or self.measured_result.board != self.search.result.board
            ):
                self.measured_result = None
                self.result_text = "Measurement replay differed; peak unavailable"
            self.record_search()
        due = (
            time.monotonic() - self.last_search_step
            >= 1 / self.settings["playback_steps_per_second"]
        )
        if self.solution_playback and due:
            try:
                index, mask = next(self.solution_playback)
                self.puzzle.masks[index] = mask
                self.selected = index
                self.click_feedback[index] = time.monotonic()
                self.last_search_step = time.monotonic()
            except StopIteration:
                self.solution_playback = None
        elif self.search and not self.search_paused and not self.modal and due:
            self.advance_search()

    def events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
                width = event.w if event.type == pygame.VIDEORESIZE else event.x
                height = event.h if event.type == pygame.VIDEORESIZE else event.y
                size = (max(1000, width), max(720, height))
                if not self.window:
                    self.display = pygame.display.set_mode(size, pygame.RESIZABLE)
                self.configure_canvas(size)
                self.layout()
            elif event.type == pygame.KEYDOWN:
                if self.modal:
                    if event.key == pygame.K_ESCAPE:
                        self.modal = None
                    elif event.key == pygame.K_RETURN:
                        if self.modal[0] == "confirm":
                            self.apply_change(self.modal[1])
                        else:
                            self.modal = None
                    continue
                if event.key == pygame.K_n:
                    self.action("new")
                elif event.key == pygame.K_r:
                    self.action("reset")
                elif event.key == pygame.K_z:
                    self.action("undo")
                elif event.key == pygame.K_l:
                    self.lock(self.selected)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    direction = -1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
                    self.turn(self.selected, direction)
                elif event.key in (
                    pygame.K_LEFT,
                    pygame.K_RIGHT,
                    pygame.K_UP,
                    pygame.K_DOWN,
                ):
                    if self.selected is None:
                        self.selected = self.puzzle.source
                    else:
                        r, c = divmod(self.selected, self.puzzle.size)
                        dr, dc = {
                            pygame.K_LEFT: (0, -1),
                            pygame.K_RIGHT: (0, 1),
                            pygame.K_UP: (-1, 0),
                            pygame.K_DOWN: (1, 0),
                        }[event.key]
                        self.selected = (
                            (r + dr) % self.puzzle.size
                        ) * self.puzzle.size + (c + dc) % self.puzzle.size
                elif event.key == pygame.K_ESCAPE:
                    self.selected = None
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.modal:
                    if event.button == 1:
                        for key, rect in self.modal_widgets:
                            if rect.collidepoint(event.pos):
                                if key == "confirm":
                                    self.apply_change(self.modal[1])
                                else:
                                    self.modal = None
                                break
                    continue
                if event.button == 1:
                    for key, rect in self.widgets:
                        if rect.collidepoint(event.pos):
                            self.action(key)
                            break
                    else:
                        self.turn(
                            self.tile_at(event.pos),
                            -1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1,
                        )
                elif event.button == 3:
                    self.lock(self.tile_at(event.pos))

    def pipe_surface(self, mask, color, angle=0, *, water=False):
        key = mask, color, self.cell, self.screen.scale, water
        if not angle and key in self.pipe_cache:
            return self.pipe_cache[key]
        # Draw at 3x resolution, then downsample for rounded, anti-aliased pipes.
        scale, size = 3, self.cell
        image = pygame.Surface((size * scale, size * scale), pygame.SRCALPHA)
        center = size * scale // 2
        stroke = max(12, int(size * 0.13) * scale)
        radius = stroke // 2
        rgb = pygame.Color(color)
        image.fill((*rgb[:3], 0))
        for dr, dc, bit, _ in DIRECTIONS:
            if mask & bit:
                end = (center + dc * (center + 2), center + dr * (center + 2))
                # Rectangles and the hub use exactly the same diameter. Mixing
                # an even-width SDL line with a circle produces a one-pixel nub.
                arm = (
                    pygame.Rect(
                        center - radius,
                        min(center, end[1]),
                        radius * 2,
                        abs(end[1] - center),
                    )
                    if dr
                    else pygame.Rect(
                        min(center, end[0]),
                        center - radius,
                        abs(end[0] - center),
                        radius * 2,
                    )
                )
                draw.rect(image, rgb, arm)
        draw.circle(image, rgb, (center, center), radius)
        if water:
            inner_radius = max(2, round(radius * 0.64))
            for dr, dc, bit, _ in DIRECTIONS:
                if mask & bit:
                    arm = (
                        pygame.Rect(
                            center - inner_radius,
                            center if dr > 0 else -2,
                            inner_radius * 2,
                            center + 2,
                        )
                        if dr
                        else pygame.Rect(
                            center if dc > 0 else -2,
                            center - inner_radius,
                            center + 2,
                            inner_radius * 2,
                        )
                    )
                    draw.rect(image, WATER, arm)
            draw.circle(image, WATER, (center, center), inner_radius)
        if angle:
            # Rotate the high-resolution source, not an already reduced bitmap.
            image = pygame.transform.rotozoom(image, angle, 1)
        output_size = tuple(
            round(n / scale * self.screen.scale) for n in image.get_size()
        )
        result = pygame.transform.smoothscale(image, output_size)
        if angle:
            return result
        self.pipe_cache[key] = result
        # Bound cache memory after window resizing.
        if len(self.pipe_cache) > 512:
            self.pipe_cache = {key: result}
        return result

    def water_distances(self):
        """Source distances along reciprocal links determine flow direction."""
        distances = {self.puzzle.source: 0}
        pending = [self.puzzle.source]
        for i in pending:
            r, c = divmod(i, self.puzzle.size)
            for dr, dc, bit, opposite in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.puzzle.size and 0 <= nc < self.puzzle.size):
                    continue
                j = nr * self.puzzle.size + nc
                if (
                    self.puzzle.masks[i] & bit
                    and self.puzzle.masks[j] & opposite
                    and j not in distances
                ):
                    distances[j] = distances[i] + 1
                    pending.append(j)
        return distances

    def draw_water_flow(self, index, mask, rect, distances, now):
        # Small highlights travel through each arm, away from the source.
        distance = distances[index]
        r, c = divmod(index, self.puzzle.size)
        phase = now * 0.85
        spacing = 0.75
        for dr, dc, bit, _ in DIRECTIONS:
            if not mask & bit:
                continue
            nr, nc = r + dr, c + dc
            neighbor = nr * self.puzzle.size + nc
            inward = (
                0 <= nr < self.puzzle.size
                and 0 <= nc < self.puzzle.size
                and distances.get(neighbor, distance + 1) < distance
            )
            low = distance - 0.5 if inward else distance
            high = distance if inward else distance + 0.5
            k = math.ceil((low - phase) / spacing)
            position = phase + k * spacing
            while position < high:
                fraction = abs(position - distance)
                point = (
                    rect.centerx + dc * fraction * self.cell,
                    rect.centery + dr * fraction * self.cell,
                )
                draw.circle(
                    self.screen, WATER_LIGHT, point, max(1.2, self.cell * 0.018)
                )
                position += spacing

    def draw_board(self, status):
        card = self.board_card
        self.box(card, PAPER, 4, LINE)
        self.text("Board", (card.x + 28, card.y + 21), 17, INK, True)
        self.text(
            "Connect all pipes. Closed loops are not allowed.",
            (card.x + 28, card.y + 54),
            14,
            MUTED,
        )
        board = self.board_rect
        self.box(board.inflate(4, 4), "#DDE0E4", 2)
        self.hover_tile = (
            self.tile_at(pygame.mouse.get_pos()) if not self.modal else None
        )
        now = time.monotonic()
        distances = self.water_distances()
        for i, mask in enumerate(self.puzzle.masks):
            r, c = divmod(i, self.puzzle.size)
            rect = pygame.Rect(
                board.x + c * self.cell, board.y + r * self.cell, self.cell, self.cell
            )
            connected = i in status.connected
            fill = "#F0F2F5" if connected else "#FAFAFA"
            if self.hover_tile == i:
                fill = "#E2E7EF" if connected else "#EDEFF3"
            if i in self.click_feedback:
                pulse = max(0, 1 - (now - self.click_feedback[i]) / 0.30)
                fill = pygame.Color(fill).lerp(pygame.Color("#D5E2FC"), pulse)
                if not pulse:
                    del self.click_feedback[i]
            self.box(rect.inflate(-2, -2), fill, 2)
            color = "#93AEC5" if connected else PIPE
            pipe = self.pipe_surface(mask, color, water=connected)
            if i in self.animations:
                old, direction, started = self.animations[i]
                duration = max(0.001, self.settings["animation_ms"] / 1000)
                progress = min(1, (now - started) / duration)
                eased = progress * progress * (3 - 2 * progress)
                pipe = self.pipe_surface(
                    old, color, -direction * 90 * eased, water=connected
                )
                if progress >= 1:
                    queue = self.rotation_queue.get(i)
                    if queue:
                        next_old, next_direction = queue.pop(0)
                        self.animations[i] = (next_old, next_direction, now)
                        if not queue:
                            del self.rotation_queue[i]
                    else:
                        del self.animations[i]
            old_clip = self.screen.get_clip()
            self.screen.set_clip(rect)
            self.screen.blit_native(
                pipe,
                (
                    rect.centerx - pipe.get_width() / self.screen.scale / 2,
                    rect.centery - pipe.get_height() / self.screen.scale / 2,
                ),
            )
            if connected and i not in self.animations and not self.reduce_motion:
                self.draw_water_flow(i, mask, rect, distances, now)
            self.screen.set_clip(old_clip)
            if i == self.puzzle.source:
                draw.circle(
                    self.screen, PAPER, rect.center, max(10, self.cell // 8) + 3
                )
                draw.circle(self.screen, ACCENT, rect.center, max(10, self.cell // 8))
                self.icon("check" if status.solved else "", rect.center, PAPER)
                if not status.solved:
                    draw.circle(self.screen, PAPER, rect.center, 3)
            if i in self.puzzle.locked:
                self.box(pygame.Rect(rect.right - 25, rect.y + 7, 18, 18), PAPER, 5)
                self.icon("lock", (rect.right - 16, rect.y + 15), ACCENT, 12)
            if i == self.selected:
                selected_color = (
                    "#C44C3C"
                    if self.search_step and self.search_step.kind == "reject"
                    else ACCENT
                )
                draw.rect(
                    self.screen,
                    selected_color,
                    rect.inflate(-4, -4),
                    2,
                    border_radius=2,
                )
        y = card.bottom - 43
        x = card.x + 28
        for label, color in (("Water flowing", WATER), ("Empty pipe", PIPE)):
            draw.circle(self.screen, color, (x + 4, y + 8), 4)
            self.text(label, (x + 16, y - 1), 12, MUTED)
            x += 170 if label.startswith("Connected") else 130
        if self.search_step:
            step = self.search_step
            description = {
                "expand": "Expand state",
                "assign": "Assign orientation",
                "queue": "Queue state",
                "reject": "Reject orientation",
                "backtrack": "Backtrack",
            }[step.kind]
            if step.reason:
                description += f": {step.reason}"
            self.text(
                description,
                (card.x + 28, card.bottom - 68),
                13,
                "#C44C3C" if step.kind == "reject" else ACCENT,
            )

    def draw_sidebar(self, status):
        card = self.side_card
        x = card.x + 24
        width = card.w - 48
        y = card.y + 24
        compact = card.h < 610
        self.box(card, PAPER, 4, LINE)
        self.text("Grid size", (x, y), 11, MUTED, True)
        self.text(
            f"{self.puzzle.size} × {self.puzzle.size}", (x, y + 26), 30, INK, True
        )
        identity = (
            f"#{self.puzzle.seed:06X}" if self.puzzle.seed is not None else "JSON map"
        )
        self.text(identity, (card.right - 101, y + 36), 13, MUTED)
        y += 64 if compact else 84
        seg = width // 3
        for k, size in enumerate((4, 5, 7)):
            self.button(
                f"size_{size}",
                f"{size} × {size}",
                pygame.Rect(x + k * seg, y, seg - 5, 36),
                active=size == self.puzzle.size,
            )
        y += 44 if compact else 52
        self.text("Connected", (x, y), 11, MUTED, True)
        y += 24
        self.text(str(len(status.connected)), (x, y), 36, ACCENT, True)
        self.text(
            f"/ {self.puzzle.size**2} tiles connected", (x + 54, y + 16), 14, MUTED
        )
        y += 38 if compact else 45
        self.box(pygame.Rect(x, y, width, 6), "#E5E7EB", 3)
        progress = int(width * len(status.connected) / (self.puzzle.size**2))
        self.box(pygame.Rect(x, y, max(6, progress), 6), ACCENT, 3)
        y += 23
        if status.solved:
            summary, summary_color = "Network complete", ACCENT
        else:
            summary, summary_color = "Source marked in blue.", MUTED
        self.text(summary, (x, y), 13, summary_color)
        y += 22 if compact else 30
        draw.line(self.screen, LINE, (x, y), (x + width, y))
        y += 15 if compact else 19
        self.text("Expanded" if self.search else "Rotations", (x, y), 10, MUTED, True)
        self.text(
            "Solver time" if self.search else "Time",
            (x + width // 2, y),
            10,
            MUTED,
            True,
        )
        self.text(
            str(self.search.result.expanded if self.search else self.puzzle.moves),
            (x, y + 20),
            25,
            INK,
            True,
        )
        if self.search:
            result = (
                self.measured_result
                if self.search.result.status != "running" and self.measured_result
                else self.search.result
            )
            elapsed = f"{result.time_ms:.1f} ms"
        else:
            minutes, seconds = divmod(int(self.elapsed), 60)
            elapsed = f"{minutes:02}:{seconds:02}"
        self.text(elapsed, (x + width // 2, y + 20), 22, INK, True)
        y += 49 if compact else 55
        button_width = (width - 10) // 2
        self.button(
            "undo",
            "Undo",
            pygame.Rect(x, y, button_width, 42),
            enabled=bool(self.puzzle.history) and self.search is None,
            icon="undo",
        )
        self.button(
            "reset",
            "Reset",
            pygame.Rect(x + button_width + 10, y, button_width, 42),
            icon="reset",
        )
        y += 54
        draw.line(self.screen, LINE, (x, y), (x + width, y))
        y += 12
        self.text("Algorithm", (x, y), 11, MUTED, True)
        y += 20
        half = (width - 8) // 2
        self.button(
            "algo_dfs",
            "DFS",
            pygame.Rect(x, y, half, 32),
            active=self.algorithm == "dfs",
        )
        self.button(
            "algo_greedy_best_first",
            "Greedy",
            pygame.Rect(x + half + 8, y, half, 32),
            active=self.algorithm == "greedy_best_first",
        )
        y += 40
        label = (
            "Pause"
            if self.search
            and self.search.result.status == "running"
            and not self.search_paused
            else "Resume"
            if self.search and self.search.result.status == "running"
            else "Run"
        )
        self.button("run", label, pygame.Rect(x, y, half, 34), primary=True)
        self.button(
            "next",
            "Next",
            pygame.Rect(x + half + 8, y, half, 34),
            enabled=self.search is None or self.search.result.status == "running",
        )
        y += 41
        rate = self.settings["playback_steps_per_second"]
        self.button("speed", f"Speed: {rate} steps/s", pygame.Rect(x, y, width, 28))
        y += 35
        if self.search:
            result = self.search.result
            label = (
                "Paused"
                if result.status == "running" and self.search_paused
                else result.status.replace("_", " ").capitalize()
            )
            memory = (
                self.measured_result.peak_memory_kib
                if self.measured_result and result.status != "running"
                else None
            )
            peak = f"{memory:.1f} KiB" if memory is not None else "—"
            self.text(
                f"{label}  ·  Peak: {peak}",
                (x, y),
                12,
                ACCENT
                if result.status == "solved"
                else "#C44C3C"
                if result.status == "unsolvable"
                else MUTED,
            )
            if result.board and y + 50 < card.bottom:
                self.button(
                    "solution", "Show solution", pygame.Rect(x, y + 23, width, 30)
                )

    def draw_modal(self):
        veil = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 95))
        self.screen.blit(veil, (0, 0))
        rect = pygame.Rect(0, 0, 550, 255)
        rect.center = self.screen.get_rect().center
        self.box(rect, PAPER, 6)
        x, y = rect.x + 32, rect.y + 28
        reset = self.modal[1] == "reset"
        self.text(
            "Start this puzzle over?" if reset else "Load a new puzzle?",
            (x, y),
            25,
            INK,
            True,
        )
        self.wrapped(
            "This clears your current rotations and locks.",
            x,
            y + 51,
            rect.w - 64,
            16,
            MUTED,
        )
        cancel = pygame.Rect(x, rect.bottom - 76, 155, 44)
        self.box(cancel, PAPER, 4, LINE)
        self.text("Cancel", cancel.center, 15, INK, True, True)
        button = pygame.Rect(rect.right - 212, rect.bottom - 76, 180, 44)
        self.box(button, ACCENT, 4)
        self.text(
            "Reset puzzle" if reset else "New puzzle",
            button.center,
            15,
            PAPER,
            True,
            True,
        )
        self.modal_widgets = [("cancel", cancel), ("confirm", button)]

    def draw(self):
        self.widgets = []
        self.screen.fill(BG)
        w, h = self.screen.get_size()
        self.text("Pipes", (32, 27), 30, INK, True)
        self.text("Rotate tiles to connect the network.", (135, 38), 14, MUTED)
        self.button(
            "new",
            "New puzzle",
            pygame.Rect(w - 206, 27, 174, 40),
            primary=True,
        )
        status = self.puzzle.status
        self.draw_board(status)
        self.draw_sidebar(status)
        footer = "Click to rotate  ·  Shift-click to reverse  ·  Right-click to lock"
        if status.solved:
            footer = "Solved"
        elif self.toast and time.monotonic() < self.toast_until:
            footer = self.toast
        if self.result_text:
            footer = self.result_text
        elif self.search:
            footer = (
                "Search exploration"
                if self.search.result.status == "running"
                else (
                    "This map is unsolvable with the current pipe layout."
                    if self.search.result.status == "unsolvable"
                    else f"{self.algorithm.replace('_', ' ')}: {self.search.result.status.replace('_', ' ')}"
                )
            )
        self.text(footer, (33, h - 31), 12, ACCENT if status.solved else MUTED)
        motion = pygame.Rect(w - 180, h - 36, 148, 23)
        self.text(
            "Motion: off" if self.reduce_motion else "Motion: on",
            motion.center,
            11,
            MUTED,
            False,
            True,
        )
        self.widgets.append(("motion", motion))
        if self.modal:
            self.draw_modal()
        else:
            over_button = any(
                rect.collidepoint(pygame.mouse.get_pos()) for _, rect in self.widgets
            )
            if pygame.display.get_driver() != "dummy":
                pygame.mouse.set_cursor(
                    pygame.SYSTEM_CURSOR_HAND
                    if over_button or self.hover_tile is not None
                    else pygame.SYSTEM_CURSOR_ARROW
                )
        self.present()

    def run(self, screenshot=None):
        self.draw()
        if screenshot:
            path = Path(screenshot)
            path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.screen.pixels, str(path))
            pygame.quit()
            return
        while self.running:
            dt = self.clock.tick(60) / 1000
            self.events()
            if not self.running:
                break
            self.update_search()
            solved = self.puzzle.status.solved
            if not self.modal and not solved and self.search is None:
                self.elapsed += dt
            if solved and not self.was_solved:
                self.notify("Puzzle solved.")
            self.was_solved = solved
            self.draw()
        self.clear_search()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Pipes")
    parser.add_argument("--size", type=int, choices=(4, 5, 7), default=None)
    parser.add_argument(
        "--seed", type=int, default=None, help="Reproduce a specific puzzle"
    )
    parser.add_argument("--screenshot", help="Save the first frame and exit")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--map", type=Path, help="Load a saved map")
    args = parser.parse_args()
    try:
        settings = load_game_config(args.config)
        if args.map:
            puzzle = load_map(args.map)
        elif args.size is not None or args.seed is not None:
            puzzle = Puzzle(
                args.size or 5,
                args.seed
                if args.seed is not None
                else random.SystemRandom().randrange(1, 0xFFFFFF),
            )
        else:
            puzzle = load_map(settings["startup_map"])
        App(puzzle=puzzle, settings=settings).run(args.screenshot)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
