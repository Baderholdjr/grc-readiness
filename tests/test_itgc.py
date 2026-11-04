"""ITGC tests on GitHub data (fake API): change management and logical access, and workpaper rules."""
import datetime as dt
import json
import re

import yaml

from grc import itgc
from grc import program as P

TODAY = dt.date(2026, 11, 4)


def _pr(n, author, merged, title="Change", body="", labels=(), head=None):
    return {"number": n, "title": title, "body": body, "user": {"login": author}, "merged_at": merged,
            "updated_at": merged or "2026-09-01T00:00:00Z", "merge_commit_sha": f"m{n}",
            "head": {"ref": f"feature-{n}", "sha": head or f"h{n}"}, "labels": [{"name": l} for l in labels],
            "html_url": f"https://github.com/acme/app/pull/{n}"}


PRS = [
    _pr(1, "alice", "2026-07-03T10:00:00Z", "Add login rate limit", "Fixes #41"),
    _pr(2, "bob", "2026-07-10T10:00:00Z", "Update CI", "", head="h2"),
    _pr(3, "carol", "2026-08-01T10:00:00Z", "Hotfix payments", "PAY-12", labels=["hotfix"]),
    _pr(4, "dave", None, "Abandoned"),                                    # closed, never merged
    _pr(5, "erin", "2026-10-02T10:00:00Z", "Outside the period"),
] + [_pr(10 + i, "alice", f"2026-09-{10 + i:02d}T10:00:00Z", f"Routine change {i}", f"#{100 + i}") for i in range(8)]
FILES = {1: ["app/auth.py"], 2: [".github/workflows/ci.yml"], 3: ["app/pay.py"]}
REVIEWS = {
    1: [{"user": {"login": "bob"}, "state": "APPROVED", "submitted_at": "2026-07-03T09:00:00Z", "commit_id": "h1"}],
    2: [{"user": {"login": "bob"}, "state": "APPROVED", "submitted_at": "2026-07-10T09:00:00Z", "commit_id": "h2"}],  # self
    3: [{"user": {"login": "alice"}, "state": "APPROVED", "submitted_at": "2026-08-01T09:00:00Z", "commit_id": "old"}],
}
CHECKS = {"h1": [{"name": "test", "conclusion": "success"}], "h2": [{"name": "test", "conclusion": "failure"}],
          "h3": []}
COMMITS = [{"sha": "m1"}, {"sha": "m2"}, {"sha": "m3"},
           {"sha": "d0000000001", "commit": {"message": "quick fix on main", "committer": {"date": "2026-07-20T00:00:00Z"}},
            "author": {"login": "bob"}, "html_url": "https://github.com/acme/app/commit/d0000000001"},
           {"sha": "b1", "commit": {"message": "branch commit"}}]


def fake(path):
    path = re.sub(r"[?&]per_page=\d+&page=(\d+)", lambda m: "" if m.group(1) == "1" else "&PAGE2", path)
    if "PAGE2" in path:
        return []
    if path.startswith("/pulls?"):
        return PRS
    if m := re.fullmatch(r"/pulls/(\d+)/files", path):
        return [{"filename": f} for f in FILES.get(int(m.group(1)), ["app/x.py"])]
    if m := re.fullmatch(r"/pulls/(\d+)/reviews", path):
        return REVIEWS.get(int(m.group(1)), [])
    if m := re.fullmatch(r"/commits/(\w+)/check-runs", path.split("?")[0]):
        return {"check_runs": CHECKS.get(m.group(1), [{"name": "test", "conclusion": "success"}])}
    if path.startswith("/commits?"):
        return COMMITS
    if m := re.fullmatch(r"/commits/(\w+)/pulls", path):
        return [{"merged_at": "2026-07-01T00:00:00Z", "base": {"ref": "main"}}] if m.group(1) == "b1" else []
    if m := re.fullmatch(r"/commits/(\w+)", path):
        return {"files": [{"filename": "app/main.py"}]}
    if path.startswith("/collaborators"):
        return [{"login": "alice", "role_name": "admin"}, {"login": "bob", "role_name": "write"},
                {"login": "mallory", "role_name": "admin"}]
    if path.startswith("/invitations"):
        return [{"invitee": {"login": "trent"}, "permissions": "write", "created_at": "2026-10-30T00:00:00Z"}]
    raise AssertionError(f"unexpected call {path}")


def _run(tmp_path, **kw):
    src = itgc.Source("acme/app", transport=fake)
    return itgc.run_change(src, "ITGC-CHG-2026Q3", dt.date(2026, 7, 1), dt.date(2026, 9, 30), root=tmp_path, today=TODAY, **kw)


