"""Command line: python -m grc <command>

  validate      Check schemas and readiness rules (CI gate)
  build         Generate brief.docx, control matrix, SoA, gap register, evidence index
  init          Scaffold a control file for every catalog requirement that lacks one
  sync-issues   Mirror gaps.yaml into GitHub Issues and phase milestones
  collect       Run evidence collectors and refresh machine-owned evidence
  ingest        Draft engagement data from client documents in intake/
  new-engagement  Reset the record for a new client (computes phases from dates)
  codeowners    Make control owners required reviewers of their control files
  bootstrap     Write a thin client repository that uses this engine
  audit         Internal audit: plan workpapers, draw reproducible samples
  impact        AI system impact assessments: start one per AI system
  docs          Policies and procedures: draft from the library, AI-fill, approve
  review        Management review: schedule one, generate its input pack
  package       Auditor package: PDFs, auditor index, checksums and a reproducible zip
  hours         Timesheet: import time-tracker exports, log hours
  portal        Client site: build the deployable bundle (site, data, Cloudflare Worker)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import yaml

from . import issues, render_md
from .model import LEGS, control_filename, load
from .rules import validate


def _model(args):
    today = dt.date.fromisoformat(args.today) if args.today else None
    return load(args.engagement, today=today)


def _emit(findings, fmt: str):
    if fmt == "json":
        print(json.dumps([f.as_dict() for f in findings], indent=2))
        return
    for f in findings:
        if fmt == "github" and f.severity in ("error", "warning"):
            kind = "error" if f.severity == "error" else "warning"
            loc = f" file={f.file}" if f.file else ""
            print(f"::{kind}{loc},title={f.code}::{f.message}")
        elif f.severity != "info" or fmt == "text-verbose":
            print(f"{f.severity.upper():8} {f.code}  {f.message}" + (f"  [{f.file}]" if f.file else ""))


def cmd_validate(args) -> int:
    model = _model(args)
    findings = validate(model)
    _emit(findings, args.format)
    errors = sum(f.severity == "error" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    infos = sum(f.severity == "info" for f in findings)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(render_md.summary_markdown(model, findings))
    print(f"\n{errors} error(s), {warnings} warning(s), {infos} unverified client claim(s).", file=sys.stderr)
    return 1 if errors or (args.strict and warnings) else 0


def cmd_build(args) -> int:
    model = _model(args)
    findings = validate(model)
    errors = [f for f in findings if f.severity == "error"]
    if errors and not args.force:
        _emit(errors, "text")
        print("\nRefusing to build from invalid data (use --force for a draft).", file=sys.stderr)
        return 1
    out = Path(args.out)
    from .build import build_outputs
    summary, docx_name = build_outputs(model, findings, out, with_docx=not args.no_docx)
    if docx_name:
        print(f"brief: {out / docx_name}")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    print(f"reports written to {out}/")
    return 0


def cmd_init(args) -> int:
    model = _model(args)
    cdir = model.engagement_dir / "controls"
    cdir.mkdir(parents=True, exist_ok=True)
    created = 0
    for r in model.requirements:
        if r["id"] in model.controls:
            continue
        data = {"id": r["id"]}
        if r["kind"] == "control":
            data["applicable"] = True
            data["justification"] = ""
        data.update({"owner": "", "implementation": "",
                     "test": {k: {"status": "not_started", "evidence": []} for k in LEGS}})
        header = f"# {r['id']} {r['title']}\n# Intent (paraphrased): {r['intent']}\n"
        (cdir / control_filename(r["id"])).write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        created += 1
    print(f"created {created} control file(s) in {cdir}")
    return 0


def cmd_sync(args) -> int:
    model = _model(args)
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if args.apply and not (repo and token):
        print("--apply needs GITHUB_REPOSITORY (or --repo) and GITHUB_TOKEN.", file=sys.stderr)
        return 2
    for line in issues.sync(model, repo, token, dry_run=not args.apply, write_back=args.write_back):
        print(line)
    return 0


def cmd_collect(args) -> int:
    from . import collect
    model = _model(args)
    results, report = collect.run(model, only=args.only, write=not args.dry_run)
    print(report)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    counts = {}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(" · ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no checks ran", file=sys.stderr)
    return 0


def cmd_ingest(args) -> int:
    from . import ingest
    report = ingest.run(args.engagement, args.intake, mode=args.mode, force=args.force)
    print(report)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    return 0


def cmd_new(args) -> int:
    from . import newengagement
    if not args.confirm_reset:
        print("This deletes everything under engagement/ and intake/ (except intake/README.md).\n"
              "Re-run with --confirm-reset to proceed.", file=sys.stderr)
        return 2
    try:
        log = newengagement.reset(Path(args.engagement), Path(args.intake), args.client,
                                  dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.stage1),
                                  dt.date.fromisoformat(args.stage2), args.hours, args.framework, args.lead)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    return cmd_init(args)


def cmd_codeowners(args) -> int:
    from . import codeowners
    model = _model(args)
    changed, missing = codeowners.update(model, Path(args.file))
    print(f"{args.file}: {'updated' if changed else 'already up to date'}")
    for m in missing:
        print(f"  no GitHub user for owner of {m} - add it to owners.yaml", file=sys.stderr)
    return 1 if (args.check and changed) else 0


def cmd_bootstrap(args) -> int:
    from . import bootstrap
    for line in bootstrap.write(Path(args.dir), args.engine_repo, args.version, args.force):
        print(line)
    print("\nNext: add the GRC_ENGINE_TOKEN secret, then run the New engagement workflow (see README.md).")
    return 0


def cmd_audit(args) -> int:
    from . import audit
    model = _model(args)
    try:
        log = audit.plan(model, args.audit_id) if args.action == "plan" else audit.sample(model, args.audit_id, args.force)
    except (ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    if args.report:
        title = "Test plan and workpapers" if args.action == "plan" else "Samples drawn"
        Path(args.report).write_text(f"## {args.audit_id}: {title}\n\n```\n" + "\n".join(log) + "\n```\n", encoding="utf-8")
    return 0


def cmd_impact(args) -> int:
    from . import impact
    model = _model(args)
    try:
        log = impact.new(model, args.system)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    if args.report:
        Path(args.report).write_text("## New AI impact assessments\n\n```\n" + "\n".join(log) + "\n```\n", encoding="utf-8")
    return 0


def cmd_docs(args) -> int:
    from . import documents
    from .ingest.ai import AIUnavailable
    model = _model(args)
    try:
        if args.action == "new":
            log = documents.new(model, args.target, mode=args.mode)
        elif args.action == "fill":
            log = documents.fill(model, args.target if args.target == "all" else [args.target], mode="ai")
        else:
            if not args.approver:
                print("error: approve needs --approver", file=sys.stderr)
                return 2
            on = dt.date.fromisoformat(args.on) if args.on else None
            log = documents.approve(model, args.target, args.approver, on)
    except (ValueError, AIUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    if args.report:
        titles = {"new": "New policies and procedures", "fill": "AI-filled document drafts", "approve": "Document approval"}
        Path(args.report).write_text(f"## {titles[args.action]}\n\n```\n" + "\n".join(log) + "\n```\n", encoding="utf-8")
    return 0


def cmd_review(args) -> int:
    from . import review
    model = _model(args)
    try:
        if args.action == "new":
            log = review.new(model, dt.date.fromisoformat(args.target) if args.target else model.today)
        else:
            if not args.target:
                print("error: pack needs the review id (e.g. MR-2027-01)", file=sys.stderr)
                return 2
            log = review.pack(model, args.target, force=args.force)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    if args.report:
        Path(args.report).write_text("## Management review\n\n```\n" + "\n".join(log) + "\n```\n", encoding="utf-8")
    return 0


def cmd_package(args) -> int:
    from . import package
    model = _model(args)
    try:
        log = package.build(model, Path(args.out), label=args.label, force=args.force)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for line in log:
        print(line)
    return 0


def cmd_hours(args) -> int:
    from . import hours
    model = _model(args)
    try:
        if args.action == "import":
            if not args.files:
                print("error: import needs one or more CSV files", file=sys.stderr)
                return 2
            log = hours.import_files(model, [Path(f) for f in args.files], match=args.match, person=args.person,
                                     order=args.date_order)
        else:
            person = args.person or os.environ.get("GITHUB_ACTOR") or ""
            if not person or args.hours is None or not args.activity:
                print("error: log needs --hours, --activity and --person (or GITHUB_ACTOR)", file=sys.stderr)
                return 2
            log = hours.log_entry(model, args.hours, args.activity, person,
                                  dt.date.fromisoformat(args.date) if args.date else None, args.note or "",
                                  [r.strip() for r in (args.refs or "").split(",") if r.strip()], args.phase)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    if args.report:
        Path(args.report).write_text("## Timesheet\n\n```\n" + "\n".join(log) + "\n```\n", encoding="utf-8")
    return 0


def cmd_portal(args) -> int:
    from . import portal
    model = _model(args)
    extra = [load(e, today=model.today) for e in args.also or []]
    for log_line in portal.build(model, Path(args.out), repo=args.repo or os.environ.get("GITHUB_REPOSITORY", ""), extra=extra):
        print(log_line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="grc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--engagement", default="engagement", help="engagement directory (default: engagement)")
    p.add_argument("--today", help="evaluate as of this date (YYYY-MM-DD); default: today")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate")
    v.add_argument("--strict", action="store_true", help="fail on warnings too")
    v.add_argument("--format", choices=["text", "text-verbose", "github", "json"], default="text")
    v.add_argument("--summary", help="append a Markdown summary to this file (e.g. $GITHUB_STEP_SUMMARY)")
    v.set_defaults(fn=cmd_validate)

    b = sub.add_parser("build")
    b.add_argument("--out", default="out")
    b.add_argument("--no-docx", action="store_true")
    b.add_argument("--force", action="store_true", help="build even if validation has errors")
    b.add_argument("--summary")
    b.set_defaults(fn=cmd_build)

    i = sub.add_parser("init")
    i.set_defaults(fn=cmd_init)

    s = sub.add_parser("sync-issues")
    s.add_argument("--apply", action="store_true", help="actually call GitHub (default is a dry run)")
    s.add_argument("--repo", help="owner/name (default: $GITHUB_REPOSITORY)")
    s.add_argument("--write-back", action="store_true", help="record issue numbers in gaps.yaml")
    s.set_defaults(fn=cmd_sync)

    c = sub.add_parser("collect", help="run evidence collectors (engagement/collectors.yaml)")
    c.add_argument("--only", nargs="*", help="evidence ids to collect")
    c.add_argument("--report", help="write the Markdown report here (PR body)")
    c.add_argument("--dry-run", action="store_true", help="run checks but don't write files")
    c.set_defaults(fn=cmd_collect)

    g = sub.add_parser("ingest", help="draft engagement data from client documents in intake/")
    g.add_argument("--intake", default="intake")
    g.add_argument("--mode", choices=["auto", "templates", "ai"], default="auto")
    g.add_argument("--force", action="store_true", help="re-process files already in the ledger")
    g.add_argument("--report", help="write the Markdown report here (PR comment)")
    g.set_defaults(fn=cmd_ingest)

    n = sub.add_parser("new-engagement", help="reset engagement/ and intake/ for a new client")
    n.add_argument("--client", required=True)
    n.add_argument("--start", required=True, help="YYYY-MM-DD")
    n.add_argument("--stage1", required=True, help="planned Stage 1 audit date")
    n.add_argument("--stage2", required=True, help="planned Stage 2 audit date")
    n.add_argument("--hours", type=float, default=200)
    n.add_argument("--framework", default="iso42001")
    n.add_argument("--lead", help="engagement lead name")
    n.add_argument("--intake", default="intake")
    n.add_argument("--confirm-reset", action="store_true")
    n.set_defaults(fn=cmd_new)

    co = sub.add_parser("codeowners", help="write control owners into .github/CODEOWNERS")
    co.add_argument("--file", default=".github/CODEOWNERS")
    co.add_argument("--check", action="store_true", help="exit 1 if the file would change")
    co.set_defaults(fn=cmd_codeowners)

    bs = sub.add_parser("bootstrap", help="write a thin client-repo skeleton that uses this engine")
    bs.add_argument("--dir", required=True, help="client repository folder")
    bs.add_argument("--engine-repo", default="Baderholdjr/grc-readiness", help="owner/name of the engine repo")
    bs.add_argument("--version", help="engine version to pin (default: this engine's version)")
    bs.add_argument("--force", action="store_true", help="overwrite existing files")
    bs.set_defaults(fn=cmd_bootstrap)

    au = sub.add_parser("audit", help="internal audit: generate workpapers, draw samples")
    au.add_argument("action", choices=["plan", "sample"])
    au.add_argument("audit_id", help="e.g. AUD-2027-01 (from engagement/audit/program.yaml)")
    au.add_argument("--force", action="store_true", help="sample: redraw samples that have no results yet")
    au.add_argument("--report", help="write a Markdown summary here")
    au.set_defaults(fn=cmd_audit)

    im = sub.add_parser("impact", help="AI system impact assessments")
    im.add_argument("action", choices=["new"])
    im.add_argument("system", help="inventory id (e.g. INV-001) or 'all'")
    im.add_argument("--report", help="write a Markdown summary here")
    im.set_defaults(fn=cmd_impact)

    dc = sub.add_parser("docs", help="policies and procedures")
    dc.add_argument("action", choices=["new", "fill", "approve"])
    dc.add_argument("target", help="document id (e.g. DOC-AI-POLICY) or 'all' (new/fill)")
    dc.add_argument("--mode", choices=["templates", "ai", "auto"], default="auto",
                    help="new: also AI-fill [[TODO]] markers (auto = if AI drafting is enabled)")
    dc.add_argument("--approver", help="approve: who approved it (role, name or GitHub user)")
    dc.add_argument("--on", help="approve: approval date YYYY-MM-DD (default: today)")
    dc.add_argument("--report", help="write a Markdown summary here")
    dc.set_defaults(fn=cmd_docs)

    rv = sub.add_parser("review", help="management review (9.3)")
    rv.add_argument("action", choices=["new", "pack"])
    rv.add_argument("target", nargs="?", help="new: planned date YYYY-MM-DD (default today); pack: review id")
    rv.add_argument("--force", action="store_true", help="pack: regenerate even after the review was held (breaks its record)")
    rv.add_argument("--report", help="write a Markdown summary here")
    rv.set_defaults(fn=cmd_review)

    pk = sub.add_parser("package", help="auditor package (PDFs, index, checksums, zip)")
    pk.add_argument("--out", default="dist")
    pk.add_argument("--label", default="package", help="e.g. stage1, stage2, surveillance-2028")
    pk.add_argument("--force", action="store_true", help="package even if validation has errors (a draft)")
    pk.set_defaults(fn=cmd_package)

    hr = sub.add_parser("hours", help="timesheet: import exports or log hours")
    hr.add_argument("action", choices=["import", "log"])
    hr.add_argument("files", nargs="*", help="import: Toggl / Harvest / Clockify / generic CSV exports")
    hr.add_argument("--match", help="import: keep only rows whose client or project contains this text")
    hr.add_argument("--person", help="who did the work (import: override; log: default $GITHUB_ACTOR)")
    hr.add_argument("--hours", type=float)
    hr.add_argument("--activity", help="log: activity id from the playbook (e.g. interviews)")
    hr.add_argument("--date", help="log: YYYY-MM-DD (default today)")
    hr.add_argument("--note")
    hr.add_argument("--refs", help="log: comma-separated gap/finding/requirement ids")
    hr.add_argument("--phase")
    hr.add_argument("--date-order", choices=["MDY", "DMY"], help="import: how to read dates like 05/09/2026")
    hr.add_argument("--report")
    hr.set_defaults(fn=cmd_hours)

    po = sub.add_parser("portal", help="client site: build the deployable bundle")
    po.add_argument("--out", default="_portal")
    po.add_argument("--repo", help="owner/name answers are sent to as pull requests (default: $GITHUB_REPOSITORY)")
    po.add_argument("--also", action="append", help="another engagement directory (another framework) to show as a tab")
    po.set_defaults(fn=cmd_portal)

    args = p.parse_args(argv)
    return args.fn(args)
