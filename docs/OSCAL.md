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
| `catalog.json` | catalog | The framework's requirements (our paraphrased wording, never a standard's text). Not written for TX-RAMP, whose profile points at NIST's own SP 800-53 Rev. 5 catalog |
| `profile.json` | profile | The requirements in this record's scope (categories, levels, classes) |
| `ssp.json` | system security plan | Scope statement, boundary, owners as users, inventory items, and for each requirement its owner, implementation statement and status |
| `assessment-plan.json` | assessment plan | What the readiness assessment reviews |
| `assessment-results.json` | assessment results | One observation per cited evidence item (method, collected and expiry dates, where it lives) and one finding per requirement |
| `poam.json` | plan of action and milestones | Every open or in-progress gap in scope, with its risk, owner, phase and due date |

How the record maps:

- **Implementation status** comes from the requirement's state: Ready → `implemented`; In progress or an
  unverified claim → `partial`; Not started or Missing → `planned`; Excluded → `not-applicable`.
- **A finding is `satisfied` only when the record shows the requirement Ready** (every leg verified with current
  evidence). Everything else is `not-satisfied`. The results say they are the client's readiness record, not an
  independent assessment: nothing in the export claims more than the record.
- **Control ids** are OSCAL tokens. NIST ids take NIST's form (`AC-2(3)` → `ac-2.3`); FedRAMP 20x ids are
  lower-cased; other frameworks are prefixed (`A.5.15` → `iso27001-A.5.15`,
  `164.308(a)(1)(ii)(A)` → `hipaa-164.308.a.1.ii.A`). A catalog imported from OSCAL keeps its own ids.
- **UUIDs are derived** from the client, framework and item, so the same record exports the same bytes and a
  re-export updates rather than duplicates what a tool imported.
- Evidence stays where it lives: observations say where it is held, never include the evidence itself.

The auditor package (`grc package`) includes the export in `09-oscal/`, with its checksums in the manifest.

If an export would not pass the schema, nothing is written and the command fails with the schema errors (that
is a bug: please report it).

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
then `new-engagement --framework <id>` starts a record on it like any built-in framework. Any OSCAL catalog and
profile work: NIST's SP 800-53 baselines (from github.com/usnistgov/oscal-content), FedRAMP Rev. 5 baselines,
or an organisation's own.

- The profile's `include-controls` choose the controls; withdrawn controls are left out. Without `--profile`,
  every control in the catalog is imported.
- Each requirement keeps the control's label as its id (`AC-2(3)`), its title, its statement as the intent (with
  parameters shown as `[label]`), its family as its group, and its OSCAL id (`oscal_id`) for the export.
- The playbook is a neutral starting point: phases, readiness criteria, the four-part evidence test. Edit it to
  fit; a later `--force` re-import refreshes the catalog and keeps your playbook.
- The command refuses to overwrite a built-in framework, an existing import without `--force`, or a file that
  isn't valid OSCAL.
- Only import catalogs you may use: NIST's are US Government works; check the license of anyone else's.

## FedRAMP 20x machine-readable packages

FedRAMP 20x defines its own JSON schemas for the certification package (on fedramp.gov) alongside OSCAL. The
engine's FedRAMP 20x record already exports as OSCAL above; a writer for FedRAMP's own package schemas will
follow once those schemas are added to the engine.
