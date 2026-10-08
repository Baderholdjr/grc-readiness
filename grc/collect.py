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
               "previous": prev.get("result") if prev else None, "requirements": check.get("requirements", [])}
        results.append(row)
        if res.result == SKIPPED:
            continue
        if res.result == ERROR and prev:
            # don't refresh the date on an error; record that the latest attempt failed
            prev["result"] = ERROR
            prev["notes"] = f"Latest collection attempt {now.date()} errored: {res.summary}"
            continue
        snapshot = {"evidence": ev_id, "title": check["title"], "collector": check["collector"],
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
            "notes": res.summary + (f" | {'; '.join(res.findings)}" if res.findings else ""),
        }
    if write:
        entries = [existing[k] for k in sorted(existing)]
        collected_path.parent.mkdir(parents=True, exist_ok=True)
        collected_path.write_text(HEADER + yaml.safe_dump({"evidence": entries}, sort_keys=False, allow_unicode=True,
                                                         width=140), encoding="utf-8")
    return results, report(model, results, now)


def report(model: Engagement, results: list[dict], now: dt.datetime) -> str:
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
    fails = [r for r in results if r["result"] == FAIL and r not in regressions]
    if fails:
        lines.append("\n### Failing checks\n")
        for r in fails:
            lines.append(f"- **{r['evidence']} {r['title']}**: " + "; ".join(r["findings"] or [r["summary"]]))
    if unused:
        lines.append("\n### Passing evidence not yet cited\nAn analyst can cite these in the control files "
                     "(in a reviewed PR) to support the legs below.\n")
        for r in unused:
            reqs = ", ".join(r["requirements"]) or "(no requirement hint)"
            lines.append(f"- **{r['evidence']}** {r['title']} → suggested: {reqs}")
    skipped = [r for r in results if r["result"] == SKIPPED]
    if skipped:
        lines.append("\n<details><summary>Skipped (credentials not configured)</summary>\n")
        lines += [f"- {r['evidence']} `{r['collector']}`: {r['summary']}" for r in skipped]
        lines.append("\n</details>")
    lines.append("\n_Merging this PR records the refreshed evidence. It does not change any control status._\n")
    return "\n".join(lines) + "\n"
