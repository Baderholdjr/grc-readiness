# Frameworks, several records in one repository, and cross-framework reuse

## Built-in frameworks

| Id | Standard | Requirements | Document library | Notes |
|---|---|---|---|---|
| `iso42001` | ISO/IEC 42001:2023 (AI management system, AIMS) | 27 clauses + 38 Annex A controls | 17 documents | AI system impact assessments (6.1.4, 8.4, A.5) |
| `iso27001` | ISO/IEC 27001:2022 (information security, ISMS) | 25 clauses + 93 Annex A controls | 20 documents | No impact assessments; risk treatment and the Statement of Applicability drive Annex A |
| `soc2` | SOC 2 (AICPA Trust Services Criteria, 2017, revised points of focus 2022) | 33 common criteria (Security) + 28 in optional categories | 18 documents (fewer if categories are left out) | An attestation, not a certification; the client chooses categories; see [SOC 2](#soc-2) |
| `hipaa` | HIPAA Security Rule and Breach Notification Rule (45 CFR Part 164, Subparts C and D) | 64 core + 4 covered entity + 3 business associate + 4 for clearinghouses, group health plans and government entities | 19 documents (15 for most clients) | No certification; required and addressable specifications; see [HIPAA](#hipaa) |
| `gdpr` | General Data Protection Regulation (Regulation (EU) 2016/679) | 7 core + 31 controller + 11 processor + 11 for a DPO, a representative, transfers, special categories and children | 16 documents | No certificate: demonstrable compliance; see [GDPR](#gdpr) |
| `txramp` | TX-RAMP Security Controls Baselines 2.0 (Texas DIR) | 117 Level 1 controls + 106 more at Level 2 (NIST SP 800-53 Rev. 5) | 17 documents, one per control family | Certification by DIR; see [TX-RAMP](#tx-ramp) |
| `fedramp20x` | FedRAMP 20x (FedRAMP Consolidated Rules for 2026) | 46 Key Security Indicators + 141 process rules (96 MUST, 45 SHOULD), by certification class | 18 documents (12 for Class A) | FedRAMP certification for federal agencies; see [FedRAMP 20x](#fedramp-20x) |

Catalogs hold identifiers, short titles and **our own paraphrase** of each requirement's intent. They never reproduce the standards' or criteria's text. Work from licensed copies of the ISO standards and the AICPA's published criteria. The HIPAA regulations are US Government works; the catalog still restates them in plain words, and the eCFR text is the authority. TX-RAMP's controls are NIST SP 800-53 controls, also a US Government work, so the catalog uses NIST's titles and statements; TX-RAMP's own parameter values stay in the client's copy of DIR's Security Plan workbook.
 FedRAMP's rules are also a US Government work: the FedRAMP 20x catalog is generated from FedRAMP's machine-readable dataset and keeps FedRAMP's own statements.

## HIPAA

The HIPAA Security Rule (45 CFR 164.302–318) and the Breach Notification Rule (164.400–414), as in force in November 2026. HHS proposed a major revision of the Security Rule on 6 January 2025; it is not final (the regulatory agenda targets July 2027), so the catalog follows the rule in force. The Privacy Rule is not covered.

**Requirements.** 32 standards (the Security Rule's 23, including 164.308(b)(2) for business associates, 164.306(a) and (e), and the seven Breach Notification sections), 21 required and 22 addressable implementation specifications. IDs are the citations: `164.308(a)(1)(ii)(A)` is the risk analysis.

**Required and addressable.** Addressable doesn't mean optional. Nothing in scope can be excluded (E004). Each addressable specification records a decision (164.306(d)):

```yaml
decision: alternative          # or as_written
justification: Session tokens expire after 15 minutes on the API, so a workstation logoff timer adds nothing.
implementation: API tokens expire after 15 minutes of inactivity; kiosks lock after 5 minutes.
```

An `alternative` needs both the reason and the equivalent measure (E017). Either way the specification stays in scope and its four-part test checks the measure actually taken. Once work on it has started, a missing decision is W114, and it can't be *Ready* until the decision is recorded. The *Security Rule Applicability and Addressable Decisions* report (`soa.md`) has a **Decision** column for every addressable specification. The control matrix shows each requirement's kind: Standard, Required or Addressable.

**Categories.** The core is always in scope: the Security Rule and the parts of the Breach Notification Rule that apply to everyone (definitions and risk assessment, law enforcement delay, burden of proof). Then choose the client's role, which decides the rest:

| Category | Adds | Document |
|---|---|---|
| `covered_entity` | Business associate assurances (164.308(b)(1)) and the notices to individuals, the media and HHS (164.404–408) | Covered Entity Duties |
| `business_associate` | Subcontractor assurances (164.308(b)(2), 164.314(a)(2)(iii)) and notifying the covered entity (164.410) | Business Associate Duties |
| `clearinghouse`, `group_health_plan`, `government` | The specifications only those organizations have | One each |

Choose at least one role (`--categories business_associate`, or both); until then validation warns (W113). A health-tech vendor serving providers is usually a business associate only.

**Dates.** `dates.stage1` is the **readiness assessment** (the security evaluation, 164.308(a)(8)); `dates.stage2` is the **independent assessment** the client has committed to (a third-party assessor or a customer's audit). HIPAA has no certificate.

**References.** The internal audit evidences 164.308(a)(8), corrective actions 164.308(a)(1)(ii)(B), and the leadership review 164.306(e). HIPAA doesn't require a management review, so a missing one is never a warning.

**Mappings.** `mappings/hipaa__iso27001.yaml` proposes 6 equivalent, 5 subset and 33 related pairs; `mappings/hipaa__soc2.yaml` 24 related pairs. Before approving an `equivalent`, confirm the ISMS scope covers the whole ePHI environment; if it doesn't, downgrade the pair to `related`. In YAML, quote a citation with no parentheses (`'164.410'`): unquoted, it is read as the number 164.41, and validation says so. In the program layer, controls can map to `hipaa` and to NIST SP 800-53 together; NIST SP 800-66 Rev. 2 maps the Security Rule to 800-53.

## GDPR

The catalog is the GDPR as in force: 60 obligations cited by article, such as `Art32(1)(a)`, restated in plain words. The Commission's Digital Omnibus proposal (COM(2025) 837) would change several articles (the personal-data definition, Art. 9, 12, 13, 22, 30, 33 and 35). It is still under negotiation, so it isn't reflected; update the catalog if it is adopted.

**Roles.** The core is always in scope: security of processing (Art. 32) and cooperation with the supervisory authority (Art. 31). Choose `controller` and/or `processor` (W113 until one is chosen). A SaaS company is usually both: a controller for its own staff and marketing data, and a processor for its customers' data. Add these categories when they apply:

| Category | When | Adds |
|---|---|---|
| `dpo` | A DPO is required (Art. 37(1)) or appointed | Art. 37-39 |
| `representative` | Established outside the EU but subject to the GDPR (Art. 3(2)) | Art. 27 |
| `transfers` | Personal data leaves the EEA, including remote access | Art. 44, 45, 46, 49 |
| `special_categories` | Health, biometric, criminal-offence and other Art. 9/10 data | Art. 9, 10 |
| `children` | Online services offered directly to children | Art. 8 |

**Obligations and conditional obligations.** An obligation in scope can't be excluded (E004). Nine are conditional: consent (Art. 7), criminal-offence data (Art. 10), portability (Art. 20), automated decisions (Art. 22), joint controllers (Art. 26), prior consultation (Art. 36), and the three transfer mechanisms. Each can be marked not applicable with a justification that says why the situation doesn't arise. The *GDPR Applicability Statement* lists them.

**Documents.** 16 policies and procedures, each in one category, so a processor-only client never gets the controller documents.

**References.** References are role-aware: the internal audit evidences Art. 5(2) (accountability) for a controller, Art. 28(3)(h) (demonstrating compliance) for a processor-only client; risk work evidences Art. 32(2). There is no management review requirement. The validate phase covers territorial scope (Art. 3) and the national laws that add to the GDPR (employment data, the age of digital consent, DPO designation, health and genetic data).

**Mappings.** `mappings/gdpr__iso27001.yaml` (24 pairs) and `gdpr__soc2.yaml` (22 pairs) are all `related`. A GDPR obligation is about personal data and people's rights, so ISO or SOC 2 evidence points to it but never proves it alone.

**Not legal advice.** Lawful basis choices, DPO designation and transfer assessments are decisions for the client's counsel; the playbook's guardrails say so.

## FedRAMP 20x

FedRAMP 20x is the US government's newer path to certify cloud services for federal agencies: the provider shows Key Security Indicators with machine-readable, preferably automated, evidence and follows FedRAMP's process rules, and a FedRAMP-recognized assessor verifies and validates. The FedRAMP Consolidated Rules for 2026 (CR26) apply to new 20x certifications since 4 July 2026 and to existing ones by 1 January 2027, at their next assessment; the vulnerability rules (VDR, VER) take effect on 7 December 2026.

**Generated, not hand-written.** `frameworks/fedramp20x/catalog.yaml` is generated by `tools/fedramp20x.py` from FedRAMP's official dataset (github.com/FedRAMP/rules; the catalog header records the version). It keeps every Key Security Indicator (`KSI-IAM-ELP`) and every process rule that affects providers on the 20x path (`VDR-TFR-PDD`), with FedRAMP's own statement as the intent, per-class differences and timeframes run in, and FedRAMP's NIST SP 800-53 mappings as `nist80053`. Agency, assessor and Marketplace-form rules are left out, as are rules that are only MAY. FedRAMP updates the dataset often: regenerate the catalog, run the tests and review the diff.

**Classes.** Classes are levels of assurance, from minimal (Class A) to significant (Class D). Class A builds on a SOC 2 Type II, GovRAMP or FedRAMP Rev5 assessment from the past 12 months (FRC-CLA-ASF). Choose the class in `scope.categories` (W113 until one is chosen):

| Class | Categories | Requirements |
|---|---|---|
| A | `class_a` | 40 for every class + 4 Class A rules = 44 |
| B | `class_b` | 40 + 136 = 176 |
| C | `class_b,class_c` | 40 + 136 + 7 = 183 |

Class C adds to Class B, so `class_c` alone, or Class A with another class, is W115. Class A is defined by FedRAMP's lists in FRC-CLA-MFR (rules and the 7 indicators it must address) and FRC-CLA-RFR (rules it should address); the generator reads them, so a rule on the mandatory list is in every class even where its own subset is written for Class B and C. Class D isn't covered yet: FedRAMP has not set all of its 20x specifics. Where a rule's text or timeframe differs by class, the intent gives each (for example, drift detection every 3 months for Class A, monthly for Class B, every 14 days for Class C).

**Kinds.** A Key Security Indicator and a MUST rule can't be excluded (E004). Eight rules are a MUST for higher classes and a SHOULD for a lower one (for example, the Initial Incident Report: MUST for Class B and C, SHOULD for Class A); the catalog marks them `mandatory_in`, and they are recommendations in a record without that class. A SHOULD rule (`recommendation`) can be marked `applicable: false`; its justification records the reason and the resulting risk to customers, as FedRAMP's default artifacts ask, and the *FedRAMP 20x Applicability Statement* lists it. FedRAMP also lets a provider explain why an indicator or MUST rule isn't met, if a senior official accepts the risk: record that as an accepted risk in the gap register, not by excluding the requirement.

**Documents.** 18: one per Key Security Indicator theme and one per process area (certification package, Minimum Assessment Scope, communications, trust center, continuous monitoring reports, significant changes, incidents, vulnerabilities, secure configuration). A document is needed when any requirement it covers is in scope, so a Class A record gets 12.

**Dates and references.** `dates.stage1` is the independent assessment; `dates.stage2` the FedRAMP certification decision. The internal readiness review and corrective actions evidence KSI-SVC-EIS (evaluating and improving security), the leadership review KSI-PIY-RES (executive support), the repository's branch protection KSI-CMT-LMC (logging changes), and the scope document MAS-CSO-IIR. A Class A record, which has neither indicator, uses FRC-CSO-MRA (maintain responsibility and accountability) for the reviews. No management review is required.

**Program controls.** Map program controls to the KSI and rule ids themselves (`maps: {fedramp20x: [KSI-IAM-ELP]}`). A KSI maps to dozens of NIST controls, so a control mapped to one NIST control is not counted for the KSI automatically.

## TX-RAMP

The Texas Risk and Authorization Management Program certifies cloud services for Texas state agencies, public universities and community colleges. The catalog is DIR's TX-RAMP Security Controls Baselines 2.0: 223 NIST SP 800-53 Rev. 5 controls, with IDs such as `AC-2(3)`.

**Levels.** Level 1 (117 controls, public or low-impact data) is always in scope as the `core` category. Add `level_2` for confidential or regulated data in moderate or high impact systems (`--categories level_2`): it adds 106 controls.

**Not applicable.** A control the cloud service provider doesn't run (fully inherited from its hosting provider, or the customer's) can be marked `applicable: false`. Its `justification` must name who is responsible, as DIR's Security Plan asks.

**Dates.** `dates.stage1` is the **assessment submission** to DIR; `dates.stage2` is the **certification decision**. DIR certifies on the Assessment Questionnaire and the attached Security Plan, boundary diagram and data flow diagram (`docs/QUESTIONNAIRES.md`).

**Documents.** One policy and procedures document per control family (17), each supporting every control in its family. That is how DIR's guide expects the `-1` policy controls to be met.

**NIST mappings.** A program control mapped to `nist80053` also counts for a TX-RAMP record, because the IDs are the same. The engine adds `txramp` to its mappings, unless the control lists its `txramp` IDs itself.

**References.** The internal audit evidences CA-2, corrective actions CA-5, and the leadership review CA-7 (continuous monitoring). TX-RAMP doesn't require a management review.

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

**Document ingestion** is per record: each record reads its own folder (`intake/` for `engagement/`, `intake-27001/` for `engagement-27001/`), and the pull request gets one report section per record that had new files. Upload a document to every folder whose framework it serves; from engine 0.20 a document in several folders is read once for all of them (`ingest --all`). Client repositories set up before engine 0.14.1 need `"intake-*/**"` added to the `paths:` of `.github/workflows/ingest.yml`.

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

## Reference catalogs

Some frameworks are reported against through the common control catalog (`program/controls.yaml`,
[PROGRAM.md](PROGRAM.md)) without an engagement record of their own. The engine ships **NIST SP 800-53
Rev. 5** as `reference/nist80053.yaml`: all 1,014 controls and enhancements with their families and the
SP 800-53B low, moderate, high and privacy baselines, generated from NIST's OSCAL content (a US Government
work, not subject to copyright in the US). A client repository can add its own reference catalog at
`reference/<id>.yaml` with the same layout (`framework`, `groups`, `requirements` with `id` and `title`).
