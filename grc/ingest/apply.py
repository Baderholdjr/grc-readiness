"""Merge a draft into the engagement files, conservatively.

- Never overwrites human data: narrative fields are filled only when empty,
  control legs are only moved from not_started -> claimed.
- Appends gaps/evidence/inventory with new ids, de-duplicating near-matches.
- Writes YAML by appending text so existing comments survive.
- Returns a Markdown report for the PR.
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
from pathlib import Path

import yaml

from ..model import LEGS, Engagement, load_yaml


def _similar(a: str, b: str, cutoff: float) -> bool:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= cutoff


def _valid_date(s) -> str | None:
    try:
        return dt.date.fromisoformat(str(s)[:10]).isoformat() if s else None
    except ValueError:
        return None


def _next_id(prefix: str, used: set[str], width: int, start: int = 1) -> str:
    n = start
    while f"{prefix}-{n:0{width}d}" in used:
        n += 1
    new = f"{prefix}-{n:0{width}d}"
    used.add(new)
    return new


def _dump_item(item: dict, indent: int = 2) -> str:
    body = yaml.safe_dump([item], sort_keys=False, allow_unicode=True, width=120)
    return "".join(" " * indent + line if line.strip() else line for line in body.splitlines(keepends=True))


def _append_items(path: Path, key: str, items: list[tuple[dict, str]], header: str = "") -> None:
    if not items:
        return
    text = path.read_text(encoding="utf-8") if path.exists() else header + f"{key}:\n"
    text = re.sub(rf"^{key}:\s*\[\]\s*$", f"{key}:", text, flags=re.M)
    if not re.search(rf"^{key}:", text, flags=re.M):
        text += f"\n{key}:\n"
    if not text.endswith("\n"):
        text += "\n"
    text += "\n  # --- drafted by `grc ingest` " + dt.date.today().isoformat() + " (review before merging)\n"
    for item, source in items:
        text += f"  # source: {source[:200]}\n" + _dump_item(item)
    path.write_text(text, encoding="utf-8")


def replace_top_block(text: str, key: str, value) -> str:
    """Replace a top-level YAML key's block, keeping comments that precede the next key."""
    lines = text.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(rf"^{re.escape(key)}:", l)), None)
    new = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, width=120)
    if start is None:
        return text + ("" if text.endswith("\n") else "\n") + "\n" + new
    end = start + 1
    while end < len(lines) and not re.match(r"^[^\s#]", lines[end]):
        end += 1
    while end - 1 > start and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
        end -= 1
    return "".join(lines[:start]) + new + "".join(lines[end:])


