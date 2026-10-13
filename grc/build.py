"""Generate every report (Markdown/CSV/JSON, and Word unless disabled) into one folder."""
from __future__ import annotations

import re
from pathlib import Path

from . import render_md
from .model import Engagement


def slug(model: Engagement) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.client.lower()).strip("-") or "client"


def workbook_name(model: Engagement) -> str:
    return f"{slug(model)}-{model.engagement['framework']}-workbook.xlsx"


def build_outputs(model: Engagement, findings, out: Path, with_docx: bool = True,
                  internal: bool = True) -> tuple[str, str | None]:
    """Returns (readiness summary markdown, brief .docx file name or None).
    with_docx: also write the Office files (Word brief, documents, review packs; Excel workbook).
    internal: include engagement economics (the Hours sheet) in the workbook."""
    docx_name = f"{slug(model)}-{model.engagement['framework']}-brief.docx" if with_docx else None
    summary = render_md.render_all(model, findings, out, brief_docx=docx_name, docs_docx=with_docx,
                                   workbook=workbook_name(model) if with_docx else None)
    if with_docx:
        from .render_xlsx import render_workbook
        render_workbook(model, out / workbook_name(model), include_hours=internal)
        from .documents import docs
        from .render_docx import render_brief, render_document, render_markdown
        from .review import pack_path, reviews, safe_date
        render_brief(model, out / docx_name)
        for did in docs(model):
            render_document(model, did, out / f"doc-{did}.docx")
        for rid, r in reviews(model).items():
            pk = pack_path(model, rid)
            if pk.exists() and not r.get("_error"):
                as_of = safe_date((r.get("pack") or {}).get("as_of") if isinstance(r.get("pack"), dict) else None)
                render_markdown(model, pk.read_text(encoding="utf-8"), out / f"mr-{rid}-pack.docx",
                                f"{model.client} — management review input pack ({rid})", as_of or model.today)
    return summary, docx_name
