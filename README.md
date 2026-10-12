# grc-readiness

> 📊 **Latest reports:** [brief, control matrix, SoA, gap register, evidence index](../../tree/reports) — rebuilt after every merge and daily.

**GRC-as-code for certification readiness engagements.** Starts with ISO/IEC 42001 (AI management systems) and is built to add more frameworks.

The engagement record lives in this repo as YAML. Git history is the audit trail, pull requests are approvals, and CI enforces the evidence rules. The analyst brief, control matrix, Statement of Applicability, gap register and evidence index are **generated** from the record and never edited by hand.

```
 client documents ──upload to intake/──▶ INGEST (templates + Claude drafting) ──┐
 GitHub · Drata · AWS/Azure/GCP ──daily──▶ COLLECT (evidence snapshots) ─────────┤  both open PRs
                                                                                 ▼
 engagement YAML ──PR──▶ CI: validate ──▶ build ──▶ brief.docx · control matrix · SoA · gap register · evidence index
        ▲                    │ blocks overstated readiness                     │
        │                    ▼                                                 ▼
   analyst / owners    PR summary (readiness %)                   artifacts · releases (audit packages)
        ▲
        └── GitHub Issues + phase Milestones (synced from gaps.yaml) ◀── weekly freshness check (stale evidence, overdue gaps)
```

**Automated end to end, approved by people:** client documents are drafted into the record, evidence is pulled from the client's systems on a schedule, and CI re-evaluates every control against it. Automation only ever opens PRs; nothing it does can mark a control `verified`. Setup: [`docs/AUTOMATION.md`](docs/AUTOMATION.md).

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
python -m grc ingest                   # draft engagement data from new files in intake/
python -m grc collect --dry-run        # run evidence collectors without writing
python -m grc codeowners               # make control owners required reviewers
python -m grc new-engagement --client "Acme" --start 2026-11-02 --stage1 2027-03-15 --stage2 2027-05-10 --confirm-reset
python -m grc bootstrap --dir ../acme-grc  # thin client repo that pins this engine
```

`--today YYYY-MM-DD` evaluates the record as of a given date, for example `--today 2027-02-22` to see what will have expired by Stage 1.

## Repository layout

```
grc/                  the engine: model, rules, renderers, issue sync, collectors/, ingest/
grc/resources/        shipped with the engine (client repos can override any of these):
  frameworks/iso42001/  catalog.yaml (requirements, paraphrased intent) · playbook.yaml (phases, needs, criteria)
  schemas/              JSON Schemas for every engagement file
  templates/            brief-template.docx (house style) · intake/ CSV templates for clients
  client/               skeleton for thin client repos (`grc bootstrap`)
