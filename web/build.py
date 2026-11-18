"""Build web/index.html: the browser version of Loom RL.

The page embeds the loomrl package sources and runs them with Pyodide, so the
browser and terminal versions run identical code. Rebuild after changing loomrl:

    python web/build.py                 # uses the jsdelivr copy of Pyodide
    python web/build.py --pyodide URL   # e.g. a local copy for testing (repeatable)
"""

# HOW TO READ THIS FILE
# The web page is one HTML file that contains the whole Loom program. This script
# makes it: it reads template.html, inserts the source code of every loomrl file
# and of driver.py as text, and writes index.html. When the page opens, Pyodide
# (Python compiled to run in the browser) writes those texts back out as files
# and runs them. Run this script again whenever loomrl changes.
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYODIDE_VERSION = "314.0.8"
# Tried in order. The last is an older, long-published release kept as a fallback;
# loomrl needs Python 3.10 or later, which it provides.
# Where the page downloads Pyodide from, tried in order until one works.
DEFAULT_URLS = [
    f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/",
    f"https://cdn.jsdelivr.net/npm/pyodide@{PYODIDE_VERSION}/",
    "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/",
]

# The loomrl files the page needs. __main__.py is left out: the page is its own front
# door.
MODULES = ["__init__.py", "maze.py", "board.py", "sim.py", "runlog.py", "ascii_view.py"]


# Fill the template's placeholders (__SOURCES__ and the others) with real content.
# json.dumps turns text into a JavaScript string literal with every quote and
# line break safely escaped.
def build(package: Path, out: Path, pyodide_urls: list[str]) -> None:
    sources = {name: (package / name).read_text(encoding="utf-8") for name in MODULES}
    driver = (HERE / "driver.py").read_text(encoding="utf-8")
    page = (HERE / "template.html").read_text(encoding="utf-8")
    # JSON is valid JavaScript; escape "</" so no source text can close the <script> tag.
    js = lambda obj: json.dumps(obj).replace("</", "<\\/")
    page = (page.replace("__SOURCES__", js(sources))
                .replace("__DRIVER__", js(driver))
                .replace("__PYODIDE_URLS__", js(pyodide_urls)))
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--package", default=str(HERE.parent / "loomrl" / "loomrl"))
    p.add_argument("--out", default=str(HERE / "index.html"))
    p.add_argument("--pyodide", action="append",
                   help="where to load Pyodide from; repeat to give fallbacks")
    a = p.parse_args()
    build(Path(a.package), Path(a.out), a.pyodide or DEFAULT_URLS)
