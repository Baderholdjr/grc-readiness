# {{title}}

## Purpose

This procedure defines how {{client}} identifies, analyses, evaluates and treats information security risks so that results are consistent, valid and comparable.

## Criteria

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Likelihood | Rare | Unlikely | Possible | Likely | Almost certain |
| Impact | Negligible | Minor | Moderate | Major | Severe |

Risk score = likelihood × impact. [[TODO: confirm these match {{client}}'s enterprise risk method, or replace them with it.]]

- **Acceptable without treatment:** score below [[TODO]].
- **Needs treatment:** score of [[TODO]] or more.
- **Who can accept residual risk:** [[TODO: e.g. risk owner up to 11; top management above]].

## Risk assessment

Assessments are performed at least every [[TODO]] months, on significant change, and after relevant incidents or audit findings. Steps:
1. **Identify** risks to the confidentiality, integrity and availability of information within scope, using the asset inventory (DOC-IS-ASSETS), threats and vulnerabilities. Each risk has an owner.
2. **Analyse** likelihood and impact, taking existing controls into account.
3. **Evaluate** against the criteria and prioritise.

## Risk treatment

1. Choose a treatment option for each risk: modify (add controls), avoid, share, or accept.
2. Determine the controls needed and compare them with Annex A of {{framework}} so nothing necessary is missed.
3. Write the risk treatment plan: action, owner, due date.
4. Risk owners approve the plan and accept the residual risk.

## Statement of Applicability

The Statement of Applicability lists every Annex A control, whether it is applicable, whether it is implemented, and the justification for including or excluding it. It is generated from the GRC record (`soa.md`) and approved by [[TODO]] alongside the treatment plan.

## Threat intelligence

Threat information is collected from [[TODO: e.g. vendor advisories, sector ISAC, CISA]], analysed by [[TODO]], and used to update risks and controls.

## Records

The risk register is kept in [[TODO: e.g. Drata / the GRC tool]]. Assessment results, treatment plans and SoA versions are retained per DOC-IS-DOCINFO.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days. Risk results are an input to management review (DOC-IS-REVIEW).
