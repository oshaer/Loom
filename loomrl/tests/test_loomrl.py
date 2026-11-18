# TESTS. Each function whose name starts with test_ checks one thing the program
# must do, using `assert`, which stops with an error if its condition is false.
# Run them all from the loomrl folder with:  python -m pytest -q
# If every test passes, pytest prints a dot for each and a short summary.
import io
import subprocess
import sys
from pathlib import Path

from loomrl.ascii_view import AsciiView, Painter, parse_watch
from loomrl.maze import Maze
from loomrl.sim import Simulation

ROOT = Path(__file__).resolve().parents[1]


def test_sim_does_not_import_renderer():
    code = "import loomrl.sim, sys; print('loomrl.ascii_view' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "False"


def test_buggles_learn_the_fastest_route(tmp_path):
    maze = Maze(20, 12, seed=4)
    sim = Simulation(maze, n_buggles=8, episodes=50, seed=4, log_path=tmp_path / "r.log")
    sim.run()
    first, last = sim.history[0], sim.history[-1]
    assert sim.best_route == sim.fastest_turns
    assert last.avg_turns < first.avg_turns / 5          # clearly faster after learning
    path = sim.route_path or []
    assert all(maze.passable(a, b) for a, b in zip(path, path[1:]))


def test_q_values_estimate_turns_to_finish(tmp_path):
    """With reward -1 per turn and no discount, a settled board value is minus turns-to-go."""
    maze = Maze(12, 8, seed=2, mud=0.0)
    sim = Simulation(maze, n_buggles=6, episodes=40, seed=2, faulty=0,
                     log_path=tmp_path / "r.log")
    sim.run()
    start_value = sim.board.value(maze.start)
    assert abs(-start_value - sim.fastest_turns) <= 2


def test_mud_costs_turns_in_fastest_path():
    maze = Maze(12, 8, seed=5, mud=0.2)
    path, turns = maze.fastest_path(mud_delay=2)
    assert turns == sum(1 + (2 if c in maze.mud else 0) for c in path[1:])
    assert turns >= len(maze.shortest_path()) - 1


def test_maze_drawing_geometry(tmp_path):
    sim = Simulation(Maze(4, 3, seed=1), n_buggles=2, episodes=1, seed=1,
                     log_path=tmp_path / "r.log")
    sim.start_episode(1)
    lines = Painter(color=False, trails=False, values=False).maze_lines(sim)
    assert len(lines) == 7 and all(len(l) == 17 for l in lines)
    assert lines[1][2] == "*" and lines[5][-3] == "G"


def test_non_tty_prints_plain_snapshot(tmp_path):
    buf = io.StringIO()
    sim = Simulation(Maze(8, 5, seed=2), n_buggles=3, episodes=3, seed=2,
                     log_path=tmp_path / "r.log")
    sim.run(AsciiView(watch={1, 2, 3}, stream=buf, speed=0))
    text = buf.getvalue()
    assert "\x1b[" not in text and text.count("Round 3 of 3") == 1
    assert "Notice board" in text and "fastest possible" in text


def test_every_run_writes_a_plain_english_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sim = Simulation(Maze(12, 8, seed=3), n_buggles=6, episodes=30, seed=3)
    sim.run()
    text = sim.log_path.read_text()
    assert sim.log_path.parent.name == "logs" and sim.log_path.name.startswith("loomrl-")
    assert text.startswith("This is Loom")
    assert text.splitlines()[2] == "Created by Katie Dunbar on November 18, 1996."
    assert text.splitlines()[3] == "This is a version from 2026."
    assert "I am running a reinforcement learning experiment" in text
    assert "Q-learning" in text and "Learning curve" in text and "Result" in text
    for jargon in ("ROUTE_", "RECORD_RUN", "B01", "epsilon"):
        assert jargon not in text


def test_log_records_interrupted_run(tmp_path):
    from loomrl.sim import Observer

    class Stop(Observer):
        def on_tick(self, sim):
            if sim.episode == 2 and sim.tick == 5:
                raise KeyboardInterrupt

    sim = Simulation(Maze(6, 4, seed=1), n_buggles=2, episodes=3, seed=1,
                     log_path=tmp_path / "x.log")
    try:
        sim.run(Stop())
    except KeyboardInterrupt:
        pass
    assert "stopped early, during round 2 of 3" in (tmp_path / "x.log").read_text()


