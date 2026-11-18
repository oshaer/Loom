"""Run log written in plain English. Every simulation run writes one.

The simulation calls the hooks below; this module turns what happened into
sentences a non-technical reader can follow. It reads simulation state but
does not import the simulation, so there is no circular dependency.
"""

# HOW TO READ THIS FILE
# Writes the plain-English log of a run. The simulation calls header() once,
# post() for each bulletin-board post, round_start() and round_end() for each
# round, and footer() at the end. Most of the file chooses the right words.
from __future__ import annotations

import os
import textwrap
from datetime import datetime
from pathlib import Path

# Lines wrap at 78 characters so the log reads well anywhere.
WIDTH = 78


# A new, date-stamped file name for each run.
def default_log_path(directory: str | os.PathLike = "logs") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(directory) / f"bugglemaze-{stamp}.log"
    n = 2
    while path.exists():  # two runs in the same second
        path = Path(directory) / f"bugglemaze-{stamp}-{n}.log"
        n += 1
    return path


# ---- wording helpers -------------------------------------------------
# "1 turn" but "2 turns".
def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


# Squares in words: (4, 2) becomes "row 3, column 5" (people count from 1).
def square(cell) -> str:
    x, y = cell
    return f"row {y + 1}, column {x + 1}"


# "Buggle 4", noting its map symbol when that differs from its number.
def buggle_name(b) -> str:
    n = b.index + 1
    return f"Buggle {n}" if str(n) == b.symbol else f"Buggle {n} (shown as {b.symbol})"


# A route as walking directions, such as "right 3, down 1".
def directions(path) -> str:
    """[(0,0),(1,0),(2,0),(2,1)] -> 'right 2, down 1'."""
    words = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
    legs: list[list] = []
    for a, b in zip(path, path[1:]):
        d = words[(b[0] - a[0], b[1] - a[1])]
        if legs and legs[-1][0] == d:
            legs[-1][1] += 1
        else:
            legs.append([d, 1])
    return ", ".join(f"{d} {n}" for d, n in legs)


def compare_to_shortest(best: int, shortest: int) -> str:
    extra = best - shortest
    if extra == 0:
        return "which matches the shortest possible route"
    return f"{plural(extra, 'step')} longer than the shortest possible route"


