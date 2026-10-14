# {{title}}

## Purpose

This procedure deals with nonconformities and drives continual improvement of the information security management system.

## Raising a finding

Findings can come from internal and external audits, incidents, concerns, monitoring and management review. Each is recorded with its source, the requirement affected, a description and a grade:

| Grade | Meaning |
|---|---|
| Major nonconformity | A requirement is not met in a way that puts the ISMS's intended results at risk, or a process is absent |
| Minor nonconformity | An isolated lapse that doesn't undermine the requirement overall |
| Opportunity for improvement | Not a nonconformity; a way to do better |

## Corrective action

For each nonconformity:
1. **React:** contain it and deal with the consequences.
2. **Find the root cause** and check whether similar nonconformities exist or could occur.
3. **Plan the action:** corrective action, owner and due date.
4. **Implement** and keep evidence that it was done.
5. Update risks or the ISMS itself if needed.

Findings and their actions are tracked in `engagement/findings.yaml` and mirrored to the issue tracker, with reminders when overdue.

## Effectiveness

Someone independent of the action owner reviews whether the action worked, using evidence, before the finding is closed. A major nonconformity cannot be closed by accepting the risk.

## Continual improvement

The ISMS owner reviews findings, audit results, monitoring results and management review outputs for improvement opportunities, and plans those adopted as objectives or changes (DOC-IS-OBJECTIVES).

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
