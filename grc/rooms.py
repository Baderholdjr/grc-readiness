"""Read-only rooms: the executive dashboard and the auditor room (docs/ROOMS.md, docs/THREAT-MODEL.md).

Each is a Cloudflare Worker bundle built from the merged record, behind its own Cloudflare Access application:

  executive/   summary numbers only: readiness, days to the audits, open gaps by severity, the top gaps (area,
               severity, due date), and a weekly trend read from the repository's own history. No requirement
               text, no evidence, no document text: what isn't in data.json can't be read from the page.
  auditor/     the auditor package (grc package) as downloads, with its manifest checksums, for named auditors
               between the dates in engagement.yaml (checked in the Worker too).

Nothing here writes to the record, and nothing in the rooms can.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess  # nosec B404 - fixed argv (git), no shell
import tarfile
import tempfile
from pathlib import Path

from .model import ENGINE, Engagement, load

SITE = ENGINE / "rooms"
SEV = {"high": 0, "medium": 1, "low": 2}
ASSET_LIMIT = 25 * 1024 * 1024    # Cloudflare Workers static assets: largest file


def _cfg(model: Engagement, room: str) -> dict:
    return dict(((model.engagement.get("rooms") or {}).get(room)) or {})


def _toml(v) -> str:
    from .portal import _toml as t
    return t(v)


def worker_name(model: Engagement, room: str) -> str:
    name = str(_cfg(model, room).get("worker_name") or "")
    if not name:
        from .portal import worker_name as portal_name
        base = portal_name(model).removeprefix("grc-portal-")
        name = f"grc-{room}-{base}"
    return name.strip("-")[:63].strip("-")


# ------------------------------------------------------------------ executive data
def summary(model: Engagement) -> dict:
    """The numbers the executive dashboard shows, and nothing more."""
    from .rules import metrics
    m = metrics(model)
    dates = model.engagement.get("dates") or {}

    def days(k):
        d = dates.get(k)
        try:
            return (dt.date.fromisoformat(str(d)) - model.today).days if d else None
        except ValueError:
            return None
    gaps = [g for g in model.gaps if isinstance(g, dict) and g.get("status") in ("open", "in_progress") and model.gap_in_scope(g)]
    by_sev = {s: sum(1 for g in gaps if g.get("severity") == s) for s in ("high", "medium", "low")}
    by_sev["unrated"] = len(gaps) - sum(by_sev.values())
    overdue = [g for g in gaps if g.get("due") and str(g["due"]) < model.today.isoformat()]
    top = sorted(gaps, key=lambda g: (SEV.get(g.get("severity"), 3), str(g.get("due") or "9999"), str(g.get("id"))))[:5]
    return {
        "as_of": model.today.isoformat(),
        "framework": m["framework"],
        "ready": m["requirements_ready"],
        "applicable": m["requirements_applicable"],
        "ready_pct": round(100 * m["requirements_ready"] / m["requirements_applicable"]) if m["requirements_applicable"] else 0,
        "checks_pct": m["legs_verified_pct"],
        "days_to_stage1": days("stage1"),
        "days_to_stage2": days("stage2"),
        "gaps_open": len(gaps),
        "gaps_overdue": len(overdue),
        "gaps_by_severity": by_sev,
        "evidence_stale": len(m["evidence_stale"]),
        # an area label, a severity and a date: the gap's finding text and requirements stay out
        "top_gaps": [{"area": str(g.get("area") or "")[:80], "severity": g.get("severity") or "unrated",
                      "due": str(g.get("due") or ""), "status": g.get("status"),
                      "overdue": bool(g.get("due") and str(g["due"]) < model.today.isoformat())} for g in top],
    }


def _git(repo: Path, *args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=60)  # nosec B603 B607
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else None


def trend(model: Engagement, weeks: int = 12) -> list[dict]:
    """Readiness at the end of each of the last `weeks` weeks, read from the record as it was committed then
    (git history: GitHub is the system of record). Weeks before the record existed, or that can't be read, are
    left out. Needs the repository's history (a full clone in CI)."""
    root, edir = model.root, model.engagement_dir
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return []
    top_p = Path(top)
    try:
        rel = edir.resolve().relative_to(top_p.resolve()).as_posix()
    except ValueError:
        return []
    points = []
    for w in range(weeks, 0, -1):
        day = model.today - dt.timedelta(days=7 * w)
        sha = _git(top_p, "rev-list", "-1", f"--before={day.isoformat()}T23:59:59Z", "HEAD")
        if not sha:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            tar = Path(tmp) / "r.tar"
            paths = [rel] + [p for p in ("frameworks",) if _git(top_p, "cat-file", "-e", f"{sha}:{p}") is not None]
            if _git(top_p, "cat-file", "-e", f"{sha}:{rel}/engagement.yaml") is None:
                continue
            if _git(top_p, "archive", "--format=tar", "-o", str(tar), sha, "--", *paths) is None:
                continue
            with tarfile.open(tar) as t:
                t.extractall(Path(tmp) / "x", filter="data")
            try:
                past = load(Path(tmp) / "x" / rel, today=day)
                s = summary(past)
            except Exception:  # noqa: BLE001 - an old record that no longer loads is simply not a point
                continue
        points.append({"week": day.isoformat(), "ready_pct": s["ready_pct"], "checks_pct": s["checks_pct"],
                       "gaps_open": s["gaps_open"]})
    now = summary(model)
    points.append({"week": model.today.isoformat(), "ready_pct": now["ready_pct"], "checks_pct": now["checks_pct"],
                   "gaps_open": now["gaps_open"]})
    return points


