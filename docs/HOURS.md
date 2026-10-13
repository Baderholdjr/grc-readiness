# Hours and budget

The engagement's hours live in `engagement/hours.yaml`, one entry per block of work: date, person, hours, activity, optional phase and references (gap, finding, requirement, document ids) and a note. Hours used, burn by phase and the forecast are computed from it. Nobody edits a running total.

## Getting hours in

- **From a time tracker.** Export a CSV from **Toggl**, **Harvest** or **Clockify** (or any CSV with `date` and `hours` columns, plus optional `person`, `activity`, `note`, `refs`, `phase`) and commit it to `intake/timesheets/`. The **Hours** workflow imports every file there and opens a *Timesheet update* PR.
  - Set the repository variable `HOURS_MATCH` (e.g. `Larkspur`) to keep only rows whose client or project contains it. Case, stray quotes and spaces don't matter; separate alternatives with commas. If the filter skips every row, the PR lists the client and project names it found.
  - Each entry's id comes from the row's content, not the file name, so re-importing a renamed or longer (cumulative) export adds only the new rows. Identical rows in one export are kept as separate work.
  - Dates like `05/09/2026` are read day/month or month/day according to the file (any day above 12 decides it). If a file is ambiguous, the PR says so and month/day is assumed; pass `--date-order DMY` (or set `hours.date_order` in the playbook) for European exports.
  - Activities are inferred from the task, tags and description using the playbook's keywords (`hours.activities`). References such as `GAP-01`, `NC-001` or `A.6.2.5` in the description are picked up when they exist in the record; bare clause numbers (`6.1.2`) are taken only from a `refs` or tags column, so "2.5 hours" isn't read as a clause.
- **One entry at a time.** Run **Actions → Hours** with `log`: hours, activity, optional date, note and references. The person defaults to whoever runs it. Locally: `python -m grc hours log --hours 2.5 --activity interviews --person ana --note "Release walkthrough" --refs A.6.2.5`.

Timesheet files in `intake/timesheets/` are never sent to document ingestion or AI drafting, and hours and budget never appear in what auditors receive: the auditor package leaves out the timesheet and the workbook's Hours sheet, its brief and status summary omit hours and budget, and budget warnings (W106, W160, W161, W163) are left out of its known issues.

**In `hours.yaml`:**
- `aliases: {"Ana Lopez": ana}` merges one person's spellings (tracker name, GitHub user).
- `ignored: [H-…]` lists entries removed on purpose, so a later import doesn't bring them back.

## Plans and forecast

- **Budget:** `budget.hours_total` in `engagement.yaml`.
- **Per phase:** set `hours:` on a phase, or the playbook's `hours.phase_split` divides the budget (validate 12%, governance 20%, implement 28%, test 20%, Stage 1 10%, Stage 2 10%). Entries without a phase count towards the phase whose dates they fall in.
- **Forecast:** the average of the last 4 full weeks (fewer early in the engagement), projected to the end of the last phase.

## Reports

`hours.md` and `hours.csv` show:
- budget, used, remaining, burn rate and forecast
- time elapsed against budget used
- hours by phase (planned, used, remaining), by activity, by person and by week
- time recorded against gaps, findings and requirements

The readiness summary and the brief show hours used.

## Rules

| Code | Severity | Rule |
|---|---|---|
| E060 | error | Duplicate entry id; future date; unknown activity, phase or reference; more than 14 hours for one person on one day (usually a duplicated import) |
| W106 | warning | 80% of the budget used |
| W160 | warning | A phase has used more than its planned hours |
| W161 | warning | The forecast exceeds the budget |
| W163 | warning | `budget.hours_used` is still set in `engagement.yaml` and differs from the timesheet (remove it; the timesheet wins) |
