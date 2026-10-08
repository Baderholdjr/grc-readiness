"""Command line: python -m grc <command>

  validate      Check schemas and readiness rules (CI gate)
  build         Generate brief.docx, control matrix, SoA, gap register, evidence index
  init          Scaffold a control file for every catalog requirement that lacks one
  sync-issues   Mirror gaps.yaml into GitHub Issues and phase milestones
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
    summary = render_md.render_all(model, findings, out)
    if not args.no_docx:
        from .render_docx import render_brief
        slug = model.client.strip("()").replace(" ", "-").lower()
        path = render_brief(model, out / f"{slug}-{model.engagement['framework']}-brief.docx")
        print(f"brief: {path}")
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

    args = p.parse_args(argv)
    return args.fn(args)
