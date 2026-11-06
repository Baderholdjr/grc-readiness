# {{title}}

## Purpose

This document sets {{client}}'s rules for the events the system records and how the records are protected and reviewed, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Events logged

The system logs [[TODO: sign-ins, privileged actions, changes to accounts and permissions, access to agency data, security configuration changes]]. Each record shows what happened, when, where, the source, the outcome and the identity.

## Storage and protection

Logs are sent to [[TODO: e.g. the SIEM]], kept for [[TODO: e.g. 1 year online, 3 years archived]], protected from change and deletion, and accessible only to [[TODO: roles]]. A logging failure alerts [[TODO]]. Clocks are synchronised to [[TODO: an authoritative time source]].

## Review and reporting

Logs are reviewed [[TODO: e.g. daily through automated alerts and weekly by the security team]] for unusual activity. Findings are reported to [[TODO]] and handled as incidents where needed.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
