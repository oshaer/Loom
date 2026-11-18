"""Multi-buggle maze traversal with a shared bulletin board.

This module has no knowledge of rendering. Anything that wants to watch the
run implements the Observer hooks and is passed to Simulation.run().
"""

# HOW TO READ THIS FILE
# Version 1 of Loom: buggles follow fixed rules, with no learning in the
# technical sense. Each turn a buggle either makes a random move (with chance
# epsilon), or follows a short list of rules in order:
#   1. if it is on the best known route, keep following it;
#   2. otherwise go somewhere it has not been this round;
#   3. otherwise head for the nearest place with an unexplored way out.
# It avoids squares posted as dead ends, posts new dead ends it discovers, and
# posts its route when it reaches the finish if that route beats the best one.
# Start with `Simulation.run`, then `step`, then `_choose` and `_move`.
from __future__ import annotations

import random
import string
import time
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field

from .board import BulletinBoard
from .maze import Cell, Maze
from .runlog import RunLog, default_log_path

# Characters used to draw buggles: 1-9, a-z, A-Z (61 in all).
SYMBOLS = string.digits[1:] + string.ascii_lowercase + string.ascii_uppercase  # 61

EXPLORING, AT_GOAL, OUT_OF_STEPS = "exploring", "at goal", "out of steps"


# One buggle. `stack` is its route this round with any loops removed (the route it
# will post if it reaches the finish); `visited` is every square it has stood on.
@dataclass
class Buggle:
    index: int
    name: str
    symbol: str
    pos: Cell = (0, 0)
    steps: int = 0
    status: str = EXPLORING
    stuck: int = 0
    stack: list[Cell] = field(default_factory=list)
    visited: set[Cell] = field(default_factory=set)

    # Back to the start for a new round. The bulletin board keeps what was posted.
    def reset(self, start: Cell) -> None:
        self.pos, self.steps, self.status, self.stuck = start, 0, EXPLORING, 0
        self.stack = [start]
        self.visited = {start}


# Anything that wants to watch the run (the terminal display, for one) supplies
# these methods; the simulation calls them at key moments. `...` means "do
# nothing". The simulation never depends on who is watching.
class Observer:
    """No-op hooks. Subclass and override what you need."""
    def on_start(self, sim: "Simulation") -> None: ...
    def on_episode_start(self, sim: "Simulation") -> None: ...
    def on_tick(self, sim: "Simulation") -> None: ...
    def on_episode_end(self, sim: "Simulation") -> None: ...
    def on_finish(self, sim: "Simulation") -> None: ...


