"""The shared blackboard: learned estimates, facts, and trust, side by side.

Three kinds of knowledge live here, in the spirit of a blackboard system:

* Estimates. Q[(square, next_square)] is the team's estimate of the reward still
  to come after that move. With -1 per turn and no discount, that is minus the
  turns to the finish.
* Facts. Buggles post symbolic claims such as "this square is a dead end".
  A claim only counts once buggles the team trusts back it, and anyone who
  stands on the square can check it.
* Trust. Every report is compared with what others reported for the same move.
  Agreement raises the author's trust, disagreement lowers it, and each report
  moves the estimates in proportion to how much its author is trusted.

With trust switched off the board is naive: every report counts in full and
every claim is believed at once. A claim is still deleted when someone sees it
is wrong, but nobody keeps score of who has been wrong before. That is the
baseline the trust-weighted version is compared against.
"""

# HOW TO READ THIS FILE
# This is the heart of Katie's idea. The "board" is what every buggle shares.
# Reading order that works well:
#   1. `report`  - what happens when a buggle says "I made this move, it cost this".
#   2. `trust` and `_judge` - how the team decides whom to believe.
#   3. `claim_dead_end` and `check_square` - facts, and how false ones get caught.
#   4. `learned_route` - reading off what the team has learned.
#
# Two terms from reinforcement learning:
#   * Q-value: a number for each (square, move) pair, the team's current estimate
#     of the reward still to come after making that move. Every turn costs -1, so a
#     Q-value of -40 means "about 40 turns from here to the finish".
#   * Learning rate (alpha): how far one new piece of evidence moves an estimate.
#     0.5 means "move halfway from the old estimate toward the new evidence".
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from .maze import Cell, Maze

# Settings that shape trust. Names in CAPITALS are constants: values that never
# change while the program runs.
#   TRUST_PRIOR: every buggle starts as if it had 6 reports that matched and 3 that
#     did not, so its trust begins at 6 / (6 + 3), about 67%. Starting in the
#     middle means one early mistake cannot sink a buggle's reputation.
#   CONFIRM_WEIGHT: how much trusted support a claim needs before it counts as fact.
#   LOST / REGAINED: the trust levels at which the log announces a change. Having
#     two thresholds stops a buggle hovering near 50% from flickering in and out.
TRUST_PRIOR = (6, 3)          # start each buggle at 2/3: the benefit of the doubt
MIN_EVIDENCE = 20             # checked reports needed before announcing a change in trust
CONFIRM_WEIGHT = 0.75         # trusted support needed before a claim counts as fact
LOST, REGAINED = 0.5, 0.6     # thresholds for announcing a change in trust


# A Message is one post on the notice board, such as "Buggle 3 set a record".
# `@dataclass` is a shortcut: Python writes the `__init__` method for us from the
# list of fields below. `frozen=True` means a message cannot be changed once
# made, which suits a record of something that happened.
@dataclass(frozen=True)
class Message:
    episode: int
    tick: int
    author: str          # "B04" or "team"
    kind: str
    turns: int = 0       # a number that goes with the message, if any
    detail: str = ""     # extra words for the log

    # The one-line version shown in the terminal's notice-board panel.
    def short(self) -> str:
        who = "team" if self.author == "team" else f"Buggle {int(self.author[1:])}"
        text = {
            "FIRST_FINISH": f"{who} finished first, {self.turns} turns",
            "RECORD_RUN": f"{who} record trip, {self.turns} turns",
            "ROUTE_LEARNED": f"route learned, {self.turns} turns",
            "ROUTE_IMPROVED": f"route improved, {self.turns} turns",
            "ROUTE_OPTIMAL": f"route is fastest possible, {self.turns}",
            "TRUST_LOST": f"team stopped trusting {who} ({self.turns}%)",
            "TRUST_REGAINED": f"team trusts {who} again ({self.turns}%)",
            "FALSE_CLAIM": f"{who}'s false dead end caught",
        }[self.kind]
        return f"r{self.episode} t{self.tick} {text}"


