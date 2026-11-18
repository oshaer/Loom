"""Browser driver for Loom RL. Runs inside Pyodide and steps the real
`loomrl` simulation one tick at a time, so the page can animate it."""

# HOW TO READ THIS FILE
# A web page cannot run a long Python loop without freezing the browser. So
# instead of calling Simulation.run(), which runs every round at once, the page
# asks this Driver to advance a few ticks at a time, then redraws, many times a
# second. The Driver does what run() does, split into small steps.
import time

from loomrl.ascii_view import Painter
from loomrl.maze import Maze
from loomrl.runlog import RunLog
from loomrl.sim import Simulation

# Maze presets for the page: (width, height, rounds). LOG is where the log is
# written, in the browser's own temporary file space.
SIZES = {"small": (12, 8, 30), "medium": (20, 12, 50), "large": (30, 18, 80)}
LOG = "/tmp/loom.log"


# One run of Loom inside the page, with an optional naive-board comparison run.
class Driver:
    def __init__(self, size, seed, buggles, faulty, trust, compare, trails):
        w, h, rounds = SIZES[size]

        # Build a simulation; `t` says whether trust is on.
        def make(t):
            return Simulation(Maze(w, h, seed=seed), n_buggles=buggles, episodes=rounds,
                              seed=seed, trust=t, faulty=faulty, write_log=False,
                              log_path=LOG)

        self.sim = make(trust)
        self.base = make(False) if (compare and trust and faulty > 0) else None
        # Point the main run at its comparison run, open the log and write its opening.
        self.sim.baseline = self.base            # the log's intro mentions the comparison
        self.sim.log = RunLog(LOG, every=10)
        self.sim.log.header(self.sim)
        self.painter = Painter(color=True, trails=trails, values=False)
        self.t0 = time.monotonic()
        self.finished = self.base_done = self.footer_written = False
        self.sim.start_episode(1)
        if self.base:
            self.base.start_episode(1)
        else:
            self.base_done = True

    # ---- stepping ------------------------------------------------------
    # One tick of a simulation, starting the next round when one ends. Returns True
    # when the last round is over. `@staticmethod` means it needs no `self`.
    @staticmethod
    def _advance(sim):
        """One tick. Returns True when the whole run is over."""
        sim.step()
        if sim.episode_done:
            sim._end_episode()
            if sim.episode >= sim.n_episodes:
                return True
            sim.start_episode(sim.episode + 1)
        return False

    # Advance the main run by n ticks (the page chooses n from the speed setting).
    def tick(self, n=1):
        for _ in range(int(n)):
            if self.finished:
                break
            self.finished = self._advance(self.sim)
        return self.finished

    # Run to the end of the current round at once.
    def skip_round(self, limit=200000):
        start = self.sim.episode
        for _ in range(limit):
            if self.finished or self.sim.episode != start:
                break
            self.finished = self._advance(self.sim)

    # Advance the naive comparison run a little. The page calls this repeatedly after
    # the main run ends, so the browser stays responsive.
    def base_work(self, ticks=400):
        """Advance the naive comparison run a little. Returns True when done."""
        for _ in range(int(ticks)):
            if self.base_done:
                break
            self.base_done = self._advance(self.base)
        return self.base_done

    # When both runs are done, write the log's closing section.
    def finalize(self):
        if self.finished and self.base_done and not self.footer_written:
            self.sim.log.footer(self.sim, True, time.monotonic() - self.t0)
            self.sim.log.close()
            self.footer_written = True
        return self.footer_written

    def close(self):
        if not self.footer_written and self.sim.log:
            self.sim.log.close()

    # ---- what the page shows -------------------------------------------
    # What the page draws: the maze and the status panel as text with colour codes,
    # made by the same Painter the terminal uses, plus a few numbers for the status
    # line.
    def maze(self):
        return "\n".join(self.painter.maze_lines(self.sim))

    def panel(self):
        return "\n".join(self.painter.panel_lines(self.sim))

    def status(self):
        s, b = self.sim, self.base
        return {
            "round": s.episode, "rounds": s.n_episodes, "tick": s.tick,
            "finished": self.finished, "footer": self.footer_written,
            "base_round": b.episode if b else 0, "base_done": self.base_done,
            "route": s.route_turns, "fastest": s.fastest_turns,
        }

    def log_text(self):
        with open(LOG, encoding="utf-8") as f:
            return f.read()