def test_parse_watch():
    assert parse_watch("1,3-5,last", 10) == {1, 3, 4, 5, 10}
    assert parse_watch("all", 3) == {1, 2, 3}
    assert parse_watch("none", 3) == set()


# ---- trust, facts and explanation ------------------------------------------

def _run(seed=3, trust=True, size=(20, 12), episodes=50, **kw):
    sim = Simulation(Maze(*size, seed=seed), n_buggles=8, episodes=episodes, seed=seed,
                     trust=trust, write_log=False, **kw)
    sim.run()
    return sim


def test_team_singles_out_faulty_buggles_without_being_told():
    sim = _run()
    for b in sim.buggles:
        if b.faulty:
            assert sim.board.trust(b.name) < 0.5
        else:
            assert sim.board.trust(b.name) > 0.9
    assert sum(b.faulty for b in sim.buggles) == 2


def test_trust_beats_a_naive_board():
    trusted, naive = _run(seed=2, size=(30, 18), episodes=80), \
        _run(seed=2, trust=False, size=(30, 18), episodes=80)
    assert trusted.first_optimal is not None
    late = lambda s: sum(r.finished for r in s.history[-10:])
    assert late(trusted) > late(naive)


def test_false_facts_are_caught_and_never_believed_at_the_end():
    sim = _run()
    assert sim.board.false_caught > 0
    assert not sim.board.false_accepted
    for c in sim.board.dead_ends:           # every believed dead end is real
        assert len(sim.maze.neighbors(c)) == 1


def test_naive_board_believes_any_claim_at_once():
    maze = Maze(8, 5, seed=1)
    sim = Simulation(maze, n_buggles=2, episodes=1, seed=1, trust=False, write_log=False)
    open_square = next(c for c in maze.cells()
                       if len(maze.neighbors(c)) > 1 and c not in (maze.start, maze.goal))
    sim.board.claim_dead_end("B01", open_square)
    assert open_square in sim.board.dead_ends and open_square in sim.board.false_accepted


def test_untrusted_reports_cannot_outvote_others_by_repetition():
    from loomrl.board import QBoard
    maze = Maze(6, 4, seed=1)
    board = QBoard(maze, alpha=0.5, gamma=1.0)
    s = maze.start
    a = maze.neighbors(s)[0]
    board.report("B01", s, a, -1, False)            # the truth, once
    for _ in range(50):
        board.report("B02", s, a, -1, True)         # a lie, fifty times
    assert board.trust("B02") < 0.5
    assert board._consensus(board.votes[(s, a)], exclude="B03")[0] == (-1, False)


def test_log_explains_trust_and_compares_with_naive_board(tmp_path):
    maze = lambda: Maze(12, 8, seed=5)
    base = Simulation(maze(), n_buggles=6, episodes=20, seed=5, trust=False, write_log=False)
    base.run()
    sim = Simulation(maze(), n_buggles=6, episodes=20, seed=5, log_path=tmp_path / "r.log")
    sim.baseline = base
    sim.run()
    text = (tmp_path / "r.log").read_text()
    for phrase in ("Faulty sensors", "Trust", "Facts as well as estimates",
                   "Who the team trusted", "What trust was worth", "naive board"):
        assert phrase in text
    assert "stopped trusting" in text


# ---- reading logs ------------------------------------------------------------

def test_latest_log_picks_the_newest(tmp_path):
    import os, time
    from loomrl.logview import latest_log
    assert latest_log(tmp_path) is None
    old, new = tmp_path / "a.log", tmp_path / "b.log"
    old.write_text("old"); new.write_text("new")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert latest_log(tmp_path) == new


def test_view_log_prints_a_log_when_not_in_a_terminal(tmp_path, monkeypatch, capsys):
    from loomrl.__main__ import main
    monkeypatch.chdir(tmp_path)
    assert main(["--view-log"]) == 1                      # no logs yet
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "run.log").write_text("This is Loom\\nCreated by Katie Dunbar\\n")
    assert main(["--view-log"]) == 0
    assert "Created by Katie Dunbar" in capsys.readouterr().out
