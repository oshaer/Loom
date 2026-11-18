"""Terminal renderer for the buggle maze simulation.

The simulation never imports this module. AsciiView plugs in through the
Observer hooks in sim.py and only reads simulation state.
"""

# HOW TO READ THIS FILE
# This file draws the simulation in a terminal window. It has two parts:
#   * Painter turns the simulation's state into lines of text. It never prints.
#   * AsciiView is an Observer (see sim.py) that prints the Painter's lines and
#     handles the terminal: hiding the cursor, redrawing in place, and putting
#     everything back when the program ends, even after Ctrl+C.
# Terminals understand "escape codes": invisible character sequences that start
# with ESC and set a colour or move the cursor. ESC + "31m" means "red from here
# on", and ESC + "0m" means "back to normal".
from __future__ import annotations

import atexit
import re
import shutil
import signal
import sys
import time
from typing import Callable, Iterable

from .sim import AT_GOAL, EXPLORING, Observer, Simulation

# ---- ANSI ------------------------------------------------------------
# The escape codes used below. "\x1b" is the ESC character.
ESC = "\x1b["
HOME, CLEAR, CLEAR_EOL, CLEAR_EOS = ESC + "H", ESC + "2J", ESC + "K", ESC + "J"
HIDE_CURSOR, SHOW_CURSOR, RESET = ESC + "?25l", ESC + "?25h", ESC + "0m"

GREEN, RED, YELLOW = ESC + "32m", ESC + "31m", ESC + "33m"
DIM, BOLD = ESC + "2m", ESC + "1m"
# Distinct 256-color hues that avoid the green/red/yellow used for meaning.
# Colours for buggles, as numbers from the terminal's 256-colour palette. They
# avoid the green, red and yellow that already mean something on the map.
BUGGLE_HUES = [33, 201, 51, 208, 141, 39, 213, 123, 172, 99, 45, 219, 81, 165, 215, 63]

# A regular expression (a text pattern) that matches any escape code. It lets us
# measure how wide a line looks on screen, ignoring the invisible codes.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# The width of a line as it appears, not counting escape codes.
def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# Add spaces so a line fills `width` columns; used to line up the panel beside the maze.
def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - visible_len(s))


# The colour code for buggle number `index`. `%` wraps around if there are more
# buggles than colours.
def buggle_color(index: int) -> str:
    return f"{ESC}1;38;5;{BUGGLE_HUES[index % len(BUGGLE_HUES)]}m"


# ---- watch selection -------------------------------------------------
# Read the --watch option, such as "1,10-12,last", into a set of round numbers.
def parse_watch(spec: str, n_episodes: int) -> set[int]:
    """'1,3,5-7,last' -> {1,3,5,6,7,N}. Also accepts 'all' and 'none'."""
    out: set[int] = set()
    for part in (p.strip().lower() for p in spec.split(",")):
        if not part or part == "none":
            continue
        if part == "all":
            out.update(range(1, n_episodes + 1))
        elif part == "last":
            out.add(n_episodes)
        elif part == "first":
            out.add(1)
        elif "-" in part:
            a, b = part.split("-", 1)
            lo = int(a)
            hi = n_episodes if b in ("", "last") else int(b)
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    return {e for e in out if 1 <= e <= n_episodes}


