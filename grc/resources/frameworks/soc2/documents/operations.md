# {{title}}

## Purpose

This procedure sets how {{client}} finds and fixes weaknesses in its system and watches for signs of attack, error or failure.

## Vulnerability management

Infrastructure, containers and dependencies are scanned [[TODO: e.g. continuously / weekly]]. A penetration test runs at least annually. Findings are fixed within these times:

| Severity | Fix within |
|---|---|
| Critical | [[TODO]] |
| High | [[TODO]] |
| Medium | [[TODO]] |

## Configuration management

Hardened baselines are defined in [[TODO: e.g. infrastructure as code]]. Drift from them is detected by [[TODO]] and corrected.

## Logging and monitoring

Security-relevant logs from [[TODO: components]] are collected in [[TODO: e.g. the SIEM]], protected from tampering and kept for [[TODO]].

## Alert handling

Alerts are triaged by [[TODO: on-call role]] within [[TODO]]. Alerts that may be security incidents are passed to the incident response process.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
