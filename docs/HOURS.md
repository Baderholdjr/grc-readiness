# Hours and budget

The engagement's hours live in `engagement/hours.yaml`, one entry per block of work: date, person, hours, activity, optional phase and references (gap, finding, requirement, document ids) and a note. Hours used, burn by phase and the forecast are computed from it. Nobody edits a running total.

## Getting hours in

- **From a time tracker.** Export a CSV from **Toggl**, **Harvest** or **Clockify** (or any CSV with `date` and `hours` columns, plus optional `person`, `activity`, `note`, `refs`, `phase`) and commit it to `intake/timesheets/`. The **Hours** workflow imports every file there and opens a *Timesheet update* PR.
  - Set the repository variable `HOURS_MATCH` (e.g. `Larkspur`) to keep only rows whose client or project contains it.
  - Each entry's id comes from its source row, so re-importing a longer export adds only the new rows.
  - Activities are inferred from the task, tags and description using the playbook's keywords (`hours.activities`). References such as `GAP-01`, `NC-001` or `A.6.2.5` in the description are picked up when they exist in the record.
- **One entry at a time.** Run **Actions → Hours** with `log`: hours, activity, optional date, note and references. The person defaults to whoever runs it. Locally: `python -m grc hours log --hours 2.5 --activity interviews --person ana --note "Release walkthrough" --refs A.6.2.5`.

Timesheet files in `intake/timesheets/` are never sent to document ingestion or AI drafting.

## Plans and forecast

- **Budget:** `budget.hours_total` in `engagement.yaml`.
- **Per phase:** set `hours:` on a phase, or the playbook's `hours.phase_split` divides the budget (validate 12%, governance 20%, implement 28%, test 20%, Stage 1 10%, Stage 2 10%). Entries without a phase count towards the phase whose dates they fall in.
- **Forecast:** the average of the last 4 full weeks, projected to the end of the last phase.

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
