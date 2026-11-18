"""Grid maze: generation, passages, mud, and true shortest path."""

# HOW TO READ THIS FILE
# This file builds the maze and answers questions about it: which squares are
# next to each other, where the walls are, and what the shortest route is.
#
# A few words used everywhere in Loom:
#   * A "cell" or "square" is one position in the grid, written as a pair of
#     numbers (x, y). x counts columns from the left, y counts rows from the top,
#     and both start at 0. So (0, 0) is the top-left corner.
#   * Two neighbouring cells are "passable" when there is no wall between them.
#
# The line below lets us write type hints such as `int | None` (meaning "an int,
# or nothing") on older versions of Python. Type hints are notes for readers and
# tools; Python itself does not enforce them.
from __future__ import annotations

# `random` makes random choices. `deque` (say "deck") is a list that is quick to
# add to and take from at both ends, which is exactly what a search queue needs.
import random
from collections import deque

# A type alias: from here on, `Cell` is simply a shorter name for "a pair of ints".
Cell = tuple[int, int]  # (x, y)


# A class bundles data with the functions that work on that data. Writing
# `m = Maze(12, 8)` builds one maze object, and `m.neighbors(...)` asks it a
# question. Functions that belong to a class are called methods; their first
# parameter, `self`, is the object itself.
class Maze:
    # `__init__` runs once, when a maze is created. The `seed` decides every random
    # choice, so the same seed always gives the same maze. `loops` is the share of
    # extra walls knocked down to create alternative routes, and `mud` is the share
    # of squares that are muddy.
    def __init__(self, width: int, height: int, seed: int | None = None,
                 loops: float = 0.10, mud: float = 0.08):
        if width < 2 or height < 2:
            raise ValueError("maze must be at least 2x2")
        self.width, self.height = width, height
        # Our own random-number generator, started from the seed, so mazes can be
        # repeated.
        self.rng = random.Random(seed)
        self.start: Cell = (0, 0)
        self.goal: Cell = (width - 1, height - 1)
        # The maze is stored as the set of open passages. Each passage is a frozenset
        # holding the two cells it joins. A set is a collection with no repeats where
        # checking "is this in it?" is very fast. We use frozenset (an unchangeable set)
        # so that the passage from A to B and from B to A count as the same passage.
        # A leading underscore, as in `_open`, is a convention meaning "internal: other
        # files should not need this".
        self._open: set[frozenset] = set()
        self._carve()
        self._add_loops(loops)
        self.mud: set[Cell] = self._place_mud(mud)

    # ---- structure -------------------------------------------------
    # True if the cell lies inside the grid.
    def in_bounds(self, c: Cell) -> bool:
        return 0 <= c[0] < self.width and 0 <= c[1] < self.height

    # Every cell, one row at a time. `yield` makes this a generator: it hands back
    # one cell each time a loop asks for the next, without building a list first.
    def cells(self):
        for y in range(self.height):
            for x in range(self.width):
                yield (x, y)

    # The up-to-four cells beside `c` (right, left, below, above), walls or not.
    # The square brackets at the end are a "list comprehension": a compact way to
    # build a list by keeping only the candidates that pass a test.
    def _adjacent(self, c: Cell) -> list[Cell]:
        x, y = c
        cand = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [n for n in cand if self.in_bounds(n)]

    # Is there an open passage between a and b?
    def passable(self, a: Cell, b: Cell) -> bool:
        return frozenset((a, b)) in self._open

    # The cells a buggle can actually move to from `c`: adjacent and not walled off.
    def neighbors(self, c: Cell) -> list[Cell]:
        return [n for n in self._adjacent(c) if self.passable(c, n)]

    # ---- generation ------------------------------------------------
    # MAZE GENERATION, step 1: the "recursive backtracker".
    # Start with every wall in place. Walk from the start, each time knocking down
    # the wall to a random neighbour we have never visited. When we get stuck, step
    # back along our path (the stack) until we find a cell with an unvisited
    # neighbour, and carry on. When the stack is empty, every cell has been reached.
    # The result is a "perfect" maze: exactly one route between any two cells.
    def _carve(self) -> None:
        """Iterative recursive-backtracker: a perfect maze."""
        # `seen` holds the cells visited so far; `stack` is the path we are on. We only
        # ever look at its top item, stack[-1] (index -1 means "the last one").
        seen = {self.start}
        stack = [self.start]
        while stack:
            c = stack[-1]
            # Neighbours we have not visited yet. If there are none, step back (pop).
            fresh = [n for n in self._adjacent(c) if n not in seen]
            if not fresh:
                stack.pop()
                continue
            n = self.rng.choice(fresh)
            self._open.add(frozenset((c, n)))
            seen.add(n)
            stack.append(n)

    # MAZE GENERATION, step 2: a perfect maze has only one route, which leaves
    # nothing to learn about choosing well. So we knock down a few extra walls,
    # chosen at random, to create loops and shortcuts that are worth discovering.
    def _add_loops(self, fraction: float) -> None:
        """Knock out some extra walls so shorter routes exist to be discovered."""
        walls = []
        for c in self.cells():
            # Looking only right and down visits each wall exactly once.
            for n in ((c[0] + 1, c[1]), (c[0], c[1] + 1)):
                if self.in_bounds(n) and not self.passable(c, n):
                    walls.append((c, n))
        # Shuffle the remaining walls, then remove the first `fraction` of them.
        self.rng.shuffle(walls)
        for a, b in walls[: int(len(walls) * fraction)]:
            self._open.add(frozenset((a, b)))

    # Pick random squares to be mud, never the start or the finish.
    def _place_mud(self, fraction: float) -> set[Cell]:
        pool = [c for c in self.cells() if c not in (self.start, self.goal)]
        return set(self.rng.sample(pool, int(len(pool) * fraction)))

    # ---- analysis --------------------------------------------------
    # BREADTH-FIRST SEARCH (BFS): the classic way to find the route with the fewest
    # moves. Explore outward from the start one step at a time, like a ripple in a
    # pond, using a queue (first in, first out). The first time the ripple reaches
    # the goal, it has done so by the shortest route. `prev` remembers which cell we
    # came from, so at the end we can walk backward from the goal to rebuild the route.
    # The buggles never see this answer; it is only used to judge how well they learn.
    def shortest_path(self) -> list[Cell]:
        """BFS shortest path (in moves) from start to goal."""
        prev = {self.start: None}
        q = deque([self.start])
        while q:
            c = q.popleft()
            if c == self.goal:
                break
            for n in self.neighbors(c):
                if n not in prev:
                    prev[n] = c
                    q.append(n)
        # Rebuild the route: follow `prev` from the goal back to the start, then reverse
        # it.
        path, c = [], self.goal
        while c is not None:
            path.append(c)
            c = prev[c]
        return path[::-1]

    # DIJKSTRA'S ALGORITHM: like breadth-first search, but for routes whose steps
    # have different costs. Mud costs extra turns, so the fastest route may avoid mud
    # even if it takes more steps. A "heap" is a queue that always hands back the
    # cheapest item first, so we always extend the cheapest route found so far.
    # Returns the route and its cost in turns.
    def fastest_path(self, mud_delay: int) -> tuple[list[Cell], int]:
        """Dijkstra in turns: entering a mud cell costs 1 + mud_delay turns."""
        import heapq
        dist = {self.start: 0}
        prev: dict = {self.start: None}
        heap = [(0, self.start)]
        while heap:
            d, c = heapq.heappop(heap)
            if c == self.goal:
                break
            if d > dist[c]:
                continue
            for n in self.neighbors(c):
                # The cost of reaching neighbour n through c. If that beats the best we
                # knew, keep it.
                nd = d + 1 + (mud_delay if n in self.mud else 0)
                if nd < dist.get(n, 1 << 30):
                    dist[n], prev[n] = nd, c
                    heapq.heappush(heap, (nd, n))
        path, c = [], self.goal
        while c is not None:
            path.append(c)
            c = prev[c]
        return path[::-1], dist[self.goal]
