# OSCAL: export the record, validate files, import a control catalog

[OSCAL](https://pages.nist.gov/OSCAL/) is NIST's machine-readable format for control catalogs, baselines, system
security plans, assessment results and plans of action. FedRAMP is moving its packages to machine-readable
formats, and GRC tools and assessors increasingly accept OSCAL. The engine reads and writes **OSCAL 1.2.3 JSON**
and checks every file against NIST's own schema (vendored in `grc/resources/oscal/`).

## Export

```
python -m grc --engagement engagement oscal export --out out/oscal
```

| File | OSCAL model | What it holds |
|---|---|---|
| `catalog.json` | catalog | The framework's requirements as the engine holds them: our paraphrases for licensed standards (ISO/IEC, AICPA, Global CBPR), and the imported text for a catalog imported from OSCAL. Not written for TX-RAMP, whose profile points at NIST's own SP 800-53 Rev. 5 catalog (release v1.6.0 of NIST's OSCAL content) |
| `profile.json` | profile | The requirements in this record's scope (categories, levels, classes) |
| `ssp.json` | system security plan | Scope statement, boundary, owners as users, inventory items, and for each requirement its owner, implementation statement and status |
| `assessment-plan.json` | assessment plan | What the readiness assessment reviews |
| `assessment-results.json` | assessment results | One observation per cited evidence item (method, collected and expiry dates, where it lives) and one finding per requirement |
| `poam.json` | plan of action and milestones | Every open or in-progress gap in scope, with its risk, owner, phase and due date |

How the record maps:

- **The record must validate.** The export refuses a record with validation errors (as `build` does). With
  `--force` it writes a draft, marked DRAFT in every file, in which no requirement that has an error is shown as
  implemented or satisfied.
- **Implementation status** comes from the requirement's state: Ready → `implemented`; In progress → `partial`;
  an unverified client claim, Not started or Missing → `planned` (a claim says so in its remarks);
  Excluded → `not-applicable`, with the justification.
- **A finding is `satisfied` only when the record shows the requirement Ready** (every leg verified, on a record
  that validates). Everything else is `not-satisfied`. Each finding targets the requirement's statement
  (`<control-id>_smt`). The results say they are the client's readiness record, not an independent assessment:
  nothing in the export claims more than the record.
- **Control ids** are OSCAL tokens. NIST ids take NIST's form (`AC-2(3)` → `ac-2.3`); FedRAMP 20x ids are
  lower-cased; other frameworks are prefixed (`A.5.15` → `iso27001-A.5.15`,
  `164.308(a)(1)(ii)(A)` → `hipaa-164.308.a.1.ii.A`). A catalog imported from OSCAL keeps its own ids.
- **UUIDs are derived** from the client, framework and item, so the same record exports the same bytes and a
  re-export updates rather than duplicates what a tool imported.
- Evidence stays where it lives: observations say where it is held, never include the evidence itself.

The auditor package (`grc package`) includes the export in `09-oscal/`, with its checksums in the manifest.

If an export would not pass the schema, nothing is written and the command fails with the schema errors (that
is a bug: please report it). An observation with no collection date in the evidence index shows the export date
(OSCAL requires one) and says so in its remarks.

## Validate

```
python -m grc oscal validate path/to/ssp.json other.json
```

Checks any OSCAL 1.2.3 JSON file (catalog, profile, component definition, SSP, assessment plan or results,
POA&M) against NIST's schema. Useful for files a client or a GRC tool sends.

## Import a control catalog and baseline

```
python -m grc oscal import \
  --catalog NIST_SP-800-53_rev5_catalog.json \
  --profile NIST_SP-800-53_rev5_MODERATE-baseline_profile.json \
  --id nist80053-moderate --name "NIST SP 800-53 Rev. 5 Moderate baseline" --short-name "800-53 Moderate"
```

Writes `frameworks/<id>/catalog.yaml` and a starting `frameworks/<id>/playbook.yaml` in the client repository,
then `new-engagement --framework <id>` starts a record on it like any built-in framework. Tested with NIST's
SP 800-53 Rev. 5 LOW (149 controls), MODERATE (287), HIGH (370) and PRIVACY (96) baselines from
github.com/usnistgov/oscal-content.

- **What a profile can select:** `include-all` or `include-controls` (`with-ids`, `matching` patterns,
  `with-child-controls`), minus `exclude-controls`. Withdrawn controls are left out. Without `--profile`, every
  control in the catalog is imported.
- **Refused, with the reason:** a profile naming controls the catalog doesn't have (the wrong catalog), a profile
  that imports another profile or more than one source, and one that changes parameters or text (`modify`).
  For those, import the publisher's *resolved profile catalog* on its own, without `--profile`: NIST publishes
  one for each baseline (`…-baseline-resolved-profile_catalog.json`), and FedRAMP publishes resolved catalogs for
  its Rev. 5 baselines.
- Each requirement keeps the control's label as its id (`AC-2(3)`), its title, its statement as the intent (with
  parameters shown as `[label]`, and selections with their choices), its family as its group (nested groups
  become one group titled "Parent: Child"), and its OSCAL id (`oscal_id`) for the export.
- The playbook is a neutral starting point: phases, readiness criteria, the four-part evidence test. Edit it to
  fit; a later `--force` re-import refreshes the catalog and keeps your playbook.
- The command refuses to overwrite a built-in framework, an existing import without `--force`, or a file that
  isn't valid OSCAL (files over 80 MB, or nested too deeply, are refused before parsing finishes).
- Only import catalogs you may use and share: NIST's are US Government works. The imported text goes into the
  client repository and into `catalog.json` in exports and auditor packages, so check the license of anyone
  else's.

## FedRAMP 20x machine-readable packages

FedRAMP 20x defines its own JSON schemas for the certification package (on fedramp.gov) alongside OSCAL. The
engine's FedRAMP 20x record already exports as OSCAL above; a writer for FedRAMP's own package schemas will
follow once those schemas are added to the engine.
