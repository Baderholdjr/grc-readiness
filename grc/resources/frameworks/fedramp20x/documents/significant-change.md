# {{title}}

## Purpose

This procedure sets how {{client}} evaluates potential significant changes to its cloud service offering and notifies all necessary parties. A significant change is one likely to substantively affect the security or privacy posture of the offering (NIST SP 800-37 Rev. 2). These rules apply to Class B and C.

## Evaluating changes

{{client}} must evaluate every potential significant change to decide its type and then follow the matching rules (SCN-CSO-EVA). The evaluation runs in this order:

1. Is it a significant change? If not, it follows normal change management (DOC-FR-CHANGE) only.
2. Is it a certification class change (for example Class B to Class C)? If so, it needs a new assessment and cannot be done under these rules.
3. Is it a routine recurring change? If so, follow "Routine recurring changes".
4. Is it a transformative change? If so, follow "Transformative changes".
5. Otherwise it is an adaptive change: follow "Adaptive changes".

The evaluation is part of the change request in [[TODO: change management tool]]. The evaluator is [[TODO: role]]; when unsure, they escalate to [[TODO: security lead]].

Every notification must include at least (SCN-CSO-INF):

- the FedRAMP ID of the offering;
- the assessor name, if applicable;
- the related vulnerability, if applicable;
- the significant change type and why it was categorized that way;
- a short description of the change and the reason for it;
- a summary of customer impact, including changes to services and to customer configuration responsibilities;
- the plan and timeline, including verification, assessment or validation of affected Key Security Indicators;
- a copy of the business or security impact analysis;
- the name and title of the approver.

Notifications follow the significant change notification schema (https://fedramp.gov/schemas/fedramp-significant-change-notifications-schema-2026-06-24.json) and are sent to all necessary parties through [[TODO: notification mechanism, e.g. trust center update plus email to agency contacts]], which is documented in the certification package.

## Routine recurring changes

A routine recurring change regularly recurs as part of ongoing operations, vulnerability mitigation or remediation. Typical tests: routine work during normal duties, no major impact on availability, no executive approval needed. Examples: scaling capacity, tuning performance settings, updating firewall rules, refreshing tokens, routine patching, and like-for-like replacement of a known-bad component.

{{client}} should not make formal Significant Change Notifications for routine recurring changes; they are exempt from notification (SCN-RTR-NNR). The evaluation is still recorded. If {{client}} does notify for them, the reason and the resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official.

## Adaptive changes

An adaptive change does not routinely recur and does not introduce substantive potential security risks needing in-depth assessment. Examples: updates with known breaking changes or service disruption, larger multi-week feature releases that are not a new service, swapping a cryptographic module for one meeting the same standards, or replacing a like-for-like component such as a scanning tool.

{{client}} must notify all necessary parties within 10 business days after finishing an adaptive change, including the required information above and a summary of any new risks or vulnerabilities resulting from the change, if any (SCN-ADP-NTF).

## Transformative changes

A transformative change introduces substantive potential security risks likely to affect existing risk determinations, and must be assessed in depth. Examples: adding, removing or replacing a critical third-party service such as the IaaS, raising the security category of a service that handles federal customer data, replacing management planes or moving workloads to containers, a data center migration, or a new AI capability that uses federal customer data in a new way.

Timeline (all business days):

| When | Notification | Rule |
| --- | --- | --- |
| at least 30 days before starting | initial plans, with a summary of likely security impacts or changes in risk | SCN-TRF-NIP |
| at least 10 days before starting | final plans, with updates to everything previously sent | SCN-TRF-NFP |
| within 5 days after finishing | notice of completion, with updates to everything previously sent | SCN-TRF-NAF |
| within 5 days after completing verification, assessment or validation | updates, a summary of new risks or vulnerabilities, and the security assessment report if any | SCN-TRF-NAV |
| within 30 days after finishing | updated service documentation published | SCN-TRF-UPD |

{{client}} must send each of these notifications (SCN-TRF-NIP, SCN-TRF-NFP, SCN-TRF-NAF, SCN-TRF-NAV) and must publish updated service documentation, such as user guides and marketplace information, within 30 business days after finishing (SCN-TRF-UPD).

Before starting a transformative change, {{client}} should engage a third-party assessor to review the scope and impact of the planned change where human validation is needed, limited to the security decisions that need it (SCN-TRF-TPR). The assessor's report, or the reason one was not engaged, is kept with the change. If {{client}} does not follow this, the reason and resulting risk are recorded in the security decision record and accepted by a senior official.

## Records and history

{{client}} must keep auditable records of its significant change evaluations and make them available to FedRAMP on request (SCN-CSO-MAR). They need not be in the certification package by default. Records are kept in [[TODO: location]] for [[TODO: retention period]]; FedRAMP requests them through the FedRAMP Security Inbox.

{{client}} must keep 12 months of historical Significant Change Notifications available with its certification data (SCN-CSO-HIS).

{{client}} must make all Significant Change Notifications and related audit records available in both human-readable and JSON formats (SCN-CSO-HRM).

The evidence set keeps at least one evaluation example for each change type. Fictitious examples may be used until real ones exist, as long as they show the decision making.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
