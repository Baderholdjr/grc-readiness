# ITGC-CHG-2026-10: Change management ITGC test, Baderholdjr/grc-readiness

**Objective:** Changes to the production branch are authorized, independently reviewed, tested and traceable.

**Period:** 2026-10-01 to 2026-10-31. **Population:** 37 item(s) from GitHub REST API, Baderholdjr/grc-readiness@main, fetched 2026-11-04 (SHA-256 `5b9140b1b2f54477…`).

**Sample:** 31 item(s). risk-based: every high-risk item, plus a deterministic random sample of the rest (Python random.Random(seed)). High-risk: 28, random: 3.

**Conclusion:** not concluded (the auditor concludes, not the tool).

## Results by attribute

| Attribute | Test | Exceptions |
|---|---|---|
| CHG-1 | The change reached the branch through a pull request (not a direct push). | 2 of 31 |
| CHG-2 | A person other than the author approved the pull request before it was merged. | 31 of 31 |
| CHG-3 | The approval was given on the final code: no commits were added after it. | 0 of 0 (31 not applicable) |
| CHG-4 | Automated checks had run on the merged code when it was merged, and none had failed. | 3 of 31 |
| CHG-5 | The change links to a ticket or issue. | 19 of 31 |

✓ pass, ✗ exception, – not applicable (an earlier attribute already failed).

## Sample

