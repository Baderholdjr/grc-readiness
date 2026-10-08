# Cross-framework mappings (planned)

When a second framework is added, a mapping file lets one piece of evidence or
one existing process satisfy requirements in several frameworks, so SOC 2 work
is reused rather than duplicated.

Proposed format, `mappings/<from>__<to>.yaml`:

```yaml
from: soc2-2017
to: iso42001
relationship_types: [equivalent, subset, superset, related]
mappings:
  - from: CC9.2            # vendor and business partner risk management
    to: A.10.3             # suppliers
    relationship: related
    note: SOC 2 vendor program covers security; AI-specific criteria must be added.
```

Rules to add when this lands:
- `reuses:` entries in control files must resolve to a mapped requirement.
- An `equivalent` mapping lets evidence verified for one framework count for the other.
- `related` or `subset` mappings never auto-verify; they only pre-populate the analyst's work.

No mappings ship yet. Build them from licensed copies of both standards and record who reviewed each one.