def apply(model: Engagement, d: dict, label: str) -> str:
    edir = model.engagement_dir
    req_ids = set(model.requirement_index)
    rep = {"added_gaps": [], "added_evidence": [], "claims": [], "kept": [], "inventory": [], "narrative": [],
           "suggested": [], "dropped": []}

    def reqs_ok(lst, where):
        good = [r for r in lst if r in req_ids]
        bad = [r for r in lst if r not in req_ids]
        if bad:
            rep["dropped"].append(f"{where}: unknown requirement id(s) {', '.join(bad)}")
        return good

    # ---------------------------------------------------------- narrative
    eng_path = edir / "engagement.yaml"
    eng_text = eng_path.read_text(encoding="utf-8")
    e = model.engagement
    if d.get("client_overview"):
        if not e.get("client", {}).get("overview"):
            eng_text = replace_top_block(eng_text, "client", {"name": e["client"]["name"], "overview": d["client_overview"]})
            rep["narrative"].append("client.overview")
        else:
            rep["suggested"] += [f"client overview: {x}" for x in d["client_overview"]]
    if d.get("ai_usage"):
        if not e.get("ai_usage"):
            eng_text = replace_top_block(eng_text, "ai_usage", d["ai_usage"])
            rep["narrative"].append("ai_usage")
        else:
            rep["suggested"] += [f"AI usage: {x}" for x in d["ai_usage"]]
    if d.get("scope_statement"):
        if not (e.get("scope") or {}).get("statement"):
            eng_text = replace_top_block(eng_text, "scope", {**(e.get("scope") or {}), "statement": d["scope_statement"]})
            rep["narrative"].append("scope.statement")
        else:
            rep["suggested"].append(f"scope: {d['scope_statement']}")
    if d.get("in_place"):
        items = [{"foundation": x["foundation"], "examples": x["examples"],
                  "requirements": reqs_ok(x.get("requirements", []), f"in_place '{x['foundation']}'")}
                 for x in d["in_place"] if x.get("source")]
        if not e.get("in_place") and items:
            eng_text = replace_top_block(eng_text, "in_place", items)
            rep["narrative"].append("in_place")
        else:
            rep["suggested"] += [f"in place: {x['foundation']} — {x['examples']}" for x in items]
    eng_path.write_text(eng_text, encoding="utf-8")

    # --------------------------------------------------------------- gaps
    used_gap = {g["id"] for g in model.gaps}
    existing = [g["finding"] for g in model.gaps]
    new_gaps = []
    for g in d.get("gaps", []):
        if not g.get("source") or not g.get("finding"):
            rep["dropped"].append(f"gap without source: {g.get('finding', '')[:80]}")
            continue
        if any(_similar(g["finding"], f, 0.75) for f in existing):
            rep["kept"].append(f"gap already tracked: {g['finding'][:90]}")
            continue
        reqs = reqs_ok(g.get("requirements", []), f"gap '{g['area']}'")
        if not reqs:
            rep["dropped"].append(f"gap with no valid requirement: {g['area']}: {g['finding'][:80]}")
            continue
        item = {"id": _next_id("GAP", used_gap, 2), "area": g["area"], "finding": g["finding"], "requirements": reqs}
        if g.get("owner"):
            item["owner"] = g["owner"]
        if _valid_date(g.get("due")):
            item["due"] = _valid_date(g["due"])
        if g.get("phase") in model.phase_index:
            item["phase"] = g["phase"]
        item["severity"] = g.get("severity") if g.get("severity") in ("high", "medium", "low") else "medium"
        item["status"] = "open"
        new_gaps.append((item, g["source"]))
        existing.append(g["finding"])
        rep["added_gaps"].append(f"{item['id']} {item['area']}: {item['finding']} _(source: {g['source'][:120]})_")
    _append_items(edir / "gaps.yaml", "gaps", new_gaps)

    # ----------------------------------------------------------- evidence
    cfg = load_yaml(edir / "collectors.yaml") if (edir / "collectors.yaml").exists() else {}
    used_ev = {x["id"] for x in model.evidence} | {c["evidence"] for c in cfg.get("checks", []) or []}
    new_ev = []
    for ev in d.get("evidence", []):
        if not ev.get("source") or not ev.get("title"):
            continue
        if any(_similar(ev["title"], x["title"], 0.85) or (ev.get("location") and ev["location"] == x.get("location"))
               for x in model.evidence + [i for i, _ in new_ev]):
            rep["kept"].append(f"evidence already indexed: {ev['title'][:90]}")
            continue
        item = {"id": _next_id("EV", used_ev, 3), "title": ev["title"], "type": ev["type"],
                "location": ev.get("location") or f"intake/{label}", "collected": _valid_date(ev.get("date")) or dt.date.today().isoformat()}
        if ev.get("owner"):
            item["owner"] = ev["owner"]
        if ev.get("approved_by"):
            item["approved_by"] = ev["approved_by"]
            if _valid_date(ev.get("approved_on")):
                item["approved_on"] = _valid_date(ev["approved_on"])
        if str(ev.get("valid_for_days", "")).isdigit():
            item["valid_for_days"] = int(ev["valid_for_days"])
        item["notes"] = "Drafted by ingest; confirm location and approval before citing."
        new_ev.append((item, ev["source"]))
        rep["added_evidence"].append(f"{item['id']} {item['title']} ({item['type']})")
    _append_items(edir / "evidence" / "index.yaml", "evidence", new_ev)

    # ------------------------------------------------------------- claims
    touched: dict[str, dict] = {}
    for c in d.get("claims", []):
        rid, leg = c.get("requirement"), c.get("leg")
        if rid not in req_ids or leg not in LEGS or not c.get("source"):
            rep["dropped"].append(f"claim {rid}.{leg}: invalid id/leg or no source")
            continue
        data = touched.get(rid) or model.controls.get(rid)
        if data is None:
            rep["dropped"].append(f"claim {rid}: no control file (run `grc init`)")
            continue
        data = touched.setdefault(rid, data)
        cur = data.setdefault("test", {}).setdefault(leg, {"status": "not_started", "evidence": []})
        if cur.get("status") != "not_started":
            rep["kept"].append(f"{rid}.{leg} already '{cur.get('status')}' — client statement noted only: {c['statement'][:80]}")
            continue
        cur["status"] = "claimed"
        cur["note"] = f"Client states: {c['statement'][:220]} [source: {c['source'][:160]}]"
        if c.get("owner") and not data.get("owner"):
            data["owner"] = c["owner"]
        rep["claims"].append(f"{rid}.{leg} → claimed: {c['statement'][:110]}")
    for rid, data in touched.items():
        path = model.control_files[rid]
        header = "".join(l for l in path.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("#"))
        path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")

    # ---------------------------------------------------------- inventory
    inv_path = edir / "inventory.yaml"
    names = {i["name"].lower() for i in model.inventory}
    used_inv = {i["id"] for i in model.inventory}
    new_inv = []
    for it in d.get("inventory", []):
        if not it.get("name") or it["name"].lower() in names or not it.get("source"):
            continue
        item = {"id": _next_id("INV", used_inv, 3), "name": it["name"], "kind": it["kind"], "in_scope": True}
        for k in ("owner", "risk_tier", "description"):
            if it.get(k):
                item[k] = it[k]
        item["source"] = it["source"][:200]
        names.add(it["name"].lower())
        new_inv.append((item, it["source"]))
        rep["inventory"].append(f"{item['id']} {item['name']} ({item['kind']})")
    _append_items(inv_path, "items", new_inv,
                  header="# AI inventory: systems, SDLC tools, infrastructure, models, datasets (A.4.x).\n"
                         "# Drafted by `grc ingest`; owners keep it current through PRs.\n")

    return render_report(rep, d.get("open_questions", []), label)


def render_report(rep: dict, questions: list[str], label: str) -> str:
    def section(title, items, limit=60):
        if not items:
            return ""
        more = f"\n- … and {len(items) - limit} more" if len(items) > limit else ""
        return f"\n### {title} ({len(items)})\n" + "\n".join(f"- {x}" for x in items[:limit]) + more + "\n"
    out = [f"## Ingestion draft — {label}\n",
           "> Drafted automatically from client documents. **Every item is a hypothesis until reviewed.** "
           "Nothing has been marked `verified`; client statements are recorded as `claimed`.\n"]
    out.append(section("Engagement profile fields filled", rep["narrative"]))
    out.append(section("New gaps", rep["added_gaps"]))
    out.append(section("New evidence pointers", rep["added_evidence"]))
    out.append(section("Control legs moved to 'claimed'", rep["claims"]))
    out.append(section("Inventory items", rep["inventory"]))
    out.append(section("Open questions for the analyst", questions))
    out.append(section("Suggested updates not applied (field already set)", rep["suggested"]))
    out.append(section("Already tracked / unchanged", rep["kept"], 25))
    out.append(section("Dropped (invalid or unsourced)", rep["dropped"], 25))
    return "".join(out)
