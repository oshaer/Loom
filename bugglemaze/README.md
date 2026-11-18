# bugglemaze

Buggles explore a maze and share what they learn on a bulletin board
(dead ends, best path so far). Python 3.10+, standard library only.

```
python -m bugglemaze                         # 12x8 maze, 6 buggles, 8 episodes, watch 1 and last
python -m bugglemaze --watch all --trails --fps 25
python -m bugglemaze --width 20 --height 10 --buggles 12 --episodes 15 --watch 1,8-9,last
python -m bugglemaze --seed 7 | cat          # not a terminal: final snapshot only
```

Every run writes a log to `logs/bugglemaze-<timestamp>.log` (override with `--log PATH`):
run settings, every bulletin board post, a per-episode summary for each buggle, and the
final best path. The log is written line by line, so `tail -f` follows a live run, and it
records interrupted runs too. The path is printed when the run ends.

Options: `--width --height --buggles (max 61) --episodes --max-steps --epsilon
--epsilon-decay --loops --mud --seed --watch --fps --trails --log --color {auto,always,never} --no-color`.

`--watch` accepts episode numbers, ranges (`4-6`, `8-`), `first`, `last`, `all`, `none`.

## Layout

| file | role |
|---|---|
| `maze.py` | maze generation (perfect maze plus extra openings), mud, BFS shortest path |
| `runlog.py` | log file writer (used by `sim.py`) |
| `board.py` | bulletin board: dead ends, best path, message log |
| `sim.py` | buggles, epsilon-greedy policy, episodes, `Observer` hooks |
| `ascii_view.py` | terminal renderer, plugs in as an `Observer` |

`sim.py` never imports `ascii_view.py` (a test checks this). To drive the
simulation from something else, subclass `sim.Observer` and pass it to `Simulation.run()`.

## Buggle policy

Each tick a buggle takes a random move with probability epsilon (decays per episode).
Otherwise it follows the board's best path if it is standing on it, else steps to an
unvisited cell, else heads for the nearest cell it has seen with an unexplored exit.
Known dead ends are avoided. A cell whose only live exit is one neighbor is posted as a
dead end, so dead ends spread inward from the tips as buggles report. A buggle reaching
the goal posts its loop-free route if it beats the board's best. Mud costs extra ticks.
