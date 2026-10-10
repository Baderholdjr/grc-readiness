# {{title}}

## Purpose

This procedure defines how {{client}} identifies, analyses, evaluates and treats risks related to its AI systems and to the AI management system itself, so that results are consistent, valid and comparable.

## Criteria

**Risk criteria** (used to decide which risks need treatment):

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Likelihood | Rare | Unlikely | Possible | Likely | Almost certain |
| Consequence | Negligible | Minor | Moderate | Major | Severe |

Risk score = likelihood × consequence. [[TODO: confirm these match {{client}}'s enterprise risk method, or replace them with it.]]

- **Acceptable without treatment:** score below [[TODO]].
- **Needs treatment:** score of [[TODO]] or more.
- **Who can accept residual risk:** [[TODO: e.g. risk owner up to score 11; top management above]].

Risks include those to the organisation (e.g. legal, reputational) and the consequences for individuals and society identified through impact assessments (DOC-IMPACT).

## Risk assessment

Risk assessments are performed:
- when an AI system is planned, before release, and at least every [[TODO]] months;
- when a system, its data, its intended use or its context changes significantly;
- after an incident or a relevant internal audit finding.

Steps:
1. **Identify** risks across the lifecycle using the AI system's intended use, the impact assessment, data sources, suppliers, and known failure modes.
2. **Analyse** each risk's likelihood and consequence, and record the existing controls.
3. **Evaluate** against the criteria and prioritise.

## Risk treatment

1. Choose an option for each risk that needs treatment: modify (add controls), avoid, share, or accept.
2. Select controls, comparing them with Annex A of {{framework}} so nothing necessary is missed; record the result in the Statement of Applicability.
3. Write a treatment plan: action, owner, due date.
4. The risk owner approves the plan and accepts the residual risk within their authority.

## Records

The AI risk register is kept in [[TODO: e.g. Drata / the GRC tool]]. Each entry records the risk, its owner, scores before and after treatment, treatment plan and acceptance. Treatment plans and the Statement of Applicability are retained per DOC-DOCINFO.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days. Risk assessment results are an input to management review (DOC-REVIEW).
