# Vendored code

| File | From | Version | SHA-256 |
|---|---|---|---|
| `js-yaml.mjs` | github.com/nodeca/js-yaml, `dist/js-yaml.mjs` at tag 4.1.1 (commit cc482e7) | 4.1.1 (includes the fix for the merge-key prototype-pollution issue) | `efbc45850bf15f0c8ee3434983f512be656002d7507dc292c7ade4449b5d57fa` |

MIT license: `js-yaml-LICENSE.txt`. The Worker parses with `CORE_SCHEMA` (no custom types). `tests/test_workspace.py`
checks the hash, so a changed file fails CI.
