"""Build the user manual as one HTML page (and optionally a PDF) from the Markdown parts.

    python docs/manual/build.py                 # -> docs/manual/_build/manual.html (+ images/)
    python docs/manual/build.py --pdf           # also _build/manual.pdf (needs Playwright + Chromium)

The Markdown files stay the source of truth (they read fine on GitHub too). This script:
  - turns the layer callouts ("In plain terms", "For GRC practitioners", "Under the hood",
    "Screenshot to add", "Lesson from the pilot") into styled boxes
  - turns images into figures captioned with their alt text
  - rewrites links between parts into in-page anchors, and fails if any anchor is broken
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
PARTS = [("README.md", "intro", "About this manual"), ("1-product-guide.md", "part-1", "Product guide"),
         ("2-training-guide.md", "part-2", "Training guide"), ("3-troubleshooting.md", "part-3", "Troubleshooting guide")]
CALLOUTS = {"In plain terms": "plain", "For GRC practitioners": "practice", "Under the hood": "tech",
            "Screenshot to add": "shot", "Lesson from the pilot": "lesson"}


def gh_slug(value: str, separator: str = "-") -> str:
    """GitHub's heading anchors: lower-case, drop punctuation, spaces become hyphens (not collapsed)."""
    v = html.unescape(re.sub(r"<[^>]+>", "", value)).strip().lower()
    v = re.sub(r"[^\w\- ]", "", v)
    return v.replace(" ", separator)


def convert(text: str) -> str:
    """CommonMark + GFM tables (same rules GitHub uses), then GitHub-style heading anchors."""
    out = MarkdownIt("commonmark", {"html": True}).enable("table").render(text)

    def anchor(m):
        level, inner = m.group(1), m.group(2)
        return f'<h{level} id="{gh_slug(inner)}">{inner}</h{level}>'
    return re.sub(r"<h([1-4])>(.*?)</h\1>", anchor, out, flags=re.S)


def callouts(body: str) -> str:
    def repl(m):
        inner = m.group(1)
        for label, cls in CALLOUTS.items():
            if re.search(rf"<strong>{re.escape(label)}:?</strong>", inner):
                inner = re.sub(rf"<strong>{re.escape(label)}:?</strong>:?\s*", "", inner, count=1)
                return f'<aside class="layer {cls}"><span class="layer-label">{label}</span>{inner}</aside>'
        return m.group(0)
    return re.sub(r"<blockquote>\s*(.*?)</blockquote>", repl, body, flags=re.S)


def figures(body: str) -> str:
    """A paragraph holding only an image becomes a figure captioned with the image's alt text."""
    def repl(m):
        tag = m.group(1)
        src = re.search(r'src="([^"]+)"', tag).group(1)
        alt = (re.search(r'alt="([^"]*)"', tag) or [None, ""])[1]
        wide = " wide" if src.endswith(".svg") else ""
        return (f'<figure class="fig{wide}"><img src="{src}" alt="{alt}">'
                f'<figcaption>{alt}</figcaption></figure>')
    return re.sub(r"<p>\s*(<img [^>]+>)\s*</p>", repl, body)


def links(body: str, part_ids: dict[str, str]) -> str:
    def repl(m):
        href = m.group(1)
        if href.startswith(("http://", "https://", "#")):
            return m.group(0)
        f, _, anchor = href.partition("#")
        if f in part_ids:
            return f'href="#{anchor or part_ids[f]}"'
        return f'href="https://github.com/Baderholdjr/grc-readiness/blob/main/docs/manual/{href}"'
    return re.sub(r'href="([^"]+)"', repl, body)


