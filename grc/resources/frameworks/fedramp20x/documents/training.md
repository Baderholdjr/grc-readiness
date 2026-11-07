# {{title}}

## Purpose

This standard sets how {{client}} provides cybersecurity education for people who work on its cloud service offering and how it persistently reviews whether that training works. It meets the Key Security Indicator KSI-CED-RAT, which every class must show; for Class A it is in FedRAMP's mandatory Class A list (FRC-CLA-MFR).

Key Security Indicator: the effectiveness of relevant cybersecurity education and training is persistently reviewed, including at least general training for all employees, role-specific training for employees in high-risk roles, training for development and engineering staff on secure software delivery, and training for staff involved with incident response or disaster recovery (KSI-CED-RAT).

Training owner: [[TODO: role]]. Training records: [[TODO: learning platform or HR system]].

## Training by role

| Audience | Content | When |
| --- | --- | --- |
| All employees and contractors | security awareness, phishing and social engineering, acceptable use, reporting incidents, handling federal customer data | on joining and [[TODO: refresh cycle]] |
| High-risk roles: [[TODO: e.g. administrators, support staff with customer data access, executives]] | role-specific threats and duties, privileged access rules, insider threat | on taking the role and [[TODO: refresh cycle]] |
| Development and engineering staff | secure software delivery: secure coding, dependency and secret handling, code review, pipeline security, CISA Secure by Design principles | on joining and [[TODO: refresh cycle]] |
| Incident response and disaster recovery staff | this library's incident and recovery procedures, FedRAMP reporting timeframes, exercises | on joining and [[TODO: refresh cycle]] |

Training content is updated when threats, procedures or FedRAMP rules change, and after incidents that show a gap.

People who have not completed required training within [[TODO: grace period]] lose [[TODO: the access affected, e.g. privileged or production access]] until they do.

## Measuring effectiveness

{{client}} shows KSI-CED-RAT with these measures (KSI-CED-RAT):

- completion rate per audience and overdue count, from [[TODO: learning platform]];
- assessment scores after each module;
- phishing simulation results over time, from [[TODO: phishing simulation tool]];
- secure delivery outcomes: for example, trends in vulnerabilities introduced in code and caught in review or the pipeline;
- incident and recovery exercise results and the time taken against the procedures' targets;
- incidents or findings with a training-related root cause.

Cycle: the measures are collected persistently, at least [[TODO: cycle, e.g. monthly]], and the training owner reviews them with [[TODO: security lead or committee]] at least [[TODO: cycle, e.g. quarterly]]. Each review records what changed in the training as a result.

Evidence is machine-readable exports from the training and testing tools, collected automatically where practical, and summarized in the security decision record with the measures, their objectives and their cycle (see DOC-FR-PACKAGE).

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
