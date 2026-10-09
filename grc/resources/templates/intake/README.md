# Intake templates

Give these to the client (open in Excel or Google Sheets; save as CSV or XLSX), then upload the
filled files to `intake/`. Files are recognised by their header row, so keep the headers.

| Template | Columns | Becomes |
|---|---|---|
| `gaps.csv` | area, finding, requirements, owner, due, severity, phase | new gaps in `gaps.yaml` |
| `evidence.csv` | title, type, location, owner, collected, approved_by, approved_on, valid_for_days | pointers in `evidence/index.yaml` |
| `controls.csv` | requirement, leg, status, owner, note | client claims (`claimed` legs) |
| `inventory.csv` | name, kind, owner, risk_tier, description | `inventory.yaml` |

- `requirements`: ISO 42001 ids such as `5.2` or `A.6.2.4`, separated by commas.
- `leg`: documented, implemented, evidence exists, tested.
- `type`: document, record, config, log, test, sample, interview, screenshot.
- `kind`: ai_system, sdlc_tool, infrastructure, model, dataset, supplier_service.
- Delete the example row before sending.