# ------------------------------------------------------------------ bundles
def _wrangler(model: Engagement, room: str, extra_vars: list[str]) -> str:
    cfg = _cfg(model, room)
    team = str(cfg.get("access_team") or (model.engagement.get("portal") or {}).get("access_team") or "")
    domains = ",".join(str(x).lower() for x in cfg.get("allowed_email_domains") or [])
    return "\n".join([
        f"# Generated by `grc rooms`. Change the settings in engagement.yaml (rooms.{room}:), not here.",
        f"name = {_toml(worker_name(model, room))}",
        'main = "worker.js"',
        'compatibility_date = "2025-06-01"',
        "workers_dev = true",
        "",
        "[observability]",
        "enabled = true               # Worker logs: who viewed or downloaded what, and when",
        "",
        "[assets]",
        'directory = "public"',
        'binding = "ASSETS"',
        "run_worker_first = true      # every request, pages and files included, passes the login check",
        "",
        "[vars]",
        f"ROOM = {_toml(room)}",
        f"ACCESS_TEAM = {_toml(team)}",
        f"ACCESS_AUD = {_toml(cfg.get('access_aud') or '')}",
        f"ALLOWED_EMAIL_DOMAINS = {_toml(domains)}",
        *extra_vars,
        "",
    ])


def _common(out: Path, page: str) -> Path:
    if out.exists():
        shutil.rmtree(out)
    pub = out / "public"
    pub.mkdir(parents=True)
    shutil.copyfile(SITE / "worker.js", out / "worker.js")
    shutil.copyfile(ENGINE / "portal" / "access.js", out / "access.js")
    for name in ("rooms.css", f"{page}.html", f"{page}.js"):
        shutil.copyfile(SITE / "site" / name, pub / ("index.html" if name.endswith(".html") else name))
    return pub


