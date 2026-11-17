# FedRAMP CR26 JSON Schemas (vendored)

FedRAMP's JSON Schemas for the FedRAMP Consolidated Rules 2026 documents, copied unchanged from
https://github.com/FedRAMP/schemas at commit 8fe79fa (2026-10-27). FedRAMP marks them as drafts.
They are a work of the United States Government (FedRAMP, GSA).

`grc fedramp export` validates every document it writes against these, and `grc fedramp validate` checks files
against them. `SHA256SUMS` lists each file's hash; the tests check them, so a changed copy is noticed. To update:
copy the new files from FedRAMP's repository, update this README and `SHA256SUMS`, run the tests and review the diff.
