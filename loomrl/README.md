# Loom RL (loomrl)

The reinforcement learning version of Loom. Buggles learn to cross a maze with
**shared, trust-weighted Q-learning**. The original rule-based version (`bugglemaze`)
is separate and unchanged.

## What is new for 1996 (Katie Dunbar's version)

Shared Q-tables between agents were already published (Tan, ICML 1993). This version adds
three things that would have been unusual at the time:

1. **Trust-weighted sharing.** Two buggles (`--faulty N`) have faulty sensors: they misreport
   mud, report imaginary finishes, and post false dead ends. The team is never told which.
   Every report is checked against other buggles' latest report for the same move (one vote
   per buggle, weighted by trust). Agreement raises trust, disagreement lowers it, and each
   report moves the estimates by `alpha x trust^2`. Where trusted buggles have already seen
   a move, a contradicting report is set aside.
2. **A blackboard that holds facts as well as estimates.** Buggles post symbolic claims
   ("this square is a dead end"). A claim becomes a fact only once trusted support reaches a
   threshold; buggles then avoid that square. Any trusted buggle standing on a claimed square
   checks it; false claims are removed and their authors lose trust.
3. **Explanation for non-experts.** The plain-English log explains the method, reports each
   change in trust with its evidence, lists who the team trusted, and compares the run with a
   **naive board** on the same maze (every report counts in full, every claim believed). The
   comparison runs by default; `--no-compare` skips it, `--no-trust` runs only the naive board.

```
python -m loomrl                          # large 30x18 maze, 8 buggles, 80 rounds
python -m loomrl --size huge              # 48x24, 150 rounds
python -m loomrl --size medium --values --trails --watch 1,10,last
python -m loomrl --seed 1 | cat           # not a terminal: final snapshot only
```

## How it learns

| RL term | In Loom |
|---|---|
| agent | each buggle |
| state | the square it stands on |
| action | an open move to a neighbouring square |
| reward | -1 per turn; mud costs extra turns, so extra penalty |
| episode | a round: every buggle starts again at the start |
| Q-table | the notice board, shared by all buggles |
| exploration | epsilon-greedy random moves, decaying each round |
| optimistic initialisation | untried moves start at 0, so buggles seek them out |

Update after each move: `Q(s,a) += alpha * (reward + gamma * max Q(s',.) - Q(s,a))`.
With gamma = 1, a settled value is minus the number of turns to the finish.
The **learned route** is what you get by following the best tried move from the start.

## Sizes

| `--size` | maze | default rounds |
|---|---|---|
| small | 12x8 | 30 |
| medium | 20x12 | 50 |
| large (default) | 30x18 | 80 |
| huge | 48x24 | 150 |

The large maze needs a terminal about 172 columns wide for maze and panel side by side,
or 121x37 with the panel below. Smaller terminals get a warning and a size suggestion.

## Options

`--size --width --height --buggles --faulty --no-trust --no-compare --rounds --max-steps --epsilon --epsilon-decay --alpha
--gamma --loops --mud --seed --watch --speed --trails --values --color --no-color --log
--log-every --view-log --show-log`

`--values` shades each explored square by the board's estimate of turns to the finish
(darker = closer). `--speed` is ticks per second while watching; the screen redraws at most
30 times a second.

## Log

Every run writes a plain-English log to `logs/loomrl-<timestamp>.log`, headed "This is
Loom". It explains the method, reports in groups of 10 rounds (`--log-every N` to change), and ends
with a learning curve and directions for the learned route.

## Reading the log

When a run ends in a terminal, Loom offers to open its log; press L and Enter. `--show-log` opens
it without asking. To read a log later, `python -m loomrl --view-log` opens the most recent one and
`--view-log PATH` any other. Long logs open one screen at a time: space for the next page, q to quit.

## Files

`maze.py` maze and fastest route · `board.py` blackboard: estimates, facts, trust ·
`sim.py` agents and Q-learning · `runlog.py` the log · `logview.py` reading logs ·
`ascii_view.py` terminal view
(the simulation never imports it).
