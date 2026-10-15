# GRC Readiness Engine: User Manual

Engine version 0.14.0 · ISO/IEC 42001, ISO/IEC 27001 and SOC 2 · October 2026

This manual covers the GRC Readiness Engine: a set of tools on GitHub that run a readiness engagement from kickoff to the certification audit (ISO) or the end of the SOC 2 observation period. It has three parts:

| Part | Kind of guide | Read it when |
|---|---|---|
| [1. Product guide](1-product-guide.md) | Reference | You want to know what the tool can do, and how each part works |
| [2. Training guide](2-training-guide.md) | Tutorial | You're new and want to run an engagement end to end, step by step |
| [3. Troubleshooting guide](3-troubleshooting.md) | Support | Something didn't work and you need the fix |

## How to read it

Most sections are written in three layers, so readers with different backgrounds can each stop at the depth they need:

> **In plain terms:** what it does and why it matters, without jargon. Enough for a client executive or a new team member.

> **For GRC practitioners:** the same thing in ISO and audit language: clauses, controls, evidence, nonconformities.

> **Under the hood:** the files, commands, workflows and rules involved. Enough to operate or change it.

> **Screenshot to add:** marks a place where a screenshot of a GitHub or Cloudflare screen belongs. Those screens sit behind your sign-in, so they can't be captured automatically. The list of slots is in the [training guide's appendix](2-training-guide.md#appendix-screenshots-to-add).

Every other picture in this manual comes from the pilot engagement, **Larkspur Health (fictional)**, which runs in sandbox mode with simulated data.

## Keeping it current

This manual lives in the engine repository (`docs/manual/`) and is versioned with the engine. Screenshots of generated reports and of the client site are captured from the pilot. Update the version line above when you release a new engine version, and refresh pictures whose screens have changed.
