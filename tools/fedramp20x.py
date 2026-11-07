"""Generate grc/resources/frameworks/fedramp20x/catalog.yaml from the FedRAMP Consolidated Rules.

    git clone https://github.com/FedRAMP/rules
    python tools/fedramp20x.py rules/fedramp-consolidated-rules.json grc/resources/frameworks/fedramp20x/catalog.yaml

Keeps what a provider on the 20x path must do: every Key Security Indicator, and the process rules (FRR) that
affect providers, apply to 20x, and apply to Class A, B or C. Agency, assessor and Marketplace-form rules
(AGU, REC, MKT) are left out. A rule is a `rule` for the classes where it is MUST / MUST NOT, otherwise a
`recommendation` for the classes where it is SHOULD / SHOULD NOT; MAY-only rules are left out.
"""
from __future__ import annotations

import collections
import json
import re
import sys

import yaml

CLASSES = ["a", "b", "c"]
SKIP = {"AGU", "REC", "MKT"}
CATEGORY = {("a", "b", "c"): "core", ("b", "c"): "class_b", ("c",): "class_c", ("a",): "class_a"}
PAIN_LABELS = {"irv_lev": "internet-reachable and likely exploitable",
               "nirv_lev": "not internet-reachable, likely exploitable",
               "nlev": "not likely exploitable"}
UNITS = {"days": "days", "bizdays": "business days", "hours": "hours", "minutes": "minutes", "months": "months"}
PROVIDERS = re.compile(r"Providers with Class [ABCD] (?:FedRAMP )?Certifications", re.I)


def clean(s) -> str:
    return " ".join(str(s or "").replace("**", "").split())


def nist(ids) -> list[str]:
    out = []
    for c in ids or []:
        base, _, enh = str(c).upper().partition(".")
        out.append(f"{base}({enh})" if enh else base)
    return out


def pain(tf: dict) -> str:
    parts = []
    for n in sorted(tf, key=int):
        items = tf[n] or {}
        if not items:
            continue
        bits = []
        for key, t in items.items():
            unit = UNITS.get(t.get("timeframe_type"), t.get("timeframe_type"))
            label = PAIN_LABELS.get(key) if len(items) > 1 else None
            num = t.get("timeframe_num")
            unit = unit[:-1] if num == 1 and unit.endswith("s") else unit
            bits.append(f"{num} {unit}" + (f" ({label})" if label else ""))
        parts.append(f"N{n}: " + ", ".join(bits))
    if not parts:
        return ""
    values = {p.split(": ", 1)[1] for p in parts}
    if len(values) == 1 and len(parts) == 5:
        return f"Timeframe at every Potential Agency Impact rating: {values.pop()}."
    return "Timeframes by Potential Agency Impact rating: " + "; ".join(parts) + "."


def text(v: dict) -> str:
    """A rule variant as one paragraph: statement, its listed items, timeframes and note."""
    s = clean(v.get("statement"))
    items = [clean(x) for x in (v.get("following_information") or []) + (v.get("following_information_bullets") or [])]
    s = s.replace("shown below", "below")
    if items:
        s = s.rstrip(":")
        s += (" " if s.endswith(".") else ": ") + "; ".join(x.rstrip(".;") for x in items) + "."
    if v.get("pain_timeframes"):
        s = s.rstrip(":") + (" " if s.endswith(".") else ". ") + pain(v["pain_timeframes"])
    note = clean(v.get("note"))
    if note:
        s += f" Note: {note}"
    return s


def combine(texts: dict[str, str]) -> str:
    """One text when every class reads the same; otherwise classes with the same text share a label."""
    norm = {c: PROVIDERS.sub("Providers", t) for c, t in texts.items()}
    if len(set(norm.values())) == 1:
        return next(iter(norm.values()))
    same: dict[str, list[str]] = {}
    for c, t in norm.items():
        same.setdefault(t, []).append(c.upper())
    label = lambda cs: f"Class {cs[0]}" if len(cs) == 1 else "Classes " + ", ".join(cs[:-1]) + " and " + cs[-1]
    return " ".join(f"{label(cs)}: {t}" for t, cs in same.items())


def artifacts(r: dict, classes: list[str], default: list[str]) -> list[str]:
    found = []
    for src in [r] + [(r.get("varies_by_class") or {}).get(c) or {} for c in classes]:
        a = src.get("artifacts")
        lists = a.values() if isinstance(a, dict) else [a] if isinstance(a, list) else []
        for lst in lists:
            for x in lst or []:
                x = clean(x)
                x = x[:1].upper() + x[1:]
                if x and x not in found:
                    found.append(x)
    return (found or default)[:5]