# One log file, written line by line as the run goes.
class RunLog:
    """Line-buffered so `tail -f` follows a live run."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8", buffering=1)
        self._dead_batch: list = []  # (buggle, turn, cell) waiting to be reported together
        self._prev_best: int | None = None
        self._posts_this_round = 0
        self._prev_round_turns: int | None = None

    # ---- low level ---------------------------------------------------
    def write(self, text: str = "", indent: int = 0, hang: bool = False) -> None:
        if self._f.closed:
            return
        if not text:
            self._f.write("\n")
            return
        pad = " " * indent
        self._f.write(textwrap.fill(text, WIDTH, initial_indent=pad,
                                    subsequent_indent=pad + ("  " if hang else "")) + "\n")

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()

    # ---- hooks called by the simulation ------------------------------
    # The opening: who made Loom, the maze, and how the notice board works.
    def header(self, sim) -> None:
        m = sim.maze
        now = datetime.now()
        when = now.strftime("%d %B %Y at %I:%M %p").lstrip("0").replace(" 0", " ")
        self.write("This is Loom")
        self.write("=" * 12)
        self.write()
        self.write(f"I am running a maze simulation: {plural(len(sim.buggles), 'buggle', 'buggles')} "
                   f"working together to find their way through a {m.width} by {m.height} "
                   f"maze, over {plural(sim.n_episodes, 'round')}.")
        self.write(f"Started {when}.")
        self.write()
        self.write("-" * WIDTH)
        self.write()
        self.write(f"The maze is {m.width} squares wide and {m.height} squares tall. "
                   f"The buggles start in the top-left corner and try to reach the "
                   f"finish in the bottom-right corner.")
        self.write()
        if m.mud:
            self.write(f"{plural(len(m.mud), 'square is', 'squares are')} muddy. "
                       f"A buggle that drives into mud is stuck for "
                       f"{plural(sim.mud_delay, 'extra turn')}.")
            self.write()
        self.write(f"The shortest possible route to the finish is "
                   f"{plural(sim.true_shortest_len, 'step')}. The buggles don't know "
                   f"this; it's here so you can judge how well they do.")
        self.write()
        self.write(f"{plural(len(sim.buggles), 'buggle', 'buggles')} take part over "
                   f"{plural(sim.n_episodes, 'round')}. In each round every buggle starts "
                   f"again from the start and has up to {sim.max_steps} turns to reach "
                   f"the finish.")
        self.write()
        self.write("The buggles share a notice board. When one finds a dead end, or a "
                   "shorter route to the finish, it posts it there and the others use "
                   "it from then on, including in later rounds.")
        last = max(sim.epsilon_min, sim.epsilon0 * sim.epsilon_decay ** (sim.n_episodes - 1))
        self.write()
        self.write(f"Buggles sometimes take a random turn to try something new. This "
                   f"happens {sim.epsilon0:.0%} of the time in round 1 and less each "
                   f"round, down to {last:.0%} in the last round.")
        if sim.seed is not None:
            self.write()
            self.write(f"(Maze number {sim.seed}: running again with the same number "
                       f"gives the same maze.)")
        self.write()

    def round_start(self, sim) -> None:
        self.write()
        title = f"Round {sim.episode} of {sim.n_episodes}"
        self.write(title)
        self.write("-" * len(title))
        self.write(f"Random turns this round: {sim.epsilon:.0%} of the time.")
        self.write()
        self._posts_this_round = 0

    # Turn a post into a sentence. Dead ends found one after another by the same
    # buggle are saved up and reported together (see _flush_dead_ends).
    def post(self, sim, msg) -> None:
        buggle = next(b for b in sim.buggles if b.name == msg.author)
        if msg.kind == "DEAD_END":
            if self._dead_batch and self._dead_batch[-1][0] is not buggle:
                self._flush_dead_ends()
            x, y = (int(v) for v in msg.detail.strip("()").split(","))
            self._dead_batch.append((buggle, msg.tick, (x, y)))
            return
        self._flush_dead_ends()
        if msg.kind == "BETTER_PATH":
            length = int(msg.detail.split("=")[1])
            if self._prev_best is None:
                text = (f"reached the finish and shared the first known route: "
                        f"{plural(length, 'step')}.")
            else:
                text = (f"found a shorter route and shared it: {plural(length, 'step')}, "
                        f"{self._prev_best - length} fewer than before.")
            self._prev_best = length
            self.write(f"Turn {msg.tick}: {buggle_name(buggle)} {text}", indent=2, hang=True)
            self._posts_this_round += 1

    def _flush_dead_ends(self) -> None:
        if not self._dead_batch:
            return
        buggle = self._dead_batch[0][0]
        first, last = self._dead_batch[0][1], self._dead_batch[-1][1]
        when = f"Turn {first}" if first == last else f"Turns {first} to {last}"
        if len(self._dead_batch) == 1:
            what = (f"found a dead end at {square(self._dead_batch[0][2])} and warned "
                    f"the others.")
        else:
            what = (f"found {len(self._dead_batch)} dead-end squares in a row, ending at "
                    f"{square(self._dead_batch[-1][2])}, and warned the others.")
        self.write(f"{when}: {buggle_name(buggle)} {what}", indent=2, hang=True)
        self._posts_this_round += 1
        self._dead_batch = []

    # A short summary of the round and how each buggle did.
    def round_end(self, sim) -> None:
        self._flush_dead_ends()
        if self._posts_this_round == 0:
            self.write("Nothing new was posted to the notice board this round.", indent=2)
        n, done = len(sim.buggles), sim.finished
        took = f"{sim.tick} turns"
        if self._prev_round_turns is not None:
            diff = self._prev_round_turns - sim.tick
            if diff > 0:
                took += f", {diff} fewer than the round before"
            elif diff < 0:
                took += f", {-diff} more than the round before"
            else:
                took += ", the same as the round before"
        self._prev_round_turns = sim.tick
        if done == n:
            who = "All the buggles" if n > 1 else "The buggle"
            line = f"{who} reached the finish. The round took {took}."
        elif done == 0:
            line = f"No buggle reached the finish this round. It lasted {took}."
        else:
            line = (f"{done} of {n} buggles reached the finish. "
                    f"The round lasted {took}.")
        self.write()
        self.write(line, indent=2)
        best = sim.board.best_len
        if best is None:
            self.write("No route to the finish is known yet.", indent=2)
        else:
            self.write(f"Best known route: {plural(best, 'step')}, "
                       f"{compare_to_shortest(best, sim.true_shortest_len)}.", indent=2)
        self.write(f"Dead ends marked on the notice board so far: "
                   f"{len(sim.board.dead_ends)}.", indent=2)
        self.write()
        for b in sim.buggles:
            self.write(f"{buggle_name(b)} {self._buggle_outcome(b)}", indent=4)

    @staticmethod
    def _buggle_outcome(b) -> str:
        explored = f"exploring {plural(len(b.visited), 'square')}"
        if b.status == "at goal":
            return f"reached the finish in {b.steps} turns, {explored}."
        if b.status == "out of steps":
            return f"ran out of turns after {explored}."
        return f"was still on its way after {b.steps} turns, {explored}."

    # The result: the best route against the shortest possible, and its directions.
    def footer(self, sim, complete: bool, seconds: float) -> None:
        self._flush_dead_ends()
        self.write()
        self.write("Result")
        self.write("------")
        if not complete:
            self.write(f"The run was stopped early, during round {sim.episode} of "
                       f"{sim.n_episodes}.")
        best = sim.board.best_len
        rounds = plural(sim.episode if not complete else sim.n_episodes, "round")
        if best is None:
            self.write(f"After {rounds}, no buggle found a way to the finish.")
        else:
            self.write(f"After {rounds}, the best route found is "
                       f"{plural(best, 'step')}, "
                       f"{compare_to_shortest(best, sim.true_shortest_len)}.")
            self.write()
            self.write(f"Directions for that route, starting from the top-left corner: "
                       f"{directions(sim.board.best_path)}.")
            self.write()
        self.write(f"The buggles marked {plural(len(sim.board.dead_ends), 'dead end')} "
                   f"for each other along the way.")
        took = "less than a second" if seconds < 1 else f"{seconds:.0f} seconds"
        self.write(f"The whole run took {took}.")
