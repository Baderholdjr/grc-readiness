# WP-01 Release gate walkthrough (A.6.2.4, A.6.2.5)

| Field | Value |
|---|---|
| Requirement(s) | A.6.2.4 AI system verification and validation; A.6.2.5 AI system deployment |
| Evidence ID | EV-022 |
| Performed by / date | Analyst, 2026-10-07 |
| Population | 3 production model promotions merged 2026-07-01..2026-09-30 (EV-011) |
| Sample | 2 of 3, selected at random |

## Procedure
1. For each sampled promotion, open the PR and the linked run of the release gate (EV-009).
2. Confirm evaluation metrics were computed and compared to the configured thresholds.
3. Confirm the merge was blocked until a reviewer other than the author approved.
4. Confirm the deployed artifact digest matches the gated artifact.

## Results
| Sample | Metrics gate | Independent approval | Digest match | Exception |
|---|---|---|---|---|
| Promotion 1 | Pass | Yes | Yes | None |
| Promotion 2 | Pass | Yes | Yes | None |

## Conclusion
Operating as designed for the sample. Leg remains **partial** until the release-owner
interview confirms the threshold-change process (who can change thresholds, and how that is approved).

> Workpapers here contain no confidential client data. Store sensitive workpapers in the
> client's system and keep only a pointer in `evidence/index.yaml`.
