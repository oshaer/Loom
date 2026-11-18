"""Loom RL: buggles learn the maze with shared, trust-weighted Q-learning.

Each buggle is an agent. Its state is the square it stands on, its actions
are the open moves from that square, and it receives a reward of -1 for
every turn it spends (mud costs extra turns, so extra negative reward).
All buggles read and write one shared blackboard, so every move any buggle
makes teaches the whole team.

Some buggles have faulty sensors and report wrong costs, imaginary finishes and
false dead ends. The team is never told which. The blackboard learns whom to
trust by checking reports against each other, and weights every report by its
author's trust. Run with trust=False to see the same team believe everything.

No rendering code here: watchers implement the Observer hooks.
"""

# HOW TO READ THIS FILE
# This file runs the experiment. Its vocabulary:
#   * round (also called an "episode" in the code, the usual word in
#     reinforcement learning): every buggle starts at the start and tries to reach
#     the finish. The board keeps what it learned from one round to the next.
#   * tick: one beat of the clock. On each tick, every buggle still travelling
#     takes one turn.
#   * epsilon: the chance that a buggle makes a random move to try something new,
#     in place of the move the board rates best. It shrinks each round, so the team
#     explores early and settles down later.
# Start with `Simulation.run` (the whole experiment), then `step` (one tick),
# then `_act` (one buggle's turn). That is the full loop.
from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass, field
from pathlib import Path

from .board import Message, QBoard
from .maze import Cell, Maze
from .runlog import RunLog, default_log_path

# The characters used to draw buggles: 1-9, then a-z, then A-Z (61 in all).
# `[1:]` means "everything from position 1 on", which skips the digit 0.
SYMBOLS = string.digits[1:] + string.ascii_lowercase + string.ascii_uppercase  # 61
EXPLORING, AT_GOAL, OUT_OF_STEPS = "exploring", "at goal", "out of turns"


# One buggle. A dataclass is a class that mainly holds data; Python writes its
# `__init__` from the fields listed. `field(default_factory=set)` gives each buggle
# its own new empty set (a plain `= set()` would make all buggles share one).
@dataclass
class Buggle:
    index: int
    name: str
    symbol: str
    pos: Cell = (0, 0)
    steps: int = 0          # turns used this round
    reward: float = 0.0     # total reward this round
    status: str = EXPLORING
    stuck: int = 0
    random_moves: int = 0
    faulty: bool = False    # bad sensors: the experimenter knows, the team does not
    visited: set[Cell] = field(default_factory=set)

    # Called at the start of every round: back to the start square, counters at zero.
    # What the buggle learned is not lost; it lives on the shared board, not here.
    def reset(self, start: Cell) -> None:
        self.pos, self.steps, self.reward, self.status = start, 0, 0.0, EXPLORING
        self.stuck = self.random_moves = 0
        self.visited = {start}


# A summary of one finished round, kept in `Simulation.history` for the log.
@dataclass
class RoundStats:
    episode: int
    epsilon: float
    ticks: int
    finished: int
    buggles: int
    avg_turns: float | None          # mean turns of buggles that finished
    best_turns: int | None           # fastest buggle this round
    route_turns: int | None          # learned route at the end of the round
    known: int
    reach: int                       # squares the learned route covers from the start
    dead_ends: int = 0               # confirmed dead-end facts on the board
    false_believed: int = 0          # of those, how many are wrong
    false_caught: int = 0            # false claims spotted and removed so far


# An Observer watches the simulation without changing it. The simulation calls
# these methods at key moments; the terminal display (ascii_view.py) and the web
# page each supply their own versions. `...` means "do nothing": these are
# empty defaults. Keeping display code out of this file means the simulation
# works the same whether anyone is watching or not.
class Observer:
    def on_start(self, sim: "Simulation") -> None: ...
    def on_episode_start(self, sim: "Simulation") -> None: ...
    def on_tick(self, sim: "Simulation") -> None: ...
    def on_episode_end(self, sim: "Simulation") -> None: ...
    def on_finish(self, sim: "Simulation") -> None: ...


