# {{title}}

## Purpose

This procedure governs the data used to develop, evaluate and operate AI systems, so that it is lawfully acquired, fit for purpose and traceable.

## Acquisition

- Each dataset has an owner and a documented legal basis or licence for its use [[TODO: e.g. BAA, consent, contract]].
- Data from third parties is acquired under agreements that cover permitted use, quality and provenance (DOC-THIRDPARTY).
- Personal and sensitive data is minimised and approved by [[TODO: e.g. Privacy]] before use.

## Quality

Data quality requirements are defined per use (training, validation, testing, production) and checked before use:

| Dimension | Check | Threshold |
|---|---|---|
| Completeness | [[TODO]] | [[TODO]] |
| Accuracy / label quality | [[TODO]] | [[TODO]] |
| Representativeness (incl. relevant subgroups) | [[TODO]] | [[TODO]] |
| Timeliness | [[TODO]] | [[TODO]] |

Known limitations and biases are recorded and taken into account in the impact assessment (DOC-IMPACT).

## Provenance

For each dataset {{client}} records where it came from, when, under what terms, and what has been done to it, so that any model can be traced back to the data it was trained and evaluated on. Records are kept in [[TODO: e.g. the data catalogue / dataset cards]].

## Preparation

Preparation steps (cleaning, labelling, de-identification, sampling, augmentation) are documented, reproducible and reviewed. Labelling guidelines and labeller qualifications are recorded where labels are created.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
