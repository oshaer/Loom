# Loom

*Created by Katie Dunbar on November 18, 1996. This is a version from 2026.*

**Run it in your browser:** https://oshaer.github.io/Loom/

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/oshaer/Loom)

## About Katie Dunbar

Katie Dunbar is a fictional character in *Weaving Wonder*, a novel by Orit Shaer. In the novel,
she graduates from Wellesley College in 1990 and completes her PhD at MIT in 1997, with Loom as
her dissertation project. The history described here belongs to the novel; the program itself is
real and can be run.

## The program

Katie wrote the first version of Loom in the fall of 1996, as a doctoral student at the MIT AI
Lab, to study how a group of learning programs should decide whose reports to believe. In Loom,
eight agents, which she called buggles, learn by trial and error to cross a maze. Each turn
carries a small penalty, so a buggle does well only by reaching the finish quickly, and everything
the buggles learn is recorded on a single shared board.

The buggles learn by Q-learning, a method in which an agent keeps an estimate, for every
situation and every action available in it, of the total reward it can expect after taking that
action [10]. After each action, the agent moves its estimate toward the reward it received plus
its best estimate for the situation it reached, and with enough experience the estimates come to
describe the best course of action.

Two of the buggles have faulty sensors that corrupt what they report about the maze, and the
team is never told which two. The board therefore checks each report against what other buggles
reported for the same move, keeps a record of how often each buggle's reports have agreed with
the rest, and weighs every report by that record. Each run ends with a plain-English log that
records how much the team came to trust each buggle and compares the outcome with a naive board
that accepts every report.

## What it contributed, in 1996 terms

By 1996, Q-learning was well established [10], and agents could already learn together by sharing
a single table of estimates [9]. Cooperation was known to speed learning, for instance when agents
learn by watching one another [11], and a survey published that year summarized the field [2].
This work assumed that every agent reported accurately. Katie asked how a group should learn when
some of its members are wrong and no one knows which.

- **Trust learned from evidence.** A buggle's standing is the share of its reports that agree with
  what other buggles observed, and each report changes the shared estimates in proportion to that
  standing. Marsh had formalized trust for artificial agents [4]; as far as Katie could find, no
  one had applied it to the way reinforcement learners pool their experience.
- **Facts beside estimates.** The board holds explicit claims, such as "this square is a dead
  end," alongside the learned estimates. A claim takes effect only when trusted buggles support
  it, and any trusted buggle that reaches the square verifies it, which brings the blackboard
  architecture of symbolic AI [1] together with Q-learning.
- **Explanation for readers outside the field.** Expert systems of the 1980s had made explanation
  part of AI, justifying their advice by describing how it was derived, on the view that trust in
  a system depends on seeing how its results were reached [8]. Learning systems rarely offered a
  comparable account, because what they learned was held in tables of numbers. Loom brings that
  principle to a learning system: each run is paired with a naive board on the same maze with the
  same faulty sensors, so the effect of trust can be seen directly, and the log explains in plain
  English why the team came to trust some buggles and not others, citing the evidence for each
  change.

The closest contemporary work is Maja Matarić's research on reinforcement learning in groups of
robots, published in 1997 [5, 6]. The grid-world setting follows Sutton's Dyna experiments [7],
and Koenig and Simmons had analyzed how quickly Q-learning reaches a goal in worlds of this
kind [3].

## Three versions

| folder | what it is | run it |
|---|---|---|
| `bugglemaze/` | Version 1. Buggles follow fixed rules and share dead ends and the best route on a bulletin board; there is no learning and no trust. | `cd bugglemaze && python -m bugglemaze` |
| `loomrl/` | Version 2, the dissertation version: shared Q-learning, with trust learned from evidence and facts verified by trusted buggles. | `cd loomrl && python -m loomrl --size medium` |
| `web/` | Version 2 in a web browser, running the same Python code through Pyodide. | open `web/index.html`, or the link above |

The terminal versions require Python 3.10 or later and no other software. Each writes a
plain-English log to a `logs/` folder, and `--help` lists every option.

To read a log, use the **Show log** button on the web page, which can be opened at any point
during a run. In the terminal, version 2 offers to open the log when a run ends;
`python -m loomrl --view-log` opens the most recent log, and `--view-log PATH` opens any other.

## Running Loom on GitHub

Loom can be run entirely on GitHub, with nothing to install.

- **In the browser.** The web version is published with GitHub Pages at
  https://oshaer.github.io/Loom/ and runs on any computer or phone.
- **From the Actions tab.** Open **Actions**, choose **Run Loom**, and click **Run workflow**. A
  form sets the version, maze size, maze number, number of buggles, number of faulty buggles, and
  whether trust is used. GitHub runs the simulation, usually within a minute, and the results page
  shows the full log and the final maze. The log can also be downloaded under **Artifacts**.
- **In a Codespace.** The **Open in GitHub Codespaces** button above opens the repository in a
  complete programming environment in the browser, with Python ready. In its terminal,
  `cd loomrl && python -m loomrl --size medium` shows the animated simulation, and the code can be
  read and changed in place.

