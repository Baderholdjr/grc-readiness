"""OSCAL: every export is valid against NIST's OSCAL 1.2.3 schema, ids are stable and unique, nothing in the
export claims more than the record shows, and a catalog and baseline import into a working framework."""
import contextlib
import io
import json
from pathlib import Path

import pytest
import yaml

from grc import oscal
from grc.cli import main
from grc.model import ENGINE, load

FIX = Path(__file__).parent / "fixtures" / "oscal"
FRAMEWORKS = [("iso42001", None), ("iso27001", None), ("soc2", None), ("hipaa", "covered_entity"),
              ("txramp", "core,level_2"), ("gdpr", "controller"), ("fedramp20x", "class_b"), ("cbpr", "cbpr,prp")]


def _new(tmp_path, fw, cats=None):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / "engagement"), "new-engagement", "--client", "Larch & Finch", "--start",
            "2026-11-09", "--stage1", "2027-02-01", "--stage2", "2027-06-01", "--framework", fw,
            "--intake", str(root / "intake"), "--confirm-reset"]
    if cats:
        args[-1:-1] = ["--categories", cats]
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(args) == 0
    return root


@pytest.mark.parametrize("fw,cats", FRAMEWORKS, ids=[f for f, _ in FRAMEWORKS])
def test_every_framework_exports_valid_oscal(tmp_path, fw, cats):
    root = _new(tmp_path, fw, cats)
    out = root / "oscal"
    names = [n for n, _ in oscal.export(load(root / "engagement"), out)]
    assert names[-4:] == ["ssp.json", "assessment-plan.json", "assessment-results.json", "poam.json"]
    assert ("catalog.json" in names) == (fw != "txramp")      # TX-RAMP points at NIST's own 800-53 catalog
    for n in names:
        doc = json.loads((out / n).read_text())
        assert oscal.validate(doc) == [], n
        assert doc[next(iter(doc))]["metadata"]["oscal-version"] == oscal.OSCAL_VERSION


def test_sample_record_exports_and_is_stable(tmp_path):
    m = load(ENGINE.parent.parent / "engagement")
    a, b = tmp_path / "a", tmp_path / "b"
    oscal.export(m, a)
    oscal.export(m, b)
    for f in a.iterdir():          # same record, same day: byte-identical (uuids are derived, not random)
        assert f.read_bytes() == (b / f.name).read_bytes(), f.name


@pytest.mark.parametrize("fw", [f for f, _ in FRAMEWORKS])
def test_control_ids_are_unique_tokens(fw):
    cat = yaml.safe_load((ENGINE / "frameworks" / fw / "catalog.yaml").read_text())
    ids = [oscal.control_id(fw, str(r["id"])) for r in cat["requirements"]]
    assert len(set(ids)) == len(ids)
    import re
    assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9._-]*", i) for i in ids)


def test_nist_ids_take_nists_form():
    assert oscal.control_id("txramp", "AC-2(3)") == "ac-2.3"
    assert oscal.control_id("txramp", "SI-04") == "si-4"
    assert oscal.control_id("hipaa", "164.308(a)(1)(ii)(A)") == "hipaa-164.308.a.1.ii.A"
    assert oscal.control_id("iso27001", "A.5.15") == "iso27001-A.5.15"


def test_nothing_is_satisfied_or_implemented_without_the_record_saying_so(tmp_path):
    root = _new(tmp_path, "soc2")
    out = tmp_path / "o"
    oscal.export(load(root / "engagement"), out)
    ar = json.loads((out / "assessment-results.json").read_text())["assessment-results"]
    states = {f["target"]["status"]["state"] for f in ar["results"][0].get("findings", [])}
    assert states == {"not-satisfied"}                      # a new record: nothing is Ready
    assert "not an independent assessment" in ar["results"][0]["description"]
    ssp = json.loads((out / "ssp.json").read_text())["system-security-plan"]
    statuses = {bc["implementation-status"]["state"] for r in ssp["control-implementation"]["implemented-requirements"]
                for bc in r["by-components"]}
    assert statuses == {"planned"}


def _verify_all(root, rid, evidence):
    f = root / "engagement" / "controls" / f"{rid}.yaml"
    d = yaml.safe_load(f.read_text())
    for leg in ("documented", "implemented", "evidenced", "tested"):
        d.setdefault("test", {})[leg] = {"status": "verified", **({"evidence": evidence} if evidence else {})}
    d["owner"] = "CISO"
    f.write_text(yaml.safe_dump(d, sort_keys=False))


def _finding(out, rid):
    ar = json.loads((out / "assessment-results.json").read_text())["assessment-results"]
    f = next(x for x in ar["results"][0]["findings"] if x["title"].startswith(rid + ":"))
    ssp = json.loads((out / "ssp.json").read_text())["system-security-plan"]
    r = next(x for x in ssp["control-implementation"]["implemented-requirements"]
             if x["props"][0]["value"] == rid)
    return f["target"]["status"]["state"], r["by-components"][0]["implementation-status"]["state"], ar