def generate(d: dict) -> dict:
    default = d["info"]["default_artifacts"]
    frr_default = [clean(x) for x in default["FRR"]]
    ksi_default = [clean(x) for x in default["KSI"]]
    reqs, groups = [], []
    for pk, p in d["FRR"].items():
        if pk in SKIP:
            continue
        info = p["info"]
        subsets = dict(info.get("subsets") or {})
        subsets.update((info.get("20x") or {}).get("subsets") or {})
        added = 0
        for app, subs in p["data"].items():
            if app not in ("all", "20x"):
                continue
            for sk, rs in subs.items():
                ap = (subsets.get(sk) or {}).get("applicability") or {}
                if ap.get("types") and "20x" not in ap["types"]:
                    continue
                sub_classes = [c.lower() for c in ap.get("classes") or ["A", "B", "C", "D"]]
                for rid, r in rs.items():
                    if "Providers" not in (r.get("affects") or []):
                        continue
                    per = {}
                    for c in CLASSES:
                        v = (r.get("varies_by_class") or {}).get(c)
                        if v is not None:
                            per[c] = (v.get("force") or r.get("force"), text({**r, **v, "note": v.get("note") or r.get("note")}))
                        elif c in sub_classes and r.get("statement"):
                            per[c] = (r.get("force"), text(r))
                    must = [c for c in CLASSES if c in per and per[c][0] in ("MUST", "MUST NOT")]
                    should = [c for c in CLASSES if c in per and per[c][0] in ("SHOULD", "SHOULD NOT")]
                    if must:
                        kind, scope = "rule", must
                    elif should:
                        kind, scope = "recommendation", should
                    else:
                        continue
                    # the intent shows every class the rule speaks to, so a SHOULD for Class A stays visible
                    shown = {c: per[c][1] for c in CLASSES if c in per and per[c][0] not in ("MAY",)}
                    reqs.append({"id": rid, "kind": kind, "category": CATEGORY[tuple(scope)], "group": pk,
                                 "title": clean(r["name"]), "intent": combine(shown),
                                 "evidence_examples": artifacts(r, scope, frr_default),
                                 **({"nist80053": nist(r["controls"])} if r.get("controls") else {})})
                    added += 1
        if added:
            groups.append({"id": pk, "title": f"{pk} {info['name']}"})
    for tk, t in d["KSI"].items():
        groups.append({"id": f"KSI-{tk}", "title": f"KSI {t['name']}"})
        for kid, i in t["indicators"].items():
            per = {}
            for c in CLASSES:
                v = (i.get("varies_by_class") or {}).get(c)
                s = clean(v.get("statement")) if v is not None else clean(i.get("statement"))
                if s and not s.startswith("Optional:"):
                    per[c] = s
            scope = [c for c in CLASSES if c in per]
            reqs.append({"id": kid, "kind": "indicator", "category": CATEGORY[tuple(scope)], "group": f"KSI-{tk}",
                         "title": clean(i["name"]), "intent": combine(per), "evidence_examples": ksi_default,
                         **({"nist80053": nist(i["controls"])} if i.get("controls") else {})})
    return {"reqs": reqs, "groups": groups}


HEAD = """# FedRAMP 20x requirement catalog, generated by tools/fedramp20x.py from the FedRAMP Consolidated Rules for 2026
# (https://github.com/FedRAMP/rules, version {version}, updated {updated}). Do not edit by hand: regenerate.
# It holds the Key Security Indicators (KSI-*) and the process rules that affect providers on the 20x path.
# FedRAMP's text is a US Government work; each `intent` is FedRAMP's own statement (bold markers removed, listed
# items and timeframes run in). Defined terms (persistently, information resource, likely, ...) have the meanings
# in the dataset's FRD definitions.
#
# kind: indicator      -> a Key Security Indicator: shown with measures, automated where practical.
#       rule           -> a MUST / MUST NOT rule for the class.
#       recommendation -> a SHOULD / SHOULD NOT rule for the class: may be marked not applicable, with the reason
#                         and the resulting risk to customers.
# FedRAMP also accepts an explanation of why a rule or indicator is not met, with the risk to customers, when a
# senior official accepts it. Record that as an accepted risk in the gap register; don't exclude the item.
#
# category: core = every 20x class (A, B and C). Choose the certification class in scope.categories:
#   Class A (pilot)    -> class_a
#   Class B (Low)      -> class_b
#   Class C (Moderate) -> class_b and class_c   (class_c adds to class_b)
# Class D (High) is on the Rev5 path, not 20x. `nist80053` lists FedRAMP's own control mappings.
"""


def main(src: str, dest: str) -> None:
    d = json.load(open(src, encoding="utf-8"))
    g = generate(d)
    data = {
        "framework": {"id": "fedramp20x", "name": "FedRAMP 20x (FedRAMP Consolidated Rules for 2026)",
                      "short_name": "FedRAMP 20x", "management_system": "Security program for the cloud service offering",
                      "source": "https://github.com/FedRAMP/rules", "version": d["info"]["version"]},
        "kinds": {"indicator": {"label": "Key Security Indicator", "short": "KSI", "mandatory": True},
                  "rule": {"label": "FedRAMP rule (MUST)", "short": "Rule", "mandatory": True},
                  "recommendation": {"label": "FedRAMP rule (SHOULD)", "short": "Should", "mandatory": False}},
        "choose_at_least_one": ["class_a", "class_b"],
        "categories": [
            {"id": "core", "title": "Every 20x class", "short": "All classes", "required": True},
            {"id": "class_a", "title": "Class A (pilot) only", "short": "Class A", "excludes": ["class_b", "class_c"]},
            {"id": "class_b", "title": "Class B (Low) and Class C (Moderate)", "short": "Class B+"},
            {"id": "class_c", "title": "Class C (Moderate) only", "short": "Class C", "requires": ["class_b"]}],
        "groups": g["groups"], "requirements": g["reqs"]}
    head = HEAD.format(version=d["info"]["version"], updated=d["info"].get("last_updated", ""))
    with open(dest, "w", encoding="utf-8") as f:
        f.write(head + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=130))
    c = collections.Counter((r["kind"], r["category"]) for r in g["reqs"])
    print(len(g["reqs"]), "requirements:", dict(sorted(c.items())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
