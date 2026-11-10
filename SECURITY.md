# Security policy

## Reporting a vulnerability

Please don't open a public issue. Use **Security → Report a vulnerability** on this repository (GitHub private
vulnerability reporting), or email the maintainer listed in CODEOWNERS. Include what you found, how to reproduce it
with fictional data, and what an attacker could do with it. We acknowledge reports within 3 business days and
agree a fix and disclosure date with you.

Never include real client data, secrets or tokens in a report.

## Supported versions

The latest `engine-v0.x` release receives security fixes. Clients receive them through the weekly *Upgrade GRC
engine* pull request.

## How the engine is kept secure

The [threat model](docs/THREAT-MODEL.md) lists what we protect, the trust boundaries and the controls. In short:

- Every change is a reviewed pull request; nothing automated marks evidence verified or an answer approved.
- The **Security** workflow runs on every pull request, on `main` and weekly:
  - bandit (code), pip-audit (known vulnerabilities in every locked dependency), and zizmor (workflow security);
  - CodeQL runs separately on the Python and the workflows (results under **Security → Code scanning**);
  - it also checks that the hash-locked dependency files match `pyproject.toml`. Run it by hand with
    **upgrade** to re-resolve the locks to the latest versions; it prints the new files to commit.
- Third-party actions are pinned to commits; dependencies install from hash-locked files.
- Every release's wheel and source archive have signed build-provenance attestations:
  `gh attestation verify <file> --repo <engine repo>`.
- Local settings and secret files (`.claude/settings.local.json`, `.env`, keys) are in `.gitignore`, and
  `grc validate` fails if one is committed.
- Workflows declare least-privilege permissions; cloud access uses OIDC, never stored keys.
- Uploaded client files and the text inside them are treated as untrusted (`grc/safety.py`).

## Repository settings to keep on

- Branch protection on `main` (a ruleset): pull requests required, the *Validate* and *Security* checks required.
  CodeQL can be added as a required check once it has run on `main`.
- Secret scanning and push protection.
- Dependabot alerts and security updates.
- Private vulnerability reporting.
- Tag protection for `engine-v*` (only maintainers can move the tags clients trust).
