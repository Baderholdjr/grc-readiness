# {{title}}

## Purpose

This standard sets how {{client}} manages configuration, secrets, encryption, integrity and residual data in its cloud service offering, and how it keeps improving security. It covers eight Key Security Indicators. KSI-SVC-PRR, KSI-SVC-RUD and KSI-SVC-VCM are required for Class C and optional for Class B; the others apply to every class. For Class A, FedRAMP's mandatory Class A list names KSI-SVC-SIN (FRC-CLA-MFR).

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Owner: [[TODO: role]].

## Configuration management

Key Security Indicator: the configuration of machine-based information resources is managed using automation and persistently reviewed for drift (KSI-SVC-ACM).

- Configuration is defined as code in [[TODO: repository]] and applied by [[TODO: deployment or configuration tool]].
- Drift is detected by [[TODO: drift detection tool]] and corrected by redeployment (see DOC-FR-CHANGE).

Measures: share of resources under automated configuration; drift events and time to correct. Cycle: persistently, drift checks at least [[TODO: cycle]].

## Secrets

Key Security Indicator: management, protection and regular rotation of digital keys, certificates and other secrets is automated and persistently reviewed (KSI-SVC-ASM).

- Secrets are stored in [[TODO: secrets manager or key management service]], never in code or images; pipeline scanning blocks committed secrets.
- Keys, certificates and other secrets are rotated automatically every [[TODO: rotation periods by secret type]] and on suspected exposure.
- Certificates are monitored for expiry.

Measures: secrets past their rotation date; secrets found in code; certificates expiring within [[TODO: days]]. Cycle: persistently, checked at least [[TODO: cycle]].

## Securing information

Key Security Indicator: information is encrypted or otherwise secured from unwanted access or modification (KSI-SVC-SIN).

- Data in transit is encrypted with [[TODO: e.g. TLS 1.2 or later]].
- Data at rest is encrypted with [[TODO: e.g. AES-256 through the key management service]].
- Cryptographic modules are documented and chosen under DOC-FR-SCG.
- Access to stored data is limited under DOC-FR-IAM.

Measures: share of data stores and endpoints with encryption enforced; unencrypted resources found by [[TODO: posture tool]]. Cycle: persistently, checked at least [[TODO: cycle]].

## Communications and resource integrity

Key Security Indicator: cryptographic methods are used to validate the integrity of machine-based information resources (KSI-SVC-VRI).

- Build artifacts and images are signed by [[TODO: signing tool]] and signatures are verified before deployment.
- Infrastructure templates and packages are verified against checksums or signatures.

(Class C; optional for Class B) Key Security Indicator: the authenticity and integrity of communications between machine-based information resources are persistently validated using automation (KSI-SVC-VCM).

- Service-to-service traffic uses [[TODO: e.g. mutual TLS through a service mesh]] with certificates issued and rotated automatically.

Measures: share of deployments with verified signatures; share of internal connections using authenticated encryption. Cycle: persistently, on every deployment and connection.

## Residual risk and unwanted data

(Class C; optional for Class B) Key Security Indicator: plans, procedures and the state of information resources are persistently reviewed after changes to limit and remove unwanted residual elements that would likely harm the confidentiality, integrity or availability of federal customer data (KSI-SVC-PRR).

- After each change, leftover resources, temporary access, test data, old snapshots and unused credentials are found by [[TODO: automated cleanup check]] and removed.

(Class C; optional for Class B) Key Security Indicator: unwanted federal customer data is removed promptly when an agency requests it, in line with customer agreements, including from backups where appropriate; this typically applies to a customer spill or a change in how a customer uses the service (KSI-SVC-RUD).

- Agencies request removal through [[TODO: request channel]].
- Removal is completed within [[TODO: time set in customer agreements]], including backups where appropriate, and confirmed to the agency.

Measures: residual items found and removed after changes; removal requests and time to complete. Cycle: persistently, after every change and every request.

## Evaluating and improving security

Key Security Indicator: information resources are persistently evaluated for opportunities to improve security, and those improvements are persistently made (KSI-SVC-EIS).

- Sources of improvements include assessment findings, incident lessons, vulnerability trends, Key Security Indicator measures and new FedRAMP rules.
- Improvements are tracked in [[TODO: backlog or tracker]] with an owner and a target date, and reviewed at least [[TODO: cycle]].

Measures: improvements identified and completed; overdue improvements. Cycle: persistently, reviewed at least [[TODO: cycle]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
