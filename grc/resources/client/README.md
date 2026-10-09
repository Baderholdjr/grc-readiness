# GRC engagement repository

> 📊 **Reports:** [`reports` branch](../../tree/reports) — brief, control matrix, SoA, gap register, evidence index.

This repository holds **one engagement's record** (`engagement/`). The engine that validates it,
collects evidence and builds the reports lives in
[__ENGINE_REPO__](https://github.com/__ENGINE_REPO__) and is pinned in `requirements.txt`
(engine __ENGINE_VERSION__ at setup). A weekly *Upgrade GRC engine* PR keeps it current.

## One-time setup
1. **Secret `GRC_ENGINE_TOKEN`** (Settings → Secrets and variables → Actions): a fine-grained token with
   *Contents: Read* on __ENGINE_REPO__ — lets workflows install the private engine.
2. **Settings → Actions → General**: tick *Allow GitHub Actions to create and approve pull requests*.
3. **Branch protection** on `main`: require the status check **`validate / validate`** and a CODEOWNERS review.
4. **Actions → New engagement → Run workflow**: enter the client and audit dates; merge the PR it opens.
5. Fill `engagement/owners.yaml`, upload client documents to `intake/`, configure `engagement/collectors.yaml`.

Full guide: [AUTOMATION.md](https://github.com/__ENGINE_REPO__/blob/main/docs/AUTOMATION.md) ·
intake templates for the client: `templates/intake/`.
