# The compliance program: common controls, governance calendar, owner certification

An engagement record (`engagement/`, `engagement-<name>/`) holds one framework. The **program layer** sits
above the records, in `program/` at the repository root, and describes how the organization actually runs
its controls: once, for every framework it reports against.

| File | Holds | Who edits |
|---|---|---|
| `program/controls.yaml` | The common control catalog: each control once, with owner, frequency, type, evidence, and the requirements it satisfies in every framework | GRC lead |
| `program/calendar.yaml` | Recurring governance obligations, each with an owner, due dates and evidence of completion | GRC lead; owners record completions |
| `program/certifications/<period>/<owner>.yaml` | Quarterly owner certifications | Opened by the workflow; completed and signed by the owner |
| `program/itgc/<test id>/` | ITGC workpapers (see [ITGC.md](ITGC.md)) | Generated; completed by the auditor |
| `program/owners.yaml` | Optional: program owners (same format as a record's `owners.yaml`). Without it, every record's owners are used | GRC lead |

Nothing in the program layer marks a requirement verified. A mapping is the program's claim that a control is
meant to satisfy a requirement; each record still tests that requirement against its evidence.

## 1. The common control catalog

```yaml
controls:
  - id: CTL-ACC-01
    title: Quarterly user access review
    description: System owners review every account with access to in-scope systems; removals are ticketed.
    owner: IT Operations Manager        # a role in program/owners.yaml (or a record's owners.yaml)
    frequency: quarterly                # continuous, daily, weekly, monthly, quarterly, semiannual, annual, event
    type: hybrid                        # manual, automated or hybrid (the scorecard reports the share automated)
    evidence: ["iso27001:EV-007", "soc2:EV-006"]     # evidence held in the records, <framework>:<id>
    maps:
      iso27001: [A.5.18, A.8.2]
      soc2: [CC6.2, CC6.3]
      nist80053: ["AC-2", "AC-2(3)"]
```

- **`maps`** can name any framework the engine knows: the frameworks you have records for (ISO 42001,
  ISO 27001, SOC 2), and **reference catalogs** you report against without a record. The engine ships NIST
  SP 800-53 Rev. 5 (`nist80053`, all 1,014 controls and enhancements, with the SP 800-53B low, moderate,
  high and privacy baselines). Put quotes around IDs YAML could read as numbers, such as `"7.5"` or `"9.2"`.
- **Evidence** is cited from a record, so it keeps that record's freshness and approval rules. The catalog
  reports evidence that has expired (P110).
- **Crosswalk suggestions.** The coverage report lists mappings the framework crosswalks in `mappings/`
  propose for each control (for example, a control mapped to ISO 27001 A.8.32 is suggested for SOC 2 CC8.1).
  They are suggestions: add one only after checking the control really meets it.

## 2. The governance calendar

```yaml
obligations:
  - id: OBL-ACCESS
    title: Quarterly user access review
    owner: IT Operations Manager
    every: quarterly                    # monthly, quarterly, semiannual or annual
    first_due: 2026-01-15               # later due dates follow from it (month ends are kept: 31 Jan -> 28 Feb)
    lead_days: 14                       # optional: open the issue this many days before (default 14)
    controls: [CTL-ACC-01]              # optional: the common controls it evidences
    source: ISO 27001 A.5.18; SOC 2 CC6.2; customer contract schedule 3
    evidence_expected: Signed review export per system and removal tickets
    done:
      - {period: 2026-10-15, completed: 2026-10-02, by: Elena Sokolova, evidence: ["iso27001:EV-007"]}
```

- An occurrence is identified by its due date (`period`). It is **on time** if `completed` is on or before
  the due date, **late** otherwise, **overdue** if it has no completion and the date has passed.
- **Evidence of completion is required.** CI refuses a completion with no evidence (P204).
- **Issues.** The *Compliance program* workflow runs every Monday and opens an Issue (label
  `grc-obligation`) for each occurrence due within `lead_days` or overdue, assigned to the owner's GitHub
  users. The Issue closes when the completion is merged.
- **Calendar file.** The reports include `governance-calendar.ics`: the next 12 months of due dates, which
  owners can subscribe to in Outlook or Google Calendar.

Use it for every recurring duty, not only framework ones: policy reviews, access and change reviews, training,
vendor reviews, board meetings, and the assessments customers, banks, partners and regulators require of you.
Put where each comes from in `source`.

## 3. Quarterly owner certification

On the first day of each quarter the *Compliance program* workflow opens **one pull request per control
owner** with `program/certifications/<quarter>/<owner>.yaml`, listing the controls they own:

```yaml
period: 2026-Q3
owner: IT Operations Manager
due: 2026-10-30                         # 30 days after the quarter ends
statement: I confirm that during 2026-Q3 each control below operated as described in program/controls.yaml,
  except where I say otherwise.
controls:
  - {id: CTL-ACC-01, title: ..., response: operating, note: "", follow_up: ""}
  - {id: CTL-ACC-02, title: ..., response: exception,
     note: "3 of 41 leavers kept Okta access for 2-6 days", follow_up: "GAP-07"}
certified_by: elena-s                   # the owner's GitHub user
certified_on: 2026-10-14
```

The owner answers every control (`operating`, `exception`, `not_operating` or `not_applicable`), explains
anything other than `operating`, names a follow-up for exceptions, signs, and approves the pull request.
CI enforces:

- nothing left `pending` once signed (P303); a note for every non-`operating` answer (P304)
- the signature is one of the owner's GitHub users (P305), on or after the quarter's last day (P309)
- an owner certifies only their own controls (P308)

On GitHub Pro, Team or Enterprise, add the certification files to `.github/CODEOWNERS` so the owner's
approval is required to merge. On GitHub Free, the signature check and the pull request history are the record.

Run it by hand with **Actions → Compliance program → certify** (optionally for a given quarter), or locally:
`python -m grc program certify --period 2026-Q3`.

## 4. Reports and the scorecard

`python -m grc program report --out out/program` (also run by *Validate* and *Publish reports*; on the
`reports` branch under `program/`):

| File | What it shows |
|---|---|
| `program.md` | The **scorecard**: controls, requirements mapped, reuse per control, share automated, evidence currency, coverage per framework, calendar on-time rate and overdue count, certification completion and exceptions, open findings and their age, open gaps |
| `control-catalog.md` | Every control with its owner, evidence and the requirements it satisfies |
| `coverage.md` | Per framework: in-scope requirements with no common control; crosswalk suggestions |
| `governance-calendar.md` / `.ics` | Obligations, last completion, next due date, overdue occurrences |
| `certifications.md` | Each quarter's certifications and the exceptions owners reported |
| `common-control-matrix.xlsx` | Controls, Mapping, Coverage and Calendar sheets |
| `scorecard.json` | The same KPIs, machine-readable. The `reports` branch history gives the trend quarter by quarter |

## Validation codes

| Code | Severity | Meaning |
|---|---|---|
| P101 | error | A program file doesn't match its schema |
| P102 | error | Control id used twice |
| P103 | error | `maps` names a framework the engine doesn't know |
| P104 | error | A mapped requirement isn't in that framework |
| P105 | error | Control evidence isn't `<framework>:<id>`, has no record, or isn't in it |
| P106 | warning | Control owner isn't a known role |
| P107 | warning | In-scope requirements of a record that no common control covers |
| P108 | warning | A control maps to a requirement the record leaves out of scope or marks not applicable |
| P109 | info | A control cites no evidence yet |
| P110 | warning | Cited evidence has expired |
| P202 | error | Obligation id used twice |
| P203 | error | A completion's `period` isn't one of the obligation's due dates |
| P204 | error | A completion with no evidence |
| P205 | error | Completion evidence isn't found |
| P206 | warning | An occurrence is overdue |
| P207 | warning | Obligation owner isn't a known role |
| P208 | error | An obligation names a control that isn't in the catalog |
| P209 | error | A completion date is in the future |
| P301 | error | A certification doesn't match its schema or its folder |
| P302 | warning | Certification owner isn't a known role |
| P303 | error | Signed with controls still pending, or only half signed |
| P304 | error | A non-`operating` answer with no note |
| P305 | error / warning | Signed by someone who isn't one of the owner's GitHub users (warning when the owner has none to check against) |
| P306 | warning | A certification is past due and unsigned |
| P307 | warning | An exception with no follow-up |
| P308 | error | A control isn't in the catalog, or belongs to another owner |
| P309 | error | Signed in the future, or before the quarter ended |
| P310 | warning | The owner owns controls the certification doesn't list (added after it was opened) |
| P401–P406 | | ITGC workpapers: see [ITGC.md](ITGC.md) |
