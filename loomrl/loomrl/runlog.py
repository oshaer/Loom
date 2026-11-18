"""Plain-English run log for Loom RL. Every run writes one."""

# HOW TO READ THIS FILE
# This file writes the plain-English log of a run, for readers who are not
# programmers. The simulation calls the RunLog's methods as things happen:
#   header()     once, before round 1: the setting and how the method works
#   post()       whenever something is posted to the notice board
#   round_end()  after every round; rounds are summarised in groups of 10
#   footer()     once, at the end: results, trust, the comparison, the curve
# Most of the file is about wording: choosing the right sentence for what
# happened. The small helper functions at the top handle grammar.
from __future__ import annotations

import os
import textwrap
from datetime import datetime
from pathlib import Path

# Lines are wrapped at 78 characters so the log reads well in any text editor.
WIDTH = 78


# A new file name for each run, stamped with the date and time, such as
# logs/loomrl-20261118-142201.log. If two runs start in the same second, add -2, -3...
def default_log_path(directory: str | os.PathLike = "logs") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(directory) / f"loomrl-{stamp}.log"
    n = 2
    while path.exists():
        path = Path(directory) / f"loomrl-{stamp}-{n}.log"
        n += 1
    return path


# "1 turn" but "2 turns". `many` gives an irregular plural, as in buggy/buggies.
def plural(n, word: str, many: str | None = None) -> str:
    return f"{n} {word if str(n) == '1' else (many or word + 's')}"


# Small numbers as words ("two"), which read better in a sentence.
def number_word(n: int) -> str:
    words = "zero one two three four five six seven eight nine ten".split()
    return words[n] if 0 <= n < len(words) else str(n)


# ["A", "B", "C"] becomes "A, B and C".
def join_and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# The code calls buggles B01, B02...; the log calls them Buggle 1, Buggle 2.
def buggle_name(name: str) -> str:
    return f"Buggle {int(name[1:])}"


# Turn a route (a list of squares) into walking directions such as
# "right 3, down 1", by grouping consecutive moves in the same direction.
def directions(path) -> str:
    words = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
    legs: list[list] = []
    for a, b in zip(path, path[1:]):
        d = words[(b[0] - a[0], b[1] - a[1])]
        if legs and legs[-1][0] == d:
            legs[-1][1] += 1
        else:
            legs.append([d, 1])
    return ", ".join(f"{d} {n}" for d, n in legs)


# "as fast as possible" or "4 turns slower than the fastest possible".
def versus_fastest(turns: int, fastest: int) -> str:
    extra = turns - fastest
    return ("as fast as possible" if extra == 0
            else f"{plural(extra, 'turn')} slower than the fastest possible")


