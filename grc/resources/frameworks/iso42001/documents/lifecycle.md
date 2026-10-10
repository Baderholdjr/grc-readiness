# {{title}}

## Purpose

This procedure defines how {{client}} designs, develops, verifies, deploys, operates and retires AI systems responsibly.

## Lifecycle stages

| Stage | Required before moving on | Owner | Record |
|---|---|---|---|
| Plan | Intended use defined; inventory entry; impact assessment started | AI system owner | Inventory, IA draft |
| Requirements | Functional, performance, fairness, safety, privacy and oversight requirements written | AI system owner | [[TODO: e.g. requirements doc / ticket]] |
| Design and build | Design decisions, data and model choices documented | Tech lead | [[TODO: e.g. design doc, model card]] |
| Verify and validate | Tests against requirements passed (see below) | [[TODO]] | Evaluation report |
| Deploy | Release approved | [[TODO]] | Release approval |
| Operate and monitor | Monitoring in place; incidents handled | [[TODO]] | Dashboards, incident log |
| Retire | Users informed; data and models handled per retention | AI system owner | Retirement record |

Technical documentation for each system (purpose, architecture, data, model, limitations, evaluation results, operating instructions) is kept at [[TODO]] and updated at each release.

## Verification and validation

- Acceptance criteria are set before testing, including performance on relevant subgroups.
- Evaluation uses data that is separate from training data and representative of the intended use.
- [[TODO: list the release gates, e.g. under-triage ≤ 2% on clinician-labelled vignettes]].
- Results and any accepted shortfalls are recorded and approved before deployment.

## Deployment

- Releases require approval by [[TODO: e.g. two reviewers including the system owner]] and are made through [[TODO: e.g. the CI/CD pipeline]].
- The deployment plan covers rollback, user communication and monitoring.

## Operation and monitoring

- Monitored indicators: [[TODO: e.g. accuracy drift, escalation rate, complaint rate, latency]] with thresholds and owners.
- Breaching a threshold triggers investigation and, where needed, rollback, a risk reassessment and an impact reassessment.
- Changes to a system in operation follow this procedure from the relevant stage.

## Event logs

AI systems record events needed to trace outputs and investigate incidents: [[TODO: e.g. inputs, model version, output, user action]]. Logs are retained for at least [[TODO: e.g. 90 days]] and protected against tampering.

## Records

Lifecycle records are retained per DOC-DOCINFO and are sampled by internal audit (DOC-AUDIT).

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