# The whole experiment: a maze, a team of buggles and their shared board.
class Simulation:
    # Settings, with their defaults:
    #   alpha = learning rate; gamma = discount for future rewards (1.0 means none);
    #   mud_delay = extra turns lost in mud; trust = use trust weighting or not;
    #   faulty = how many buggles have faulty sensors; p_bad_cost, p_fake_finish and
    #   p_false_claim = how often a faulty sensor garbles each kind of report.
    def __init__(self, maze: Maze, n_buggles: int = 8, episodes: int = 60,
                 max_steps: int | None = None, epsilon: float = 0.2,
                 epsilon_decay: float = 0.93, epsilon_min: float = 0.01,
                 alpha: float = 0.5, gamma: float = 1.0, mud_delay: int = 2,
                 seed: int | None = None, log_path: str | None = None,
                 log_every: int = 10, trust: bool = True, faulty: int = 2,
                 write_log: bool = True, p_bad_cost: float = 0.6,
                 p_fake_finish: float = 0.15, p_false_claim: float = 0.1,
                 created_by: str = "Katie Dunbar",
                 created_on: str = "November 18, 1996",
                 version_note: str = "This is a version from 2026."):
        if not 1 <= n_buggles <= len(SYMBOLS):
            raise ValueError(f"buggles must be between 1 and {len(SYMBOLS)}")
        self.maze = maze
        self.mud_delay = mud_delay
        self.board = QBoard(maze, alpha, gamma, trust=trust)
        # Connect the board to the simulation: its messages go to the log, and it can
        # ask the simulation what round and tick it is.
        self.board.on_post = self._log_post
        self.board.clock = lambda: (self.episode, self.tick)
        self.trust_on = trust
        self.created_by = created_by
        self.created_on = created_on
        self.version_note = version_note
        self.write_log = write_log
        self.p_bad_cost, self.p_fake_finish = p_bad_cost, p_fake_finish
        self.p_false_claim = p_false_claim
        self.baseline: "Simulation | None" = None   # a no-trust run on the same maze, for the log
        # One random-number generator for all the buggles' choices, started from the
        # seed
        # so that a run can be repeated exactly.
        self.rng = random.Random(seed)
        self.seed = seed
        self.n_episodes = episodes
        self.max_steps = max_steps or 4 * maze.width * maze.height
        self.epsilon0, self.epsilon_decay, self.epsilon_min = epsilon, epsilon_decay, epsilon_min
        # Make the team. An f-string fills values into text: f"B{i + 1:02d}" turns
        # i = 0 into "B01" (the :02d means "at least two digits, padded with 0").
        self.buggles = [Buggle(i, f"B{i + 1:02d}", SYMBOLS[i]) for i in range(n_buggles)]
        # Choose which buggles get faulty sensors, using a separate generator seeded the
        # same way, so the same maze number always picks the same faulty buggles.
        n_faulty = max(0, min(faulty, n_buggles - 1))       # keep at least one honest buggle
        for i in sorted(random.Random(seed).sample(range(n_buggles), n_faulty)):
            self.buggles[i].faulty = True
        # The true fastest route, worked out once for judging results. The buggles never
        # see it.
        self.fastest_path, self.fastest_turns = maze.fastest_path(mud_delay)
        self.history: list[RoundStats] = []
        self.route_path: list[Cell] = []          # where the board's estimates point
        self.route_turns: int | None = None       # its cost, if it reaches the finish
        self.record_run: int | None = None
        self.episode = self.tick = 0
        self.epsilon = epsilon
        self.log_path = Path(log_path) if log_path else default_log_path()
        self.log: RunLog | None = None
        self.log_every = max(1, log_every)

    # ---- convenience -------------------------------------------------
    # A property is a method that reads like a plain value: `sim.alpha`, with no
    # brackets. These four are small conveniences.
    @property
    def alpha(self) -> float:
        return self.board.alpha

    @property
    def gamma(self) -> float:
        return self.board.gamma

    # How many buggles have reached the finish this round. `sum` of True/False values
    # counts the Trues.
    @property
    def finished(self) -> int:
        return sum(b.status == AT_GOAL for b in self.buggles)

    # The round is over when no buggle is still exploring.
    @property
    def episode_done(self) -> bool:
        return all(b.status != EXPLORING for b in self.buggles)

    # ---- main loop ---------------------------------------------------
    # THE WHOLE EXPERIMENT. For each round: reset the buggles, tick until every buggle
    # has finished or run out of turns, then record the round. `try ... finally`
    # makes sure the log is completed even if the run is stopped part-way (for
    # example by Ctrl+C); the log then says it was stopped early.
    def run(self, observer: Observer | None = None) -> None:
        obs = observer or Observer()
        if self.write_log:
            self.log = RunLog(self.log_path, every=self.log_every)
            self.log.header(self)
        t0, complete = time.monotonic(), False
        try:
            obs.on_start(self)
            for e in range(1, self.n_episodes + 1):
                self.start_episode(e)
                obs.on_episode_start(self)
                while not self.episode_done:
                    self.step()
                    obs.on_tick(self)
                self._end_episode()
                obs.on_episode_end(self)
            complete = True
            obs.on_finish(self)
        finally:
            if self.log:
                self.log.footer(self, complete, time.monotonic() - t0)
                self.log.close()

    # Begin round e. Epsilon shrinks each round: it is multiplied by epsilon_decay
    # (0.93) once per round, but never drops below epsilon_min. `**` means "to the power
    # of".
    def start_episode(self, e: int) -> None:
        self.episode, self.tick = e, 0
        self.epsilon = max(self.epsilon_min, self.epsilon0 * self.epsilon_decay ** (e - 1))
        for b in self.buggles:
            b.reset(self.maze.start)
        if self.log:
            self.log.round_start(self)

    # ONE TICK. Every travelling buggle takes a turn, in a random order so that no
    # buggle always moves first. A buggle stuck in mud spends its turn waiting.
    # A buggle that has used all its turns stops for this round.
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
                self._act(b)
            if b.status == EXPLORING and b.steps >= self.max_steps:
                b.status = OUT_OF_STEPS
        # Every 25 ticks (% gives the remainder), weigh the dead-end claims against
        # current trust again.
        if self.tick % 25 == 0:
            self.board.refresh_claims()
        self._check_route()

    # ---- one agent step ----------------------------------------------
    # ONE BUGGLE'S TURN, the basic loop of reinforcement learning:
    #   1. choose a move: usually the best the board knows, sometimes a random one;
    #   2. make it and see what it cost: -1 per turn, more in mud;
    #   3. report the result to the board, which learns from it;
    #   4. look around for dead ends.
    # This balance of trying new things and using what is known is called
    # "exploration versus exploitation".
    def _act(self, b: Buggle) -> None:
        s = b.pos
        if self.rng.random() < self.epsilon:
            a = self.rng.choice(self.board.moves(s))         # explore
            b.random_moves += 1
        else:
            a = self.board.greedy(s, self.rng)               # exploit what the team knows
        in_mud = a in self.maze.mud
        reward = -(1 + (self.mud_delay if in_mud else 0))
        finished = a == self.maze.goal
        self._report(b, s, a, reward, finished)
        b.reward += reward
        b.pos = a
        b.visited.add(a)
        if in_mud:
            b.stuck = self.mud_delay
        self._look_around(b, a)
        if finished:
            b.status = AT_GOAL
            self._finished_run(b)

    # How faulty sensors go wrong. With probability p_bad_cost the cost is misread
    # (mud as dry ground, or dry ground as mud). With probability p_fake_finish the
    # buggle reports reaching the finish when it has not. The buggle still drives
    # correctly: only what it reports is wrong. Nothing here tells the board which
    # buggles are faulty; the board has to work that out.
    def _report(self, b: Buggle, s: Cell, a: Cell, reward: int, finished: bool) -> None:
        """Tell the board what the move cost. Faulty sensors garble the report."""
        if b.faulty:
            if self.rng.random() < self.p_bad_cost:
                reward = -1 if reward < -1 else -(1 + self.mud_delay)   # mud seen as dry, or dry as mud
            if not finished and self.rng.random() < self.p_fake_finish:
                finished = True                                          # an imaginary finish line
        self.board.report(b.name, s, a, reward, finished)

    # Facts. An honest buggle on a square with only one way out claims a dead end. A
    # faulty one sometimes claims a dead end where there is none. Then the buggle
    # checks any existing claim about the square it is standing on.
    def _look_around(self, b: Buggle, c: Cell) -> None:
        """Post or check dead-end facts about the square the buggle stands on."""
        exits = len(self.maze.neighbors(c))
        if b.faulty:
            if exits > 1 and self.rng.random() < self.p_false_claim:
                self.board.claim_dead_end(b.name, c)                    # a false fact
        elif exits == 1:
            self.board.claim_dead_end(b.name, c)
        self.board.check_square(b.name, c)

    # A buggle reached the finish. Post news if it was the first ever, or a record.
    def _finished_run(self, b: Buggle) -> None:
        turns = b.steps
        if self.record_run is None:
            self.record_run = turns
            self.board.post(Message(self.episode, self.tick, b.name, "FIRST_FINISH", turns))
        elif turns < self.record_run:
            self.record_run = turns
            self.board.post(Message(self.episode, self.tick, b.name, "RECORD_RUN", turns))

    # After every tick, read off the route the board's estimates point to, and post
    # news if it beats every earlier one.
    def _check_route(self) -> None:
        """Post when the route the team's values point to beats every earlier one.

        The learned route can wobble while values are still settling; only new
        bests are news.
        """
        self.route_path, self.route_turns = self.board.learned_route(self.mud_delay)
        turns = self.route_turns
        if turns is None:
            return
        if self.best_route is not None and turns >= self.best_route:
            return
        if turns == self.fastest_turns:
            kind = "ROUTE_OPTIMAL"
            self.first_optimal = self.episode
        elif self.best_route is None:
            kind = "ROUTE_LEARNED"
        else:
            kind = "ROUTE_IMPROVED"
        self.best_route = turns
        self.board.post(Message(self.episode, self.tick, "team", kind, turns))

    # Class-level defaults, shared until a simulation sets its own value.
    best_route: int | None = None
    first_optimal: int | None = None      # round in which the fastest route was first learned

    # Close a round: weigh the claims again, then save a summary for the log.
    def _end_episode(self) -> None:
        self.board.refresh_claims()
        done = [b.steps for b in self.buggles if b.status == AT_GOAL]
        self.history.append(RoundStats(
            episode=self.episode, epsilon=self.epsilon, ticks=self.tick,
            finished=len(done), buggles=len(self.buggles),
            avg_turns=sum(done) / len(done) if done else None,
            best_turns=min(done) if done else None,
            route_turns=self.route_turns, known=len(self.board.known),
            reach=len(self.route_path), dead_ends=len(self.board.dead_ends),
            false_believed=len(self.board.false_accepted),
            false_caught=self.board.false_caught))
        if self.log:
            self.log.round_end(self)

    # Pass each board message to the log, if there is one.
    def _log_post(self, msg: Message) -> None:
        if self.log:
            self.log.post(self, msg)
