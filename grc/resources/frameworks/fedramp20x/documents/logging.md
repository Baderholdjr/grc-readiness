# {{title}}

## Purpose

This standard sets how {{client}} logs, monitors and audits activity in its cloud service offering, and how it evaluates configuration. It covers five Key Security Indicators. Class B and C must show all of them except KSI-MLA-ALA, which is required for Class C and optional for Class B. They are not in FedRAMP's mandatory Class A list (FRC-CLA-MFR), so Class A need not show them.

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Logging owner: [[TODO: role]].

## Event types

Key Security Indicator: a list of information resources and event types that will be logged, monitored and audited is maintained and persistently reviewed to ensure these activities occur (KSI-MLA-LET).

The list is kept in [[TODO: location, ideally as code]] and covers at least:

- authentication and authorization events, including privileged elevation;
- account, role and permission changes;
- configuration and infrastructure changes (see DOC-FR-CHANGE);
- access to federal customer data and to the trust center;
- network flow and security tool events such as WAF, IDS and endpoint detection;
- administrative actions by {{client}} staff and by customers' top-level administrative accounts.

Measures: share of inventory resources sending the listed events; resources or sources that stopped sending logs, detected by [[TODO: log source health check]]. Cycle: persistently, with the list reviewed at least [[TODO: cycle]] and when resources are added.

## SIEM

Key Security Indicator: a Security Information and Event Management (SIEM) or similar system is used and persistently reviewed for centralized, tamper-resistant logging of events, activities and changes (KSI-MLA-OSM).

- The SIEM is [[TODO: SIEM product]].
- Logs are sent in near real time and stored with [[TODO: tamper resistance, e.g. write-once storage and separate account]].
- Retention is [[TODO: retention period]].
- Detection rules are version-controlled and tested.

Measures: ingestion coverage and delay; integrity check results; detection rule test results. Cycle: persistently, with a SIEM health review at least [[TODO: cycle]].

## Reviewing logs

Key Security Indicator: logs are persistently reviewed and audited (KSI-MLA-RVL).

- Automated detections run continuously; alerts are triaged by [[TODO: team or service]] within [[TODO: target time]].
- People review [[TODO: which logs, e.g. privileged activity and alert-suppression changes]] at least [[TODO: cycle]].
- Findings go to the incident procedure (DOC-FR-INCIDENT) or the vulnerability register (DOC-FR-VULN).

Measures: alert triage times; count of reviews completed against schedule; findings raised from reviews.

## Evaluating configurations

Key Security Indicator: the configuration of machine-based information resources, especially infrastructure as code, is persistently evaluated and tested (KSI-MLA-EVC).

- Infrastructure as code is checked by [[TODO: policy-as-code or IaC scanning tool]] on every change before deployment.
- Deployed configuration is checked by [[TODO: posture management tool]] against the intended state and benchmarks.

Measures: failing checks by severity; time to fix; share of resources covered. Cycle: persistently, on every change and at least [[TODO: cycle]] for deployed resources.

## Log access

(Class C; optional for Class B) Key Security Indicator: a least-privileged, role- and attribute-based, just-in-time access model is used and persistently reviewed for access to log data, based on data sensitivity defined by {{client}} (KSI-MLA-ALA).

- Log data is classified as [[TODO: sensitivity levels for log data]].
- Access to sensitive logs is granted just in time through [[TODO: access tool]] and expires after [[TODO: duration]].
- Access to logs is itself logged and reviewed.

Measures: standing access to sensitive logs; access grants and their duration; review results. Cycle: persistently, at least [[TODO: cycle]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