# One log file. `buffering=1` writes each line to disk as soon as it is finished,
# so you can watch a log grow while the program runs (for example with `tail -f`).
class RunLog:
    def __init__(self, path: str | os.PathLike, every: int = 10):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8", buffering=1)
        self.every = every              # rounds per log entry
        self._block: list = []          # round stats waiting to be summarised
        self._block_msgs: list = []     # notice-board posts in those rounds
        self._prev_caught = 0

    # Write a paragraph, wrapped to WIDTH. `hang` indents the second and later lines,
    # which is how the bullet points in each round summary are laid out.
    def write(self, text: str = "", indent: int = 0, hang: bool = False) -> None:
        if self._f.closed:
            return
        if not text:
            self._f.write("\n")
            return
        pad = " " * indent
        self._f.write(textwrap.fill(text, WIDTH, initial_indent=pad,
                                    subsequent_indent=pad + ("  " if hang else "")) + "\n")

    # Write one line exactly as given (used for tables, where wrapping would break the
    # columns).
    def raw(self, line: str) -> None:
        if not self._f.closed:
            self._f.write(line + "\n")

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()

    # ---- header ------------------------------------------------------
    # THE OPENING: who made Loom and when, what this run is, the maze, and how the
    # buggles learn, in plain words.
    def header(self, sim) -> None:
        m, w = sim.maze, self.write
        now = datetime.now()
        when = f"{now:%B} {now.day}, {now.year} at {now.strftime('%I:%M %p').lstrip('0')}"
        w("This is Loom")
        w("=" * 12)
        w(f"Created by {sim.created_by} on {sim.created_on}.")
        if sim.version_note:
            w(sim.version_note)
        w()
        n_faulty = sum(b.faulty for b in sim.buggles)
        intro = (f"I am running a reinforcement learning experiment: "
                 f"{plural(len(sim.buggles), 'buggle')} learning by trial and error, as a "
                 f"team, to cross a {m.width} by {m.height} maze over "
                 f"{plural(sim.n_episodes, 'round')}.")
        if n_faulty:
            intro += (f" {number_word(n_faulty).capitalize()} of them "
                      f"{'has a faulty sensor' if n_faulty == 1 else 'have faulty sensors'}, "
                      f"and the team must work out whom to trust.")
        w(intro)
        w(f"Started {when}.")
        w()
        w("-" * WIDTH)
        w()
        w("The maze", hang=False)
        w()
        w(f"The maze has {m.width * m.height} squares. The buggles start in the top-left "
          f"corner and the finish is in the bottom-right corner. "
          f"{plural(len(m.mud), 'square is', 'squares are')} muddy: driving into mud "
          f"costs {plural(sim.mud_delay, 'extra turn')}.")
        w()
        w(f"The fastest possible trip takes {sim.fastest_turns} turns. The buggles are "
          f"never told this; it is here so you can judge how well they learn.")
        w()
        w("How the buggles learn")
        w()
        w("This is reinforcement learning. Nobody tells the buggles where to go. They "
          "get a small penalty for every turn they spend, so the only way to do well "
          "is to reach the finish quickly. They improve by trying things and keeping "
          "track of what happened.")
        w()
        w("The notice board is now a shared memory. For every square and every "
          "possible move from it, the board holds the team's current estimate of how "
          "many turns that move will take to reach the finish. After each move, the "
          "buggle that made it updates that estimate using what it found on the next "
          "square. This method is called Q-learning, and because all the buggles write "
          "to the same board, every move any of them makes teaches the whole team.")
        w()
        w(f"Usually a buggle picks the move the board rates best. Sometimes it picks a "
          f"random move instead, to try something new. That happens "
          f"{sim.epsilon0:.0%} of the time in round 1 and less each round after that. "
          f"Each new piece of evidence moves an estimate {sim.alpha:.0%} of the way "
          f"toward the new value (the learning rate).")
        w()
        w("Moves nobody has tried yet start with a hopeful guess: zero turns to the "
          "finish. Since every tried move scores worse than that, the buggles are "
          "drawn toward untried moves until the whole maze has been checked. This "
          "trick is called optimism in the face of uncertainty, and it is why the "
          "early rounds look like a frantic search.")
        w()
        self._trust_intro(sim)
        w(f"Every buggle starts each round back at the start, with up to "
          f"{sim.max_steps} turns to reach the finish. The board keeps everything "
          f"learned from one round to the next.")
        if sim.seed is not None:
            w()
            w(f"(Maze number {sim.seed}: running again with the same number gives the "
              f"same maze.)")
        w()
        if self.every > 1:
            w(f"To keep it short, this log reports in groups of {self.every} rounds.")
            w()

    # The part of the opening that explains faulty sensors, trust and facts. Its
    # wording depends on whether trust is switched on for this run.
    def _trust_intro(self, sim) -> None:
        w = self.write
        faulty = [b for b in sim.buggles if b.faulty]
        if faulty:
            names = join_and([buggle_name(b.name) for b in faulty])
            w("Faulty sensors")
            w()
            w(f"{names} {'has a faulty sensor' if len(faulty) == 1 else 'have faulty sensors'}. "
              f"{'It' if len(faulty) == 1 else 'They'} sometimes report mud where the "
              f"ground is dry and dry ground where there is mud, now and then report "
              f"reaching the finish when they haven't, and mark open squares as dead "
              f"ends. Nobody tells the team which buggles these are. I name them here "
              f"only so you can check whether the team works it out.")
            w()
        if sim.trust_on:
            w("Trust")
            w()
            w("The board checks every report against what other buggles reported for "
              "the same move. A buggle whose reports keep matching earns trust; one "
              "whose reports keep clashing loses it. Each report changes the board's "
              "estimates in proportion to how much the team trusts its author, so a "
              "distrusted buggle can still speak, but the board barely listens. Every "
              "buggle starts with the benefit of the doubt.")
            w()
            w("Facts as well as estimates")
            w()
            w("Besides its estimates, the board holds facts: claims that a square is a "
              "dead end, with one way in and no way on. A claim counts only once "
              "buggles the team trusts back it; then the buggles stop wasting turns "
              "there. Any trusted buggle that stands on a claimed square checks it with "
              "its own eyes. A false claim is removed, and whoever posted it loses "
              "trust. Learned numbers and stated facts sit side by side on one board "
              "and keep each other honest.")
        else:
            w("A naive board")
            w()
            w("In this run the board trusts everyone equally. Every report counts in "
              "full and every dead-end claim is believed at once. A claim is removed "
              "when a buggle sees it is wrong, but nobody keeps score of who has been "
              "wrong before.")
        w()
        if sim.baseline is not None:
            w("To show what trust is worth, I also ran the same maze with the same "
              "buggles on a naive board that believes every report. The comparison is "
              "at the end.")
            w()

    # ---- rounds ------------------------------------------------------
    # Nothing to write when a round starts; rounds are reported when they end.
    def round_start(self, sim) -> None:
        pass

    # Collect notice-board posts; they are reported with the group of rounds they
    # happened in.
    def post(self, sim, msg) -> None:
        self._block_msgs.append(msg)

    # Store the round, and write a summary every `every` rounds (10 by default).
    def round_end(self, sim) -> None:
        st = sim.history[-1]
        self._block.append(st)
        if st.episode % self.every == 0 or st.episode == sim.n_episodes:
            self._flush_block(sim)

    # Write one summary for a group of rounds: how often buggles moved at random,
    # how trip times changed, who finished, the notable moments, and where things stand.
    def _flush_block(self, sim) -> None:
        rounds, msgs = self._block, self._block_msgs
        self._block, self._block_msgs = [], []
        if not rounds:
            return
        w = self.write
        first, last = rounds[0], rounds[-1]
        title = (f"Round {first.episode}" if first is last
                 else f"Rounds {first.episode} to {last.episode}")
        w(title)
        w("-" * len(title))

        # how often they explored
        if first is last or round(first.epsilon * 100) == round(last.epsilon * 100):
            w(f"Random moves: {last.epsilon:.0%} of the time.", indent=2)
        else:
            w(f"Random moves: {first.epsilon:.0%} of the time, falling to "
              f"{last.epsilon:.0%}.", indent=2)

        # trip times
        timed = [r for r in rounds if r.avg_turns is not None]
        if timed:
            a, z = timed[0], timed[-1]
            if a is z:
                w(f"Average trip: {a.avg_turns:.0f} turns.", indent=2)
            elif abs(z.avg_turns - a.avg_turns) <= 2:
                lo = min(r.avg_turns for r in timed)
                hi = max(r.avg_turns for r in timed)
                rng = "" if round(lo) == round(hi) else f" (between {lo:.0f} and {hi:.0f})"
                w(f"Average trip: steady at about {z.avg_turns:.0f} turns{rng}.", indent=2)
            else:
                direction = "down" if z.avg_turns < a.avg_turns else "up"
                best_round = min(timed, key=lambda r: r.avg_turns)
                line = (f"Average trip: {a.avg_turns:.0f} turns in round {a.episode}, "
                        f"{direction} to {z.avg_turns:.0f} in round {z.episode}.")
                if best_round not in (a, z):
                    line += (f" The quickest round on average was round "
                             f"{best_round.episode}, at {best_round.avg_turns:.0f}.")
                w(line, indent=2)

        # who finished
        short = [r for r in rounds if r.finished < r.buggles]
        if not short:
            w("Every buggle reached the finish in every round.", indent=2)
        else:
            items = [f"round {r.episode} ({r.finished} of {r.buggles})" for r in short]
            parts = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
            w(f"Every buggle reached the finish except in {parts}.", indent=2)

        # notable moments
        notes = []
        for m in msgs:
            if m.kind == "FIRST_FINISH":
                notes.append(f"Round {m.episode}: {buggle_name(m.author)} became the first "
                             f"buggle ever to reach the finish, taking {m.turns} turns.")
        records = [m for m in msgs if m.kind == "RECORD_RUN"]
        if records:
            best = records[-1]
            eps = [str(r) for r in sorted({m.episode for m in records})]
            when = eps[0] if len(eps) == 1 else ", ".join(eps[:-1]) + " and " + eps[-1]
            label = "round" if len(eps) == 1 else "rounds"
            if len(records) == 1:
                notes.append(f"Round {best.episode}: {buggle_name(best.author)} set a new "
                             f"single-trip record of {best.turns} turns.")
            else:
                notes.append(f"New single-trip records were set {len(records)} times "
                             f"({label} {when}), down to {best.turns} turns by "
                             f"{buggle_name(best.author)} in round {best.episode}.")
        for m in msgs:
            if m.kind == "ROUTE_LEARNED":
                notes.append(f"Round {m.episode}: for the first time, the board's estimates "
                             f"pointed all the way from start to finish, a route of "
                             f"{m.turns} turns.")
            elif m.kind == "ROUTE_IMPROVED":
                notes.append(f"Round {m.episode}: the route the board points to improved "
                             f"to {m.turns} turns.")
            elif m.kind == "ROUTE_OPTIMAL":
                notes.append(f"Round {m.episode}: the route the board points to reached "
                             f"{m.turns} turns, as fast as possible.")
        notes += self._trust_notes(sim, msgs, rounds)
        if notes:
            w()
            for n in notes:
                w("- " + n, indent=2, hang=True)
        else:
            w("Nothing new was learned in these rounds.", indent=2)

        # where things stand
        w()
        best = sim.best_route
        if best is None:
            w("Status: the board doesn't yet point to a complete route.", indent=2)
        elif last.route_turns is None:
            w(f"Status: best route found so far is {best} turns, "
              f"{versus_fastest(best, sim.fastest_turns)}. At the end of round "
              f"{last.episode} the estimates were still settling.", indent=2)
        else:
            w(f"Status: the route the board points to is {last.route_turns} turns, "
              f"{versus_fastest(last.route_turns, sim.fastest_turns)}.", indent=2)
        if sim.trust_on:
            w(self._trust_status(sim), indent=2)
        w()

    # The trust events of a group of rounds in plain words, each with its evidence:
    # who lost or regained the team's trust and how many of its reports had matched,
    # and which false facts were caught.
    def _trust_notes(self, sim, msgs, rounds) -> list[str]:
        """Explain changes in trust and caught false facts, with the evidence."""
        notes = []
        for m in msgs:
            if m.kind in ("TRUST_LOST", "TRUST_REGAINED"):
                agree, total = (int(x) for x in m.detail.split(" of "))
                if m.kind == "TRUST_LOST":
                    notes.append(f"Round {m.episode}: the team stopped trusting "
                                 f"{buggle_name(m.author)}. Only {agree} of its {total} "
                                 f"checked reports had matched what the others saw, and "
                                 f"its trust fell to {m.turns}%.")
                else:
                    notes.append(f"Round {m.episode}: the team began trusting "
                                 f"{buggle_name(m.author)} again ({m.turns}%), after "
                                 f"{agree} of its {total} checked reports matched.")
        believed = [m for m in msgs if m.kind == "FALSE_CLAIM"]
        if believed:
            posters = join_and(sorted({buggle_name(m.author) for m in believed}))
            if len(believed) == 1:
                m = believed[0]
                where, viewer = m.detail.split("|")
                notes.append(f"Round {m.episode}: the team had accepted {posters}'s claim "
                             f"that the square at {where} is a dead end. "
                             f"{buggle_name(viewer)} went there, found more than one way "
                             f"out, and the claim was removed.")
            else:
                notes.append(f"{plural(len(believed), 'false dead-end claim')} that the "
                             f"team had accepted, all from {posters}, were checked by "
                             f"other buggles and removed.")
        caught = rounds[-1].false_caught - self._prev_caught
        self._prev_caught = rounds[-1].false_caught
        ignored = caught - len(believed)
        if ignored > 0 and sim.trust_on:
            notes.append(f"Trusted buggles checked and removed "
                         f"{plural(f'{ignored:,}', 'false dead-end claim')} that the team "
                         f"had never believed in the first place.")
        return notes

    # One line on who the team trusts at the end of a group of rounds.
    def _trust_status(self, sim) -> str:
        board = sim.board
        low = [(b, board.trust(b.name)) for b in sim.buggles if board.trust(b.name) < 0.6]
        high = [board.trust(b.name) for b in sim.buggles if board.trust(b.name) >= 0.6]
        if not low:
            return "Trust: the team trusts every buggle."
        lows = join_and([f"{buggle_name(b.name)} ({t:.0%})" for b, t in low])
        if high:
            floor = f"{min(high):.0%}"
            rest = "at 100%" if floor == "100%" else f"at {floor} or more"
            return f"Trust: low for {lows}; every other buggle {rest}."
        return f"Trust: low for {lows}."

    # ---- result ------------------------------------------------------
    # THE RESULT: the learned route against the fastest possible, how much faster
    # the team got, who it trusted, the comparison with a naive board, a learning
    # curve, and walking directions for the learned route.
    def footer(self, sim, complete: bool, seconds: float) -> None:
        self._flush_block(sim)
        w = self.write
        w("Result")
        w("------")
        w()
        h = sim.history
        if not complete:
            w(f"The run was stopped early, during round {sim.episode} of "
              f"{sim.n_episodes}.")
            w()
        if not h:
            w("No round finished, so there is nothing to report yet.")
            return
        first, last = h[0], h[-1]
        if last.route_turns is not None:
            w(f"After {plural(len(h), 'round')}, the route the team learned takes "
              f"{last.route_turns} turns, "
              f"{versus_fastest(last.route_turns, sim.fastest_turns)}.")
        else:
            w(f"After {plural(len(h), 'round')}, the team has not yet learned a complete "
              f"route. More rounds would help.")
        if first.avg_turns and last.avg_turns:
            w(f"In round 1 a buggle needed {first.avg_turns:.0f} turns on average to "
              f"finish. In the last round it needed {last.avg_turns:.0f}.")
        total = sim.maze.width * sim.maze.height
        w(f"Over the run, the buggles moved out of {last.known} of the {total} squares "
          f"at least once. Most of that searching happened in the first few rounds.")
        w()
        self._trust_result(sim)
        self._comparison(sim)
        self._curve(sim)
        if sim.route_turns is not None:
            w()
            w(f"Directions for the learned route, from the top-left corner: "
              f"{directions(sim.route_path)}.")
        w()
        took = "less than a second" if seconds < 1 else plural(round(seconds), "second")
        w(f"The whole run took {took}.")

    # A table of every buggle's final trust, next to whether its sensor really was
    # faulty. This is the test of whether the team worked out whom to believe.
    def _trust_result(self, sim) -> None:
        if not sim.trust_on:
            return
        w, board = self.write, sim.board
        w("Who the team trusted")
        w()
        w("The team was never told which buggles had faulty sensors. This is how much "
          "it trusted each one at the end, with how many of its checked reports "
          "matched what the others saw:")
        w()
        for b in sim.buggles:
            agree, total = board.agreement(b.name)
            match = (f"{agree / total:.0%} of {total:,} reports matched" if total
                     else "no reports checked")
            sensor = "faulty sensor" if b.faulty else "sensor fine"
            self.raw(f"  {buggle_name(b.name):<10} {board.trust(b.name):>5.0%}   "
                     f"{sensor:<14} {match}")
        w()
        faulty = [b for b in sim.buggles if b.faulty]
        honest = [b for b in sim.buggles if not b.faulty]
        if faulty and all(board.trust(b.name) < 0.5 for b in faulty) and \
                all(board.trust(b.name) >= 0.9 for b in honest):
            w(f"The team singled out every faulty buggle and kept trusting all the "
              f"others. It removed {plural(f'{board.false_caught:,}', 'false dead-end claim')} "
              f"along the way, and at the end it believed "
              f"{plural(len(board.false_accepted), 'false fact')}."
              .replace("believed 0 false facts", "believed no false facts"))
        elif faulty:
            missed = [buggle_name(b.name) for b in faulty if board.trust(b.name) >= 0.5]
            wrong = [buggle_name(b.name) for b in honest if board.trust(b.name) < 0.9]
            if missed:
                w(f"The team had not yet caught {join_and(missed)}.")
            if wrong:
                w(f"It was still unsure about {join_and(wrong)}, whose sensors are fine.")
        w()

    # WHAT TRUST WAS WORTH: the same maze and the same faulty buggles, run on a naive
    # board that believes every report. The small functions inside pick out the
    # numbers to compare.
    def _comparison(self, sim) -> None:
        base = sim.baseline
        if base is None:
            return
        w = self.write
        w("What trust was worth")
        w()
        w("Same maze, same buggles, same faulty sensors, on a naive board that "
          "believes every report:")
        w()

        def first_optimal(x):
            return x.first_optimal

        def late_avg(x):
            tail = [r.avg_turns for r in x.history[-10:] if r.avg_turns is not None]
            return sum(tail) / len(tail) if tail else None

        def finished(x):
            total = sum(r.buggles for r in x.history)
            return sum(r.finished for r in x.history) / total if total else 0

        a, b = first_optimal(sim), first_optimal(base)
        rows = [
            ("Learned the fastest route", f"round {a}" if a else "never",
             f"round {b}" if b else "never"),
            ("Best route the board found", f"{sim.best_route} turns" if sim.best_route else "none",
             f"{base.best_route} turns" if base.best_route else "none"),
            ("Average trip, last 10 rounds",
             f"{late_avg(sim):.0f} turns" if late_avg(sim) else "no finishes",
             f"{late_avg(base):.0f} turns" if late_avg(base) else "no finishes"),
            ("Trips that reached the finish", f"{finished(sim):.0%}", f"{finished(base):.0%}"),
        ]
        self.raw(f"  {'':<30} {'With trust':<14} Naive board")
        for label, x, y in rows:
            self.raw(f"  {label:<30} {x:<14} {y}")
        w()
        if (late_avg(base) or 1e9) > 1.5 * (late_avg(sim) or 1e9) or (a and not b):
            w("Without trust, the faulty buggles' reports count as much as anyone's. "
              "Imaginary finish lines and wrong mud reports keep pulling the board's "
              "estimates off course, so the team struggles to settle on a route. With "
              "trust, the same false reports barely move the board once their authors "
              "are known.")
        else:
            w("On this maze the naive board coped too, so trust made less difference "
              "here. Faulty reports matter most when they land on the routes that "
              "count.")
        w()

    # A learning curve drawn with # characters: average turns per round, which
    # should shrink as the team learns. With a comparison run, its numbers are shown
    # alongside.
    def _curve(self, sim) -> None:
        """A small text chart of average turns per round: the learning curve."""
        h = [s for s in sim.history if s.avg_turns is not None]
        if len(h) < 2:
            return
        self.write("Learning curve: average turns to finish, by round. Shorter bars "
                   "mean the team got faster.")
        self.write()
        n = len(sim.history)
        step = self.every if self.every > 1 else max(1, n // 10)
        picks = {1, n} | set(range(step, n + 1, step))
        while len(picks) > 16:                   # keep the chart short for long runs
            step *= 2
            picks = {1, n} | set(range(step, n + 1, step))
        rows = [s for s in sim.history if s.episode in picks and s.avg_turns is not None]
        top = max(s.avg_turns for s in rows)
        bar_w = 40
        base = {r.episode: r.avg_turns for r in sim.baseline.history} if sim.baseline else {}
        if base:
            self.raw(f"  {'':9}  {'with trust':<{bar_w}}  {'turns':>5}   naive board")
        for s in rows:
            bar = "#" * max(1, round(bar_w * s.avg_turns / top))
            extra = ""
            if base:
                v = base.get(s.episode)
                extra = f"   {v:.0f}" if v is not None else "   none finished"
            self.raw(f"  Round {s.episode:>3}  {bar:<{bar_w}}  {s.avg_turns:>5.0f}{extra}")
        fastest = "|" * 1
        pos = max(1, round(bar_w * sim.fastest_turns / top))
        self.raw(f"  {'':9}  {' ' * (pos - 1)}{fastest}  <- fastest possible "
                 f"({sim.fastest_turns})")
