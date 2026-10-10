# {{title}}

## Purpose

This procedure defines how {{client}} assesses the potential consequences of its AI systems for individuals, groups of individuals and society, throughout their lifecycle.

## When an assessment is required

An impact assessment is required for every AI system in the AIMS scope (inventory kinds: {{impact_required_kinds}}):

- before an AI system is released;
- when its intended use, model, data, user population or deployment context changes materially;
- after a serious incident involving the system;
- at least on the review cycle: {{impact_review_cycle}}.

AI systems currently requiring an assessment:

{{ai_systems_table}}

## Method

1. **Context.** Record the intended use, reasonably foreseeable misuse, affected parties, deployment, human oversight, data used, and jurisdictions.
2. **Screening.** Decide for **every** category below whether it is relevant, and record why.

{{impact_categories_table}}

3. **Assessment.** For each relevant category, describe each potential impact and rate it before mitigation:

{{impact_scales}}

   Score = likelihood × severity, banded as {{impact_bands}}.
4. **Mitigation.** Record the measures that reduce each impact, and re-rate it (residual likelihood and severity). Link the controls and gaps involved.
5. **Conclusion.** Summarise whether the benefits justify the remaining impacts, and propose a decision: approve, approve with conditions, or reject.

## Approval and acceptance

- The assessor and the approver must be different people.
- A residual score of **{{acceptance_required_at}} or more** must be accepted by name, with a date and rationale, by someone other than the assessor.
- A residual score of **{{unacceptable_at}} or more** cannot be approved: the impact must be reduced, or the system rejected.
- An "approve with conditions" decision lists each condition with an owner and due date.

## Records

Each assessment is kept as a version-controlled record (one file per AI system in the GRC repository: `engagement/impact/IA-NNN.yaml`). The approval, any acceptance and every later change are visible in its history. Superseded assessments are retained. Results feed the AI risk assessment (DOC-RISK) and are made available to interested parties where appropriate (DOC-COMMS).

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