def test_verified_without_evidence_is_refused_or_shown_unmet(tmp_path):
    root = _new(tmp_path, "soc2")
    _verify_all(root, "CC1.1", None)                 # E005: verified with no evidence
    m = load(root / "engagement")
    with pytest.raises(oscal.OscalError, match="validation error"):
        oscal.export(m, tmp_path / "o")
    oscal.export(m, tmp_path / "o", force=True)
    target, impl, ar = _finding(tmp_path / "o", "CC1.1")
    assert (target, impl) == ("not-satisfied", "partial")
    assert ar["metadata"]["remarks"].startswith("DRAFT")


def test_ready_requirement_is_satisfied_and_points_at_its_evidence(tmp_path):
    from grc.rules import validate
    root = _new(tmp_path, "soc2")
    idx = root / "engagement" / "evidence" / "index.yaml"
    ev = [{"id": "EV-901", "title": "Code of conduct", "type": "document", "location": "https://example.invalid/coc",
           "owner": "CISO", "collected": "2026-11-01", "approved_by": "CEO"},
          {"id": "EV-902", "title": "Signed acknowledgements", "type": "record", "location": "https://example.invalid/ack",
           "owner": "CISO", "collected": "2026-11-01"},
          {"id": "EV-903", "title": "Acknowledgement sample test", "type": "test", "location": "https://example.invalid/t",
           "owner": "CISO", "collected": "2026-11-02"}]
    idx.write_text(yaml.safe_dump({"evidence": ev}, sort_keys=False))
    f = root / "engagement" / "controls" / "CC1.1.yaml"
    d = yaml.safe_load(f.read_text())
    d["owner"] = "CISO"
    d["test"] = {"documented": {"status": "verified", "evidence": ["EV-901"]},
                 "implemented": {"status": "verified", "evidence": ["EV-902"]},
                 "evidenced": {"status": "verified", "evidence": ["EV-902"]},
                 "tested": {"status": "verified", "evidence": ["EV-903"]}}
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    m = load(root / "engagement", today=__import__("datetime").date(2026, 11, 9))
    assert [x for x in validate(m) if x.severity == "error"] == []
    oscal.export(m, tmp_path / "o")
    target, impl, ar = _finding(tmp_path / "o", "CC1.1")
    assert (target, impl) == ("satisfied", "implemented")
    obs = {o["props"][0]["value"]: o for o in ar["results"][0]["observations"]}
    assert sorted(obs) == ["EV-901", "EV-902", "EV-903"]
    assert obs["EV-903"]["methods"] == ["TEST"] and obs["EV-901"]["collected"] == "2026-11-01T00:00:00Z"
    others = {x["target"]["status"]["state"] for x in ar["results"][0]["findings"] if not x["title"].startswith("CC1.1:")}
    assert others == {"not-satisfied"}


def test_open_gaps_become_poam_items(tmp_path):
    m = load(ENGINE.parent.parent / "engagement")
    oscal.export(m, tmp_path)
    poam = json.loads((tmp_path / "poam.json").read_text())["plan-of-action-and-milestones"]
    open_gaps = [g for g in m.gaps if isinstance(g, dict) and g.get("status") in ("open", "in_progress") and m.gap_in_scope(g)]
    assert len(poam["poam-items"]) == max(1, len(open_gaps))


def test_invalid_document_is_never_written(tmp_path, monkeypatch):
    root = _new(tmp_path, "soc2")
    monkeypatch.setattr(oscal, "poam_doc", lambda model, today: {"plan-of-action-and-milestones": {"uuid": "nope"}})
    with pytest.raises(oscal.OscalError, match="poam.json"):
        oscal.export(load(root / "engagement"), tmp_path / "out")
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


# ------------------------------------------------------------------ import
def test_import_catalog_and_profile(tmp_path):
    cat = oscal.import_catalog(FIX / "catalog.json", FIX / "profile.json", "example-x", "Example Baseline", "Example")
    reqs = {r["id"]: r for r in cat["requirements"]}
    assert list(reqs) == ["XA-1", "XA-1(1)", "XB-1"]        # withdrawn XA-2 and out-of-baseline XB-2 left out
    assert reqs["XA-1"]["intent"] == "Review the access policy [frequency]."
    assert reqs["XB-1"]["intent"] == "a. Back up data daily; b. Test restores."
    assert reqs["XA-1(1)"]["oscal_id"] == "xa-1.1"
    assert [g["id"] for g in cat["groups"]] == ["xa", "xb"]


