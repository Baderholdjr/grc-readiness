# Engine and client repositories

`grc-readiness` is the **engine**: code, the ISO 42001 catalog and playbook, schemas, the Word template, and the reusable workflows. Each client engagement lives in its own **thin client repository**, which contains only:

```
engagement/            the engagement record (the only thing analysts edit)
intake/                client documents to ingest
templates/intake/      CSV templates to hand to the client
requirements.txt       grc-readiness @ git+https://github.com/<owner>/grc-readiness@engine-vX.Y.Z
.github/workflows/     small wrappers that call the engine's workflows at @engine-vMAJOR
```

A fix to the engine therefore reaches every client through **one** reviewed upgrade PR per client, instead of being copied by hand.

## How versions work

| Thing | Pinned by | Moves when |
|---|---|---|
| Engine code and resources | `requirements.txt` → `engine-vX.Y.Z` (exact) | You merge the client's *Upgrade GRC engine* PR |
| Workflow logic | wrappers → `@engine-vMAJOR`, e.g. `@engine-v0` | Each engine release with that major version |

Breaking changes to workflows or data formats bump the **major** version (`engine-v1`). Client wrappers keep calling `@engine-v0` until someone deliberately edits them. GitHub's built-in token isn't allowed to edit workflow files, so that edit is made by a person.

## Releasing a new engine version

1. In a PR, bump the version in `grc/__init__.py` **and** `pyproject.toml` (tests check they match). Add the change notes to the PR description. Merge it.
2. Go to **Actions → Release GRC engine → Run workflow**, on `main`, and enter one line of notes.
   The workflow:
   - runs the tests
   - refuses to run if the version already exists
   - creates the release `engine-vX.Y.Z`
   - moves `engine-vMAJOR` to it
3. Each client repo's weekly **Upgrade GRC engine** workflow opens a PR bumping `requirements.txt`. `validate` runs on it with the new engine. Merge to upgrade. To upgrade sooner, run it from that repo's Actions tab.

## One-time setup in the engine repo

**Settings → Actions → General → Access**: choose *Accessible from repositories owned by the user* (or your organization). Without this, client repos can't call the engine's reusable workflows.

## Creating a client repository

1. Create an **empty private** repository, for example `acme-grc`.
2. Write the skeleton into it, from a clone of the engine (or wherever the engine is installed):
   ```bash
   python -m grc bootstrap --dir ../acme-grc --engine-repo <owner>/grc-readiness
   ```
   Commit and push the result to `main`.
3. In the client repo, follow its README's setup steps:
   - Add the secret `GRC_ENGINE_TOKEN`: a fine-grained token with *Contents: Read* on the engine repo only.
   - Allow GitHub Actions to create pull requests.
   - Protect `main`, requiring the **`validate / validate`** check.
   - Run **New engagement**.

## Customising per client

A client repo can override any engine resource by placing a file at the same path:

| Path in the client repo | Overrides |
|---|---|
| `frameworks/iso42001/playbook.yaml` | Phases, needs, guardrails, readiness criteria |
| `frameworks/iso42001/catalog.yaml` | The requirement catalog (rarely needed) |
| `templates/brief-template.docx` | House style for the Word brief |

Files that aren't overridden come from the pinned engine version.