# ---- frame building --------------------------------------------------
# Draws the maze and the status panel as lists of text lines.
class Painter:
    """Turns simulation state into lines of text. No I/O."""

    PANEL_WIDTH = 46

    def __init__(self, color: bool, trails: bool):
        self.color = color
        self.trails = trails

    # Wrap text in a colour code, or leave it plain when colour is off.
    def c(self, code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if self.color else text

    # -- maze --
    # DRAWING THE MAZE. Each square is 3 characters wide. For every row we build two
    # lines: the wall above it ("+---+" or "+   +" where there is a passage) and the
    # row itself ("|" for a wall on the left, then the square's symbol).
    def maze_lines(self, sim: Simulation) -> list[str]:
        m, board = sim.maze, sim.board
        occupants: dict[tuple, list] = {}
        for b in sim.buggles:
            if b.status != AT_GOAL:  # finished buggles step off the board
                occupants.setdefault(b.pos, []).append(b)
        best = set(board.best_path)
        trail: set = set()
        if self.trails:
            for b in sim.buggles:
                trail |= b.visited

        # The symbol for one square. The order of these tests sets what wins when
        # several apply: buggles first, then start and finish, the best route,
        # dead ends, mud and trails.
        def glyph(cell) -> str:
            here = occupants.get(cell)
            if here and len(here) > 1:
                return self.c(BOLD, "*")
            if here:
                b = here[0]
                return self.c(buggle_color(b.index), b.symbol)
            if cell == m.start:
                return self.c(BOLD, "S")
            if cell == m.goal:
                return self.c(BOLD, "G")
            if cell in best:
                return self.c(GREEN, ".")
            if cell in board.dead_ends:
                return self.c(RED, "x")
            if cell in m.mud:
                return self.c(YELLOW, "~")
            if cell in trail:
                return self.c(DIM, ",")
            return " "

        # Build the picture row by row, then add the bottom wall.
        lines = []
        for y in range(m.height):
            top = "+"
            mid = ""
            for x in range(m.width):
                above_open = y > 0 and m.passable((x, y - 1), (x, y))
                top += ("   " if above_open else "---") + "+"
                left_open = x > 0 and m.passable((x - 1, y), (x, y))
                mid += (" " if left_open else "|") + " " + glyph((x, y)) + " "
            lines += [top, mid + "|"]
        lines.append("+" + "---+" * m.width)
        return lines

    # THE STATUS PANEL: round and tick, the best route on the board against the
    # shortest possible, a table of buggles, the latest bulletin-board posts and a
    # legend. `max_rows` trims the table when the screen is short.
    def panel_lines(self, sim: Simulation, max_rows: int | None = None) -> list[str]:
        board = sim.board
        best = board.best_len
        gap = "" if best is None else f"  (+{best - sim.true_shortest_len})"
        head = [
            self.c(BOLD, f"Episode {sim.episode} of {sim.n_episodes}") +
            f"   tick {sim.tick}   eps {sim.epsilon:.2f}",
            f"Finished {sim.finished}/{len(sim.buggles)}",
            f"Best on board: {best if best is not None else 'none'}{gap}"
            f"   true shortest: {sim.true_shortest_len}",
            "",
            self.c(BOLD, f"{'Buggle':<7}{'Sym':<5}{'Steps':>6}  Status"),
        ]
        rows = []
        for b in sim.buggles:
            status = b.status
            if status == EXPLORING and b.stuck:
                status = "exploring (mud)"
            sym = self.c(buggle_color(b.index), b.symbol)
            rows.append(f"{b.name:<7}{sym}{' ' * 4}{b.steps:>6}  {status}")

        msgs = [str(msg) for msg in board.recent(6)]
        tail = ["", self.c(BOLD, "Bulletin board")] + (msgs or ["(no posts yet)"])
        tail += ["", self.c(BOLD, "Legend")] + self.legend(sim)

        if max_rows is not None:
            room = max_rows - len(head) - len(tail)
            if room < len(rows):
                keep = max(1, room - 1)
                rows = rows[:keep] + [f"... {len(rows) - keep} more buggles"]
        return head + rows + tail

    # What each symbol means, and which colour is which buggle.
    def legend(self, sim: Simulation) -> list[str]:
        out = [
            f"{self.c(BOLD, 'S')} start  {self.c(BOLD, 'G')} goal  "
            f"{self.c(BOLD, '*')} 2+ buggles in a cell",
            f"{self.c(YELLOW, '~')} mud  {self.c(RED, 'x')} dead end  "
            f"{self.c(GREEN, '.')} best path"
            + (f"  {self.c(DIM, ',')} trail" if self.trails else ""),
        ]
        line = ""
        for b in sim.buggles:
            item = f"{self.c(buggle_color(b.index), b.symbol)}={b.name} "
            if visible_len(line + item) > self.PANEL_WIDTH:
                out.append(line.rstrip())
                line = ""
            line += item
        if line:
            out.append(line.rstrip())
        return out

    # -- layout --
    # Put the maze and panel together: side by side if the screen is wide enough,
    # otherwise the panel goes below.
    def frame(self, sim: Simulation, cols: int, rows: int) -> list[str]:
        maze = self.maze_lines(sim)
        maze_w = 4 * sim.maze.width + 1
        if cols >= maze_w + 3 + self.PANEL_WIDTH:  # side by side
            panel = self.panel_lines(sim, max_rows=max(rows - 1, len(maze)))
            height = max(len(maze), len(panel))
            maze += [""] * (height - len(maze))
            panel += [""] * (height - len(panel))
            return [pad(a, maze_w) + "   " + b for a, b in zip(maze, panel)]
        panel = self.panel_lines(sim, max_rows=max(8, rows - 1 - len(maze) - 1))
        return maze + [""] + panel


# ---- the observer ----------------------------------------------------
# The terminal display. It is an Observer, so the simulation calls its on_...
# methods. `watch` says which rounds to animate; other rounds run at full speed
# with a one-line progress bar.
class AsciiView(Observer):
    def __init__(self, watch: set[int] | Callable[[int], bool] = frozenset({1}),
                 fps: float = 20.0, trails: bool = False, color: str = "auto",
                 stream=None, pause_between: float = 0.8):
        self.out = stream or sys.stdout
        self.tty = bool(getattr(self.out, "isatty", lambda: False)())
        self._watch = watch if callable(watch) else (lambda e, w=set(watch): e in w)
        self.delay = 1.0 / fps if fps > 0 else 0.0
        self.trails = trails
        use_color = {"always": True, "never": False}.get(color, self.tty)
        self.painter = Painter(color=use_color, trails=trails)
        self.pause_between = pause_between
        self.animate = self.tty
        self.watching = False
        self._cursor_hidden = False
        self._progress_open = False
        self._last_progress = 0.0
        self._prev_sigterm = None

    # -- terminal housekeeping --
    # Write text to the screen (short for "write").
    def _w(self, s: str) -> None:
        self.out.write(s)

    # The terminal's size in columns and rows. 80 x 24 is assumed if unknown.
    def _size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size((80, 24))
        return size.columns, size.lines

    # Hide the blinking cursor during the animation, and arrange for it to come back
    # however the program ends: `atexit` runs at normal exit, and the SIGTERM
    # handler covers being told to stop by the system.
    def _hide_cursor(self) -> None:
        if not self._cursor_hidden:
            self._w(HIDE_CURSOR)
            self._cursor_hidden = True
            atexit.register(self.restore)
            try:
                self._prev_sigterm = signal.signal(signal.SIGTERM, self._on_sigterm)
            except ValueError:  # not in main thread
                pass

    def _on_sigterm(self, signum, frame) -> None:
        self.restore()
        sys.exit(128 + signum)

    # Show the cursor again and reset colours. Safe to call more than once.
    def restore(self) -> None:
        """Show the cursor and reset colors. Safe to call more than once."""
        if self._cursor_hidden:
            self._w(RESET + SHOW_CURSOR)
            self._end_progress()
            self.out.flush()
            self._cursor_hidden = False
            if self._prev_sigterm is not None:
                try:
                    signal.signal(signal.SIGTERM, self._prev_sigterm)
                except ValueError:
                    pass

    # -- observer hooks --
    # Before round 1: check the maze fits the terminal. If not, warn, suggest a
    # smaller size, and run without animation.
    def on_start(self, sim: Simulation) -> None:
        if not self.tty:
            return
        cols, rows = self._size()
        need_w, need_h = 4 * sim.maze.width + 1, 2 * sim.maze.height + 1
        if need_w > cols or need_h > rows - 1:
            sw = max(2, min(sim.maze.width, (cols - 1) // 4))
            sh = max(2, min(sim.maze.height, (rows - 2) // 2))
            self._w(f"Warning: the maze needs {need_w}x{need_h} characters but the terminal "
                    f"is {cols}x{rows}.\nTry --width {sw} --height {sh}, or enlarge the "
                    f"window. Running without animation.\n")
            self.animate = False
        self._hide_cursor()

    # Start of a round: clear the screen if this round is animated, otherwise show
    # the progress bar.
    def on_episode_start(self, sim: Simulation) -> None:
        self.watching = self.animate and self._watch(sim.episode)
        if self.watching:
            self._end_progress()
            self._w(CLEAR + HOME)
            self._draw(sim)
        elif self.tty:
            self._progress(sim, force=True)

    # After every tick: redraw the picture, then pause so the animation runs at the
    # chosen frames per second.
    def on_tick(self, sim: Simulation) -> None:
        if self.watching:
            self._draw(sim)
            if self.delay:
                time.sleep(self.delay)
        elif self.tty:
            self._progress(sim)

    # End of a round: draw the final picture, then pause a moment before the next.
    def on_episode_end(self, sim: Simulation) -> None:
        if self.watching:
            self._draw(sim)
            self._w("\n")
            self.out.flush()
            if self.pause_between:
                time.sleep(self.pause_between)
        elif self.tty:
            self._progress(sim, force=True)
            self._end_progress()

    # End of the run: print a summary and the log's location. If the output is not a
    # terminal (for example, saved to a file), print one plain snapshot instead.
    def on_finish(self, sim: Simulation) -> None:
        if self.tty and self.animate:
            self.restore()
            self._w(self.summary(sim) + "\n")
        else:
            self.restore()
            if self.tty:
                self._w("\n")
            self._w(self.snapshot(sim) + "\n")
        self.out.flush()

    # -- drawing --
    # Redraw in place: move the cursor to the top-left corner (HOME) and write over
    # the old picture. This avoids the flicker of clearing the screen every frame.
    def _draw(self, sim: Simulation) -> None:
        cols, rows = self._size()
        lines = self.painter.frame(sim, cols, rows)
        self._w(HOME + (CLEAR_EOL + "\n").join(lines) + CLEAR_EOL + "\n" + CLEAR_EOS)
        self.out.flush()

    # The one-line progress bar for rounds that are not animated. "\r" returns to
    # the start of the line, so each update overwrites the last.
    def _progress(self, sim: Simulation, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_progress < 0.05:
            return
        self._last_progress = now
        cols, _ = self._size()
        bar_w = max(10, min(30, cols - 60))
        done = sum(b.status != EXPLORING for b in sim.buggles)
        frac = max(done / len(sim.buggles),
                   max(b.steps for b in sim.buggles) / sim.max_steps)
        fill = int(bar_w * min(1.0, frac))
        best = sim.board.best_len
        line = (f"Episode {sim.episode}/{sim.n_episodes} [{'#' * fill}{'.' * (bar_w - fill)}] "
                f"tick {sim.tick}  finished {sim.finished}/{len(sim.buggles)}  "
                f"best {best if best is not None else 'none'}")
        self._w("\r" + line[: cols - 1] + CLEAR_EOL)
        self.out.flush()
        self._progress_open = True

    def _end_progress(self) -> None:
        if self._progress_open:
            self._w("\n")
            self._progress_open = False

    # -- static output --
    # Two closing lines: the result, and where the log was saved.
    def summary(self, sim: Simulation) -> str:
        best = sim.board.best_len
        return (f"Done: {sim.n_episodes} episodes. Best path on board "
                f"{best if best is not None else 'none'}, true shortest "
                f"{sim.true_shortest_len}, {len(sim.board.dead_ends)} dead ends posted.\n"
                f"Log: {sim.log_path}")

    # A final picture with no animation, for output saved to a file.
    def snapshot(self, sim: Simulation) -> str:
        cols, rows = self._size() if self.tty else (200, 10_000)
        return "\n".join(self.painter.frame(sim, cols, rows)) + "\n\n" + self.summary(sim)
