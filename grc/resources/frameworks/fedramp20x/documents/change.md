# {{title}}

## Purpose

This standard sets how {{client}} makes, records and validates changes to its cloud service offering. It covers four Key Security Indicators that apply to every class; for Class A, FedRAMP's mandatory Class A list names KSI-CMT-LMC (FRC-CLA-MFR).

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Changes that may be significant are also evaluated under DOC-FR-SCN.

Change owner: [[TODO: role]]. Change tooling: [[TODO: version control, CI/CD and ticketing tools]].

## Logging changes

Key Security Indicator: modifications to the cloud service offering are logged and monitored (KSI-CMT-LMC).

- Every change to code, infrastructure, configuration and access goes through [[TODO: version control and pipeline]], which records who, what, when, why and the approval.
- Changes made outside the pipeline, such as console actions or emergency fixes, are captured by [[TODO: cloud audit log or configuration recorder]] and sent to the SIEM (see DOC-FR-LOGGING).
- Alerts fire on unapproved or out-of-pipeline changes and are triaged by [[TODO: team]].
- Emergency changes are logged at the time and reviewed within [[TODO: hours or days]].

Measures:

- share of production changes linked to an approved change record;
- count of out-of-pipeline changes detected, and time to review each;
- coverage of change logging across the inventory.

Cycle: persistently, on every change, with a summary reviewed [[TODO: cycle]].

## Immutable redeployment

Key Security Indicator: changes to machine-based information resources are made by redeploying version-controlled resources rather than by direct modification wherever reasonable (KSI-CMT-RMV).

- Infrastructure is defined as code in [[TODO: e.g. Terraform or CloudFormation repository]].
- Workloads are rebuilt from versioned images or artifacts and replaced, not patched in place.
- Interactive access to production for changes is [[TODO: disabled or limited to break-glass]].
- Exceptions, where direct modification is the only reasonable way, are listed with the reason in [[TODO: exception register]].

Measures:

- share of machine-based resources managed as code;
- count of direct modifications detected by drift detection (see DOC-FR-SERVICE);
- age of running images against the latest build.

Cycle: persistently, with drift checks at least [[TODO: cycle]].

## Validation in the pipeline

Key Security Indicator: persistent testing and validation of changes throughout deployment is automated (KSI-CMT-VTD).

The pipeline runs, before and during deployment:

- unit, integration and regression tests;
- static analysis, dependency and secret scanning, and image scanning (see DOC-FR-VULN);
- policy-as-code checks on infrastructure definitions against the intended state;
- staged rollout with automated health checks and automatic rollback on failure;
- post-deployment checks that the deployed state matches what was approved.

Measures:

- share of deployments that passed every required gate;
- failed and rolled-back deployments and their causes;
- gates bypassed, with approver.

Cycle: persistently, on every deployment.

## Reviewing change procedures

Key Security Indicator: the effectiveness of documented change management procedures is persistently reviewed (KSI-CMT-RVP).

The change owner reviews, at least [[TODO: cycle]]:

- change failure rate and time to restore;
- incidents caused by changes;
- out-of-pipeline changes and exceptions;
- findings from audits and the independent assessment.

Each review records its conclusions and the changes made to this standard or the pipeline. The review output is kept in [[TODO: location]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
