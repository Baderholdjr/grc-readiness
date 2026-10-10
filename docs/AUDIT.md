# Internal audit (9.2) and corrective actions (10.2)

## Files

| File | Holds | Who edits |
|---|---|---|
| `engagement/audit/program.yaml` | The audit programme: each audit's scope, criteria, auditors, dates, status and sample populations | Engagement lead |
| `engagement/audit/<AUD-ID>/workpapers/WP-NN.yaml` | One workpaper per requirement in scope: test steps, sample, results, conclusion | Generated, then completed by the auditor |
| `engagement/audit/populations/*.csv` | Optional populations the client supplies, e.g. an incident list | Analyst |
| `engagement/findings.yaml` | Nonconformities (`NC-001`, major/minor), opportunities for improvement (`OFI-001`), and corrective actions, from any source | Auditor raises; owner and analyst maintain |

## Running an audit

1. **Set up.** In `program.yaml`, set the **auditors** and confirm scope and dates.
   - Scope can be `all`, or a list of requirement IDs and groups such as `A.6` or `9`. Use `exclude` to drop items.
   - Auditors can be names, roles or GitHub users. CI rejects any auditor who owns a control in scope (**E020**). Exclude those controls from scope, or have someone else audit them.
2. **Plan.** Run **Actions → Internal audit**, enter the audit ID, choose `plan`. Locally: `python -m grc audit plan AUD-2027-01`.
   This creates a workpaper for every requirement in scope. Each workpaper has test steps built from:
   - the requirement's intent and expected evidence
   - its owner
   - any open client claims and linked gaps

   If a collector's evidence supports the requirement (`supports:` in `collectors.yaml`), its snapshot becomes the workpaper's sample **population**, for example every PR merged in the last 90 days. Merge the PR it opens.
3. **Sample.** Run the same workflow with `sample`.
   - **Size:** by default 1 for a population of 1, 2 for up to 4 items, 3 for up to 12, 5 for up to 52, 15 for up to 250, otherwise 25. Override per workpaper with `sample_size`.
   - **Reproducible:** the same population and audit/workpaper IDs always select the same items. The population size, its SHA-256 and the seed are recorded, so anyone can re-perform the selection.
   - **Other populations:** set `population:` to a name defined under `populations:` in `program.yaml`. That can be a CSV file, a list, or another collector's evidence ID.
4. **Fieldwork.** Set the audit's status to `fieldwork`. For each workpaper:
   - mark each sample item `pass` or `exception`, with a note
   - write a `summary`
   - set `conclusion` to `effective`, `not_effective` or `not_applicable`
   - set `performed_by` and `performed_on`

   CI enforces two rules here (**E022**):
   - An `effective` conclusion with exceptions needs an `exception_rationale`.
   - A `not_effective` conclusion must cite a finding.
5. **Findings.** Add each nonconformity to `findings.yaml` (source `internal_audit`, with `audit` and `workpaper`). It becomes an Issue labelled `grc-finding`, assigned to the owner, with overdue reminders.
6. **Review.** A *different* person sets `reviewed_by` and `reviewed_on` on each workpaper. A reviewed `effective` workpaper becomes **test evidence**: a control's *Tested* leg can cite it as `AUD-2027-01/WP-07`.
7. **Report and close.** Move the audit to `reporting`, then `closed` with `report: {issued, approved_by, conclusion}`. CI checks each step (**E021**). The audit report is published on the `reports` branch as `audit-<ID>.md`.

## Corrective action lifecycle (10.2)

```
open → action_planned → implemented → closed
       (owner, due,      (evidence)    (effectiveness: effective: true,
        root_cause,                     reviewed_by ≠ owner, reviewed_on, evidence)
        corrective_action)
```

- **Accepting findings:** `accepted` is allowed for minor findings and OFIs, never for a major one.
- **Open major findings:** while a major finding is open, its requirement's *Tested* leg can't be `verified` (**E026**).
- **Other sources:** findings from Stage 1, Stage 2, incidents or management review go in the same register, with `source` set accordingly.

## Reports

The `reports` branch gains:
- `internal-audit.md`: the programme, with progress for each audit
- `audit-<ID>.md`: one report per audit, with scope, results by workpaper, and findings
- `corrective-actions.md` and `.csv`: the full register