def test_imported_framework_runs_end_to_end(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["oscal", "import", "--catalog", str(FIX / "catalog.json"), "--profile", str(FIX / "profile.json"),
                     "--id", "example-x", "--name", "Example Baseline", "--short-name", "Example",
                     "--root", str(root)]) == 0
    assert "imported 3 controls in 2 groups" in out.getvalue()
    pb = yaml.safe_load((root / "frameworks" / "example-x" / "playbook.yaml").read_text())
    assert pb["terms"]["system"] == "Example scoped system"
    _new(tmp_path, "example-x")
    edir = root / "engagement"
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(edir), "validate"]) == 0
        assert main(["--engagement", str(edir), "oscal", "export", "--out", str(tmp_path / "o")]) == 0
    ssp = json.loads((tmp_path / "o" / "ssp.json").read_text())["system-security-plan"]
    assert {r["control-id"] for r in ssp["control-implementation"]["implemented-requirements"]} == {"xa-1", "xa-1.1", "xb-1"}
    # a second import keeps the playbook the client edited, and needs --force
    with contextlib.redirect_stderr(io.StringIO()):
        assert main(["oscal", "import", "--catalog", str(FIX / "catalog.json"), "--id", "example-x",
                     "--name", "Example", "--root", str(root)]) == 1


def test_import_refuses_bad_input(tmp_path):
    with pytest.raises(oscal.OscalError, match="built-in"):
        oscal.write_framework(tmp_path, oscal.import_catalog(FIX / "catalog.json", None, "soc2", "x"))
    with pytest.raises(oscal.OscalError, match="--id"):
        oscal.import_catalog(FIX / "catalog.json", None, "../evil", "x")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"catalog": {"uuid": "not-a-uuid"}}))
    with pytest.raises(oscal.OscalError, match="not valid OSCAL"):
        oscal.import_catalog(bad, None, "example-y", "x")
    with pytest.raises(oscal.OscalError, match="not an OSCAL catalog"):
        oscal.import_catalog(FIX / "profile.json", None, "example-y", "x")


def _profile(tmp_path, imp, **extra):
    d = json.loads((FIX / "profile.json").read_text())
    d["profile"]["imports"] = [{"href": "catalog.json", **imp}]
    d["profile"].update(extra)
    p = tmp_path / "p.json"
    p.write_text(json.dumps(d))
    return p


def test_profile_selection(tmp_path):
    ids = lambda imp, **kw: [r["id"] for r in oscal.import_catalog(FIX / "catalog.json", _profile(tmp_path, imp, **kw),
                                                                     "example-x", "x")["requirements"]]
    assert ids({"include-all": {}, "exclude-controls": [{"with-ids": ["xa-1"]}]}) == ["XA-1(1)", "XB-1", "XB-2"]
    assert ids({"include-controls": [{"with-ids": ["xa-1"], "with-child-controls": "yes"}]}) == ["XA-1", "XA-1(1)"]
    assert ids({"include-controls": [{"matching": [{"pattern": "xb-*"}]}]}) == ["XB-1", "XB-2"]
    with pytest.raises(oscal.OscalError, match="doesn't have"):
        ids({"include-controls": [{"with-ids": ["zz-9"]}]})
    with pytest.raises(oscal.OscalError, match="resolved catalog"):
        ids({"include-all": {}}, modify={"set-parameters": [{"param-id": "xa-01_odp", "values": ["yearly"]}]})


def test_nested_groups_without_ids_and_selection_parameters(tmp_path):
    d = json.loads((FIX / "catalog.json").read_text())
    xa, xb = d["catalog"]["groups"]
    del xb["id"]
    d["catalog"]["groups"] = [{"id": "fam", "title": "Families", "groups": [xa, xb]}]   # a group holds groups or controls
    xa["controls"][0]["params"] = [{"id": "xa-01_odp", "select": {"how-many": "one-or-more",
                                                                     "choice": ["yearly", "after a change"]}}]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(d))
    cat = oscal.import_catalog(p, None, "example-x", "x")
    groups = {g["id"]: g["title"] for g in cat["groups"]}
    xb1 = next(r for r in cat["requirements"] if r["id"] == "XB-1")
    assert groups[xb1["group"]] == "Families: Example Backup" and xb1["group"] == "group-1-2"
    xa = next(r for r in cat["requirements"] if r["id"] == "XA-1")
    assert xa["intent"] == "Review the access policy [selection (one or more of): yearly; after a change]."


def test_hostile_json_is_refused_not_crashed(tmp_path):
    deep = tmp_path / "deep.json"
    deep.write_text('{"catalog": ' + "[" * 100_000 + "]" * 100_000 + "}")
    with pytest.raises(oscal.OscalError, match="nested too deeply|not valid"):
        oscal.import_catalog(deep, None, "example-y", "x")
    assert main(["oscal", "validate", str(deep)]) == 1


def test_validate_command(tmp_path, capsys):
    assert main(["oscal", "validate", str(FIX / "catalog.json")]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"catalog": {}}')
    assert main(["oscal", "validate", str(bad)]) == 1
    assert "error(s)" in capsys.readouterr().out
