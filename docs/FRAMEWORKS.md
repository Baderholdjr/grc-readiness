# Frameworks, several records in one repository, and cross-framework reuse

## Built-in frameworks

| Id | Standard | Requirements | Document library | Notes |
|---|---|---|---|---|
| `iso42001` | ISO/IEC 42001:2023 (AI management system, AIMS) | 27 clauses + 38 Annex A controls | 17 documents | AI system impact assessments (6.1.4, 8.4, A.5) |
| `iso27001` | ISO/IEC 27001:2022 (information security, ISMS) | 25 clauses + 93 Annex A controls | 20 documents | No impact assessments; risk treatment and the Statement of Applicability drive Annex A |
| `soc2` | SOC 2 (AICPA Trust Services Criteria, 2017, revised points of focus 2022) | 33 common criteria (Security) + 28 in optional categories | 18 documents (fewer if categories are left out) | An attestation, not a certification; the client chooses categories; see [SOC 2](#soc-2) |

Catalogs hold identifiers, short titles and **our own paraphrase** of each requirement's intent. They never reproduce the standards' or criteria's text. Work from licensed copies of the ISO standards and the AICPA's published criteria.

## SOC 2

A SOC 2 report is an attestation by a CPA firm (the *service auditor*), not a certificate. The engine runs a SOC 2 record the same way as an ISO record: four-part evidence test, gaps, documents, internal audit (readiness assessment), management review, auditor package and client site. What differs:

**Categories.** Security (the common criteria, CC1–CC9) is always in scope. Availability, Confidentiality, Processing Integrity and Privacy are optional. Choose them when you start the record (`--categories availability,confidentiality`, or the **categories** input of *New engagement*), or later in `engagement.yaml`:

```yaml
scope:
  statement: The Larkspur clinical scheduling platform and the people and processes that run it.
  categories: [availability, confidentiality]
```

Criteria in categories you didn't choose are left out everywhere: no assessment files, no requests, no documents (the Privacy Program isn't drafted unless Privacy is chosen). If you add a category later, validation reports the missing assessment files (E002) until you run `python -m grc init` (or *Validate* on a branch, then commit the new files). A category name the framework doesn't have is an error (E016). If you take a category out again, open gaps that only concern it are flagged (W112) and no longer chased.

**Applicability.** Every criterion in a chosen category applies. A criterion can be marked `applicable: false` only with a `justification`, which the system description will need to explain (E004 otherwise). The *Criteria Applicability* report (`soa.md`) takes the place of the ISO Statement of Applicability and lists the left-out categories with their reason.

**Dates.** `dates.stage1` is the **observation period start** (also the as-of date of a Type 1 report, if the client wants one first); `dates.stage2` is the **observation period end**, when Type 2 fieldwork begins. The client site counts down to the observation period, and reports, the auditor package and the Help page use SOC 2 wording. Phases run from scoping through a readiness assessment to the observation period.

**References.** The internal audit evidences CC4.1, the corrective action register CC4.2, and the management (and board) review CC1.2.

**Mapping.** `mappings/iso27001__soc2.yaml` proposes 4 equivalent, 2 subset, 1 superset and 42 related pairs between ISO 27001 and SOC 2, for clients pursuing both. As with every engine mapping, nothing counts until it is reviewed in the client repository.

**Wording for other frameworks.** All of this comes from the SOC 2 catalog (`kinds:`, `categories:`) and playbook (`terms:`, `glossary:`). A new framework sets the same keys to use its own words; ISO wording is the default.

## One client, two frameworks: two records in one repository

Each framework gets its own record, side by side:

```
engagement/            the main record (e.g. ISO 42001)
engagement-27001/      a second framework's record (framework: iso27001)
intake/                documents for the main record
intake-27001/          documents for the second record
mappings/              reviewed cross-framework mappings (optional)
```

Each record keeps everything a certification body expects per standard:
- its own controls and Statement of Applicability
- its own gaps, documents, internal audit, management review and auditor package

The records share the repository, the owners and the client site.

### Starting the second record

Go to **Actions → New engagement → Run workflow**:
- **framework:** `iso27001`
- **engagement:** `engagement-27001`

Locally:

```
python -m grc --engagement engagement-27001 new-engagement --framework iso27001 \
  --client "Acme" --start 2026-11-02 --stage1 2027-03-15 --stage2 2027-05-10 \
  --intake intake-27001 --confirm-reset
```

This creates `engagement-27001/` and `intake-27001/` only. The main record is not touched.

### What runs for every record