def test_change_population_and_risk_based_sample(tmp_path):
    wp = _run(tmp_path)
    pop = json.loads((tmp_path / "program/itgc/ITGC-CHG-2026Q3/population.json").read_text())
    ids = [i["id"] for i in pop["items"]]
    assert "#4" not in ids and "#5" not in ids                       # never merged / outside the period
    assert "commit:d000000000" in ids and "commit:b1" not in ids      # direct push found; PR branch commit isn't one
    assert wp["population"] == {**wp["population"], "size": 12, "pull_requests": 11, "direct_pushes": 1}
    tested = {s["item"]: s for s in wp["sample"]}
    # every high-risk item is tested: the direct push, the CI change, the hotfix
    assert {"commit:d000000000", "#2", "#3"} <= set(tested)
    assert wp["sampling"]["high_risk"] == 3 and wp["sampling"]["random"] == 3       # 9 low-risk -> 3
    again = _run(tmp_path / "again")
    assert [s["item"] for s in again["sample"]] == [s["item"] for s in wp["sample"]]   # re-performable


def test_change_attributes(tmp_path):
    wp = _run(tmp_path, sample_size=20)
    s = {x["item"]: x["attributes"] for x in wp["sample"]}
    assert all(v["result"] == "pass" for v in s["#1"].values())
    assert s["#2"]["CHG-2"]["result"] == "exception" and "author's own" in s["#2"]["CHG-2"]["note"]
    assert s["#2"]["CHG-3"]["result"] == "not_applicable"
    assert s["#2"]["CHG-4"]["result"] == "exception"                  # failed check
    assert s["#2"]["CHG-5"]["result"] == "exception"
    assert s["#3"]["CHG-2"]["result"] == "pass" and s["#3"]["CHG-3"]["result"] == "exception"   # approved old commit
    assert s["#3"]["CHG-4"]["result"] == "exception"                  # no checks ran
    d = s["commit:d000000000"]
    assert d["CHG-1"]["result"] == "exception" and d["CHG-3"]["result"] == "not_applicable"
    r = wp["results"]["by_attribute"]
    assert r["CHG-3"]["not_applicable"] == 10      # #2, the direct push, and 8 routine PRs nobody reviewed
    md = (tmp_path / "program/itgc/ITGC-CHG-2026Q3/workpaper.md").read_text()
    assert "not applicable" in md
    assert wp["conclusion"] == "not_concluded"                        # automation never concludes


def test_no_ticket_attribute(tmp_path):
    wp = _run(tmp_path, ticket_pattern=None)
    assert [a["id"] for a in wp["attributes"]] == ["CHG-1", "CHG-2", "CHG-3", "CHG-4"]


def test_access_against_approved_list(tmp_path):
    f = tmp_path / itgc.approved_access_path("acme/app")
    f.parent.mkdir(parents=True)
    f.write_text(yaml.safe_dump({"reviewed_by": "CISO", "reviewed_on": "2026-10-01", "approved": [
        {"user": "alice", "permission": "admin", "reason": "owner"}, {"user": "bob", "permission": "read"},
        {"user": "zed", "permission": "write"}]}))
    wp = itgc.run_access(itgc.Source("acme/app", transport=fake), "ITGC-ACC-2026Q4", root=tmp_path, today=TODAY)
    s = {x["item"]: x["attributes"] for x in wp["sample"]}
    assert all(v["result"] == "pass" for v in s["alice"].values())
    assert s["bob"]["ACC-2"]["result"] == "exception"                 # write, approved for read
    assert s["mallory"]["ACC-1"]["result"] == "exception" and s["mallory"]["ACC-3"]["result"] == "exception"
    assert s["trent"]["ACC-1"]["result"] == "exception"               # pending invitation
    assert wp["approved_list"]["approved_but_absent"] == ["zed"]
    assert wp["population"]["admins"] == 2


def test_workpaper_rules(tmp_path):
    root = tmp_path
    _run(root)
    p = root / "program/itgc/ITGC-CHG-2026Q3/workpaper.yaml"

    def edit(**kw):
        d = yaml.safe_load(p.read_text())
        d.update(kw)
        p.write_text(yaml.safe_dump(d, sort_keys=False))
        return [f.code for f in itgc.check(root, TODAY)]

    assert edit() == []
    assert "P405" in [f.code for f in itgc.check(root, TODAY + dt.timedelta(days=40))]
    assert {"P402", "P403"} <= set(edit(conclusion="effective"))     # exceptions, no rationale, no performer
    assert "P402" in edit(conclusion="not_effective", performed_by="Ann", performed_on="2026-11-05")
    c = edit(conclusion="not_effective", findings=["NC-004"], reviewed_by="ann", reviewed_on="2026-11-06")
    assert "P404" in c and "P406" in c                                # self-review; exceptions without notes
    c = edit(reviewed_by="Ben")
    assert "P404" not in c


def test_program_validate_includes_itgc(tmp_path):
    _run(tmp_path)
    assert P.exists(tmp_path)
    p = tmp_path / "program/itgc/ITGC-CHG-2026Q3/workpaper.yaml"
    d = yaml.safe_load(p.read_text())
    d["conclusion"] = "effective"
    p.write_text(yaml.safe_dump(d))
    assert "P402" in [f.code for f in P.validate(P.load_program(tmp_path, today=TODAY))]