# The shared blackboard. It holds three kinds of knowledge side by side:
#   estimates (Q-values), facts (dead-end claims), and trust (each buggle's record).
class QBoard:
    def __init__(self, maze: Maze, alpha: float, gamma: float, trust: bool = True,
                 history: int = 5000):
        self.maze = maze
        self.alpha, self.gamma = alpha, gamma
        self.trust_on = trust
        # A dict ("dictionary") maps keys to values. Here the key is (square, next
        # square)
        # and the value is the Q-value. Moves nobody has tried are simply missing, and a
        # missing move counts as 0: the most hopeful possible estimate ("zero turns to
        # go").
        # Since every tried move scores below 0, buggles are drawn toward untried moves.
        # This trick is called optimism in the face of uncertainty.
        self.q: dict[tuple[Cell, Cell], float] = {}   # missing entries are 0: optimistic
        self.known: set[Cell] = set()
        self.updates = 0
        # reports: each buggle's latest account of each move (cost, ends the trip?)
        # For each move, each buggle's latest account of it: (cost, did it end the
        # trip?).
        # One entry per buggle, so repeating a report cannot add votes.
        self.votes: dict[tuple[Cell, Cell], dict[str, tuple[int, bool]]] = {}
        self.record: dict[str, list[int]] = {}         # author -> [agree, disagree]
        self.distrusted: set[str] = set()
        # facts
        # Facts. `claims` maps a square to the set of buggles saying it is a dead end;
        # `dead_ends` holds the claims the team currently believes.
        self.claims: dict[Cell, set[str]] = {}         # square -> buggles claiming dead end
        self.dead_ends: set[Cell] = set()              # confirmed claims
        self.false_caught = 0
        self.false_accepted: set[Cell] = set()         # wrong claims the board believed
        # The notice board's message history. With `maxlen`, the oldest messages fall
        # off
        # the end automatically once it is full.
        self.messages: deque[Message] = deque(maxlen=history)
        self.on_post = None
        # `lambda` makes a tiny function on the spot. The simulation replaces this one
        # with a function that returns the current (round, tick), so messages can be
        # dated.
        self.clock = lambda: (0, 0)                    # (episode, tick), set by the simulation

    # ---- trust -------------------------------------------------------
    # TRUST, as a number between 0 and 1. It is the share of a buggle's checked
    # reports that matched what others saw, with the starting "benefit of the doubt"
    # (TRUST_PRIOR) added in. A buggle with 90 matches and 10 clashes has trust
    # (90 + 6) / (100 + 9), about 88%. With trust switched off, everyone counts fully.
    def trust(self, author: str) -> float:
        if not self.trust_on:
            return 1.0
        a, d = self.record.get(author, (0, 0))
        return (a + TRUST_PRIOR[0]) / (a + d + TRUST_PRIOR[0] + TRUST_PRIOR[1])

    # How much one report counts. Squaring trust makes doubt bite harder: a buggle at
    # 50% trust carries a quarter of the weight of a fully trusted one, and at 30%,
    # less than a tenth.
    def weight(self, author: str) -> float:
        """How much one report moves the estimates. Squaring makes doubt bite."""
        return self.trust(author) ** 2

    # (matches, total checked) for the log.
    def agreement(self, author: str) -> tuple[int, int]:
        a, d = self.record.get(author, (0, 0))
        return a, a + d

    # Record one check of a buggle's report, matched or not, and post a message if
    # that pushes its trust across a threshold. `setdefault` fetches the buggle's
    # [matches, clashes] list, creating [0, 0] the first time we see that buggle.
    def _judge(self, author: str, agreed: bool) -> None:
        if not self.trust_on:
            return
        rec = self.record.setdefault(author, [0, 0])
        rec[0 if agreed else 1] += 1
        t = self.trust(author)
        agree, total = rec[0], rec[0] + rec[1]
        detail = f"{agree} of {total}"
        # Do not announce anything on thin evidence.
        if total < MIN_EVIDENCE:
            return
        if t < LOST and author not in self.distrusted:
            self.distrusted.add(author)
            self._post(author, "TRUST_LOST", round(t * 100), detail)
        elif t > REGAINED and author in self.distrusted:
            self.distrusted.discard(author)
            self._post(author, "TRUST_REGAINED", round(t * 100), detail)

    # ---- estimates -----------------------------------------------------
    # The Q-value of moving from square s to square a. Missing means untried, so 0.
    def Q(self, s: Cell, a: Cell) -> float:
        return self.q.get((s, a), 0.0)

    # Facts shape behaviour here: a square the team believes is a dead end is
    # skipped, unless it is the finish or there is no other way to go.
    def moves(self, s: Cell) -> list[Cell]:
        """Open moves, minus confirmed dead ends (unless that is all there is)."""
        nbrs = self.maze.neighbors(s)
        keep = [a for a in nbrs if a not in self.dead_ends or a == self.maze.goal]
        return keep or nbrs

    # The value of a square: the Q-value of the best move out of it. At the finish
    # nothing is left to pay, so it is 0.
    def value(self, s: Cell) -> float:
        if s == self.maze.goal:
            return 0.0
        return max(self.Q(s, a) for a in self.moves(s))

    # THE CORE OF LOOM: one buggle reports one move, and the whole team learns from it.
    #   s      = the square it moved from
    #   a      = the square it moved to
    #   reward = what the move cost (-1, or -3 if it drove into mud)
    #   terminal = whether it says the move reached the finish
    # A faulty buggle may garble `reward` and `terminal`. The board cannot tell
    # directly, so it compares the report with what other buggles said about the
    # same move.
    def report(self, author: str, s: Cell, a: Cell, reward: int, terminal: bool) -> None:
        """A buggle reports what one move cost. Check it, then learn from it."""
        # Step 1, CHECK: find what the others reported for this move, weighted by their
        # trust, and judge this report against it.
        key, claim = (s, a), (reward, terminal)
        box = self.votes.setdefault(key, {})
        consensus, backing = self._consensus(box, exclude=author)
        if consensus is not None:
            self._judge(author, claim == consensus)
        # Step 2, REMEMBER this buggle's account (replacing its earlier one).
        box[author] = claim

        # When buggles the team trusts have already seen this move, learn from what
        # they saw; a report that contradicts them is set aside.
        if (self.trust_on and consensus is not None and backing >= CONFIRM_WEIGHT
                and claim != consensus):
            reward, terminal = consensus
            step = self.alpha
        else:
            step = self.alpha * self.weight(author)
        # Step 3, LEARN: the Q-learning update (Watkins and Dayan, 1992).
        #   target = reward now + value of the square we landed on
        #   new estimate = old + step * (target - old)
        # The gap (target - old) is how surprised we are. `step` is the learning rate,
        # scaled down for buggles the team does not trust, so a distrusted buggle can
        # still speak but the board barely moves. `gamma` discounts the future; Loom
        # uses 1.0, so a value is simply minus the turns left.
        future = 0.0 if terminal else self.value(a)
        old = self.Q(s, a)
        self.q[key] = old + step * (reward + self.gamma * future - old)
        self.known.add(s)
        self.updates += 1

    # Add up the trust behind each different account of a move, leaving out one buggle
    # (the one being judged, so it cannot agree with itself). Returns the account with
    # the most support and how much support it has.
    def _consensus(self, box: dict, exclude: str):
        """The account of a move with the most trusted support, ignoring one author."""
        tally: dict[tuple[int, bool], float] = {}
        for who, claim in box.items():
            if who != exclude:
                tally[claim] = tally.get(claim, 0.0) + self.weight(who)
        if not tally:
            return None, 0.0
        best = max(tally, key=tally.get)
        return best, tally[best]

    # Pick the move with the best Q-value. If several tie, pick one of them at random.
    def greedy(self, s: Cell, rng: random.Random) -> Cell:
        moves = self.moves(s)
        best = max(self.Q(s, a) for a in moves)
        return rng.choice([a for a in moves if self.Q(s, a) == best])

    # ---- facts -----------------------------------------------------------
    # FACTS: a buggle claims square c is a dead end. Whether the team believes it
    # depends on who backs the claim (see `_refresh`).
    def claim_dead_end(self, author: str, c: Cell) -> None:
        if c in (self.maze.start, self.maze.goal):
            return
        backers = self.claims.setdefault(c, set())
        if author in backers:
            return
        backers.add(author)
        self._refresh(c)

    # Seeing is believing: a trusted buggle standing on a claimed square counts the
    # ways out for itself. A true dead end has exactly one. If the claim was right,
    # its backers gain trust; if wrong, the claim is removed and each backer is
    # judged wrong twice, because a false fact misleads more than one bad number.
    def check_square(self, viewer: str, c: Cell) -> None:
        """A buggle standing on a claimed square sees for itself how many ways out it has."""
        if c not in self.claims:
            return
        if self.trust_on and self.trust(viewer) < REGAINED:
            return                               # the team only takes the word of trusted eyes
        true_dead_end = len(self.maze.neighbors(c)) == 1 and c not in (self.maze.start,
                                                                         self.maze.goal)
        backers = [b for b in self.claims[c] if b != viewer]
        if true_dead_end:
            for b in backers:
                self._judge(b, True)
            return
        was_fact = c in self.dead_ends
        del self.claims[c]
        self.dead_ends.discard(c)
        self.false_accepted.discard(c)
        self.false_caught += 1
        for b in backers:
            self._judge(b, False)
            self._judge(b, False)        # a false fact is a worse error than a bad number
        if was_fact:                         # only news if the team had believed it
            for b in backers:
                self._post(b, "FALSE_CLAIM", 1, f"row {c[1] + 1}, column {c[0] + 1}|{viewer}")

    # Believe a claim once the squared trust of its backers adds up to CONFIRM_WEIGHT.
    # One fully trusted buggle is enough; a distrusted one is not. Without trust,
    # every claim is believed at once. A believed claim is dropped again if its
    # backers lose the team's trust.
    def _refresh(self, c: Cell) -> None:
        backing = sum(self.trust(b) ** 2 for b in self.claims.get(c, ()))
        if backing >= CONFIRM_WEIGHT or not self.trust_on:
            if c not in self.dead_ends:
                self.dead_ends.add(c)
                if len(self.maze.neighbors(c)) > 1:
                    self.false_accepted.add(c)
        elif c in self.dead_ends:            # its backers are no longer trusted enough
            self.dead_ends.discard(c)
            self.false_accepted.discard(c)

    # Trust changes over time, so every claim is weighed again now and then.
    def refresh_claims(self) -> None:
        """Re-weigh every claim against current trust. Called now and then, not every move."""
        for c in list(self.claims):
            self._refresh(c)

    # ---- what the team has learned -----------------------------------
    # What has the team learned? Start at the start and keep taking the best-rated
    # move among those someone has actually tried. If that reaches the finish, it is
    # the learned route. If it runs out of tried moves, or goes in a circle, the
    # estimates do not yet point all the way.
    # The `key=lambda ...` tells max() how to rank moves: by Q-value first, then by
    # position, so that ties are broken the same way every time.
    def learned_route(self, mud_delay: int) -> tuple[list[Cell], int | None]:
        """Follow the best tried move from the start.

        Returns the path and its cost in turns. The cost is None when the path
        stops short of the finish.
        """
        m = self.maze
        path, seen, c = [m.start], {m.start}, m.start
        while c != m.goal:
            tried = [a for a in self.moves(c) if (c, a) in self.q]
            if not tried:
                return path, None
            nxt = max(tried, key=lambda a: (self.q[(c, a)], -a[1], -a[0]))
            if nxt in seen:
                return path, None
            path.append(nxt)
            seen.add(nxt)
            c = nxt
        turns = sum(1 + (mud_delay if c in m.mud else 0) for c in path[1:])
        return path, turns

    # ---- message feed --------------------------------------------------
    # The notice board. `on_post` lets the simulation listen in, which is how
    # messages reach the log.
    def _post(self, author: str, kind: str, turns: int = 0, detail: str = "") -> None:
        e, t = self.clock()
        self.post(Message(e, t, author, kind, turns, detail))

    def post(self, msg: Message) -> None:
        self.messages.append(msg)
        if self.on_post:
            self.on_post(msg)

    def recent(self, n: int = 6) -> list[Message]:
        return list(self.messages)[-n:]
