# {{title}}

## Purpose

This document sets {{client}}'s rules for assessing risk to the system and finding vulnerabilities, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Security categorisation

The system and its information are categorised by impact ([[TODO: FIPS 199 low, moderate or high]]), which sets the TX-RAMP level.

## Risk assessment

Risks to the system are assessed every [[TODO: 12 months]] and after significant changes, and the results are shared with [[TODO]].

## Vulnerability scanning

Infrastructure, containers, web applications and databases are scanned [[TODO: e.g. monthly]] with up-to-date signatures. Findings are fixed within [[TODO: e.g. Critical 15 days, High 30 days, Moderate 90 days]], and High and Critical findings without a fix get a POA&M entry.

## Responding to risk

Accepted risks are approved by [[TODO]] and recorded.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
