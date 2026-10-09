"""Run configured evidence collectors and refresh machine-owned evidence.

  engagement/collectors.yaml               what to collect (human-owned config)
  engagement/evidence/collected/<ID>.json  latest snapshot per check (history = git log)
  engagement/evidence/collected.yaml       evidence index entries written by collectors

A refresh never changes a control's status. It only updates evidence; CI then
re-evaluates every control that cites that evidence (a failing check downgrades
any 'verified' leg relying on it), and a human merges the refresh PR.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

from .collectors import CheckResult, run_check
from .collectors.base import ERROR, FAIL, PASS, SKIPPED, as_jsonable, utcnow
from .model import LEGS, Engagement, load_yaml

HEADER = ("# MACHINE-OWNED: written by `python -m grc collect`. Do not edit by hand.\n"
          "# Configure checks in engagement/collectors.yaml. Snapshots live in evidence/collected/.\n")
ICON = {PASS: "✅", FAIL: "❌", ERROR: "⚠️", SKIPPED: "⏭️"}


ALLOWED_VARS = {"GITHUB_REPOSITORY", "GITHUB_REPOSITORY_OWNER"}


def expand(value):
    """Expand ${VAR} from the environment in string params (e.g. ${GITHUB_REPOSITORY})."""
    import os
    import re
    if isinstance(value, str):
        # Only non-secret variables may be expanded (snapshots and PRs are committed).
        def sub(m):
            name = m.group(1)
            if name in ALLOWED_VARS or name.startswith("GRC_VAR_"):
                return os.environ.get(name, m.group(0))
            return m.group(0)
        return re.sub(r"\$\{([A-Z0-9_]+)\}", sub, value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def load_config(edir: Path) -> dict:
    p = edir / "collectors.yaml"
    return load_yaml(p) if p.exists() else {}


def _cited_by(model: Engagement) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for cid, c in model.controls.items():
        for k in LEGS:
            leg = c.get("test", {}).get(k, {})
            for e in leg.get("evidence", []) or []:
                out.setdefault(e, []).append(f"{cid}·{k}({leg.get('status')})")
    return out


def run(model: Engagement, only: list[str] | None = None, now: dt.datetime | None = None,
        write: bool = True) -> tuple[list[dict], str]:
    from . import sandbox
    sandbox.configure(model)
    tag = "[SANDBOX] " if sandbox.active() else ""
    edir = model.engagement_dir
    cfg = load_config(edir)
    now = now or utcnow()
    if not cfg.get("enabled", False):
        return [], "Collectors are disabled (`enabled: false` in engagement/collectors.yaml).\n"
    defaults = cfg.get("defaults", {}) or {}
    collected_path = edir / "evidence" / "collected.yaml"
    existing = {e["id"]: e for e in ((load_yaml(collected_path).get("evidence") or []) if collected_path.exists() else [])}
    snap_dir = edir / "evidence" / "collected"
    results = []
    for check in cfg.get("checks", []) or []:
        ev_id = check["evidence"]
        if only and ev_id not in only:
            continue
        if check.get("enabled", True) is False:
            continue
        params = expand(check.get("params", {}) or {})
        unresolved = [v for v in params.values() if isinstance(v, str) and "${" in v]
        res: CheckResult = (run_check(check["collector"], params) if not unresolved else
                            CheckResult(SKIPPED, f"Skipped: unresolved parameter {unresolved[0]}"))
        prev = existing.get(ev_id)
        row = {"evidence": ev_id, "title": check["title"], "collector": check["collector"], "result": res.result,
               "summary": res.summary, "findings": res.findings,
               "previous": prev.get("result") if prev else None, "requirements": check.get("requirements", []),
               "supports": check.get("supports", [])}
        results.append(row)
        if res.result == SKIPPED:
            continue
        if res.result == ERROR and prev:
            # don't refresh the date on an error; record that the latest attempt failed
            prev["result"] = ERROR
            prev["notes"] = f"Latest collection attempt {now.date()} errored: {res.summary}"
            continue
        snapshot = {"evidence": ev_id, "sandbox": bool(tag), "title": check["title"], "collector": check["collector"],
                    "params": params, "collected_at": now.isoformat(), "result": res.result,
                    "summary": res.summary, "findings": res.findings, "details": as_jsonable(res.details),
                    "sha256": res.digest()}
        rel = f"engagement/evidence/collected/{ev_id}.json"
        if write:
            snap_dir.mkdir(parents=True, exist_ok=True)
            (snap_dir / f"{ev_id}.json").write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        existing[ev_id] = {
            "id": ev_id, "title": check["title"], "type": check.get("type", "record"), "location": rel,
            "owner": check.get("owner", "collector"), "collected": now.date(),
            "valid_for_days": int(check.get("valid_for_days", defaults.get("valid_for_days", 30))),
            "sha256": res.digest(), "collector": check["collector"], "result": res.result,
            "notes": tag + res.summary + (f" | {'; '.join(res.findings)}" if res.findings else ""),
        }
    claimed_before = {(cid, leg): (v.get("note") or "") for cid, c in model.controls.items()
                      for leg, v in (c.get("test") or {}).items() if v.get("status") == "claimed"}
    links = link_evidence(model, cfg, results, write=write)
    if write:
        entries = [existing[k] for k in sorted(existing)]
        collected_path.parent.mkdir(parents=True, exist_ok=True)
        collected_path.write_text(HEADER + yaml.safe_dump({"evidence": entries}, sort_keys=False, allow_unicode=True,
                                                         width=140), encoding="utf-8")
    out = report(model, results, now, links, claimed_before)
    if tag:
        out = ("> ⚠️ **SANDBOX MODE.** Drata, cloud and AI results below come from canned test data in "
               "`sandbox/`, not from real client systems. GitHub checks are real.\n\n") + out
    return results, out


def link_evidence(model: Engagement, cfg: dict, results: list[dict], write: bool = True) -> list[str]:
    """Cite passing collector evidence on the legs listed in `supports`.

    Adds the evidence id to the leg and moves not_started/claimed legs to 'partial'
    (machine evidence alone never makes a leg 'verified'). Failing evidence is left
    cited - the rules then treat it as non-current. Changes land in the refresh PR.
    """
    import yaml
    passing = {r["evidence"] for r in results if r["result"] == PASS}
    touched: dict[str, dict] = {}
    log: list[str] = []
    for check in cfg.get("checks", []) or []:
        ev = check["evidence"]
        if ev not in passing:
            continue
        for ref in check.get("supports", []) or []:
            rid, leg = ref.rsplit(":", 1)
            if rid not in model.controls or leg not in LEGS or not model.is_applicable(rid):
                log.append(f"⚠️ {ev} → {ref}: no applicable control/leg with that id")
                continue
            data = touched.get(rid) or model.controls[rid]
            cur = data.setdefault("test", {}).setdefault(leg, {"status": "not_started", "evidence": []})
            cur.setdefault("evidence", [])
            changed = []
            if ev not in cur["evidence"]:
                cur["evidence"].append(ev)
                changed.append("cited")
            if cur.get("status") in ("not_started", "claimed") and not (data.get("owner") or "").strip():
                changed.append("status unchanged: control has no owner yet")
            elif cur.get("status") in ("not_started", "claimed"):
                before = cur.get("status")
                cur["status"] = "partial"
                note = f"Auto: collector evidence {ev} passing. Analyst to confirm before 'verified'."
                cur["note"] = f"{cur['note']} | {note}" if cur.get("note") else note
                changed.append(f"{before} → partial")
            if changed:
                touched[rid] = data
                log.append(f"{ev} → {rid}·{leg}: {', '.join(changed)}")
    if write:
        for rid, data in touched.items():
            path = model.control_files[rid]
            header = "".join(l for l in path.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("#"))
            path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return log


def report(model: Engagement, results: list[dict], now: dt.datetime, links: list[str] | None = None,
           claimed: dict | None = None) -> str:
    cited = _cited_by(model)
    lines = [f"## Evidence collection — {now.strftime('%Y-%m-%d %H:%M UTC')}\n",
             "| Evidence | Check | Result | Summary | Cited by |", "|---|---|---|---|---|"]
    regressions, unused = [], []
    for r in results:
        change = ""
        if r["previous"] == PASS and r["result"] in (FAIL, ERROR):
            change = " **(regressed)**"
            regressions.append(r)
        by = ", ".join(cited.get(r["evidence"], [])) or "—"
        if r["result"] == PASS and r["evidence"] not in cited:
            unused.append(r)
        lines.append(f"| {r['evidence']} | `{r['collector']}` | {ICON.get(r['result'], '')} {r['result']}{change} | "
                     f"{r['summary']} | {by} |")
    if regressions:
        lines.append("\n### ❌ Regressions\nThese checks passed last time and now fail. Any control leg citing them "
                     "is downgraded by CI until fixed.\n")
        for r in regressions:
            lines.append(f"- **{r['evidence']} {r['title']}**: " + "; ".join(r["findings"] or [r["summary"]]))
    contradictions = []
    for r in results:
        if r["result"] != FAIL:
            continue
        reqs = {ref.rsplit(":", 1)[0] for ref in r.get("supports", [])} | set(r.get("requirements", []))
        for (rid, leg), note in sorted((claimed or {}).items()):
            if rid in reqs:
                    claim = note.replace("Client states: ", "")[:140]
                    contradictions.append(f"**{rid}·{leg}** — client claims: _{claim}_ → **{r['evidence']}** says: "
                                          + "; ".join(r["findings"] or [r["summary"]]))
    if contradictions:
        lines.append("\n### ⚠️ Evidence contradicts a client claim\nThese legs were `claimed` by the client. "
                     "Raise them with the owner before relying on the claim.\n")
        lines += [f"- {x}" for x in contradictions]
    fails = [r for r in results if r["result"] == FAIL and r not in regressions]
    if fails:
        lines.append("\n### Failing checks\n")
        for r in fails:
            lines.append(f"- **{r['evidence']} {r['title']}**: " + "; ".join(r["findings"] or [r["summary"]]))
    if links:
        lines.append("\n### Linked to controls by this refresh\nMerging this PR records these citations. "
                     "Legs move to `partial` at most; an analyst confirms `verified`.\n")
        lines += [f"- {x}" for x in links]
    linked = {x.split(" → ")[0] for x in links or []}
    unused = [r for r in unused if r["evidence"] not in linked]
    if unused:
        lines.append("\n### Passing evidence not yet cited\nAdd `supports: [\"<requirement>:<leg>\"]` to these checks in "
                     "collectors.yaml to link them automatically.\n")
        for r in unused:
            reqs = ", ".join(r["requirements"]) or "(no requirement hint)"
            lines.append(f"- **{r['evidence']}** {r['title']} → suggested: {reqs}")
    skipped = [r for r in results if r["result"] == SKIPPED]
    if skipped:
        lines.append("\n<details><summary>Skipped (credentials not configured)</summary>\n")
        lines += [f"- {r['evidence']} `{r['collector']}`: {r['summary']}" for r in skipped]
        lines.append("\n</details>")
    lines.append("\n_Merging this PR records the refreshed evidence and the citations above. "
                 "Nothing is ever marked `verified` automatically._\n")
    return "\n".join(lines) + "\n"
