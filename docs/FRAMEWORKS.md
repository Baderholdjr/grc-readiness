# Frameworks, several records in one repository, and cross-framework reuse

## Built-in frameworks

| Id | Standard | Requirements | Document library | Notes |
|---|---|---|---|---|
| `iso42001` | ISO/IEC 42001:2023 (AI management system, AIMS) | 27 clauses + 38 Annex A controls | 17 documents | AI system impact assessments (6.1.4, 8.4, A.5) |
| `iso27001` | ISO/IEC 27001:2022 (information security, ISMS) | 25 clauses + 93 Annex A controls | 20 documents | No impact assessments; risk treatment and the Statement of Applicability drive Annex A |

Catalogs hold identifiers, short titles and **our own paraphrase** of each requirement's intent. They never reproduce the standards' text. Work from licensed copies.

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

**Not yet per record:**
- **Document ingestion** reads `intake/` for the main record only. For the second record, run `python -m grc --engagement engagement-27001 ingest` locally.
- **Hours** are kept in the main record (one engagement budget).

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

1. Add `frameworks/<id>/catalog.yaml` (clauses and controls, paraphrased) and `playbook.yaml`:
   - phases and readiness criteria
   - document library with templates in `frameworks/<id>/documents/`
   - management review inputs
   - `impact_assessment: {required_for_kinds: []}` unless the framework needs impact assessments
2. Make sure the document library covers every requirement exactly once. The tests check this for the built-in frameworks.
3. Optionally, add proposed mappings in `mappings/<a>__<b>.yaml`.