CSS = """
/* Manual: quiet reading layout. Navy/teal from the house style of the Word brief; three layer colours. */
:root{
  --paper:#fbfcfc; --surface:#ffffff; --ink:#1b2a33; --muted:#5b6b75; --rule:#dbe3e7;
  --navy:#183b4e; --teal:#2f6f73;
  --plain-bg:#e8f3f1; --plain-fg:#1f5f5b; --prac-bg:#e9eff6; --prac-fg:#26496b;
  --tech-bg:#f1f3f4; --tech-fg:#3d4b53; --shot-bg:transparent; --shot-fg:#8a5a12; --lesson-bg:#fbf1e2;
  --code-bg:#f1f4f5;
  --display:"Source Serif 4", "Iowan Old Style", Georgia, serif;
  --body:"IBM Plex Sans", "Segoe UI", Helvetica, Arial, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --paper:#12191d; --surface:#172126; --ink:#e3eaed; --muted:#9db0b8; --rule:#2c3a41;
  --navy:#9ccbe0; --teal:#7cc3bd;
  --plain-bg:#163029; --plain-fg:#9fd8cf; --prac-bg:#172739; --prac-fg:#a9c8e8;
  --tech-bg:#1d272c; --tech-fg:#c3cfd4; --shot-fg:#e2b46a; --lesson-bg:#33281a; --code-bg:#1d272c; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#12191d; --surface:#172126; --ink:#e3eaed; --muted:#9db0b8; --rule:#2c3a41;
  --navy:#9ccbe0; --teal:#7cc3bd;
  --plain-bg:#163029; --plain-fg:#9fd8cf; --prac-bg:#172739; --prac-fg:#a9c8e8;
  --tech-bg:#1d272c; --tech-fg:#c3cfd4; --shot-fg:#e2b46a; --lesson-bg:#33281a; --code-bg:#1d272c; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:16px/1.6 var(--body);margin:0}
.wrap{display:grid;grid-template-columns:260px minmax(0,1fr);gap:48px;max-width:1180px;margin:0 auto;padding-inline:24px;padding-block:32px 80px}
nav.toc{position:sticky;top:calc(env(safe-area-inset-top,0px) + 16px);align-self:start;max-height:calc(100vh - 32px);overflow:auto;font-size:14px;padding-right:8px}
nav.toc p{font:600 13px var(--body);color:var(--muted);margin:18px 0 6px}
nav.toc a{display:block;color:var(--ink);text-decoration:none;padding:3px 0;line-height:1.35}
nav.toc a:hover{color:var(--teal)}
nav.toc ol{list-style:none;margin:0;padding:0}
nav.toc ol ol{padding-left:12px;border-left:1px solid var(--rule);margin:2px 0 8px}
nav.toc ol ol a{color:var(--muted);font-size:13px}
main{min-width:0;max-width:760px}
header.cover{border-bottom:1px solid var(--rule);padding-bottom:28px;margin-bottom:12px}
header.cover .kicker{font-size:14px;color:var(--muted);margin:0 0 6px}
header.cover h1{font:600 clamp(32px,5vw,46px)/1.1 var(--display);color:var(--navy);margin:0;text-wrap:balance}
header.cover .meta{color:var(--muted);margin:12px 0 0}
section.part{padding-top:24px}
section.part > h1{font:600 34px/1.15 var(--display);color:var(--navy);margin:48px 0 8px;text-wrap:balance;border-top:3px solid var(--navy);padding-top:22px}
h2{font:600 25px/1.25 var(--display);color:var(--navy);margin:48px 0 10px;text-wrap:balance}
h3{font:600 18px/1.35 var(--body);margin:32px 0 8px}
p,li{max-width:70ch}
a{color:var(--teal)}
code{font:0.88em var(--mono);background:var(--code-bg);padding:1px 5px;border-radius:4px}
pre{background:var(--code-bg);padding:14px 16px;border-radius:6px;overflow-x:auto;font:13px/1.5 var(--mono)}
pre code{background:none;padding:0}
.tbl{overflow-x:auto;margin:14px 0}
table{border-collapse:collapse;font-size:14.5px;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--rule);padding:7px 10px;text-align:left;vertical-align:top}
th{font-weight:600;color:var(--muted);border-bottom:2px solid var(--rule)}
hr{border:0;border-top:1px solid var(--rule);margin:36px 0}
.layer{display:block;margin:14px 0;padding:12px 16px 12px 16px;border-radius:6px;background:var(--tech-bg);color:var(--ink)}
.layer p{margin:4px 0}
.layer-label{display:block;font:600 12.5px var(--body);letter-spacing:.02em;margin-bottom:2px}
.layer.plain{background:var(--plain-bg)} .layer.plain .layer-label{color:var(--plain-fg)}
.layer.plain p{font-size:16.5px}
.layer.practice{background:var(--prac-bg)} .layer.practice .layer-label{color:var(--prac-fg)}
.layer.tech{background:var(--tech-bg);font-size:15px} .layer.tech .layer-label{color:var(--tech-fg);font-family:var(--mono);font-weight:500}
.layer.shot{background:var(--shot-bg);border:1.5px dashed var(--shot-fg);color:var(--muted)} .layer.shot .layer-label{color:var(--shot-fg)}
.layer.lesson{background:var(--lesson-bg)} .layer.lesson .layer-label{color:var(--shot-fg)}
figure.fig{margin:22px 0;max-width:100%}
figure.fig img{display:block;max-width:100%;height:auto;border:1px solid var(--rule);border-radius:6px;background:#fff}
figure.fig.wide img{border:0}
figcaption{font-size:13.5px;color:var(--muted);margin-top:6px}
.legend{display:flex;flex-wrap:wrap;gap:8px 12px;margin:16px 0}
.legend .layer{margin:0;flex:1 1 220px}
:focus-visible{outline:3px solid var(--teal);outline-offset:2px}
@media (max-width:900px){.wrap{grid-template-columns:1fr;gap:8px;padding-inline:16px}
  nav.toc{position:static;max-height:none;border-bottom:1px solid var(--rule);padding-bottom:12px}
  nav.toc ol ol{display:none}}
@media print{
  nav.toc{display:none} .wrap{display:block;max-width:none;padding:0}
  main{max-width:none} body{font-size:10.5pt;background:#fff;color:#111}
  section.part{break-before:page} section.part:first-of-type{break-before:auto}
  h2,h3{break-after:avoid} figure,.layer,table,pre{break-inside:avoid}
  a{color:inherit;text-decoration:none}
}
"""


