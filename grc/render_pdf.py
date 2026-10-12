"""Markdown (the subset our reports use) -> PDF, with ReportLab. Pure Python, so CI needs no office suite.

Output is reproducible: ReportLab's invariant mode plus a fixed document date means the same
Markdown always produces the same bytes (stable SHA-256 in the auditor package manifest).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

NAVY = colors.HexColor("#183B4E")
BAND = colors.HexColor("#F3F3F3")
CALLOUT = colors.HexColor("#EAF2F3")

# The built-in PDF fonts only cover Latin-1/WinAnsi; map the symbols our reports use.
SYMBOLS = {"✅": "[OK]", "⚠️": "[!]", "⚠": "[!]", "❌": "[FAIL]", "❔": "[?]", "⬜": "[ ]", "🟡": "[~]", "⏰": "",
           "≥": ">=", "≤": "<=", "→": "->", "←": "<-", "▶": ">", "◀": "<", "↔": "<->", "✔": "[OK]", "✓": "[OK]",
           "‑": "-", " ": " ", " ": " ", "​": "", "️": ""}


def _latin(text: str) -> str:
    for k, v in SYMBOLS.items():
        text = text.replace(k, v)
    out = []
    for ch in text:
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


MAX_CELL = 3000   # characters per table cell in the PDF; the full text stays in the Markdown/CSV/source record


def inline(text: str) -> str:
    """Markdown inline -> ReportLab paragraph markup (escaped).

    Code spans and links are lifted out as placeholders first, so emphasis markers inside them (or
    unbalanced ones around them) can't produce broken markup; `para()` falls back to plain text if
    the result still doesn't parse.
    """
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</?(details|summary)\b[^>]*>", "", text, flags=re.I)
    tokens: list[str] = []

    def keep(markup: str) -> str:
        tokens.append(markup)
        return f"\x00{len(tokens) - 1}\x00"

    def code(m):
        return keep(f'<font face="Courier">{html.escape(_latin(m.group(1)), quote=False)}</font>')

    def link(m):
        label, url = m.group(1), m.group(2)
        label = html.escape(_latin(re.sub(r"[*_`]", "", label)), quote=False)
        if re.match(r"https?://", url):
            return keep(f'<link href="{html.escape(url, quote=True)}" color="#1F5F8B">{label}</link>')
        return keep(label)
    text = re.sub(r"`([^`]*)`", code, text)
    text = re.sub(r"\[([^\]]*)\]\(([^)\s]*)\)", link, text)
    s = html.escape(_latin(text), quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])_(?!_)(.+?)(?<!_)_(?![\w*])", r"<i>\1</i>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], s)


def para(text: str, style) -> Paragraph:
    """A paragraph from Markdown; if the markup is rejected, the same text escaped and unformatted."""
    try:
        return Paragraph(inline(text), style)
    except Exception:  # ReportLab parse error on unusual input
        plain = re.sub(r"[*_`]", "", re.sub(r"<[^>]*>", "", text))
        return Paragraph(html.escape(_latin(plain), quote=False), style)


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT)
    return {
        "p": base,
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=NAVY,
                             spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.5),
        "head": ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.white),
        "quote": ParagraphStyle("quote", parent=base, backColor=CALLOUT, borderPadding=5, leftIndent=4, rightIndent=4,
                                spaceBefore=4, spaceAfter=6),
        "code": ParagraphStyle("code", parent=base, fontName="Courier", fontSize=7.5, leading=9.5),
    }


def _table(rows: list[list[str]], width: float, st) -> Table:
    n = max(len(r) for r in rows)
    rows = [(r + [""] * n)[:n] for r in rows]
    # column widths in proportion to content length, within sensible bounds
    lens = [max(min(len(r[i]), 60) for r in rows) + 4 for i in range(n)]
    # never narrower than the longest single word (ids like DOC-IMPACT must not break mid-word)
    floor = [max((len(w) for r in rows for w in re.sub(r"[*`]", "", r[i]).split()), default=1) * 4.4 + 8 for i in range(n)]
    total = sum(lens)
    widths = [max(width * l / total, f, 14 * mm if n < 9 else 9 * mm) for l, f in zip(lens, floor)]
    if sum(widths) > width:   # shrink the flexible part, keep the word floors where possible
        extra = sum(w - f for w, f in zip(widths, floor) if w > f)
        over = sum(widths) - width
        if extra > over:
            widths = [w - (w - f) * over / extra if w > f else w for w, f in zip(widths, floor)]
        else:
            widths = [w * width / sum(widths) for w in widths]
    clip = lambda c: c if len(c) <= MAX_CELL else c[:MAX_CELL] + " ... [truncated in the PDF; full text in the CSV / source record]"
    data = [[para(clip(c), st["head"] if ri == 0 else st["cell"]) for c in r] for ri, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1, splitInRow=1)   # a tall row may break across pages
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for i in range(1, len(rows)):
        if i % 2 == 1:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    t.setStyle(TableStyle(style))
    return t


def flowables(md: str, width: float) -> list:
    st = _styles()
    lines = md.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s in ("<details>", "</details>") or re.fullmatch(r"<!--.*-->", s):
            i += 1
            continue
        if s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append(Preformatted(_latin("\n".join(lines[i + 1:j])), st["code"]))
            i = j + 1
            continue
        if re.fullmatch(r"-{3,}|\*{3,}", s):
            out.append(Spacer(1, 4))
            i += 1
            continue
        if s.startswith("#"):
            level = min(len(s) - len(s.lstrip("#")), 3)
            out.append(para(s.lstrip("#").strip(), st[f"h{level}"]))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                out += [_table(rows, width, st), Spacer(1, 6)]
            continue
        if s.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(para(" ".join(quote), st["quote"]))
            continue
        m = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
        if m:
            items, numbered = [], m.group(2)[0].isdigit()
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
                if not m2:
                    if lines[i].startswith("   ") and lines[i].strip() and items:   # continuation line
                        items[-1] = (items[-1][0], items[-1][1] + " " + lines[i].strip())
                        i += 1
                        continue
                    break
                items.append((len(m2.group(1)), m2.group(3)))
                i += 1
            lf = ListFlowable([ListItem(para(t, st["p"]), leftIndent=12 + ind * 4) for ind, t in items],
                              bulletType="1" if numbered else "bullet", start=1 if numbered else "\u2022",
                              leftIndent=10, bulletFontSize=7 if not numbered else 8.5)
            out.append(lf)
            continue
        lines_ = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(#|\||>|```|[-*]\s|\d+[.)]\s)", lines[i]):
            lines_.append(lines[i].strip())
            i += 1
        out.append(para(" ".join(lines_), st["p"]))
        out.append(Spacer(1, 3))
    return out


def render(md: str, out_path: Path, title: str, footer: str, wide: bool | None = None, banner: str | None = None) -> Path:
    """wide=None: landscape when the document has a table with 7+ columns."""
    if wide is None:
        wide = any(line.strip().startswith("|") and line.count("|") >= 8 for line in md.splitlines())
    size = landscape(A4) if wide else A4
    margin = 14 * mm
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=size, leftMargin=margin, rightMargin=margin, topMargin=16 * mm,
                            bottomMargin=14 * mm, title=_latin(title), author="grc-readiness", creator="grc-readiness",
                            producer="grc-readiness", invariant=1)
    width = size[0] - 2 * margin
    story = []
    if banner:
        story.append(para(banner, _styles()["quote"]))
    story += flowables(md, width)

    def page(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(margin, 8 * mm, _latin(footer)[:180])
        canvas.drawRightString(size[0] - margin, 8 * mm, f"Page {d.page}")
        canvas.drawString(margin, size[1] - 9 * mm, _latin(title)[:160])
        canvas.restoreState()
    doc.build(story or [Spacer(1, 1)], onFirstPage=page, onLaterPages=page)
    return out_path
