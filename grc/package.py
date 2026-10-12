"""Auditor package: one reproducible, checksummed bundle of the record as of a commit.

    python -m grc package --out dist [--label stage1]

Produces dist/<client>-<framework>-<label>-<as-of>/ and the same as a .zip:

    00-auditor-index.pdf / .md      how to read the package; requirement -> evidence traceability; contents
    01-overview/                    brief (PDF, Word), readiness status, gap register
    02-applicability/               Statement of Applicability, control matrix (PDF, CSV)
    03-documented-information/      policy and procedure register; each document (PDF, Word)
    04-risk-and-impact/             AI impact assessments
    05-evidence/                    evidence index (PDF, CSV) and collector snapshots (JSON)
    06-internal-audit/              audit programme, audit reports, corrective actions
    07-management-review/           review records and frozen input packs
    08-source-record/               the engagement YAML/Markdown the reports were generated from
    manifest.json, SHA256SUMS       every file with its SHA-256

The same commit always produces the same bytes (fixed timestamps; deterministic PDF, Word and zip),
so an auditor can re-verify every checksum, or regenerate the package and compare.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import __version__
from .model import LEGS, Engagement

SECTIONS = [
    ("01-overview", "Overview", ("brief", "status", "gap-register")),
    ("02-applicability", "Applicability", ("soa", "control-matrix")),
    ("03-documented-information", "Documented information", ("documents", "doc-")),
    ("04-risk-and-impact", "Risk and impact", ("impact-assessments", "ia-")),
    ("05-evidence", "Evidence", ("evidence-index",)),
    ("06-internal-audit", "Internal audit and corrective action", ("internal-audit", "audit-", "corrective-actions")),
    ("07-management-review", "Management review", ("management-reviews", "mr-")),
]
SKIP = {"README.md"}   # the landing page links to the live reports; the index replaces it here


def commit_sha(model: Engagement) -> str:
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if sha:
        return sha
    try:
        return subprocess.run(["git", "-C", str(model.root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "uncommitted"
    except Exception:
        return "uncommitted"


def section_for(name: str) -> str:
    stem = name.rsplit(".", 1)[0]
    for folder, _, prefixes in SECTIONS:
        for p in prefixes:
            if stem == p or (p.endswith("-") and stem.startswith(p)) or stem.startswith(p + "-") or stem.startswith(p + "."):
                return folder
    if name.endswith("-brief.docx"):
        return "01-overview"
    return "01-overview"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell(v) -> str:
    return str(v if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def _table(headers, rows) -> str:
    if not rows:
        return "_None._\n"
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
                     + ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]) + "\n"


def where_in_package(eid: str, files: set[str]) -> str | None:
    """Package path for evidence the package itself contains (documents, assessments, reviews, snapshots)."""
    candidates = {"DOC-": f"03-documented-information/doc-{eid}.pdf", "IA-": f"04-risk-and-impact/ia-{eid}.pdf",
                  "MR-": f"07-management-review/mr-{eid}.pdf", "EV-": f"05-evidence/snapshots/{eid}.json"}
    for prefix, path in candidates.items():
        if eid.startswith(prefix) and path in files:
            return path
    if eid.startswith("AUD-"):
        aid = eid.split("/")[0]
        path = f"06-internal-audit/audit-{aid}.pdf"
        if path in files:
            return path + f" (workpaper {eid.split('/')[-1]})"
    return None


def index_markdown(model: Engagement, findings, files: dict[str, dict], label: str, sha: str) -> str:
    from .rules import leg_effective, metrics, requirement_state
    m = metrics(model)
    e = model.engagement
    fw = model.catalog["framework"]
    names = set(files)
    ev = model.evidence_index
    sandbox = bool((e.get("sandbox") or {}).get("enabled"))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    L = [f"# {model.client} — {fw.get('short_name', fw.get('name'))} auditor package ({label})\n\n"]
    if sandbox:
        L.append("> **SANDBOX ENGAGEMENT.** Collector and AI-drafted content in this package is simulated test data.\n\n")
    L.append(_table(["Item", "Detail"], [
        ["Organisation", model.client], ["Standard", fw.get("name")],
        ["AIMS scope", model.fmt(str((e.get("scope") or {}).get("statement") or "—"))],
        ["Certification body", e.get("certification_body") or "—"],
        ["Stage 1 / Stage 2", f"{(e.get('dates') or {}).get('stage1', '—')} / {(e.get('dates') or {}).get('stage2', '—')}"],
        ["Record as of", str(model.today)], ["Source commit", sha], ["Generated by", f"grc-readiness engine {__version__}"],
        ["Validation at packaging", f"{len(errors)} errors · {len(warnings)} warnings (listed in section 5)"],
    ]))
    L.append("\n## 1. How to read this package\n\n"
             "Every requirement is assessed on four legs, each backed by cited evidence:\n\n")
    L.append(_table(["Leg", "Question"], [[t["label"], model.fmt(t["question"])] for t in model.playbook["evidence_test"]]))
    L.append("\n- **verified** means a reviewer confirmed the leg against current evidence in a reviewed change. Automated "
             "collectors and AI drafting never set a leg to verified.\n"
             "- **partial** means some evidence exists; **claimed** means the client says so but it is not yet evidenced.\n"
             "- Evidence is cited by id. Where the package contains the evidence itself (documents, impact assessments, "
             "management reviews, collector snapshots, audit workpapers), section 3 gives its path; otherwise it gives "
             "where the artifact is held, to be inspected on request.\n"
             "- `SHA256SUMS` lists a checksum for every file. The package can be regenerated from the source commit and "
             "will be byte-for-byte identical.\n")
    L.append("\n## 2. Readiness at a glance\n\n"
             f"- Requirements ready: **{m['requirements_ready']} of {m['requirements_applicable']}** applicable; "
             f"evidence-test legs verified: **{m['legs_verified_pct']}%**.\n"
             f"- Open gaps: {m['gaps_open']} of {m['gaps_total']}. Open nonconformities: {m.get('nc_open_major', 0)} major, "
             f"{m.get('nc_open_minor', 0)} minor.\n"
             f"- Policies and procedures approved and current: {m.get('docs_approved', 0)} of {m.get('docs_required', 0)}. "
             f"AI systems with a current impact assessment: {m.get('ia_current', 0)} of {m.get('ia_required', 0)}.\n"
             f"- Last management review held: {m.get('mr_last_held') or 'none yet'}.\n")
    L.append("\n## 3. Requirement → evidence traceability\n\n")
    rows = []
    for r in model.requirements:
        rid = r["id"]
        c = model.controls.get(rid, {})
        if not model.is_applicable(rid):
            rows.append([rid, r["title"], "excluded", "—", "—", "—", "—", "—"])
            continue
        legs = []
        for k in LEGS:
            leg = (c.get("test") or {}).get(k) or {}
            refs = ", ".join(str(x) for x in leg.get("evidence") or [])
            legs.append(f"{leg_effective(model, leg)}" + (f": {refs}" if refs else ""))
        rows.append([rid, r["title"], c.get("owner") or "—", requirement_state(model, rid), *legs])
    L.append(_table(["Req.", "Title", "Owner", "State", "Documented", "Implemented", "Evidenced", "Tested"], rows))
    cited = sorted({str(x) for c in model.controls.values() for k in LEGS
                    for x in (((c.get("test") or {}).get(k) or {}).get("evidence") or [])})
    erows = []
    for eid in cited:
        item = ev.get(eid)
        if not item:
            erows.append([eid, "**not in the evidence index**", "—", "—", "—"])
            continue
        current = ("FAILING" if model.evidence_is_failing(item) else "EXPIRED" if model.evidence_is_expired(item) else "current")
        erows.append([eid, item.get("title"), item.get("type"), where_in_package(eid, names) or item.get("location"), current])
    L.append("\n**Where each cited item is**\n\n")
    L.append(_table(["Evidence", "Title", "Type", "In this package / held at", "Status"], erows))
    L.append("\n## 4. Records in this package\n\n")
    for folder, title, _ in SECTIONS:
        items = sorted(n for n in names if n.startswith(folder + "/") and n.endswith(".pdf"))
        if items:
            L.append(f"**{title}** (`{folder}/`): " + ", ".join(f"`{n.split('/', 1)[1]}`" for n in items) + "\n\n")
    L.append("\n## 5. Known issues at packaging\n\n")
    if errors or warnings:
        L.append(_table(["Severity", "Code", "Finding"], [[f.severity, f.code, f.message] for f in errors + warnings]))
    else:
        L.append("None: validation passed without errors or warnings.\n")
    L.append("\n## 6. Contents and checksums\n\n")
    L.append(_table(["File", "Bytes", "SHA-256"], [[n, files[n]["bytes"], files[n]["sha256"]] for n in sorted(files)]))
    L.append("\n_This index and `SHA256SUMS` are not listed above; `SHA256SUMS` covers this index too._\n")
    return "".join(L)


def _zip(folder: Path, zip_path: Path, stamp: dt.date) -> None:
    ts = (max(stamp.year, 1980), stamp.month, stamp.day, 12, 0, 0)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(x for x in folder.rglob("*") if x.is_file()):
            info = zipfile.ZipInfo(f"{folder.name}/{p.relative_to(folder).as_posix()}", date_time=ts)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())


def build(model: Engagement, out: Path, label: str = "package", force: bool = False) -> list[str]:
    from .build import build_outputs, slug
    from .render_pdf import render
    from .rules import validate
    findings = validate(model)
    errors = [f for f in findings if f.severity == "error"]
    if errors and not force:
        raise ValueError(f"{len(errors)} validation error(s); an auditor package is only built from a valid record "
                         "(use --force for a draft)")
    sha = commit_sha(model)
    safe_label = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in label)[:40] or "package"
    name = f"{slug(model)}-{model.engagement.get('framework', 'iso42001')}-{safe_label}-{model.today}"
    root = out / name
    if root.exists():
        shutil.rmtree(root)
    staging = out / f".{name}-reports"
    if staging.exists():
        shutil.rmtree(staging)
    build_outputs(model, findings, staging, with_docx=True)
    footer = f"{model.client} · record as of {model.today} · commit {sha[:12]} · grc-readiness {__version__}"
    sandbox = bool((model.engagement.get("sandbox") or {}).get("enabled"))
    banner = "SANDBOX ENGAGEMENT - simulated data, not client evidence." if sandbox else None
    for f in sorted(staging.iterdir()):
        if f.name in SKIP or not f.is_file():
            continue
        dest = root / section_for(f.name)
        dest.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".md":
            text = f.read_text(encoding="utf-8")
            title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")), f.stem)
            render(text, dest / f"{f.stem}.pdf", title, footer, banner=banner)
        else:
            shutil.copy2(f, dest / f.name)
    shutil.rmtree(staging)
    snaps = model.engagement_dir / "evidence" / "collected"
    if snaps.is_dir():
        for s in sorted(snaps.glob("*.json")):
            (root / "05-evidence" / "snapshots").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, root / "05-evidence" / "snapshots" / s.name)
    src = root / "08-source-record"
    for p in sorted(model.engagement_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".md", ".csv", ".json"):
            dest = src / "engagement" / p.relative_to(model.engagement_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
    files = {p.relative_to(root).as_posix(): {"bytes": p.stat().st_size, "sha256": _sha(p)}
             for p in sorted(root.rglob("*")) if p.is_file()}
    idx = index_markdown(model, findings, files, safe_label, sha)
    (root / "00-auditor-index.md").write_text(idx, encoding="utf-8")
    render(idx, root / "00-auditor-index.pdf", f"{model.client} — auditor package ({safe_label})", footer)
    manifest = {"client": model.client, "framework": model.engagement.get("framework"), "label": safe_label,
                "as_of": str(model.today), "commit": sha, "engine": __version__, "sandbox": sandbox,
                "validation": {"errors": len(errors), "warnings": sum(f.severity == "warning" for f in findings)},
                "files": files}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{_sha(p)}  {p.relative_to(root).as_posix()}" for p in sorted(root.rglob("*")) if p.is_file()]
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    # normalise file times so the folder (not just the zip) is stable too
    stamp = dt.datetime.combine(model.today, dt.time(12, 0)).timestamp()
    for p in root.rglob("*"):
        os.utime(p, (stamp, stamp))
    zip_path = out / f"{name}.zip"
    _zip(root, zip_path, model.today)
    return [f"auditor package: {root}/ ({len(files) + 4} files)", f"archive: {zip_path} (sha256 {_sha(zip_path)[:16]})",
            f"index: {root / '00-auditor-index.pdf'}"]
