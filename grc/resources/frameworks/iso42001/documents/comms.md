# {{title}}

## Purpose

This procedure determines what information {{client}} gives to users of its AI systems and to other interested parties, how people can report problems, and how AI incidents are communicated.

## Information for users

For each AI system, users and affected people receive information appropriate to the system's impact:

| Information | Where provided | Owner |
|---|---|---|
| That they are interacting with an AI system | [[TODO: e.g. in-product disclosure]] | AI system owner |
| Intended use and known limitations | [[TODO]] | AI system owner |
| How to get human help or contest an outcome | [[TODO]] | AI system owner |
| Instructions for safe use (for operators) | [[TODO]] | AI system owner |

AI systems in scope:

{{ai_systems_table}}

## External reporting

Users and other interested parties can report adverse impacts or problems with an AI system through [[TODO: channel]]. Reports are logged, assessed and handled as concerns (DOC-ROLES) or incidents (below).

## Incident communication

An AI incident is an event where an AI system causes or could cause harm, or behaves materially outside its intended use.

1. **Detect and log** the incident in [[TODO: incident tool]].
2. **Assess** severity and who is affected; involve the AI system owner, [[TODO: Security, Privacy, Legal, Clinical safety]].
3. **Notify** affected users, customers and authorities within the timelines required by law and contract [[TODO: e.g. HIPAA breach rules, customer contracts]].
4. **Record** what was communicated, to whom and when.
5. **Learn:** raise a finding (DOC-IMPROVE) and reassess risk and impact where needed.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days and after any significant incident.
