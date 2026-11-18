"""Shared bulletin board: dead ends and the best known path."""

# HOW TO READ THIS FILE
# In this first version of Loom, the buggles share a simple bulletin board. It
# holds two kinds of knowledge: squares known to be dead ends, and the shortest
# complete route anyone has found so far. Every post is kept as a message, which
# is how the log knows what happened. There is no learning and no trust here; that
# comes in version 2 (loomrl).
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .maze import Cell


# One post on the board. `@dataclass` makes Python write the `__init__` for us;
# `frozen=True` means a message cannot be changed after it is made.
@dataclass(frozen=True)
class Message:
    episode: int
    tick: int
    author: str
    kind: str
    detail: str

    # How a message prints, such as "t214 B04 posted BETTER_PATH len=88".
    def __str__(self) -> str:
        return f"t{self.tick} {self.author} posted {self.kind} {self.detail}"


# The shared board. `dead_ends` is a set of squares; `best_path` is a list of
# squares from start to finish. `on_post` lets the simulation hear every new
# post, so nothing is lost when old messages fall off the end of `messages`.
class BulletinBoard:
    def __init__(self, history: int = 500, on_post=None):
        self.dead_ends: set[Cell] = set()
        self.best_path: list[Cell] = []
        self._best_index: dict[Cell, int] = {}
        self.messages: deque[Message] = deque(maxlen=history)
        self.on_post = on_post  # called with every Message, so nothing is lost to maxlen

    def _post(self, msg: Message) -> None:
        self.messages.append(msg)
        if self.on_post:
            self.on_post(msg)

    # The length of the best route, in moves, or None if no one has finished yet.
    @property
    def best_len(self) -> int | None:
        return len(self.best_path) - 1 if self.best_path else None

    # Where square c sits on the best route (0 is the start), or None if it is not
    # on it. A dict lookup makes this fast.
    def index_on_best(self, c: Cell) -> int | None:
        return self._best_index.get(c)

    # Record a dead end, unless it is already known. Returns True if it was news.
    def post_dead_end(self, episode: int, tick: int, author: str, c: Cell) -> bool:
        if c in self.dead_ends:
            return False
        self.dead_ends.add(c)
        self._post(Message(episode, tick, author, "DEAD_END", f"({c[0]},{c[1]})"))
        return True

    # Offer a route to the finish. It replaces the best route only if it is shorter.
    def post_path(self, episode: int, tick: int, author: str, path: list[Cell]) -> bool:
        """Accept a start-to-goal path if it beats the current best."""
        if self.best_path and len(path) >= len(self.best_path):
            return False
        self.best_path = list(path)
        self._best_index = {c: i for i, c in enumerate(self.best_path)}
        self._post(Message(episode, tick, author, "BETTER_PATH", f"len={len(path) - 1}"))
        return True

    def recent(self, n: int = 6) -> list[Message]:
        return list(self.messages)[-n:]
