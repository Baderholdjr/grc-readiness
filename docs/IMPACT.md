# AI system impact assessments (6.1.4, 8.4, Annex A.5)

ISO/IEC 42001 requires the organisation to assess the potential consequences of its AI systems for individuals, groups and society (6.1.4), to repeat that at planned intervals and when things change (8.4), and to document it (A.5.2–A.5.5). The engine keeps one assessment file per AI system, checks it before anyone can approve it, and lets an approved assessment serve as evidence.

## Files

| File | Holds | Who edits |
|---|---|---|
| `engagement/inventory.yaml` | AI systems and other assets. Every item with `kind: ai_system` (and `in_scope` not `false`) needs an assessment | Analyst |
| `engagement/impact/IA-NNN.yaml` | One assessment: context, screening of every category, scored impacts, mitigations, residual ratings, decision, approval | Generated, then completed by the assessor |
| Playbook `impact_assessment:` | The method: categories, 1–5 scales, bands, thresholds, review cycle | Engine default; a client repo can override the playbook |

## Method (engine default)

- **Categories (11).** Individuals: safety, health, privacy, autonomy, transparency, security. Groups: fairness. Society: economic, information integrity, environment, rights.
- **Scoring.** Likelihood × severity, each 1–5. Bands: 1–5 Low, 6–11 Medium, 12–19 High, 20–25 Critical.
- **Residual risk** is scored after mitigations.
  - 12 or more (High) needs **acceptance** (`accepted_by`, `accepted_on`, `rationale`) by someone other than the assessor.
  - 20 or more (Critical) can't be approved; reduce it or record the decision `reject`.
- **Review cycle.** Every 180 days for systems with `risk_tier: High` (any capitalisation), otherwise every 365 days, counted from `approved_on`. An explicit `next_review` can bring the date forward but never push it past the cycle. A material change to the system, its data or its use also calls for a reassessment.

## Running an assessment

1. **Start.** Run **Actions → AI impact assessment** with an inventory ID (`INV-001`) or `all`. Locally: `python -m grc impact new all`.
   This creates `IA-NNN.yaml` for every in-scope AI system that lacks an active assessment. Context is prefilled from the inventory, and every category is listed with `relevant: null`. Every run uses the same branch and PR (`impact/new`), so numbers never collide. Merge it (or keep working in it).
2. **Assess.** The assessor:
   - completes `context` (intended use, foreseeable misuse, affected parties, deployment, human oversight, data, jurisdictions)
   - sets `relevant: true/false` with a `rationale` for **every** category
   - adds at least one impact for each relevant category: description, likelihood, severity, mitigations, residual likelihood and severity, and links to `controls` and `gaps` where they exist
   - writes a `conclusion`, sets `decision` (`approve`, `approve_with_conditions` with `conditions`, or `reject`), `assessor` and `assessed_on`, and sets `status: in_review`
3. **Approve.** A different person sets `approver`, `approved_on` and `status: approved`, and accepts any High residual risk. CI blocks the merge if anything is missing (**E031**, **E032**).
4. **Cite it.** Controls, gap closures and findings can cite `IA-001` as evidence, typically for A.5.2–A.5.5 and 6.1.4/8.4. It counts only while the assessment is approved (not with a future date), independently, with an approve decision, and not past review. Otherwise anything relying on it fails validation (**E015** / **E007** for controls, **E013** for gaps, **E024** for findings).
5. **Reassess.** When it's due (**W132**) or the system changes: mark the old file `status: superseded`, run the workflow again for that system, and complete the new one.

Independence uses the same identity rules as the internal audit: names, roles and GitHub users in `owners.yaml` are treated as one person.

## Reports

`impact-assessments.md` lists every AI system with its assessment, status, highest residual rating and next review. Each assessment has its own page (`ia-IA-001.md`) with the screening and the impact table. The readiness summary shows how many AI systems have a current, approved assessment.

## Rules

| Code | Severity | Rule |
|---|---|---|
| E030 | error | File/ID mismatch; unknown system, category, requirement or gap; a category screened twice; duplicate impact IDs; more than one active assessment per system |
| E031 | error | Approved while incomplete, with future or out-of-order dates, or by its own assessor |
| E032 | error | Residual rating missing, unacceptable, or High without independent, dated acceptance |
| W130 | warning | AI system without an assessment |
| W131 | warning | Assessment is draft or in review |
| W132 | warning | Past its review date |
| W133 | warning | Residual rated higher than inherent |

The engine checks that the assessment is complete and consistent. Whether the judgements in it are sound is for the assessor, the approver and, later, the auditor.
