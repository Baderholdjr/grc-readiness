# ITGC tests on GitHub: change management and logical access

IT general controls (ITGCs) are the controls auditors rely on for financial reporting (SOX) and for SOC 2
and ISO 27001: changes to production are authorized and tested, and only approved people have access. The
engine tests both directly against GitHub, on the real population, and writes a workpaper the auditor
completes.

```
python -m grc itgc change --repo acme/payments --id ITGC-CHG-2026Q3 --from 2026-07-01 --to 2026-09-30
python -m grc itgc access --repo acme/payments --id ITGC-ACC-2026Q4
```

Or **Actions → ITGC test** (it opens a pull request with the workpaper). To test a repository other than the
one the workflow runs in, add a read-only `GH_COLLECTOR_TOKEN` secret (fine-grained: Metadata, Contents,
Pull requests, Checks read; Administration read for the access test).

Each test writes `program/itgc/<id>/`:

| File | Holds |
|---|---|
| `population.json` | Every item fetched from GitHub, with its SHA-256, so anyone can re-perform the test |
| `workpaper.yaml` | Attributes, the sample, the automated result of every attribute for every sampled item, and the blanks the auditor fills |
| `workpaper.md` | The same, readable (also in the pull request body) |

## Change management

**Population:** every change that reached the branch in the period: merged pull requests, plus commits on the
branch that no merged pull request accounts for (direct pushes).

| Attribute | Test |
|---|---|
| CHG-1 | The change reached the branch through a pull request (not a direct push) |
| CHG-2 | Someone other than the author approved it before it was merged |
| CHG-3 | The approval was given on the final code (no unreviewed commits after it) |
| CHG-4 | Automated checks ran on the merged code and none failed |
| CHG-5 | The change links to a ticket or issue (`--ticket-pattern`, or `--no-ticket` to drop it) |

An attribute that can't apply because an earlier one failed (no approval to compare in CHG-3) is marked not
applicable, not counted twice.

**Risk-based sample.** Every high-risk change is tested: direct pushes, changes to sensitive paths (CI
workflows, CODEOWNERS, infrastructure as code, IAM policies; set your own with `--sensitive`), and changes
labelled emergency or hotfix. The rest are sampled at random, sized like the internal audit (1, 2, 3, 5, 15 or
25 by population size; `--sample` overrides). The draw is deterministic from the test id, and the seed and
population hash are recorded.

## Logical access

**Population:** every collaborator and pending invitation on the repository. Every item is tested.

The approved list is `program/itgc/access/<owner>__<repo>.yaml`, kept by the system owner:

```yaml
reviewed_by: CISO
reviewed_on: 2026-10-01
approved:
  - {user: alice, permission: admin, reason: Repository owner}
  - {user: bob, permission: write, reason: Payments engineer}
```

| Attribute | Test |
|---|---|
| ACC-1 | The person is on the approved list |
| ACC-2 | Their permission is no higher than approved (read < triage < write < maintain < admin) |
| ACC-3 | Admin access only for people approved for admin |

The workpaper also lists people approved but no longer present, so the list can be tidied.

## Completing the workpaper

Automation tests the attributes; it never concludes. In the pull request, the auditor:

1. reviews each exception and writes an `auditor_note` (explained, or a deficiency)
2. sets `conclusion` to `effective` or `not_effective`, writes `summary`, `performed_by` and `performed_on`
3. raises a finding in the record's `findings.yaml` for each deficiency and lists it under `findings`

A different person sets `reviewed_by` and `reviewed_on`. `python -m grc program validate` enforces:

| Code | Severity | Meaning |
|---|---|---|
| P401 | error | The workpaper isn't valid YAML, its id doesn't match its folder, or the conclusion is unknown |
| P402 | error | `effective` with exceptions and no `exception_rationale`; or `not_effective` citing no finding |
| P403 | error | A conclusion without `performed_by` and `performed_on` |
| P404 | error | Reviewed before it was concluded, reviewed by the performer, or `reviewed_by` without `reviewed_on` |
| P405 | warning | Generated more than 30 days ago and still not concluded |
| P406 | warning | Concluded with an exception that has no `auditor_note` |

## Limits

- GitHub only. Deployments made outside GitHub (console changes, other pipelines) aren't in the population;
  pair the test with the platform's own change log.
- On GitHub Free, private repositories can't enforce reviews or checks, so exceptions are expected there; the
  test shows what actually happened, which is what an auditor needs.
- Approvals by a GitHub team count as the reviewing person; bots (Dependabot, Renovate) are authors like
  anyone else and need a human approval.
