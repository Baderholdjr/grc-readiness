# {{title}}

## Purpose

This policy sets how {{client}} controls logical access to the system and the information in it.

## Principles

Access follows least privilege and need to know. Duties that conflict (for example approving and deploying your own change) are separated. Every user has a unique identity; shared accounts are [[TODO: not allowed / tightly controlled]].

## Joiners and leavers

Access is requested and approved by [[TODO: the manager and system owner]] before it is granted. Leavers lose access within [[TODO: e.g. 24 hours]] of their last day; movers have access adjusted to the new role.

## Access reviews

System owners review user access to [[TODO: production, customer data, critical tools]] at least [[TODO: e.g. quarterly]]. Inappropriate access is removed and the review is recorded.

## Privileged access

Administrative access is limited to [[TODO: roles]], requires MFA, and is logged. [[TODO: e.g. just-in-time elevation]]

## Remote and external access

Access from outside the system boundary goes through [[TODO: e.g. SSO with MFA, VPN, bastion hosts]]. Network boundaries are protected by [[TODO: e.g. security groups, firewalls, WAF]].

## Encryption at rest

Customer data and other sensitive information is encrypted at rest using [[TODO: e.g. AES-256 with keys managed in KMS]]. Key access is restricted to [[TODO]].

## Review

The owner reviews this policy at least every {{doc_review_days}} days.
