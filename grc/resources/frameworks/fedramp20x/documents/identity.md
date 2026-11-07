# {{title}}

## Purpose

This standard sets how {{client}} authenticates people and machines and controls their access to its cloud service offering. It covers six Key Security Indicators that Class B and C must show. Class A must show only KSI-IAM-AAM and KSI-IAM-APM, the ones FedRAMP's mandatory Class A list names (FRC-CLA-MFR).

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Identity owner: [[TODO: role]]. Identity provider: [[TODO: identity provider]].

## Phishing-resistant and passwordless authentication

Key Security Indicator: secure passwordless methods are used for user authentication and authorization when feasible; otherwise strong passwords with phishing-resistant MFA are used (KSI-IAM-APM).

- Workforce users sign in through [[TODO: identity provider]] with [[TODO: passwordless method, e.g. FIDO2 security keys or platform passkeys]].
- Where passwordless is not feasible, passwords meet [[TODO: password standard]] and are combined with phishing-resistant MFA. SMS, voice and one-time codes are not used as the only second factor for privileged access.
- Exceptions are recorded with the reason and an end date.

Measures: share of users and of privileged users on passwordless or phishing-resistant methods; count of exceptions. Cycle: persistently, at least [[TODO: cycle]].

## Non-user authentication

Key Security Indicator: appropriately secure authentication methods are used and persistently reviewed for non-user accounts and services (KSI-IAM-SNU).

- Services use workload identities or short-lived credentials issued by [[TODO: e.g. cloud IAM roles or workload identity federation]] instead of long-lived keys.
- Remaining static credentials are stored and rotated under DOC-FR-SERVICE.
- Each non-user account has an owner and a documented purpose.

Measures: count of long-lived credentials and their age; non-user accounts without an owner. Cycle: persistently, at least [[TODO: cycle]].

## Account lifecycle automation

Key Security Indicator: the lifecycle and privileges of all accounts, roles and groups are securely managed using automation (KSI-IAM-AAM).

- Joiners, movers and leavers are driven from [[TODO: HR system or source of truth]] into the identity provider and downstream systems.
- Roles and group memberships are defined as code or in [[TODO: access management tool]] and changed through review.
- Leavers lose access within [[TODO: time]]; inactive accounts are disabled after [[TODO: days]].

Measures: time from HR event to access change; count of orphaned or inactive accounts; share of systems connected to automated provisioning. Cycle: persistently, on every lifecycle event, with a reconciliation at least [[TODO: cycle]].

## Least privilege and just-in-time access

Key Security Indicator: identity and access management measures are used and persistently reviewed to ensure each user or device can only access the resources it needs (KSI-IAM-ELP).

Key Security Indicator: a least-privileged, role- and attribute-based, just-in-time authorization model is used and persistently reviewed for all user and non-user accounts and services (KSI-IAM-JIT).

- Standing privileged access is removed; elevation is requested through [[TODO: just-in-time access tool]], approved, time-limited and logged.
- Access decisions use role and attributes such as team, device posture and environment.
- Access reviews by resource owners run at least [[TODO: cycle]], and unused permissions are removed.

Measures: count of standing privileged assignments; median and maximum elevation duration; review completion and permissions removed. Cycle: persistently, at least [[TODO: cycle]].

## Suspicious activity

Key Security Indicator: accounts with privileged access are disabled or otherwise secured in response to suspicious activity (KSI-IAM-SUS).

- Detection rules in the SIEM (see DOC-FR-LOGGING) flag suspicious privileged activity, such as impossible travel, unusual elevation or MFA fatigue.
- On a high-confidence alert, [[TODO: automation, e.g. SOAR playbook]] disables the account or revokes its sessions and credentials, and the incident procedure starts (see DOC-FR-INCIDENT).

Measures: time from alert to account secured; share of such responses that were automated; tested by [[TODO: test method and cycle]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
