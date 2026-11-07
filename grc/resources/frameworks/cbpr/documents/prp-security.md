# {{title}}

## Purpose

This is {{client}}'s written information security policy for the personal information it processes on behalf of its customers, who are the controllers of that information (PRP1). It sets how {{client}}, as a processor, protects that information, tells controllers about breaches, and disposes of or returns the information.

## Scope

The policy covers all personal information {{client}} processes for controllers, in any form, every system and location that stores or processes it, and everyone working for {{client}} (PRP1). Sub-processors that handle the information are bound to equivalent safeguards under the Sub-processor Management Procedure.

{{scope_statement}}

## Safeguards

{{client}} uses physical, technical and administrative safeguards that support this policy (PRP2). They suit the sensitivity of the information and the services provided, and include:

- access control: access to controllers' information granted by role, approved by [[TODO: approver]], and reviewed at least [[TODO: frequency]];
- encryption: in transit with [[TODO: e.g. TLS 1.2 or later]] and at rest with [[TODO: method]];
- boundary protection: [[TODO: e.g. firewalls, network segmentation, separation between customers' data]];
- audit logging of access to and changes in controllers' information;
- monitoring of those logs and of security alerts;
- physical protection of offices and devices: [[TODO: e.g. badge access, device encryption]].

Safeguards are reviewed and reassessed at least [[TODO: frequency]] and when systems, services or risks change (PRP2). Where a controller's agreement asks for a specific safeguard, it is recorded against that controller.

## People

Employees understand why security matters and what they must do, through ongoing training and oversight (PRP3):

- security awareness training when they join and [[TODO: frequency]] after, with completion recorded;
- signed acknowledgement of this policy and confidentiality terms;
- reminders through [[TODO: e.g. staff meetings, phishing exercises]];
- access removed on the day someone leaves or changes role.

Managers oversee their teams' compliance (PRP3).

## Detecting and responding to attacks

{{client}} has measures to detect, prevent and respond to attacks, intrusions and other security failures (PRP4):

- prevention: [[TODO: e.g. multi-factor authentication, endpoint protection, patching within set times]];
- detection: alerts from [[TODO: monitoring tools]] reviewed by [[TODO: team]];
- response: an incident response plan at [[TODO: location]] that sets roles, escalation, containment, recovery and lessons learned.

Incidents are recorded with their cause, impact and the controllers affected.

## Notifying controllers of breaches

When {{client}} becomes aware of a privacy or security breach affecting a controller's personal information, it tells that controller (PRP6):

- within [[TODO: time, or "the time set in each controller's agreement"]] of becoming aware;
- through the contact named in the controller's agreement: [[TODO: where controller contacts are kept]];
- with what is known: what happened, when, the information and people affected, the likely consequences, and what {{client}} has done and will do;
- with updates as more becomes known, and the help the controller needs for its own notifications.

Notifications are logged with the date, the controller and the content (PRP6). {{client}} does not notify individuals or regulators about a controller's information unless the controller instructs it or the law requires it.

## Disposal or return

At the end of the service, or when a controller instructs, {{client}} securely disposes of or returns the controller's personal information, as the controller chooses (PRP7):

- return in [[TODO: format]] within [[TODO: time]];
- secure deletion from live systems within [[TODO: time]], and from backups as they expire within [[TODO: period]];
- devices and media wiped or destroyed by [[TODO: method or provider]], with certificates kept.

Disposal or return is confirmed to the controller on request and recorded (PRP7).

## Testing and assessments

Safeguards are tested at appropriate intervals and adjusted based on the results (PRP5):

- vulnerability scans [[TODO: frequency]];
- penetration tests [[TODO: frequency]];
- access reviews and restore tests [[TODO: frequency]].

Findings are tracked to closure with an owner and a due date.

Where {{client}} uses third-party certifications or risk assessments, they happen at appropriate intervals, safeguards are adjusted and recommendations are acted on and tracked (PRP8). Those used: [[TODO: list, or "none"]]. If none are used, PRP8 is marked not applicable and the reason is recorded.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes or a significant incident, and before each annual recertification.
