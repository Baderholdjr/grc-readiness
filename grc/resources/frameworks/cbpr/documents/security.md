# {{title}}

## Purpose

This is {{client}}'s written information security policy (PR33). It sets how {{client}}, as a controller, protects personal information against loss, unauthorised access, use, change, disclosure and other misuse.

## Scope

The policy applies to all personal information {{client}} holds, in any form, to every system and location that stores or processes it, and to everyone who works for {{client}}. Processors and service providers that handle personal information for {{client}} must protect it too, under the Processor Management Procedure (PR34).

{{scope_statement}}

## Proportionate safeguards

{{client}} uses physical, technical and administrative safeguards that suit its size and complexity, the nature and scope of its activities, and the sensitivity of the information (PR34). They include:

- access control: access granted by role, approved by [[TODO: approver]], and reviewed at least [[TODO: frequency]];
- encryption of personal information (see Systems and encryption);
- boundary protection: [[TODO: e.g. firewalls, web application firewall, network segmentation]];
- audit logging of access to and changes in systems holding personal information;
- monitoring of those logs and of security alerts.

Safeguards are chosen from a documented security risk assessment that weighs the likelihood and severity of harm to people, the sensitivity of the information, and the context in which it is held (PR35). Sensitive and children's information gets stronger safeguards. The assessment is kept in [[TODO: risk register]] and repeated at least [[TODO: frequency]] and when systems or processing change. Safeguards are reviewed and reassessed on the same cycle (PR34).

## People

Employee training and management is one of the four areas the safeguards cover (PR37a). Employees understand why security matters and what they must do (PR36):

- security awareness training when they join and [[TODO: frequency]] after, with completion recorded;
- signed acknowledgement of this policy and the acceptable use rules;
- reminders through [[TODO: e.g. staff meetings, phishing exercises, newsletters]];
- background checks for roles with access to sensitive information, where the law allows: [[TODO: roles and checks]];
- access removed on the day someone leaves or changes role.

Managers oversee their teams' compliance, and breaches of this policy are handled through [[TODO: disciplinary process]] (PR36).

## Systems and encryption

Information systems are designed and run securely, covering network and software design and how information is processed, stored, transmitted and disposed of (PR37b):

- secure configuration baselines for [[TODO: systems in scope]];
- security patches applied within [[TODO: time by severity]];
- secure development practices, including code review and separate test environments without live personal information unless approved;
- backups taken [[TODO: frequency]] and protected like the live data.

Personal information is protected by encryption or similar means (PR37): in transit with [[TODO: e.g. TLS 1.2 or later]] and at rest with [[TODO: method, e.g. cloud provider key management]]. Where encryption is not used, the reason and the compensating safeguard are recorded.

## Detecting and responding to attacks

{{client}} has measures to detect, prevent and respond to attacks, intrusions and other security failures (PR37c, PR39):

- prevention: [[TODO: e.g. endpoint protection, email filtering, multi-factor authentication]];
- detection: alerts from [[TODO: monitoring tools]] reviewed by [[TODO: team]];
- response: an incident response plan at [[TODO: location]] that sets roles, escalation, containment, recovery and lessons learned.

Incidents are recorded. Any that affect personal information also follow the Breach Notification Procedure.

## Physical security

Offices, data rooms and devices are protected (PR37d): [[TODO: e.g. badge access, visitor log, locked storage for paper records, clear desk rules, device encryption]]. Cloud providers' physical controls are checked through their assurance reports.

## Secure disposal

{{client}} follows a secure disposal policy (PR38). Personal information no longer needed is disposed of so it cannot be recovered:

- electronic records deleted under the retention schedule at [[TODO: location]];
- devices and media wiped or destroyed by [[TODO: method or provider]], with certificates kept;
- paper shredded or placed in locked confidential waste bins.

Disposal is recorded in [[TODO: location]].

## Testing and assessments

Safeguards are tested at appropriate intervals and adjusted based on the results (PR40):

- vulnerability scans [[TODO: frequency]];
- penetration tests [[TODO: frequency]];
- access reviews and restore tests [[TODO: frequency]].

Findings are tracked to closure with an owner and a due date.

Where {{client}} uses third-party certifications or other assessments, such as privacy compliance audits, they happen at appropriate intervals and their recommendations are acted on and tracked (PR41). Those used: [[TODO: list, or "none" with the reason]]. If none are used, PR41 is marked not applicable and the reason is recorded.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes or a significant incident, and before each annual recertification.
