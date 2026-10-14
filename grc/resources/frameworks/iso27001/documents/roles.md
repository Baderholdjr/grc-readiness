# {{title}}

## Purpose

This procedure assigns responsibility and authority for information security at {{client}}.

## Roles

| Role | Responsibilities |
|---|---|
| Top management | Approves the policy, objectives and resources; chairs management review |
| ISMS owner ([[TODO]]) | Runs the ISMS; reports its performance to top management |
| Risk owners | Approve treatment plans and accept residual risk within their authority |
| Control owners | Operate their controls and keep evidence current |
| All staff | Follow the policies and report security events (DOC-IS-INCIDENT) |

Current role holders:

{{owners_table}}

## Segregation of duties

Conflicting duties are separated. At minimum:
- people who request access don't approve it;
- people who write code don't approve their own changes to production (DOC-IS-SDLC);
- internal auditors don't audit their own work.

Where separation isn't practical, compensating controls are recorded: [[TODO]].

## External contacts

| Contact | Purpose | Owner |
|---|---|---|
| [[TODO: e.g. data protection authority]] | Breach notification | [[TODO]] |
| [[TODO: e.g. law enforcement, CERT]] | Incident support | [[TODO]] |
| [[TODO: e.g. sector ISAC, security forums]] | Threat information and good practice | [[TODO]] |

The contact list is checked at least annually.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days and on organisational change.