| Workflow | With several records |
|---|---|
| Validate & build readiness reports | Validates and builds every record. Any record's errors fail the check. |
| Publish reports | The main record's reports are at the top of the `reports` branch; others are in a subfolder (`engagement-27001/`), linked from the landing page. |
| Collect evidence | Runs each record's `collectors.yaml`, all in one *Evidence refresh* PR. |
| Sync gap register to GitHub Issues | The second record's issues are marked `iso27001:GAP-01`, titled `[ISO 27001] …`, with their own milestones. |
| Weekly evidence freshness check | One drift issue covering every record. |
| Publish evidence package (release) | One auditor package per record. An error in any record blocks the release. |
| Client site | One tab per framework, automatically. |

**Workflows you run by hand** take an **engagement** input: `engagement` (the default) or `engagement-27001`. These are:
- Internal audit
- Policies and procedures
- Management review
- AI impact assessment
- New engagement

Their branches are suffixed (`docs/drafts-27001`), so the two records never share a pull request.

**Locally**, pass `--engagement engagement-27001` before the command, or set `GRC_ENGAGEMENT=engagement-27001`. `python -m grc engagements` lists the records.

**Document ingestion** is per record: each record reads its own folder (`intake/` for `engagement/`, `intake-27001/` for `engagement-27001/`), and the pull request gets one report section per record that had new files. Upload a document to every folder whose framework it serves. Client repositories set up before engine 0.14.1 need `"intake-*/**"` added to the `paths:` of `.github/workflows/ingest.yml`.

**Not yet per record:** hours are kept in the main record (one engagement budget).

## Cross-framework reuse

Much of ISO 27001 and ISO 42001 shares the same management-system structure: documented information, corrective action, continual improvement, planning of changes. When one process serves both, its evidence should be collected once.

### Mapping files

`mappings/iso27001__iso42001.yaml` lists pairs of requirements and how they relate:

| Relationship | Meaning | Lets evidence count for both? |
|---|---|---|
| `equivalent` | One process can meet both as it is | **Yes**, once reviewed |
| `related` | Overlapping subject; each needs its own evidence | No: a pointer for the analyst |
| `subset` / `superset` | One is narrower than the other | No |

The engine ships **proposed** mappings: 4 equivalent and 35 related. A proposed mapping does nothing until a person reviews it:
1. Copy the engine's file to `mappings/` at the client repository root.
2. Check each line against licensed copies of both standards and the client's real processes.
3. Fill `reviewed_by` and `reviewed_on` on the lines you accept, then merge. The pull request is the sign-off.

```yaml
- {iso27001: "7.5", iso42001: "7.5", relationship: equivalent,
   note: One document control procedure and repository can control both.,
   reviewed_by: Bernard Aderhold, reviewed_on: 2026-11-03}
```

### Citing evidence from the other record

With a reviewed equivalent mapping, a control leg in one record can cite evidence held in the other, as `<framework>:<id>`:

```yaml
# engagement-27001/controls/7.5.yaml
test:
  documented:
    status: verified
    evidence: [iso42001:DOC-DOCINFO]     # the approved ISO 42001 document control procedure
```

The evidence keeps its own rules: expiry, approval, and failing collector checks all apply as if it were local. It is never copied. This record's evidence index and workbook list it with the folder it's held in, and only where this record cites it.

The cited item must be evidence **for the mapped requirement** in the other record: one of that requirement's legs must cite it. You can't borrow an unrelated record just because a mapping exists.

| Code | Severity | Rule |
|---|---|---|
| E080 | error | Cites `<framework>:<id>` with no such record in the repo, or with no reviewed **equivalent** mapping for this requirement |
| E081 | error | Mapping file invalid: schema, framework list, unknown requirement ids, unknown relationship |
| I180 | info | Reuse opportunity: the other record has verified this leg on a mapped requirement; its evidence could be cited here |

`cross-framework.md` in each record's reports lists every mapping:
- its relationship
- whether it has been reviewed (and by whom)
- the readiness of both sides

### On the client site

A requirement request that a reviewed equivalent mapping ties to an open request in the main framework appears **once**, on the main framework's tab, marked "Also counts toward ISO 27001 7.5". One answer serves both.

## Adding another framework

1. Add `frameworks/<id>/catalog.yaml` (requirements, paraphrased; optional `kinds:` and `categories:`) and `playbook.yaml`:
   - phases and readiness criteria
   - document library with templates in `frameworks/<id>/documents/`
   - management review inputs
   - `impact_assessment: {required_for_kinds: []}` unless the framework needs impact assessments
   - `terms:` and `glossary:` if the framework's words differ from ISO's (see `frameworks/soc2/playbook.yaml`)
2. Make sure the document library covers every requirement exactly once. The tests check this for the built-in frameworks.
3. Optionally, add proposed mappings in `mappings/<a>__<b>.yaml`.
