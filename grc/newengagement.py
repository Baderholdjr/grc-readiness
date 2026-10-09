"""Start a new engagement: wipe the example record and scaffold a clean one.

    python -m grc new-engagement --client "Acme Corp" --start 2026-11-02 \
        --stage1 2027-03-15 --stage2 2027-05-10 --hours 200 --confirm-reset

Keeps: the engine, workflows, and any local framework/template overrides.
Resets: everything under engagement/, plus intake/ (except its README).
Phases are computed from the dates and can be edited afterwards.
"""
from __future__ import annotations

import calendar
import datetime as dt
import shutil
from pathlib import Path

import yaml

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
PREP_PHASES = [("validate", 0.20), ("governance", 0.25), ("implement", 0.30), ("test", 0.25)]


def _label(start: dt.date, end: dt.date) -> str:
    a, b = f"{MONTHS[start.month - 1]}", f"{MONTHS[end.month - 1]}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{a} {start.year}"
    if start.year == end.year:
        return f"{a}–{b} {end.year}"
    return f"{a} {start.year}–{b} {end.year}"


def _month_end(d: dt.date) -> dt.date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def compute_phases(start: dt.date, stage1: dt.date, stage2: dt.date) -> list[dict]:
    if not start < stage1 < stage2:
        raise ValueError("dates must satisfy start < stage1 < stage2")
    prep_end = stage1.replace(day=1) - dt.timedelta(days=1)
    total = (prep_end - start).days + 1
    if total < 56:
        raise ValueError("leave at least 8 weeks between the start and the Stage 1 month")
    phases, cursor = [], start
    for i, (pid, share) in enumerate(PREP_PHASES):
        end = prep_end if i == len(PREP_PHASES) - 1 else cursor + dt.timedelta(days=max(7, round(total * share)) - 1)
        phases.append({"id": pid, "label": _label(cursor, end), "start": cursor, "end": end})
        cursor = end + dt.timedelta(days=1)
    s1_end = _month_end(stage1)
    phases.append({"id": "stage1", "label": _label(stage1.replace(day=1), s1_end), "start": stage1.replace(day=1), "end": s1_end})
    s2_end = _month_end(stage2 + dt.timedelta(days=21))
    phases.append({"id": "stage2", "label": _label(s1_end + dt.timedelta(days=1), s2_end),
                   "start": s1_end + dt.timedelta(days=1), "end": s2_end})
    return phases


ENGAGEMENT_HEADER = """# Engagement definition - the source of truth for the analyst brief.
# Change it through a pull request; CI validates and regenerates every report.
# "{client}" anywhere in text is replaced with client.name.
# Empty narrative fields (overview, ai_usage, scope, in_place) are filled by
# `grc ingest` from client documents, or by hand.

"""

COLLECTORS = """# Evidence collectors - see docs/AUTOMATION.md.
# Each check refreshes ONE machine-owned evidence item (ids EV-100..EV-199).
# `supports` lists the control legs the evidence backs ("<requirement>:<leg>");
# the refresh PR cites passing evidence there and proposes 'partial' for legs
# that were not_started/claimed. It never sets 'verified'.

enabled: true
defaults:
  valid_for_days: 30

checks:
  # Self-checks on this engagement repo (work with no setup).
  - evidence: EV-101
    title: "Engagement repo: main branch protection"
    collector: github.branch_protection
    params: {repo: "${GITHUB_REPOSITORY}", branch: main, min_approvals: 1, require_code_owner_review: true, required_checks: ["validate / validate"]}
    type: config
    supports: ["7.5:implemented"]
  - evidence: EV-102
    title: "Engagement repo: independent review of merged changes (90 days)"
    collector: github.pr_reviews
    params: {repo: "${GITHUB_REPOSITORY}", base: main, days: 90}
    type: record
    supports: ["7.5:evidenced"]

  # Add client checks here (GitHub, Drata, AWS/Azure/GCP). Examples:
  # - evidence: EV-110
  #   title: Model release gate runs and passes
  #   collector: github.workflow_runs
  #   params: {repo: client-org/ml-release, workflow: release-gate.yml, days: 30}
  #   type: record
  #   supports: ["A.6.2.4:implemented", "A.6.2.4:evidenced"]
"""

OWNERS = """# Who is accountable for what. Control and gap `owner` fields use these role
# names; the GitHub users listed here are assigned to the matching Issues, get
# overdue reminders, and become required reviewers for those control files
# (`python -m grc codeowners`). Users need access to this repository.

owners:
  - role: Engagement Lead
    github: []
  # - role: VP Engineering
  #   github: [client-vp-eng]
  #   email: vp@example.com
"""


def reset(engagement_dir: Path, intake_dir: Path, client: str, start: dt.date, stage1: dt.date,
          stage2: dt.date, hours: float, framework: str = "iso42001", lead: str | None = None) -> list[str]:
    log = []
    phases = compute_phases(start, stage1, stage2)
    if engagement_dir.exists():
        shutil.rmtree(engagement_dir)
        log.append(f"removed {engagement_dir}")
    (engagement_dir / "controls").mkdir(parents=True)
    (engagement_dir / "evidence").mkdir()
    (engagement_dir / "workpapers").mkdir()

    eng = {
        "framework": framework,
        "client": {"name": client, "overview": []},
        "subtitle": f"Analyst Orientation | Certification readiness and gap closure | {start.year}-{stage2.year}",
        "ai_usage": [],
        "scope": {},
        "in_place": [],
        "budget": {"hours_total": hours, "hours_used": 0, "note": "protect time for internal audit and certification support."},
        "dates": {"start": start, "stage1": stage1, "stage2": stage2},
        "certification_body": "TBD",
        "team": {"engagement_lead": lead or "Engagement Lead", "analysts": []},
        "phases": phases,
        "evidence_expiry_warning_days": 30,
        "ingest": {"ai_drafting": False, "model": "claude-sonnet-5-5"},
    }
    (engagement_dir / "engagement.yaml").write_text(
        ENGAGEMENT_HEADER + yaml.safe_dump(eng, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    (engagement_dir / "gaps.yaml").write_text(
        "# Gap register. Mirrored to GitHub Issues by `grc sync-issues`. Edit here, not in GitHub.\n"
        "# Closing a gap requires closure_evidence (CI enforces).\n\ngaps: []\n", encoding="utf-8")
    (engagement_dir / "evidence" / "index.yaml").write_text(
        "# Evidence index: POINTERS to artifacts held in the client's systems (entered by people).\n"
        "# Collector-produced evidence lives in collected.yaml (machine-owned).\n\nevidence: []\n", encoding="utf-8")
    (engagement_dir / "collectors.yaml").write_text(COLLECTORS, encoding="utf-8")
    (engagement_dir / "owners.yaml").write_text(OWNERS, encoding="utf-8")
    (engagement_dir / "workpapers" / "README.md").write_text(
        "# Workpapers\n\nAnalyst test workpapers (non-confidential). Reference them from evidence/index.yaml "
        "as `type: test`, `sample` or `interview`.\n", encoding="utf-8")
    log.append(f"wrote engagement for '{client}' with {len(phases)} phases")

    if intake_dir.exists():
        for p in intake_dir.iterdir():
            if p.name == "README.md":
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        log.append(f"cleared {intake_dir} (kept README.md)")
    return log