# The experiment: a maze, a team of buggles and their bulletin board.
class Simulation:
    def __init__(self, maze: Maze, n_buggles: int = 6, episodes: int = 10,
                 max_steps: int | None = None, epsilon: float = 0.35,
                 epsilon_decay: float = 0.8, epsilon_min: float = 0.02,
                 mud_delay: int = 2, seed: int | None = None,
                 log_path: str | None = None):
        if not 1 <= n_buggles <= len(SYMBOLS):
            raise ValueError(f"buggles must be between 1 and {len(SYMBOLS)}")
        self.maze = maze
        self.board = BulletinBoard(on_post=self._log_post)
        self.seed = seed
        self.log_path = Path(log_path) if log_path else default_log_path()
        self.log: RunLog | None = None
        self.rng = random.Random(seed)
        self.n_episodes = episodes
        self.max_steps = max_steps or 3 * maze.width * maze.height
        self.epsilon0, self.epsilon_decay, self.epsilon_min = epsilon, epsilon_decay, epsilon_min
        self.mud_delay = mud_delay
        # Make the team. f"B{i + 1:02d}" turns 0 into "B01" (two digits, padded with 0).
        self.buggles = [Buggle(i, f"B{i + 1:02d}", SYMBOLS[i]) for i in range(n_buggles)]
        self.true_shortest = maze.shortest_path()
        self.episode = 0
        self.tick = 0
        self.epsilon = epsilon

    # Properties read like values: `sim.true_shortest_len`, no brackets needed.
    @property
    def true_shortest_len(self) -> int:
        return len(self.true_shortest) - 1

    @property
    def finished(self) -> int:
        return sum(b.status == AT_GOAL for b in self.buggles)

    @property
    def episode_done(self) -> bool:
        return all(b.status != EXPLORING for b in self.buggles)

    # ---- main loop ---------------------------------------------------
    # The whole experiment: for each round, reset the buggles and tick until every
    # buggle has finished or run out of turns. `try ... finally` completes the log
    # even if the run is stopped part-way.
    def run(self, observer: Observer | None = None) -> None:
        obs = observer or Observer()
        self.log = RunLog(self.log_path)
        self.log.header(self)
        t0 = time.monotonic()
        complete = False
        try:
            obs.on_start(self)
            for e in range(1, self.n_episodes + 1):
                self.start_episode(e)
                obs.on_episode_start(self)
                while not self.episode_done:
                    self.step()
                    obs.on_tick(self)
                self.log.round_end(self)
                obs.on_episode_end(self)
            complete = True
            obs.on_finish(self)
        finally:
            self.log.footer(self, complete, time.monotonic() - t0)
            self.log.close()

    # ---- logging (wording lives in runlog.py) -----------------------
    def _log_post(self, msg) -> None:
        if self.log:
            self.log.post(self, msg)

    # Begin round e. Epsilon, the chance of a random move, shrinks each round.
    def start_episode(self, e: int) -> None:
        self.episode, self.tick = e, 0
        self.epsilon = max(self.epsilon_min, self.epsilon0 * self.epsilon_decay ** (e - 1))
        for b in self.buggles:
            b.reset(self.maze.start)
        if self.log:
            self.log.round_start(self)

    # One tick: every travelling buggle takes a turn, in random order. A buggle stuck
    # in mud waits instead of moving.
    def step(self) -> None:
        self.tick += 1
        order = list(self.buggles)
        self.rng.shuffle(order)
        for b in order:
            if b.status != EXPLORING:
                continue
            b.steps += 1
            if b.stuck:
                b.stuck -= 1
            else:
                self._move(b, self._choose(b))
            if b.status == EXPLORING and b.steps >= self.max_steps:
                b.status = OUT_OF_STEPS

    # ---- policy ------------------------------------------------------
    # THE RULES. Pick the buggle's next square. `options` leaves out known dead ends
    # (unless nothing else is left). `back` is the square it came from.
    def _choose(self, b: Buggle) -> Cell:
        nbrs = self.maze.neighbors(b.pos)
        dead = self.board.dead_ends
        options = [n for n in nbrs if n not in dead] or nbrs
        back = b.stack[-2] if len(b.stack) > 1 else None

        # Sometimes move at random, to stumble on routes the rules would never try.
        if self.rng.random() < self.epsilon:
            return self.rng.choice(options)

        # Rule 1: on the best known route? Take its next step.
        i = self.board.index_on_best(b.pos)
        if i is not None and i + 1 < len(self.board.best_path):
            nxt = self.board.best_path[i + 1]
            if nxt in options:
                return nxt

        # Rule 2: somewhere new this round. Rule 3 (below): head for unexplored
        # territory.
        fresh = [n for n in options if n not in b.visited]
        if fresh:
            return self.rng.choice(fresh)
        step = self._toward_frontier(b)
        if step is not None:
            return step
        if back is not None:
            return back
        return self.rng.choice(options)

    # Breadth-first search (see maze.py) through the squares this buggle has visited,
    # looking for the nearest one with a way out it has not tried. Returns the first
    # step toward it. `prev` remembers how we reached each square, so we can trace
    # back to the first step.
    def _toward_frontier(self, b: Buggle) -> Cell | None:
        """First step toward the nearest known cell with an unexplored, live exit.

        Searches only through cells this buggle has visited this episode, so it
        uses its own map plus the shared dead-end list, nothing more.
        """
        dead = self.board.dead_ends
        prev = {b.pos: None}
        q = deque([b.pos])
        while q:
            c = q.popleft()
            if c != b.pos and any(n not in b.visited and n not in dead
                                  for n in self.maze.neighbors(c)):
                while prev[c] != b.pos:
                    c = prev[c]
                return c
            for n in self.maze.neighbors(c):
                if n in b.visited and n not in prev:
                    prev[n] = c
                    q.append(n)
        return None

    # Make the move. If the buggle steps back onto its own trail, the loop it just made
    # is cut off its `stack`, so the route it posts never goes in circles.
    def _move(self, b: Buggle, nxt: Cell) -> None:
        b.pos = nxt
        b.visited.add(nxt)
        if nxt in b.stack:  # walked back onto its own trail: drop the loop
            del b.stack[b.stack.index(nxt) + 1:]
        else:
            b.stack.append(nxt)
        if nxt in self.maze.mud:
            b.stuck = self.mud_delay

        # Reached the finish: offer the route to the board.
        if nxt == self.maze.goal:
            b.status = AT_GOAL
            self.board.post_path(self.episode, self.tick, b.name, b.stack)
            return
        self._check_dead_end(b, nxt)

    # A square is a dead end if at most one way out does not lead to a known dead end.
    # Posting these one by one makes dead ends spread inward from the tips of blind
    # corridors, like water filling a channel. This never cuts the start off from the
    # finish, because a square on a route between them always has two live ways out.
    def _check_dead_end(self, b: Buggle, c: Cell) -> None:
        """A cell is a dead end if at most one non-dead neighbor leads out of it.

        Repeated pruning of such cells never cuts the start off from the goal,
        so the posted dead ends grow inward from the tips as buggles report.
        """
        if c in (self.maze.start, self.maze.goal) or c in self.board.dead_ends:
            return
        live = [n for n in self.maze.neighbors(c) if n not in self.board.dead_ends]
        if len(live) <= 1:
            self.board.post_dead_end(self.episode, self.tick, b.name, c)