def build(out: Path) -> Path:
    part_ids = {f: pid for f, pid, _ in PARTS}
    sections, toc = [], []
    for f, pid, title in PARTS:
        body = convert((HERE / f).read_text(encoding="utf-8"))
        body = callouts(body)
        body = figures(body)
        body = links(body, part_ids)
        body = re.sub(r"(<table>.*?</table>)", r'<div class="tbl">\1</div>', body, flags=re.S)
        if f == "README.md":
            body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
            body = re.sub(r"^\s*<p>(Engine version[^<]*)</p>", "", body, count=1)
            sections.append(f'<section class="part" id="{pid}">{body}</section>')
        else:
            body = re.sub(r"<h1([^>]*)>", rf'<h1\1 data-part="{pid}">', body, count=1)
            sections.append(f'<section class="part" id="{pid}">{body}</section>')
        subs = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)
        subs = [(i, re.sub("<[^>]+>", "", t)) for i, t in subs if not t.lower().startswith(("contents", "modules", "index"))]
        toc.append((pid, title, subs))
    html_body = "\n".join(sections)
    # every in-page link must land
    ids = set(re.findall(r'id="([^"]+)"', html_body)) | {pid for _, pid, _ in PARTS}
    broken = sorted({a for a in re.findall(r'href="#([^"]+)"', html_body) if a not in ids})
    if broken:
        sys.exit("broken anchors: " + ", ".join(broken))
    dupes = sorted({i for i in re.findall(r'id="([^"]+)"', html_body) if re.findall(rf'id="{re.escape(i)}"', html_body).__len__() > 1})
    if dupes:
        sys.exit("duplicate anchors: " + ", ".join(dupes))
    nav = ['<nav class="toc" aria-label="Contents"><p>Contents</p><ol>']
    for pid, title, subs in toc:
        nav.append(f'<li><a href="#{pid}"><b>{html.escape(title)}</b></a>')
        if subs:
            nav.append("<ol>" + "".join(f'<li><a href="#{i}">{html.escape(html.unescape(t))}</a></li>' for i, t in subs) + "</ol>")
        nav.append("</li>")
    nav.append("</ol></nav>")
    version = re.search(r"Engine version ([0-9.]+)", (HERE / "README.md").read_text()).group(1)
    page = f"""<title>GRC Readiness Manual</title>
<meta name="description" content="User manual for the GRC Readiness Engine: product guide, training guide and troubleshooting.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">
<style>{CSS}</style>
<div class="wrap">
{''.join(nav)}
<main>
<header class="cover"><p class="kicker">GRC Readiness Engine · ISO/IEC 42001 · ISO/IEC 27001</p><h1>User manual</h1>
<p class="meta">Engine version {version} · Product guide, training guide and troubleshooting guide</p></header>
{html_body}
</main></div>"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "manual.html").write_text(page, encoding="utf-8")
    if (out / "images").exists():
        shutil.rmtree(out / "images")
    shutil.copytree(HERE / "images", out / "images")
    return out / "manual.html"


def pdf(page: Path) -> Path:
    from playwright.sync_api import sync_playwright
    full = page.with_name("print.html")
    full.write_text("<!doctype html><html lang=en><head><meta charset=utf-8></head><body>" + page.read_text(encoding="utf-8")
                    + "</body></html>", encoding="utf-8")
    target = page.with_suffix(".pdf")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        pg.route("**/fonts.gstatic.com/**", lambda r: r.abort())
        pg.goto(full.as_uri())
        pg.wait_for_timeout(500)
        pg.emulate_media(media="print", color_scheme="light")
        pg.pdf(path=str(target), format="Letter", print_background=True,
               margin={"top": "0.7in", "bottom": "0.7in", "left": "0.75in", "right": "0.75in"},
               display_header_footer=True, header_template="<span></span>",
               footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#777">GRC Readiness Engine · User manual · '
                               '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        b.close()
    full.unlink()
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "_build"))
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    page = build(Path(a.out))
    print(page)
    if a.pdf:
        print(pdf(page))