| Item | Selected because | CHG-1 | CHG-2 | CHG-3 | CHG-4 | CHG-5 | Result |
|---|---|---|---|---|---|---|---|
| [commit:af54ed2210](https://github.com/Baderholdjr/grc-readiness/commit/af54ed22109377d55974d29b30e0365cb25c45ee) Initial GRC-as-code engine for ISO/IEC 42001 readiness engagements | direct push to the branch; changes sensitive paths: .github/workflows/freshness. | ✗ | ✗ | – | ✗ | ✗ | exception |
| [commit:2ca4a933c5](https://github.com/Baderholdjr/grc-readiness/commit/2ca4a933c55d11bf95c0eb8f3262a316d4284765) Remove references to external repo; example evidence points to client  | direct push to the branch | ✗ | ✗ | – | ✗ | ✗ | exception |
| [#14](https://github.com/Baderholdjr/grc-readiness/pull/14) Bump actions/upload-artifact from 4 to 6 | changes sensitive paths: .github/workflows/validate.yml | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#15](https://github.com/Baderholdjr/grc-readiness/pull/15) Bump actions/setup-python from 5 to 7 | changes sensitive paths: .github/workflows/freshness.yml, .github/workflows/rele | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#16](https://github.com/Baderholdjr/grc-readiness/pull/16) Bump actions/checkout from 4 to 7 | changes sensitive paths: .github/workflows/freshness.yml, .github/workflows/rele | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#17](https://github.com/Baderholdjr/grc-readiness/pull/17) Release workflow: publish evidence package from a GitHub release | changes sensitive paths: .github/workflows/release.yml | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#19](https://github.com/Baderholdjr/grc-readiness/pull/19) CI: validate before unit tests; tests use a frozen fixture | changes sensitive paths: .github/workflows/validate.yml | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#20](https://github.com/Baderholdjr/grc-readiness/pull/20) Automation: document ingestion and evidence collectors | changes sensitive paths: .github/workflows/collect.yml, .github/workflows/ingest | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#22](https://github.com/Baderholdjr/grc-readiness/pull/22) Collect: clear error when Actions can't open PRs | changes sensitive paths: .github/workflows/collect.yml | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#23](https://github.com/Baderholdjr/grc-readiness/pull/23) Publish browsable reports to a reports branch | changes sensitive paths: .github/workflows/publish-reports.yml | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#24](https://github.com/Baderholdjr/grc-readiness/pull/24) Engagement ops: new-engagement, owners, evidence linking, sandbox mode | changes sensitive paths: .github/workflows/collect.yml, .github/workflows/new-en | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#26](https://github.com/Baderholdjr/grc-readiness/pull/26) Package the engine: thin client repos, reusable workflows, versioned u | changes sensitive paths: .github/workflows/collect.yml, .github/workflows/engine | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#27](https://github.com/Baderholdjr/grc-readiness/pull/27) Engine 0.2.1: report unprotected branches on GitHub Free private repos | random sample | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#29](https://github.com/Baderholdjr/grc-readiness/pull/29) Engine 0.3.0: internal audit (9.2) and corrective actions (10.2) | changes sensitive paths: .github/workflows/audit.yml, .github/workflows/grc-audi | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#30](https://github.com/Baderholdjr/grc-readiness/pull/30) AI system impact assessments (C) — engine 0.4.0 | changes sensitive paths: .github/workflows/grc-impact.yml, .github/workflows/imp | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#31](https://github.com/Baderholdjr/grc-readiness/pull/31) Policies and procedures as code (B) — engine 0.5.0 | changes sensitive paths: .github/workflows/docs.yml, .github/workflows/grc-docs. | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#32](https://github.com/Baderholdjr/grc-readiness/pull/32) Management review (F) — engine 0.6.0 | changes sensitive paths: .github/workflows/grc-review.yml, .github/workflows/rev | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#33](https://github.com/Baderholdjr/grc-readiness/pull/33) More evidence collectors (D) — engine 0.7.0 | changes sensitive paths: .github/workflows/grc-collect.yml | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#34](https://github.com/Baderholdjr/grc-readiness/pull/34) Auditor package (G) — engine 0.8.0 | changes sensitive paths: .github/workflows/grc-release.yml | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#36](https://github.com/Baderholdjr/grc-readiness/pull/36) Hours tracking (H) — engine 0.9.0 | changes sensitive paths: .github/workflows/grc-hours.yml, .github/workflows/hour | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#38](https://github.com/Baderholdjr/grc-readiness/pull/38) Excel workbook export (J) — engine 0.10.0 | random sample | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#39](https://github.com/Baderholdjr/grc-readiness/pull/39) Client view (I) — engine 0.11.0 | changes sensitive paths: grc/resources/schemas/engagement.schema.json | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#40](https://github.com/Baderholdjr/grc-readiness/pull/40) Client site: readiness portal; answers arrive as reviewed PRs (engine  | changes sensitive paths: .github/workflows/grc-portal.yml, .github/workflows/por | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#42](https://github.com/Baderholdjr/grc-readiness/pull/42) Client site: failure reference codes and Worker logs (0.12.1) | random sample | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#44](https://github.com/Baderholdjr/grc-readiness/pull/44) User manual; hours kept out of auditor-facing output; clear YAML error | changes sensitive paths: .github/workflows/grc-release.yml | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#45](https://github.com/Baderholdjr/grc-readiness/pull/45) ISO 27001, two frameworks per client repo, reviewed cross-framework re | changes sensitive paths: .github/workflows/audit.yml, .github/workflows/docs.yml | ✓ | ✗ | – | ✓ | ✓ | exception |
| [#47](https://github.com/Baderholdjr/grc-readiness/pull/47) SOC 2 framework (engine 0.14.0) | changes sensitive paths: .github/workflows/grc-new-engagement.yml, .github/workf | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#48](https://github.com/Baderholdjr/grc-readiness/pull/48) Document loading for every record (engine 0.14.1) | changes sensitive paths: .github/workflows/grc-ingest.yml, .github/workflows/ing | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#49](https://github.com/Baderholdjr/grc-readiness/pull/49) Smaller, shorter-lived run artifacts (0.14.2) | changes sensitive paths: .github/workflows/grc-portal.yml, .github/workflows/grc | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#50](https://github.com/Baderholdjr/grc-readiness/pull/50) Add PolyForm Noncommercial 1.0.0 license | changes sensitive paths: LICENSE | ✓ | ✗ | – | ✓ | ✗ | exception |
| [#51](https://github.com/Baderholdjr/grc-readiness/pull/51) LICENSE: full PolyForm text with Required Notice | changes sensitive paths: LICENSE | ✓ | ✗ | – | ✗ | ✗ | exception |

## Exceptions

| Item | Attribute | Detail | Auditor note |
|---|---|---|---|
| commit:af54ed2210 | CHG-1 | pushed straight to the branch by Baderholdjr |  |
| commit:af54ed2210 | CHG-2 | no pull request, so nobody approved it |  |
| commit:af54ed2210 | CHG-4 | no pull request, so no checks gated the change |  |
| commit:af54ed2210 | CHG-5 | no ticket reference in the commit message |  |
| commit:2ca4a933c5 | CHG-1 | pushed straight to the branch by Baderholdjr |  |
| commit:2ca4a933c5 | CHG-2 | no pull request, so nobody approved it |  |
| commit:2ca4a933c5 | CHG-4 | no pull request, so no checks gated the change |  |
| commit:2ca4a933c5 | CHG-5 | no ticket reference in the commit message |  |
| #14 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #15 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #16 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #17 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #19 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #20 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #20 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #22 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #22 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #23 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #23 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #24 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #24 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #26 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #26 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #27 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #27 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #29 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #30 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #31 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #32 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #33 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #33 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #34 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #36 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #38 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #38 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #39 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #39 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #40 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #40 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #42 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #42 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #44 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #44 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #45 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #47 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #47 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #48 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #48 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #49 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #49 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #50 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #50 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
| #51 | CHG-2 | no approval by a person other than the author (0 review(s), none approving at merge) |  |
| #51 | CHG-4 | merged while 1 check(s) were still running |  |
| #51 | CHG-5 | no ticket or issue reference in the title, description or branch |  |
