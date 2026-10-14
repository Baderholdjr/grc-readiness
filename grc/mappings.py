"""Cross-framework mappings: one piece of evidence counting for two frameworks' records.

A client repository can hold one record per framework (engagement/ and engagement-<name>/). A mapping file
links requirements of two frameworks:

    mappings/iso27001__iso42001.yaml     (file name: the two framework ids, sorted, joined by "__")

    frameworks: [iso27001, iso42001]
    mappings:
      - {iso27001: "7.5", iso42001: "7.5", relationship: equivalent, note: "...",
         reviewed_by: "Bernard Aderhold", reviewed_on: 2026-11-02}

Relationships: equivalent, related, subset (the first framework's requirement is narrower), superset.
The engine ships *proposed* mappings (no reviewer). A mapping counts only after a person reviews it in the
client repository: copy the file to mappings/ at the repository root and fill reviewed_by / reviewed_on.

What a reviewed **equivalent** mapping allows: a control leg in one record may cite evidence held in the other
record as "<framework>:<id>" (for example `iso42001:EV-012` or `iso42001:DOC-DOCINFO`). The evidence keeps
its own freshness and approval rules. Related, subset and superset mappings never let evidence count twice;
they are listed as pointers for the analyst.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .model import Engagement, discover, load_yaml, resource, to_date

RELATIONSHIPS = ("equivalent", "related", "subset", "superset")


def file_name(a: str, b: str) -> str:
    return "__".join(sorted((a, b))) + ".yaml"


def mapping_path(model: Engagement, other_fw: str) -> Path:
    return resource(model.root, "mappings", file_name(model.engagement.get("framework", ""), other_fw))


def raw(model: Engagement, other_fw: str) -> dict:
    p = mapping_path(model, other_fw)
    if not p.exists():
        return {}
    data = load_yaml(p)
    return data if isinstance(data, dict) else {}


def _reviewed(m: dict, today: dt.date) -> bool:
    try:
        on = to_date(m.get("reviewed_on"))
    except (TypeError, ValueError):
        on = None
    return bool(str(m.get("reviewed_by") or "").strip()) and on is not None and on <= today


def pairs(model: Engagement, other_fw: str) -> list[dict]:
    """[{mine, other, relationship, reviewed, note}] from this record's point of view."""
    fw = model.engagement.get("framework", "")
    out = []
    for m in raw(model, other_fw).get("mappings") or []:
        if not isinstance(m, dict) or m.get(fw) is None or m.get(other_fw) is None:
            continue
        out.append({"mine": str(m[fw]), "other": str(m[other_fw]), "relationship": str(m.get("relationship") or ""),
                    "reviewed": _reviewed(m, model.today), "note": str(m.get("note") or ""),
                    "reviewed_by": str(m.get("reviewed_by") or "")})
    return out


def equivalents(model: Engagement, other_fw: str) -> dict[str, set[str]]:
    """My requirement -> the other framework's requirements it is (reviewed) equivalent to."""
    eq: dict[str, set[str]] = {}
    for p in pairs(model, other_fw):
        if p["relationship"] == "equivalent" and p["reviewed"]:
            eq.setdefault(p["mine"], set()).add(p["other"])
    return eq


def siblings(model: Engagement) -> dict[str, Engagement]:
    """The other records in this repository, by framework id (loaded once per model)."""
    cache = getattr(model, "_siblings", None)
    if cache is not None:
        return cache
    from .model import load
    out: dict[str, Engagement] = {}
    for d in discover(model.root):
        if d.resolve() == model.engagement_dir.resolve():
            continue
        try:
            sib = load(d, today=model.today)
        except SystemExit:
            continue                     # an unreadable record is reported when it is validated itself
        sib._siblings = {}               # no recursion: a sibling never looks further
        sib._cross = {}
        out[str(sib.engagement.get("framework") or d.name)] = sib
    model._siblings = out
    return out


def cross_evidence(model: Engagement) -> dict[str, dict]:
    """Evidence held in the other records, keyed '<framework>:<id>'."""
    cache = getattr(model, "_cross", None)
    if cache is not None:
        return cache
    model._cross = {}                    # set before computing, in case anything re-enters
    out: dict[str, dict] = {}
    for fw, sib in siblings(model).items():
        for eid, e in sib.evidence_index.items():
            out[f"{fw}:{eid}"] = {**e, "id": f"{fw}:{eid}", "held_in": sib.record_dir}
    model._cross = out
    return out


def report(model: Engagement, out: Path) -> list[tuple[str, str, str]]:
    """cross-framework.md: each mapping with its status and both sides' readiness."""
    sibs = siblings(model)
    if not sibs:
        return []
    from .client_view import md
    from .rules import requirement_state
    fw_short = (model.catalog.get("framework") or {}).get("short_name", "")
    L = [f"# {md(model.client)} — cross-framework mappings\n\n",
         "Mappings link this record's requirements to another framework's. Only a **reviewed equivalent** mapping lets "
         "evidence from the other record be cited here (as `<framework>:<id>`); the rest are pointers. Engine mappings are "
         "proposals until a person reviews them in `mappings/` at the repository root.\n"]
    total = reviewed_eq = 0
    for ofw, sib in sibs.items():
        other_short = (sib.catalog.get("framework") or {}).get("short_name", ofw)
        ps = pairs(model, ofw)
        total += len(ps)
        reviewed_eq += sum(1 for p in ps if p["reviewed"] and p["relationship"] == "equivalent")
        L.append(f"\n## {md(fw_short)} ↔ {md(other_short)} (`{sib.record_dir}/`)\n\n")
        if not ps:
            L.append(f"No mapping file yet. Copy the engine's `mappings/{file_name(model.engagement.get('framework', ''), ofw)}` "
                     "to the repository root to start.\n")
            continue
        L.append(f"| {md(fw_short)} | State here | {md(other_short)} | State there | Relationship | Reviewed | Note |\n"
                 "|---|---|---|---|---|---|---|\n")
        for p in sorted(ps, key=lambda x: (x["relationship"] != "equivalent", x["mine"])):
            L.append(f"| {md(p['mine'])} | {requirement_state(model, p['mine']) if p['mine'] in model.requirement_index else '?'} "
                     f"| {md(p['other'])} | {requirement_state(sib, p['other']) if p['other'] in sib.requirement_index else '?'} "
                     f"| {md(p['relationship'])} | {md(p['reviewed_by']) if p['reviewed'] else 'proposed'} | {md(p['note'])} |\n")
    (out / "cross-framework.md").write_text("".join(L), encoding="utf-8")
    return [("Cross-framework mappings", "cross-framework.md",
             f"{total} mapping(s) to other frameworks in this repository; {reviewed_eq} reviewed equivalent (evidence can be shared)")]