## Reading the code

The code is annotated for readers who are new to programming. Each file opens with a note headed
**HOW TO READ THIS FILE**, and the comments explain what each part of the program does and which
features of Python it relies on.

For version 2 (`loomrl/loomrl/`), this reading order works well:

1. `maze.py`: how a maze is built, and the two search methods (breadth-first search and
   Dijkstra's algorithm) that find the true shortest route used to judge results.
2. `board.py`: the core of Katie's idea. Start with `report`, where a single buggle's report is
   checked, weighed by trust, and learned from.
3. `sim.py`: the experiment itself. Read `run`, then `step`, then `_act`, which is one buggle's turn.
4. `runlog.py` and `ascii_view.py`: the plain-English log and the terminal display.

Version 1 (`bugglemaze/`) is a useful starting point, since its `sim.py` shows agents following
fixed rules before any learning is introduced. In `web/driver.py`, the same simulation runs in
small steps inside a web page.

## For the repository owner

One setting is needed once, after the first upload. Under **Settings → Pages → Build and
deployment**, set **Source** to **GitHub Actions**; the website is then published on every push.
Its home page is made from this README, and the browser version of Loom is linked from it. The **Run Loom** workflow
and Codespaces need no setup. On a free GitHub account, Pages requires the repository to be public,
and Codespaces includes a monthly allowance of free hours for each user.

## Tests

Inside `bugglemaze/` or `loomrl/`, run `python -m pytest -q` (after installing `pytest`). GitHub
runs both suites on every push and checks that `web/index.html` was rebuilt after any change to
`loomrl` (`python web/build.py`).

## References

Publication details were checked against publisher records and standard indexes. Each link is a
DOI or the publisher's own page.

1. Lee D. Erman, Frederick Hayes-Roth, Victor R. Lesser, and D. Raj Reddy. 1980. The Hearsay-II
   Speech-Understanding System: Integrating Knowledge to Resolve Uncertainty. *ACM Computing
   Surveys* 12, 2 (June 1980), 213–253. https://doi.org/10.1145/356810.356816
2. Leslie Pack Kaelbling, Michael L. Littman, and Andrew W. Moore. 1996. Reinforcement Learning:
   A Survey. *Journal of Artificial Intelligence Research* 4 (1996), 237–285.
   https://doi.org/10.1613/jair.301
3. Sven Koenig and Reid G. Simmons. 1993. Complexity Analysis of Real-Time Reinforcement Learning.
   In *Proceedings of the Eleventh National Conference on Artificial Intelligence (AAAI '93)*.
   AAAI Press. https://mlanthology.org/aaai/1993/koenig1993aaai-complexity/
4. Stephen Paul Marsh. 1994. *Formalising Trust as a Computational Concept*. Ph.D. Dissertation.
   University of Stirling. http://hdl.handle.net/1893/2010
5. Maja J. Matarić. 1997. Reinforcement Learning in the Multi-Robot Domain. *Autonomous Robots*
   4, 1 (1997), 73–83. https://doi.org/10.1023/A:1008819414322
6. Maja J. Matarić. 1997. Using Communication to Reduce Locality in Multi-Robot Learning. In
   *Proceedings of the Fourteenth National Conference on Artificial Intelligence (AAAI '97)*.
   AAAI Press, 643–648. https://mlanthology.org/aaai/1997/mataric1997aaai-using/
7. Richard S. Sutton. 1990. Integrated Architectures for Learning, Planning, and Reacting Based on
   Approximating Dynamic Programming. In *Proceedings of the Seventh International Conference on
   Machine Learning (ICML '90)*. Morgan Kaufmann, 216–224.
   https://papersdb.cs.ualberta.ca/~papersdb/view_publication.php?pub_id=505
8. William R. Swartout. 1983. XPLAIN: A System for Creating and Explaining Expert Consulting
   Programs. *Artificial Intelligence* 21, 3 (September 1983), 285–325.
   https://doi.org/10.1016/S0004-3702(83)80014-9
9. Ming Tan. 1993. Multi-Agent Reinforcement Learning: Independent vs. Cooperative Agents. In
   *Proceedings of the Tenth International Conference on Machine Learning (ICML '93)*. Morgan
   Kaufmann, 330–337. https://doi.org/10.1016/B978-1-55860-307-3.50049-6
10. Christopher J. C. H. Watkins and Peter Dayan. 1992. Q-learning. *Machine Learning* 8, 3–4
    (1992), 279–292. https://doi.org/10.1007/BF00992698
11. Steven D. Whitehead. 1991. Complexity and Cooperation in Q-Learning. In *Proceedings of the
    Eighth International Workshop on Machine Learning (ML '91)*. Morgan Kaufmann.
    https://doi.org/10.1016/B978-1-55860-200-7.50075-1

## Copyright

© 2026 Orit Shaer. *Weaving Wonder*, Katie Dunbar and the story of Loom are the work of Orit
Shaer. All rights reserved, including for the code, until a license is chosen.
