"""Reading a run's log from the terminal."""
# HOW TO READ THIS FILE
# Every run writes a plain-English log to a file (see runlog.py). This file lets
# you read one without leaving the terminal: right after a run, or later, with
#     python -m loomrl --view-log            (the most recent log)
#     python -m loomrl --view-log PATH       (a particular log)
# Long logs open in a "pager", a viewer that shows one screen at a time: press
# the space bar for the next page, arrow keys to scroll, and q to quit.
from __future__ import annotations

import pydoc
import sys
from pathlib import Path


# Find the newest log in a folder. Log names contain the date and time
# (loomrl-20261118-142201.log), but comparing the files' modification times is
# simpler and also works for logs saved under other names.
def latest_log(directory: str | Path = "logs") -> Path | None:
    logs = list(Path(directory).glob("*.log"))
    if not logs:
        return None
    return max(logs, key=lambda p: p.stat().st_mtime)


# Show a log. `pydoc.pager` is part of Python's standard library: in a terminal it
# opens the text in a pager (usually `less`), and when the output is going to a
# file or another program it simply prints the text.
def show(path: str | Path) -> None:
    text = Path(path).read_text(encoding="utf-8")
    pydoc.pager(text)


# After a run, offer to open its log. Only asked when a person is at the keyboard:
# if input or output is redirected (for example, saved to a file), we stay quiet.
# Returns True if the log was shown.
def offer(path: str | Path) -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        answer = input("Press L and then Enter to read the log, or just Enter to finish: ")
    except (EOFError, KeyboardInterrupt):     # Ctrl+D or Ctrl+C means "no, thanks"
        print()
        return False
    if answer.strip().lower() in ("l", "log", "y", "yes"):
        show(path)
        return True
    return False
