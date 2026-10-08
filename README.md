# grc-readiness

**GRC-as-code for certification readiness engagements.** Starts with ISO/IEC 42001 (AI management systems) and is built to add more frameworks.

The engagement record lives in this repo as YAML. Git history is the audit trail, pull requests are approvals, and CI enforces the evidence rules. The analyst brief, control matrix, Statement of Applicability, gap register and evidence index are **generated** from the record and never edited by hand.

```
 engagement YAML ──PR──▶ CI: validate ──▶ build ──▶ brief.docx · control matrix · SoA · gap register · evidence index
        ▲                    │ blocks overstated readiness                     │
        │                    ▼                                                 ▼
   analyst / owners    PR summary (readiness %)                   artifacts · tagged releases (audit packages)
        ▲
        └── GitHub Issues + phase Milestones (synced from gaps.yaml) ◀── weekly freshness check (stale evidence, overdue gaps)
```

## The core idea: the four-part evidence test, enforced in code

Every requirement (Clauses 4–10 plus the 38 Annex A controls) has one file in `engagement/controls/`. Each file records four legs:

| Leg | Question | To mark it `verified`, CI requires |
|---|---|---|
| **Documented** | Is the requirement formally defined? | An **approved** `document` (has `approved_by`), not a draft |
| **Implemented** | Is the process actually in use? | Operating evidence (record, log, config…), not just policy |
| **Evidence exists** | Can the client produce records showing execution? | Current operating evidence; Implemented at least partial |
| **Tested** | Does sampling or interview support consistent operation? | `test`, `sample` or `interview` evidence; Evidence exists verified |

Each leg's status is one of: `not_started` · `claimed` (the client says so; treated as a hypothesis) · `partial` · `verified`.

Evidence has a shelf life (`valid_for_days`). When evidence expires, any `verified` leg that relies on it is downgraded automatically. This is the brief's working rule made mechanical: *if you can't trace a control to an owner, a current artifact and operating evidence, it's unresolved.*

## Quick start

```bash
pip install -r requirements.txt
python -m grc validate                 # schemas + readiness rules (the CI gate)
python -m grc build --out out          # brief.docx + Markdown/CSV reports
python -m grc sync-issues              # dry run: what Issues/Milestones would be created
```

`--today YYYY-MM-DD` evaluates the record as of a given date, for example `--today 2027-02-22` to see what will have expired by Stage 1.

## Repository layout

```
frameworks/iso42001/
  catalog.yaml        requirement IDs, short titles, paraphrased intent, evidence examples
  playbook.yaml       reusable engagement content: evidence test, phases, needs, readiness criteria
engagement/           ← one engagement's record (replace with your client's)
  engagement.yaml     client profile, scope, what's in place, budget, dates, phases, guardrails, risks
  controls/<ID>.yaml  four-part evidence test per requirement (65 files)
  gaps.yaml           gap register → GitHub Issues
  evidence/index.yaml pointers to evidence (location, date, approver, expiry, sha256)
  workpapers/         analyst test workpapers (non-confidential)
schemas/              JSON Schemas for all of the above
templates/            brief-template.docx (house style)
grc/                  the CLI: model, rules, renderers, issue sync
.github/workflows/    validate · weekly freshness · issue sync · release evidence package
```

## Validation rules

| Code | Severity | Rule |
|---|---|---|
| E001 | error | Data doesn't match the schema |
| E002 / E003 | error | A requirement has no assessment file / a file isn't in the catalog |
| E004 | error | Annex A exclusion without justification, or a mandatory clause excluded |
| E005 | error | Leg is `verified` but cites no evidence |
| E006 | error | Cites evidence that isn't in the index |
| E007 | error | Leg is `verified` but all its evidence has expired |
| E008 | error | Legs out of order (for example, Tested verified before Evidence exists) |
| E009 | error | Progress recorded with no accountable owner |
| E010 | error | Gap references an unknown requirement or phase |
| E012 | error | Evidence type doesn't fit the leg (draft for Documented, policy for Implemented…) |
| E013 | error | Gap closed without `closure_evidence` |
| W102 | warning | Operates in practice but isn't codified in an approved document |
| W101 / W104 / W105 / W106 | warning | Evidence expiring soon · gap past due · gap due after its phase ends · budget at or above 80% |
| I201 | info | Client claim not yet backed by evidence (the analyst's follow-up list) |

## GitOps workflow

1. **Change through PRs.** For example: *"A.6.2.4 tested → verified after release-owner interview"*. The PR template walks through the evidence test.
2. **CI gates the merge** (`validate.yml`). It runs tests, validation and the build, and posts a readiness summary on the PR. The generated reports are attached as a build artifact.
3. **Merging is approval.** `CODEOWNERS` decides who must approve which files. For example, client control owners approve their own controls, and the engagement lead approves `engagement.yaml`.
4. **Gaps become Issues** (`sync-issues.yml`). Each gap becomes an Issue with a hidden ID marker and a milestone per phase. Re-running updates the existing Issues instead of duplicating them. A closed gap closes its Issue.
5. **Weekly drift check** (`freshness.yml`). This re-evaluates the record against today's date and maintains one `grc-drift` Issue listing expired evidence and overdue gaps.
6. **Freeze for audits** (`release.yml`). Publish a release from the GitHub UI with a tag such as `v2027.02-stage1`. CI attaches the brief, reports, readiness summary and SHA-256 checksums as of that commit. Validation errors block the package; warnings are listed in the release notes.

## Starting a new engagement

1. Click **Use this template** (Settings → Template repository), or copy the repo. Use **one private repo per client**.
2. Edit `engagement/engagement.yaml`, then clear `gaps.yaml` and `evidence/index.yaml`.
3. Delete `engagement/controls/*` and run `python -m grc init` to scaffold 65 blank assessment files.
4. Set the real reviewers in `.github/CODEOWNERS`, and turn on branch protection for `main` (require the *validate* check and a CODEOWNERS review).

## Adding a framework

Add `frameworks/<id>/catalog.yaml` and `playbook.yaml`, then set `framework: <id>` in `engagement.yaml`. The rules and renderers are framework-agnostic. For cross-framework reuse (for example, a SOC 2 control satisfying ISO 42001 requirements), see [`mappings/README.md`](mappings/README.md).

## Important boundaries

- **ISO text is copyrighted.** The catalog contains identifiers, short titles and *our own paraphrased* intent. It doesn't reproduce the standard's text. Work from a licensed copy.
- **Evidence stays in the client's systems.** The index stores pointers, dates, approvers and optional hashes. Don't commit confidential artifacts. Keep each client's repo private.
- **The tool doesn't decide conformity.** It enforces bookkeeping discipline (traceability, freshness, evidence types). Whether evidence is *sufficient* is still the analyst's and auditor's judgment.