def build_executive(model: Engagement, out: Path) -> list[str]:
    pub = _common(Path(out), "executive")
    d = {"client": model.client, **summary(model), "trend": trend(model)}
    (pub / "data.json").write_text(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (Path(out) / "wrangler.toml").write_text(_wrangler(model, "executive", []), encoding="utf-8")
    log = [f"executive dashboard written to {out}/ (worker {worker_name(model, 'executive')}): "
           f"{d['ready']} of {d['applicable']} ready, {d['gaps_open']} open gap(s), {len(d['trend'])} trend point(s)"]
    if not _cfg(model, "executive").get("access_aud"):
        log.append("  note: rooms.executive.access_aud is not set - the deployed dashboard refuses everyone until it is")
    return log


def auditor_window(model: Engagement) -> tuple[str, str, list[str]]:
    cfg = _cfg(model, "auditor")
    auditors = sorted({str(a).strip().lower() for a in cfg.get("auditors") or [] if str(a).strip()})
    return str(cfg.get("opens") or ""), str(cfg.get("closes") or ""), auditors


def build_auditor(model: Engagement, out: Path, force: bool = False) -> list[str]:
    from . import package
    out = Path(out)
    pub = _common(out, "auditor")
    files = pub / "files"
    with tempfile.TemporaryDirectory() as tmp:
        package.build(model, Path(tmp), label="auditor-room", force=force)
        zips = sorted(Path(tmp).glob("*.zip"))
        if len(zips) != 1:
            raise ValueError("the auditor package did not build")
        zip_path = zips[0]
        files.mkdir()
        dest_zip = files / zip_path.name
        shutil.copyfile(zip_path, dest_zip)
        # each file of the package too, so an auditor can take one without the whole archive
        shutil.copytree(Path(tmp) / zip_path.stem, files / zip_path.stem)
        manifest = json.loads((files / zip_path.stem / "manifest.json").read_text(encoding="utf-8"))
    opens, closes, auditors = auditor_window(model)
    d = {"client": model.client, "framework": model.catalog["framework"]["short_name"], "as_of": model.today.isoformat(),
         "opens": opens, "closes": closes, "package": {"name": dest_zip.name, "bytes": dest_zip.stat().st_size,
                                                       "sha256": package._sha(dest_zip)},
         "folder": zip_path.stem, "commit": manifest.get("commit"), "engine": manifest.get("engine"),
         "files": [{"path": p, **v} for p, v in sorted((manifest.get("files") or {}).items())]}
    (pub / "room.json").write_text(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (out / "wrangler.toml").write_text(_wrangler(model, "auditor", [
        f"AUDITORS = {_toml(','.join(auditors))}", f"ROOM_OPENS = {_toml(opens)}", f"ROOM_CLOSES = {_toml(closes)}"]),
        encoding="utf-8")
    log = [f"auditor room written to {out}/ (worker {worker_name(model, 'auditor')}): {dest_zip.name}, "
           f"{len(d['files'])} file(s) listed; open {opens or '?'} to {closes or '?'} for {len(auditors)} auditor(s)"]
    big = [p.relative_to(pub).as_posix() for p in pub.rglob("*") if p.is_file() and p.stat().st_size > ASSET_LIMIT]
    if big:
        log.append(f"  note: Cloudflare serves files up to 25 MiB; too large to deploy: {', '.join(big)}")
    if not (opens and closes and auditors):
        log.append("  note: rooms.auditor needs opens, closes and auditors - the deployed room refuses everyone until set")
    if not _cfg(model, "auditor").get("access_aud"):
        log.append("  note: rooms.auditor.access_aud is not set - the deployed room refuses everyone until it is")
    return log


def check(model: Engagement) -> list:
    """W180/W181: auditor-room settings that would leave it shut or open too long."""
    from .rules import Finding
    out = []
    cfg = _cfg(model, "auditor")
    if not cfg.get("enabled"):
        return out
    opens, closes, auditors = auditor_window(model)
    if not (opens and closes and auditors):
        out.append(Finding("warning", "W180", "rooms.auditor is enabled but needs opens, closes and at least one "
                                              "auditor; until then the room refuses everyone", "engagement.yaml"))
    elif closes < opens:
        out.append(Finding("warning", "W180", f"rooms.auditor closes ({closes}) before it opens ({opens})", "engagement.yaml"))
    elif (dt.date.fromisoformat(closes) - dt.date.fromisoformat(opens)).days > 120:
        out.append(Finding("warning", "W181", f"rooms.auditor stays open {opens} to {closes}, over 120 days: keep the "
                                              "window to the audit", "engagement.yaml"))
    return out