engagement/           ← the example engagement (fictional) used to develop and test the engine
  engagement.yaml     client profile, scope, what's in place, budget, dates, phases, guardrails, risks
  controls/<ID>.yaml  four-part evidence test per requirement (65 files)
  gaps.yaml           gap register → GitHub Issues
  inventory.yaml      AI systems, tools, infrastructure, models, datasets (drafted by ingest)
  collectors.yaml     which evidence to collect automatically, from where, and which control legs it supports
  owners.yaml         owner roles → GitHub users (issue assignment, reminders, CODEOWNERS)
  evidence/index.yaml pointers to evidence entered by people (location, date, approver, expiry)
  evidence/collected.yaml + collected/*.json   machine-owned evidence and snapshots
  workpapers/         analyst test workpapers (non-confidential)
intake/               drop client documents here (in a PR) to draft the record
docs/ENGINE.md        engine releases, thin client repos, upgrades, overrides
docs/AUTOMATION.md    credentials and setup for ingestion and collectors
.github/workflows/    grc-*.yml = reusable workflows client repos call · the rest run this repo
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
| E015 | error | Leg is `verified` but the collector check behind its evidence is failing |
| W102 | warning | Operates in practice but isn't codified in an approved document |
| W101 / W104 / W105 / W106 | warning | Evidence expiring soon · gap past due · gap due after its phase ends · budget at or above 80% |
| E020 | error | An internal auditor would audit a control they own (independence) |
| E021 | error | Audit status ahead of its work (fieldwork without workpapers; reporting/closed with open or unreviewed workpapers, or no approved report) |
| E022 | error | Workpaper concluded without performer, summary or tested sample; "effective" despite unexplained exceptions; "not effective" with no finding; self-reviewed |
| E024 | error | Finding lifecycle skipped (no root cause/action/owner/due, no implementation evidence, no independent effectiveness review); major NC risk-accepted |
| E025 | error | Audit, workpaper or finding references something that doesn't exist |
| E026 | error | Control's *Tested* leg is verified while a major nonconformity on it is open |
| W120–W123 | warning | Finding past due · 9.2 verified without a completed audit · audit overrunning · in-scope requirement without a workpaper |
| E030 | error | Impact assessment references an unknown system, category, requirement or gap; or a system has more than one active assessment |
| E031 | error | Impact assessment approved while incomplete (context, unscreened categories, missing rationale, relevant category with no impact, no conditions) or approved by its own assessor |
| E032 | error | Approved impact with no residual rating; residual at or above the unacceptable level without a `reject` decision; high residual without independent acceptance |
| E040–E042 | error | Document claims an unknown requirement; approved while incomplete or self-approved; approved without a fingerprint or changed after approval |
| W140–W143 | warning | Library documents not started · draft not yet approved · document past review · approved document not cited on its requirements |
| E050–E052 | error | Management review record incomplete (inputs, decisions, frozen input pack, minutes) or actions without owner/due/evidence |
| W150–W153 | warning | Review overdue · none held within the cycle or before Stage 1 · action overdue · 9.3 verified without a held review |
| W130–W133 | warning | AI system without an impact assessment · assessment not yet approved · past its review date · residual higher than inherent |
| W108 / W109 | warning | A collector check is failing / could not run |
| W110 / W111 | warning | Client claims with no owner yet / an owner not listed in owners.yaml |
| I201 | info | Client claim not yet backed by evidence (the analyst's follow-up list) |

## GitOps workflow

1. **Change through PRs.** For example: *"A.6.2.4 tested → verified after release-owner interview"*. The PR template walks through the evidence test.
2. **CI gates the merge** (`validate.yml`). It runs tests, validation and the build, and posts a readiness summary on the PR. The generated reports are attached as a build artifact.
3. **Merging is approval.** `CODEOWNERS` decides who must approve which files. For example, client control owners approve their own controls, and the engagement lead approves `engagement.yaml`.
4. **Gaps become Issues** (`sync-issues.yml`). Each gap becomes an Issue with a hidden ID marker and a milestone per phase. Re-running updates the existing Issues instead of duplicating them. A closed gap closes its Issue.
5. **Weekly drift check** (`freshness.yml`). This re-evaluates the record against today's date and maintains one `grc-drift` Issue listing expired evidence and overdue gaps.
6. **Read the reports** on the [`reports` branch](../../tree/reports) (`publish-reports.yml`). It's rebuilt after every merge to `main` and daily; its history is a dated record of readiness.
7. **Freeze for audits** (`release.yml`). Publish a release from the GitHub UI with a tag such as `v2027.02-stage1`. CI attaches the brief, reports, readiness summary and SHA-256 checksums as of that commit. Validation errors block the package; warnings are listed in the release notes.

## Starting a new engagement

**Each client gets its own thin repository** that pins a version of this engine. See [`docs/ENGINE.md`](docs/ENGINE.md) for the steps (`python -m grc bootstrap`). Engine fixes then reach every client through a reviewed *Upgrade GRC engine* PR, instead of being copied by hand.

In the client repository:

1. Add the `GRC_ENGINE_TOKEN` secret, as described in its README.
2. Go to **Actions → New engagement → Run workflow**. Enter the client name, start date, and planned Stage 1 and Stage 2 dates. It opens a PR that replaces the example with a clean record: 65 blank control files, and phases computed from your dates. Merge it.
3. List the client's people in `engagement/owners.yaml` (role → GitHub users), then run **`python -m grc codeowners`** so each owner is a required reviewer of their own controls. Gap Issues get assigned to them, and they're reminded when gaps go overdue.
4. Upload client documents to `intake/` and point `engagement/collectors.yaml` at their systems. See [`docs/AUTOMATION.md`](docs/AUTOMATION.md).
5. Settings: protect `main` (require the **`validate / validate`** check and a CODEOWNERS review), and allow GitHub Actions to create pull requests.

**Internal audit (9.2) and corrective actions (10.2):** see [`docs/AUDIT.md`](docs/AUDIT.md). Each new engagement starts with an audit scheduled in its Test phase.

**Management review (9.3):** see [`docs/REVIEW.md`](docs/REVIEW.md). **Actions → Management review** schedules a review and generates its input pack from the record; actions become Issues.

**Policies and procedures:** see [`docs/DOCUMENTS.md`](docs/DOCUMENTS.md). **Actions → Policies and procedures** drafts all 17 documents from the library, filled from the engagement record (and by AI if enabled); approval records a fingerprint of the approved text.

**AI system impact assessments (6.1.4, 8.4, A.5):** see [`docs/IMPACT.md`](docs/IMPACT.md). **Actions → AI impact assessment** starts one per AI system in `inventory.yaml`; an approved assessment can be cited as evidence (`IA-001`).

**No credentials yet?** Set `sandbox: {enabled: true}` in `engagement.yaml` to run Drata, cloud and AI drafting against canned data in `sandbox/`. Everything produced is labelled `[SANDBOX]`.

## Adding a framework

Add `frameworks/<id>/catalog.yaml` and `playbook.yaml`, then set `framework: <id>` in `engagement.yaml`. The rules and renderers are framework-agnostic. For cross-framework reuse (for example, a SOC 2 control satisfying ISO 42001 requirements), see [`mappings/README.md`](mappings/README.md).

## Important boundaries

- **ISO text is copyrighted.** The catalog contains identifiers, short titles and *our own paraphrased* intent. It doesn't reproduce the standard's text. Work from a licensed copy.
- **Evidence stays in the client's systems.** The index stores pointers, dates, approvers and optional hashes. Don't commit confidential artifacts. Keep each client's repo private.
- **The tool doesn't decide conformity.** It enforces bookkeeping discipline (traceability, freshness, evidence types). Whether evidence is *sufficient* is still the analyst's and auditor's judgment.
