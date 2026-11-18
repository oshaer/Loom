# TESTS. Each function whose name starts with test_ checks one thing the program
# must do, using `assert`, which stops with an error if its condition is false.
# Run them all from the bugglemaze folder with:  python -m pytest -q
# If every test passes, pytest prints a dot for each and a short summary.
import io
import subprocess
import sys
from pathlib import Path

from bugglemaze.ascii_view import AsciiView, Painter, parse_watch
from bugglemaze.maze import Maze
from bugglemaze.sim import Simulation

ROOT = Path(__file__).resolve().parents[1]


def test_sim_does_not_import_renderer():
    code = "import bugglemaze.sim, sys; print('bugglemaze.ascii_view' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "False"


def test_run_headless_finds_valid_path(tmp_path):
    maze = Maze(10, 6, seed=3)
    sim = Simulation(maze, n_buggles=5, episodes=5, seed=3, log_path=tmp_path / 'r.log')
    sim.run()
    best = sim.board.best_path
    assert best[0] == maze.start and best[-1] == maze.goal
    assert all(maze.passable(a, b) for a, b in zip(best, best[1:]))
    assert sim.board.best_len >= sim.true_shortest_len
    assert not set(best) & sim.board.dead_ends


def test_maze_drawing_geometry():
    maze = Maze(4, 3, seed=1)
    sim = Simulation(maze, n_buggles=2, episodes=1, seed=1)
    sim.start_episode(1)
    lines = Painter(color=False, trails=False).maze_lines(sim)
    assert len(lines) == 2 * 3 + 1
    assert all(len(l) == 4 * 4 + 1 for l in lines)
    assert lines[0] == "+---+---+---+---+"
    assert lines[1][2] == "*"  # both buggles sit on S at tick 0
    assert lines[5][-3] == "G"


def test_non_tty_prints_plain_snapshot_only(tmp_path):
    buf = io.StringIO()
    sim = Simulation(Maze(6, 4, seed=2), n_buggles=3, episodes=2, seed=2,
                     log_path=tmp_path / 'r.log')
    sim.run(AsciiView(watch={1, 2}, stream=buf, fps=0))
    text = buf.getvalue()
    assert "\x1b[" not in text
    assert text.count("Episode") == 1  # one final snapshot, no frames
    assert "Bulletin board" in text and "true shortest" in text


def test_parse_watch():
    assert parse_watch("1,3-5,last", 10) == {1, 3, 4, 5, 10}
    assert parse_watch("all", 3) == {1, 2, 3}
    assert parse_watch("none", 3) == set()
    assert parse_watch("8-", 9) == {8, 9}


def test_every_run_writes_a_complete_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sim = Simulation(Maze(8, 5, seed=4), n_buggles=4, episodes=3, seed=4)
    sim.run()
    assert sim.log_path.parent.name == "logs" and sim.log_path.exists()
    text = sim.log_path.read_text()
    assert text.count("Round ") >= 3 and "Round 3 of 3" in text
    assert "Result" in text and "stopped early" not in text
    assert "DEAD_END" not in text and "B01" not in text  # no jargon
    assert sim.log_path.name.startswith("bugglemaze-")


def test_log_records_interrupted_run(tmp_path):
    from bugglemaze.sim import Observer

    class Stop(Observer):
        def on_tick(self, sim):
            if sim.tick == 5:
                raise KeyboardInterrupt

    sim = Simulation(Maze(6, 4, seed=1), n_buggles=2, episodes=2, seed=1,
                     log_path=tmp_path / "x.log")
    try:
        sim.run(Stop())
    except KeyboardInterrupt:
        pass
    assert "stopped early, during round 1 of 2" in (tmp_path / "x.log").read_text()


def test_directions_wording():
    from bugglemaze.runlog import directions
    assert directions([(0, 0), (1, 0), (2, 0), (2, 1)]) == "right 2, down 1"
