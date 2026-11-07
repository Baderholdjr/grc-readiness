# {{title}}

## Purpose

This policy sets how {{client}} governs security for its cloud service offering: inventories, executive support, security investment, security in software development, and its vulnerability disclosure program. It covers five Key Security Indicators that Class B and C must show. They are not in FedRAMP's mandatory Class A list (FRC-CLA-MFR), so Class A need not show them.

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Roles and owners:

{{owners_table}}

## Inventories

Key Security Indicator: authoritative sources are used to automatically generate real-time inventories of all information resources when needed (KSI-PIY-GIV).

- Machine-based resources are listed from [[TODO: authoritative sources, e.g. cloud provider APIs, infrastructure as code state, container registry]].
- Non-machine-based resources such as people, policies and procedures are listed from [[TODO: HR system and document library]].
- Third-party resources are listed from [[TODO: supplier register]].
- The inventory is generated on demand by [[TODO: script or tool]] and feeds the Minimum Assessment Scope (DOC-FR-SCOPE).

Current inventory:

{{inventory_table}}

Measures: time to generate a full inventory; differences between the generated inventory and the assessed scope; resources without an owner. Cycle: persistently, generated at least [[TODO: cycle]] and on every significant change.

## Executive support

Key Security Indicator: executive support for achieving {{client}}'s security goals is persistently reviewed and demonstrated (KSI-PIY-RES).

- {{client}}'s security goals for the offering are set by [[TODO: executive or board body]] and recorded in [[TODO: location]].
- The senior official accountable for the certification package and for accepting risk is [[TODO: name and title]].
- Executives review security status, open risks, accepted vulnerabilities and progress against goals at least [[TODO: cycle]], and the decisions are minuted.

Measures: reviews held against schedule; decisions and actions from each review and their closure.

## Security investment

Key Security Indicator: the effectiveness of {{client}}'s investments in achieving security goals is persistently reviewed (KSI-PIY-RIS).

- Security spending and staffing for the offering are planned in [[TODO: budget process]].
- Each significant investment has an expected outcome tied to a security goal or a Key Security Indicator measure.
- The outcome is reviewed at least [[TODO: cycle]] and the result informs the next budget.

Measures: investments with a defined outcome; outcomes met; changes in related Key Security Indicator measures.

## Security in the development lifecycle

Key Security Indicator: the effectiveness of building security and privacy into the software development lifecycle and aligning with CISA Secure by Design principles is persistently reviewed (KSI-PIY-RSD).

- Security requirements, threat modeling for significant features, code review, and automated testing are part of the lifecycle (see DOC-FR-CHANGE).
- Secure by Design practices adopted: [[TODO: e.g. memory-safe languages, secure defaults, MFA by default, removal of default passwords]].
- Engineers are trained under DOC-FR-TRAINING.

Measures: vulnerabilities introduced per release and where they were caught; threat models completed for significant features; Secure by Design commitments met. Cycle: persistently, reviewed at least [[TODO: cycle]].

## Vulnerability disclosure

Key Security Indicator: the effectiveness of {{client}}'s vulnerability disclosure program is persistently reviewed (KSI-PIY-RVD).

- The program is published at [[TODO: disclosure policy URL]], with a reporting channel at [[TODO: reporting channel]] and safe harbor terms.
- Reports are acknowledged within [[TODO: time]] and handled under DOC-FR-VULN.

Measures: reports received, valid share, time to acknowledge and to fix; findings reported externally before internal detection. Cycle: persistently, reviewed at least [[TODO: cycle]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
