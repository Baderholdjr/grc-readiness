"""The common 'draft' shape produced by both template import and AI drafting."""
from __future__ import annotations

LEG_ALIASES = {"documented": "documented", "implemented": "implemented", "evidenced": "evidenced",
               "evidence exists": "evidenced", "evidence": "evidenced", "tested": "tested",
               "d": "documented", "i": "implemented", "e": "evidenced", "t": "tested"}
EVIDENCE_TYPES = ["document", "record", "config", "log", "test", "sample", "interview", "screenshot"]
INVENTORY_KINDS = ["ai_system", "sdlc_tool", "infrastructure", "model", "dataset", "supplier_service",
                   "application", "information_asset", "endpoint", "facility"]
SEVERITIES = ["high", "medium", "low"]


def empty() -> dict:
    return {"client_overview": [], "ai_usage": [], "scope_statement": "", "in_place": [], "inventory": [],
            "gaps": [], "evidence": [], "claims": [], "open_questions": []}


def merge(a: dict, b: dict) -> dict:
    out = empty()
    for k in out:
        if isinstance(out[k], list):
            out[k] = (a.get(k) or []) + (b.get(k) or [])
        else:
            out[k] = a.get(k) or b.get(k) or ""
    return out


# JSON schema for Claude's structured output. Every property is required (use ""
# or [] for unknown) to stay within structured-output limits on optional params.
def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


S = {"type": "string"}
SRC = {"type": "string", "description": "file name + page/section + a short verbatim quote (<= 25 words) supporting the item"}
REQS = {"type": "array", "items": S, "description": "requirement ids from the provided catalog only"}

OUTPUT_SCHEMA = _obj({
    "client_overview": {"type": "array", "items": S, "description": "3-5 factual bullets about the organization"},
    "ai_usage": {"type": "array", "items": S, "description": "3-5 factual bullets about the systems, information and (where relevant) AI use in the proposed management-system scope"},
    "scope_statement": {"type": "string"},
    "in_place": {"type": "array", "items": _obj({"foundation": S, "examples": S, "requirements": REQS, "source": SRC})},
    "inventory": {"type": "array", "items": _obj({"name": S, "kind": {"enum": INVENTORY_KINDS}, "owner": S,
                                                  "risk_tier": S, "description": S, "source": SRC})},
    "gaps": {"type": "array", "items": _obj({"area": S, "finding": S, "requirements": REQS, "owner": S,
                                             "severity": {"enum": SEVERITIES}, "source": SRC})},
    "evidence": {"type": "array", "items": _obj({"title": S, "type": {"enum": EVIDENCE_TYPES}, "location": S,
                                                 "owner": S, "date": {"type": "string", "description": "YYYY-MM-DD or ''"},
                                                 "approved_by": {"type": "string", "description": "only if the document explicitly records approval; else ''"},
                                                 "source": SRC})},
    "claims": {"type": "array", "items": _obj({"requirement": S, "leg": {"enum": ["documented", "implemented", "evidenced", "tested"]},
                                               "statement": S, "owner": {"type": "string", "description": "accountable owner named in the document, else ''"},
                                               "source": SRC})},
    "open_questions": {"type": "array", "items": S, "description": "ambiguities or contradictions an analyst must resolve"},
})
