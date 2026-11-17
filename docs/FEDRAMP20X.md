# FedRAMP 20x documents in FedRAMP's JSON formats

FedRAMP asks providers on the 20x path for machine-readable documents: a Certification Package Overview, a
Security Decision Record, an Ongoing Certification Report every 3 months, vulnerability reports, incident reports
and Significant Change Notifications. FedRAMP publishes a JSON Schema for each
([github.com/FedRAMP/schemas](https://github.com/FedRAMP/schemas), for the Consolidated Rules 2026). The engine
writes all of them from a FedRAMP 20x record and checks each one against FedRAMP's schema before writing it.

```
python -m grc fedramp init                      # starter files in engagement/fedramp/ (fictional examples)
python -m grc fedramp export --out out/fedramp20x [--from 2026-08-01 --to 2026-10-31]
python -m grc fedramp validate FILE...          # check any file against FedRAMP's schemas
```

## What is written

| File | FedRAMP rule | Built from |
|---|---|---|
| `certification-package-overview.json` | FRC-CSO-PKG, CDS-CSO-PUB, CDS-CSO-UTC, MAS-CSO-TPR | `fedramp/package.yaml` |
| `security-decision-record.json` | SDR-CSO-FRR, SDR-CSO-MTD | every Key Security Indicator and rule in the record's scope, with ports and protocols from `package.yaml` |
| `ongoing-certification-report-<from>_<to>.json` | CCM-OCR-AVL | `fedramp/reports.yaml`, plus accepted vulnerabilities, transformative changes, incidents and agencies from the other files |
| `vulnerability-detail-report-<from>_<to>.json` | VER-RPT-VDT, VER-RPT-PER | vulnerabilities not accepted, with activity in the period |
| `accepted-vulnerability-info-<from>_<to>.json` | VER-RPT-AVI | accepted vulnerabilities with activity in the period |
| `historical-vulnerability-activity.json` | VER-TFR-MRH | every vulnerability, as of the run |
| `incidents/<id>.json` | IEC-CSO-IIR, IEC-CSO-OIR, IEC-CSO-FIR | `fedramp/incidents.yaml`: one report per incident, at its stage |
| `significant-changes/<id>.json` | SCN-CSO-INF, SCN-CSO-EVA | `fedramp/changes.yaml` |

FedRAMP asks for these in human-readable and JSON formats, so each JSON file has a Markdown copy beside it
(`.md`), using the field names from FedRAMP's schema.

**The period.** The report files cover one period. By default it is the latest entry in `fedramp/reports.yaml` that
has ended; with no entry, the 3 months up to today. `--from` and `--to` choose another. Periods are in UTC. A
vulnerability has activity in a period if it was detected, evaluated, reduced, closed or accepted in it, or was still
open during it. The overview's next report date is 3 months after the latest period, and is left out once it has
passed (the validator warns instead).

**Nothing is written unless all of it is right.** The export stops, and writes nothing, when the record has
validation errors, `package.yaml` is missing or has no `overview_url`, `vulnerabilities.yaml` or `incidents.yaml` is
missing (an empty list states there are none; a missing file says nothing), or any document doesn't match FedRAMP's
schema. The message says what to fix. `--force` writes drafts anyway: each Markdown copy says it is a draft not for
submission, and the Security Decision Record's version starts with `DRAFT`. Even then, a report whose source file is
missing or unreadable isn't written (it would wrongly say there was nothing to report), and an id that isn't a plain
token (letters, digits, `.`, `_`, `-`) or appears twice, ignoring case, stops the export: ids become file names.

**In the auditor package.** For a FedRAMP 20x record, the auditor package carries the same files in
`10-fedramp20x/`, with their checksums. If they can't be built yet, the package's index says why.

## The Security Decision Record

One entry per Key Security Indicator (`keySecurityIndicators`) and per FedRAMP rule (`fedRampRequirements`) in the
record's scope: 44 for Class A, 176 for Class B, 183 for Class C.

| Field | From the record |
|---|---|
| Implementation status | **Implemented** only when the requirement is Ready (every check verified by a reviewer) and has no validation error. **Partially Implemented** when some checks are verified or partly in place. **Not Implemented** when nothing is verified, including when the provider has only claimed it. A SHOULD rule marked not applicable has no status. |
| Implementation | The implementation statement. A SHOULD rule marked not applicable gives its justification (the reason and the resulting risk to customers); a gap with status `risk_accepted` adds a line saying the risk is accepted. |
| Validation | The *Implemented*, *Evidence exists* and *Tested* checks that have started: their status and the evidence they cite, each labelled as a readiness review by the engagement team, not an independent assessment. |
| Assessment | Always empty: it is the independent assessor's to fill. |
| Tests | Evidence cited by a verified check that is a test or sample, or produced by a collector (with its latest result). |
| Evidence | Each item cited by a check that is verified or partly in place (never by a bare claim): its type, title and date. Its location is included only when it is a web address and the item isn't marked `confidential` or `restricted`. |

Notes on the checks are working notes and are never copied into the record.

## The files in `engagement/fedramp/`

Run `grc fedramp init` for commented starter files. The validator checks each file (E001), and flags duplicate ids
or unknown requirement ids (E092).

**`package.yaml`**: the offering. `overview_url` is the https address where the Certification Package Overview
will be published: every other report points to it. `fedramp_id` is the FedRAMP ID, or until one is assigned, the
provider's name and the service's acronym (the default). `service` holds the name, acronym, description, website,
logo, service models (`SaaS`, `PaaS`, `IaaS`), deployment model and business categories (FedRAMP's list).
`contacts` needs at least one `Security` and one `Sales` contact. Also: `trust_center` and
`secure_configuration_guide` (URL, description, whether sign-in is needed, how to request access),
`repositories`, `assessor`, `advisors`, `certified_services`, `third_party` (certified and non-certified
third-party information resources), `ports_and_protocols`, `agencies` (agencies directly using the offering), and
`sdr` (`version`, `update_source`).

**`vulnerabilities.yaml`**: one entry per vulnerability, by your own tracking `id`: `detected` and `source`,
`description`, `impact`, `evaluated`, `internet_reachable`, `likely_exploitable`, `rating` (the Potential Agency
Impact N-rating, 0 to 5), `next_reduction`, `reductions` (completed reductions, each a `date` and `rating`), `supplementary`, and once it's done,
`disposition` and `closed`. *Partially Mitigated* still counts as open. An accepted vulnerability has `accepted: {rationale, date}`. A vulnerability that isn't
fully mitigated or remediated 192 days after evaluation must be an accepted vulnerability (VER-TFR-MAV): the
reports show it as overdue and the validator warns (W183). `overdue: {explanation}` records any other overdue reason.

**`incidents.yaml`**: one entry per FedRAMP Reportable Incident. Its report is an *Initial* report until there is
observed activity, indicators, CVEs, a root cause or response activity (then *Ongoing*), and *Final* once
`resolved` is set.

**`changes.yaml`**: one entry per significant change: `type` (`Adaptive` or `Transformative`) and why, the
description, reason, customer impact, plan and timeline, the KSIs or rules it touches (`requirements`), and the
impact analysis. Routine recurring changes don't need one.

**`reports.yaml`**: one entry per Ongoing Certification Report period (`from`, `to`): changes to certification
data, planned changes and how far ahead they run (`planned_through`, default 3 months past the period), and
updated recommendations. The rest of the report is filled in from the other files.

**Keep these files in the client's private repository.** Vulnerability and incident details are sensitive. The
client site and the rooms never show them; the auditor package carries them for the assessor.

## Rules

| Code | Severity | Rule |
|---|---|---|
| E001 | error | A file in `engagement/fedramp/` doesn't match its format |
| E092 | error | The same id twice in a file, or a change naming a KSI or rule that isn't in the catalog |
| W182 | warning | `package.yaml`, `vulnerabilities.yaml` or `incidents.yaml` is missing, or the package still needs `overview_url`, a Security or Sales contact or `trust_center`, or the next Ongoing Certification Report is overdue |
| W183 | warning | A vulnerability is still open 192 days after evaluation and isn't an accepted vulnerability (VER-TFR-MAV) |

## FedRAMP's schemas

The engine carries FedRAMP's schemas unchanged in `grc/resources/fedramp20x/schemas/`, with their SHA-256 sums
(the tests check them). FedRAMP marks them as drafts and versions each one. To update: copy the new files from
FedRAMP's repository, update the README and `SHA256SUMS` there, run the tests and review the differences in the
exported documents.
