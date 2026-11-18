"""Build the GitHub Pages website from the repository.

HOW TO READ THIS FILE
GitHub shows README.md on the repository's front page, so the README stays in
Markdown, the format GitHub expects. The website needs HTML. This script, run
by the "Publish web version" workflow each time the site is published:
  1. converts README.md to HTML and wraps it in a page styled like the
     simulation, with a "Run Loom" button: this becomes the site's home page;
  2. copies the web version (web/index.html) to web/ on the site.
Because the home page is made from the README at publishing time, the two never
disagree. On GitHub, the placeholder YOUR-USERNAME/loom is replaced with the
real owner and repository name, which GitHub provides as GITHUB_REPOSITORY.

Run it yourself with:  python site/build_site.py _site   (needs: pip install markdown)
"""
import html
import os
import re
import shutil
import sys
from pathlib import Path

import markdown   # turns Markdown text into HTML

ROOT = Path(__file__).resolve().parent.parent   # the repository folder

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Loom</title>
<link rel="icon" href="data:,">
<style>
  :root {{ --bg:#181a1f; --panel:#1f2228; --line:#2e323a; --fg:#e2e6ec; --dim:#969eaa; --green:#66d678;
           --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
           --mono:ui-monospace,"SF Mono",Menlo,Consolas,"DejaVu Sans Mono",monospace; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
          font:16px/1.65 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  main {{ max-width: 820px; margin: 0 auto; padding: 28px 20px 64px; }}
  h1 {{ font-family:var(--serif); font-size:44px; margin:0 0 4px; }}
  h2 {{ font-family:var(--serif); font-size:26px; margin:38px 0 10px; padding-top:12px;
        border-top:1px solid var(--line); }}
  a {{ color:#8fc7ff; }}
  em {{ color:var(--dim); }}
  code {{ font-family:var(--mono); font-size:.9em; background:var(--panel); padding:1px 5px;
          border-radius:4px; }}
  pre {{ background:var(--panel); padding:12px 14px; border-radius:8px; overflow-x:auto; }}
  pre code {{ background:none; padding:0; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; margin:12px 0; display:block;
           overflow-x:auto; }}
  th, td {{ border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }}
  th {{ background:var(--panel); }}
  li {{ margin:6px 0; }}
  ol li {{ font-size:15px; }}
  .run {{ display:inline-block; margin:18px 0 6px; padding:12px 22px; background:#23462b;
          border:1px solid #2f6b3b; border-radius:9px; color:var(--fg); text-decoration:none;
          font-size:17px; font-weight:600; }}
  .run:hover {{ border-color:var(--green); }}
  footer {{ margin-top:40px; color:var(--dim); font-size:13px; }}
</style>
</head>
<body>
<main>
{body}
<footer>This page is made from the repository's README. Source code:
  <a href="https://github.com/{repo}">github.com/{repo}</a></footer>
</main>
</body>
</html>
"""


def _autolink(m: "re.Match") -> str:
    """Wrap one address in <...>, leaving off punctuation that ends the sentence.

    A DOI may contain brackets, as in S0004-3702(83)80014-9, so a closing bracket
    is kept when the address also opened one."""
    url, tail = m.group(0), ""
    while url and (url[-1] in ".,;:" or (url[-1] == ")" and url.count("(") < url.count(")"))):
        url, tail = url[:-1], url[-1] + tail
    return f"<{url}>{tail}"


def build(out: Path) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "YOUR-USERNAME/loom")
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    text = text.replace("YOUR-USERNAME/loom", repo)
    owner, name = repo.split("/", 1)
    text = text.replace(f"https://YOUR-USERNAME.github.io/loom/",
                        f"https://{owner.lower()}.github.io/{name}/")
    # GitHub turns bare web addresses into links by itself; the converter does
    # not, so wrap each one in <...>, Markdown's way of marking a link.
    text = re.sub(r"(?<![(<\[\w])https?://[^\s<>\]]+", _autolink, text)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    # Inside the website, the browser version is one click away: point its links there.
    site = re.escape(f"https://{owner.lower()}.github.io/{name}/")
    body = re.sub(f'<a href="{site}">{site}</a>', '<a href="web/">Run Loom in your browser</a>',
                  body)
    # The README's "Run it in your browser" line becomes the page's big button.
    body = re.sub(r"<p><strong>Run it in your browser:</strong>.*?</p>",
                  '<p><a class="run" href="web/">Run Loom in your browser &rarr;</a></p>', body)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(PAGE.format(body=body, repo=html.escape(repo)),
                                    encoding="utf-8")
    shutil.copytree(ROOT / "web", out / "web", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.py", "*.md", "template.html"))
    print(f"built the site in {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "_site"))
