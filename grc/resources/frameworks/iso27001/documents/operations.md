# {{title}}

## Purpose

This procedure covers the day-to-day security of {{client}}'s operational systems and networks.

## Operational planning

Operational processes are planned and controlled, with documented procedures (DOC-IS-DOCINFO) and evidence kept. Outsourced processes are controlled through DOC-IS-SUPPLIER.

## Capacity and malware

Capacity is monitored and adjusted ([[TODO: tooling]]). Malware protection runs on [[TODO: endpoints and servers]] with central reporting.

## Vulnerabilities and configuration

| Severity | Fix within |
|---|---|
| Critical | [[TODO]] days |
| High | [[TODO]] days |
| Medium | [[TODO]] days |

Systems are scanned [[TODO]]. Secure configuration baselines are defined for [[TODO]] and drift is monitored.

## Logging and monitoring

Security-relevant events are logged, protected from tampering, kept for [[TODO: e.g. 1 year]], and monitored by [[TODO: SIEM / alerting]]. Clocks are synchronized to [[TODO]].

## Software installation

Only approved software is installed on operational systems, through [[TODO: deployment pipelines]].

## Networks

Networks are secured and segregated ([[TODO: e.g. VPCs, security groups]]); network services have defined security requirements; web access is filtered where appropriate.

## Cryptography

Encryption is used for data in transit ([[TODO: TLS 1.2+]]) and at rest ([[TODO]]); keys are managed in [[TODO: KMS]] with rotation every [[TODO]].

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
