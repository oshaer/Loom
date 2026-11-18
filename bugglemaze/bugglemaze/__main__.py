"""Command line: python -m bugglemaze [options]"""

# HOW TO READ THIS FILE
# The program's front door: `python -m bugglemaze` runs this file. It reads the
# command-line options, builds the maze and simulation, and runs them with the
# terminal display. `python -m bugglemaze --help` lists every option.
from __future__ import annotations

import argparse
import sys

from .ascii_view import AsciiView, parse_watch
from .maze import Maze
from .sim import Simulation


# Describe every command-line option; `argparse` turns this into a --help page.
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bugglemaze",
                                description="Buggles exploring a maze with a shared bulletin board.")
    p.add_argument("--width", type=int, default=12, help="maze width in cells")
    p.add_argument("--height", type=int, default=8, help="maze height in cells")
    p.add_argument("--buggles", type=int, default=6, help="number of buggles (max 61)")
    p.add_argument("--episodes", type=int, default=8)
    p.add_argument("--max-steps", type=int, default=None,
                   help="step budget per buggle per episode (default 3 x cells)")
    p.add_argument("--epsilon", type=float, default=0.35, help="starting exploration rate")
    p.add_argument("--epsilon-decay", type=float, default=0.8, help="per-episode multiplier")
    p.add_argument("--loops", type=float, default=0.08, help="fraction of extra walls removed")
    p.add_argument("--mud", type=float, default=0.06, help="fraction of cells that are mud")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--watch", default="1,last",
                   help="episodes to animate, e.g. '1,4-6,last', 'all', 'none' (default 1,last)")
    p.add_argument("--fps", type=float, default=15.0, help="frames per second while watching")
    p.add_argument("--trails", action="store_true", help="mark cells visited this episode with ','")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--log", metavar="PATH", default=None,
                   help="log file (default logs/bugglemaze-<timestamp>.log)")
    p.add_argument("--no-color", dest="color", action="store_const", const="never")
    return p


# Build everything from the options and run it. Ctrl+C stops the run cleanly.
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    maze = Maze(args.width, args.height, seed=args.seed, loops=args.loops, mud=args.mud)
    sim = Simulation(maze, n_buggles=args.buggles, episodes=args.episodes,
                     max_steps=args.max_steps, epsilon=args.epsilon,
                     epsilon_decay=args.epsilon_decay, seed=args.seed,
                     log_path=args.log)
    view = AsciiView(watch=parse_watch(args.watch, args.episodes), fps=args.fps,
                     trails=args.trails, color=args.color)
    try:
        sim.run(view)
    except KeyboardInterrupt:
        view.restore()
        sys.stdout.write(f"\nInterrupted. Log: {sim.log_path}\n")
        return 130
    finally:
        view.restore()
    return 0


# True only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    sys.exit(main())
