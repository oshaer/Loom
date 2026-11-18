"""Command line: python -m loomrl [options]"""

# HOW TO READ THIS FILE
# This is the program's front door. `python -m loomrl` runs the file named
# __main__.py inside the loomrl folder, which reads the options typed on the
# command line, builds a maze and a simulation, and runs them with the terminal
# display. Type `python -m loomrl --help` to see every option.
from __future__ import annotations

import argparse
import os
import random
import sys

from .ascii_view import AsciiView, parse_watch
from .logview import latest_log, offer, show
from .maze import Maze
from .sim import Simulation

# width, height, default rounds. Bigger mazes need more rounds to learn.
# The maze presets. Each size maps to (width, height, number of rounds).
SIZES = {
    "small": (12, 8, 30),
    "medium": (20, 12, 50),
    "large": (30, 18, 80),
    "huge": (48, 24, 150),
}


# Describe every command-line option. `argparse` turns this description into
# working options and a --help page.
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loomrl",
                                description="Loom RL: buggles learn a maze with shared Q-learning.")
    p.add_argument("--size", choices=SIZES, default="large",
                   help="maze preset: small 12x8, medium 20x12, large 30x18 (default), huge 48x24")
    p.add_argument("--width", type=int, help="override the preset width")
    p.add_argument("--height", type=int, help="override the preset height")
    p.add_argument("--buggles", type=int, default=8, help="number of buggles (max 61)")
    p.add_argument("--faulty", type=int, default=2,
                   help="how many buggles have faulty sensors (default 2; the team isn't told which)")
    p.add_argument("--no-trust", dest="trust", action="store_false",
                   help="naive board: every report counts in full, every claim is believed")
    p.add_argument("--no-compare", dest="compare", action="store_false",
                   help="skip the comparison run on a naive board (it adds a few seconds)")
    p.add_argument("--episodes", "--rounds", dest="episodes", type=int,
                   help="number of rounds (default depends on --size)")
    p.add_argument("--max-steps", type=int, help="turn limit per round (default 4 x squares)")
    p.add_argument("--epsilon", type=float, default=0.2, help="starting share of random moves")
    p.add_argument("--epsilon-decay", type=float, default=0.93, help="per-round multiplier")
    p.add_argument("--alpha", type=float, default=0.5, help="learning rate")
    p.add_argument("--gamma", type=float, default=1.0, help="discount factor")
    p.add_argument("--loops", type=float, default=0.10, help="share of extra walls removed")
    p.add_argument("--mud", type=float, default=0.08, help="share of squares that are mud")
    p.add_argument("--seed", type=int)
    p.add_argument("--watch", default="1,last",
                   help="rounds to animate, e.g. '1,10,last', 'all', 'none' (default 1,last)")
    p.add_argument("--speed", type=float, default=60.0,
                   help="ticks per second while watching (screen redraws at most 30 times/s)")
    p.add_argument("--trails", action="store_true", help="mark squares visited this round")
    p.add_argument("--values", action="store_true",
                   help="shade squares by the board's estimate of turns to the finish")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--no-color", dest="color", action="store_const", const="never")
    p.add_argument("--created-by", default="Katie Dunbar", metavar="NAME",
                   help="name shown in the log header (default: Katie Dunbar)")
    p.add_argument("--created-on", default="November 18, 1996", metavar="DATE",
                   help="creation date shown in the log header (default: November 18, 1996)")
    p.add_argument("--version-note", default="This is a version from 2026.", metavar="TEXT",
                   help="line shown under the creation line ('' to leave it out)")
    p.add_argument("--log-every", type=int, default=10, metavar="N",
                   help="summarise the log in groups of N rounds (default 10; 1 = every round)")
    # Two ways to read a log in the terminal (see logview.py). nargs="?" makes the
    # PATH optional: --view-log on its own means "the most recent log".
    p.add_argument("--view-log", nargs="?", const="latest", metavar="PATH",
                   help="show a log and exit: the most recent one, or the file given")
    p.add_argument("--show-log", action="store_true",
                   help="show this run's log as soon as the run ends")
    p.add_argument("--log", metavar="PATH", help="log file (default logs/loomrl-<timestamp>.log)")
    return p


# Run the program. A maze number (seed) is picked at random if none was given, so
# every run is different but can still be repeated from the number in its log.
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # --view-log: read an existing log and stop; no simulation is run.
    if args.view_log:
        path = latest_log() if args.view_log == "latest" else args.view_log
        if path is None or not os.path.exists(path):
            print("No log found. Logs are saved in the logs/ folder of the folder you run from.",
                  file=sys.stderr)
            return 1
        show(path)
        return 0
    w, h, rounds = SIZES[args.size]
    width, height = args.width or w, args.height or h
    episodes = args.episodes or rounds
    seed = args.seed if args.seed is not None else random.randrange(1, 10**6)

    # Build one simulation with these settings. It is called twice when comparing:
    # once with trust, and once for the naive board, on the same maze.
    def make(trust: bool, write_log: bool) -> Simulation:
        maze = Maze(width, height, seed=seed, loops=args.loops, mud=args.mud)
        return Simulation(maze, n_buggles=args.buggles, episodes=episodes,
                          max_steps=args.max_steps, epsilon=args.epsilon,
                          epsilon_decay=args.epsilon_decay, alpha=args.alpha,
                          gamma=args.gamma, seed=seed, log_path=args.log,
                          log_every=args.log_every, trust=trust, faulty=args.faulty,
                          write_log=write_log, created_by=args.created_by,
                          created_on=args.created_on, version_note=args.version_note)

    sim = make(args.trust, write_log=True)
    # The comparison run goes first, quietly, so its results are ready for the log
    # of the main run.
    if args.compare and args.trust and args.faulty > 0:
        if sys.stdout.isatty():
            print("Running the comparison on a naive board first (no animation)...",
                  flush=True)
        baseline = make(False, write_log=False)
        try:
            baseline.run()
        except KeyboardInterrupt:
            sys.stdout.write("\nInterrupted.\n")
            return 130
        sim.baseline = baseline
    view = AsciiView(watch=parse_watch(args.watch, episodes), speed=args.speed,
                     trails=args.trails, values=args.values, color=args.color)
    try:
        sim.run(view)
    except KeyboardInterrupt:
        view.restore()
        sys.stdout.write(f"\nInterrupted. Log: {sim.log_path}\n")
        return 130
    finally:
        view.restore()
    # The run is over: show its log at once (--show-log), or offer to.
    if args.show_log:
        show(sim.log_path)
    else:
        offer(sim.log_path)
    return 0


# This line is true only when the file is run directly, not when it is imported.
if __name__ == "__main__":
    sys.exit(main())
