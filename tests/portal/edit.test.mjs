// node --test tests/portal/edit.test.mjs : changes proposed from the client site (POST /api/edit) and the
// YAML edits behind them. tests/test_portal_edits.py runs the edits through Python's YAML parser as well.
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { env, fakeGitHub, installFetch, loadWorker, makeKeys, mint } from "./harness.mjs";

const W = await loadWorker();
const Y = await import(new URL("../../grc/resources/portal/yamledit.js", import.meta.url).href);
const keys = await makeKeys();
const ORIGIN = "https://site.example";
const RK = "aaaaaaaaaaaa", OK = "bbbbbbbbbbbb", NOEDIT = "cccccccccccc";

const CONTROL = "# A.5.15 Access control\n# Intent (paraphrased): ...\nid: A.5.15\nowner: Head of Platform\ntest:\n  documented:\n    status: not_started\n    evidence: []\n";
const OWNERS = "# Who is accountable\nowners:\n  - role: Engagement Lead\n    github: [lead]\n  - role: 'Head of Platform'\n    github: []\n  - role: Legal\n    email: old@client.example\n";
const EVIDENCE = "# Evidence index\n\nevidence:\n  - id: EV-001\n    title: Policy\n    type: document\n    location: \"x\"\n    collected: 2026-10-05\n\n  - id: EV-009\n    title: Log\n    type: log\n    location: \"y\"\n    collected: 2026-10-06\n";

const pub = await mkdtemp(join(tmpdir(), "grc-pub-"));
async function portal(edits = ["implementation", "owner_email", "evidence"]) {
  await writeFile(join(pub, "portal.json"), JSON.stringify({ edits,
    owners: { path: "engagement/owners.yaml", roles: [{ key: OK, role: "Head of Platform", email: "" }] },
    frameworks: [{ key: "iso27001", requests: [
      { key: RK, kind: "Requirement", ref: "A.5.15", title: "Access control", framework: "iso27001", answerable: true,
        edit: { path: "engagement/controls/A.5.15.yaml", implementation: "", evidence: true } },
      { key: NOEDIT, kind: "Gap", ref: "GAP-01", title: "x", framework: "iso27001", answerable: true, edit: null },
    ], areas: [{ id: "A.5", requirements: [{ id: "A.5.16", key: "dddddddddddd", title: "Identity",
      edit: { path: "engagement/controls/A.5.16.yaml", implementation: "", evidence: true } }] }] }] }));
}
await portal();

let gh;
function fresh() {
  gh = fakeGitHub();
  gh.base = { "engagement/controls/A.5.15.yaml": CONTROL, "engagement/owners.yaml": OWNERS, "engagement/evidence/index.yaml": EVIDENCE };
  installFetch(keys, gh);
  W._resetCertCache();
  W._resetState();
  return env(pub);
}

async function post(body, { email = "dana@client.example", headers = {} } = {}) {
  const h = new Headers({ "Content-Type": "application/json", Origin: ORIGIN, ...headers });
  h.set("Cf-Access-Jwt-Assertion", await mint(keys, { email }));
  return W.default.fetch(new Request(ORIGIN + "/api/edit", { method: "POST", headers: h, body: JSON.stringify(body) }), fresh());
}

const branchFile = (path) => Object.entries(gh.files).find(([k]) => k.endsWith(":" + path));

test("implementation: one line changes in the control file, plus a submission saying who", async () => {
  const r = await post({ kind: "implementation", key: RK, value: "Okta SSO with quarterly \"access\" reviews:\n- HR feed", no_sensitive_data: true });
  assert.equal(r.status, 200, await r.clone().text());
  const [k, text] = branchFile("engagement/controls/A.5.15.yaml");
  assert.match(k, /^portal\/aaaaaaaaaaaa\/SUB-\d{8}-[0-9a-f]{6}:/);
  assert.equal(text, CONTROL.replace("owner: Head of Platform\n", 'owner: Head of Platform\nimplementation: "Okta SSO with quarterly \\"access\\" reviews:\\n- HR feed"\n'));
  assert.equal(gh.puts[0].sha, "blob-engagement/controls/A.5.15.yaml");     // written over what was read
  const [, sub] = Object.entries(gh.files).find(([k2]) => k2.includes("engagement/submissions/"));
  assert.match(sub, /submitted_by: "dana@client.example"/);
  assert.match(sub, /change:\n  kind: "implementation"\n  file: "engagement\/controls\/A.5.15.yaml"\n  target: "A.5.15"/);
  assert.match(sub, /status: received\n$/);
  assert.match(gh.pulls[0].title, /^Client change: implementation statement for A\.5\.15/);
  assert.deepEqual(gh.labels["1"], ["client-submission"]);
});

test("a requirement from the Progress page can be changed too", async () => {
  gh = null;
  const e = fresh();
  gh.base["engagement/controls/A.5.16.yaml"] = CONTROL.replace(/A\.5\.15/g, "A.5.16");
  const h = new Headers({ "Content-Type": "application/json", Origin: ORIGIN, "Cf-Access-Jwt-Assertion": await mint(keys) });
  const r = await W.default.fetch(new Request(ORIGIN + "/api/edit", { method: "POST", headers: h,
    body: JSON.stringify({ kind: "implementation", key: "dddddddddddd", value: "SSO", no_sensitive_data: true }) }), e);
  assert.equal(r.status, 200, await r.clone().text());
  assert.match(branchFile("engagement/controls/A.5.16.yaml")[1], /implementation: "SSO"/);
});

test("owner email: set on the matching role only", async () => {
  const r = await post({ kind: "owner_email", key: OK, value: "Pat@Client.example", no_sensitive_data: true });
  assert.equal(r.status, 200, await r.clone().text());
  const [, text] = branchFile("engagement/owners.yaml");
  assert.equal(text, OWNERS.replace("  - role: 'Head of Platform'\n", "  - role: 'Head of Platform'\n    email: \"pat@client.example\"\n"));
});

test("evidence: a new item at the end with the next id, linked to the requirement, not reviewed", async () => {
  const r = await post({ kind: "evidence", key: RK, title: "Access review Q3", type: "record", link: "https://drive.example.com/q3", no_sensitive_data: true });
  assert.equal(r.status, 200, await r.clone().text());
  const [, text] = branchFile("engagement/evidence/index.yaml");
  assert.ok(text.startsWith(EVIDENCE));
  const added = text.slice(EVIDENCE.length);
  assert.match(added, /^\n  - id: EV-010\n    title: "Access review Q3"\n    type: "record"\n    location: "https:\/\/drive.example.com\/q3"\n    collected: "\d{4}-\d{2}-\d{2}"\n    notes: "Added from the client site by dana@client.example on \d{4}-\d{2}-\d{2}; not reviewed yet."\n    requirements: \["A.5.15"\]\n$/);
});

test("the browser never chooses the file, and only allowed changes on allowed targets go through", async () => {
  let r = await post({ kind: "implementation", key: NOEDIT, value: "x", no_sensitive_data: true, path: "engagement/gaps.yaml" });
  assert.equal(r.status, 409);
  r = await post({ kind: "owner_email", key: RK, value: "a@b.example", no_sensitive_data: true });     // a requirement key isn't a role
  assert.equal(r.status, 409);
  r = await post({ kind: "status", key: RK, value: "verified", no_sensitive_data: true });
  assert.equal(r.status, 400);
  await portal(["evidence"]);                                       // the engagement narrowed what clients may change
  r = await post({ kind: "implementation", key: RK, value: "x", no_sensitive_data: true });
  assert.equal(r.status, 409);
  await portal();
  assert.equal(gh.pulls.length, 0);
});

test("validation", async () => {
  const bad = [
    [{ kind: "implementation", key: RK, value: "x" }, /no patient or personal data/],
    [{ kind: "implementation", key: RK, value: "   ", no_sensitive_data: true }, /Write how/],
    [{ kind: "implementation", key: RK, value: "x".repeat(4001), no_sensitive_data: true }, /under 4,000/],
    [{ kind: "owner_email", key: OK, value: "not an email", no_sensitive_data: true }, /email address/],
    [{ kind: "owner_email", key: OK, value: "a\"b@x.example", no_sensitive_data: true }, /email address/],
    [{ kind: "evidence", key: RK, title: "t", type: "test", link: "https://x.example", no_sensitive_data: true }, /what kind/],
    [{ kind: "evidence", key: RK, title: "t", type: "record", link: "http://x.example", no_sensitive_data: true }, /https/],
    [{ kind: "evidence", key: RK, title: "", type: "record", link: "https://x.example", no_sensitive_data: true }, /title/],
    [{ kind: "implementation", key: "../../x", value: "x", no_sensitive_data: true }, /Unknown request/],
  ];
  for (const [body, msg] of bad) {
    const r = await post(body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.match((await r.json()).error, msg);
  }
  const x = await post({ kind: "implementation", key: RK, value: "x", no_sensitive_data: true }, { headers: { Origin: "https://evil.example" } });
  assert.equal(x.status, 403);
});

test("no change, or a file laid out differently: refused, nothing left behind", async () => {
  await post({ kind: "implementation", key: RK, value: "Okta", no_sensitive_data: true });
  gh.base["engagement/controls/A.5.15.yaml"] = CONTROL.replace("owner: Head of Platform\n", 'owner: Head of Platform\nimplementation: "Okta"\n');
  let r = await W.default.fetch(new Request(ORIGIN + "/api/edit", { method: "POST",
    headers: { "Content-Type": "application/json", Origin: ORIGIN, "Cf-Access-Jwt-Assertion": await mint(keys, { email: "z@client.example" }) },
    body: JSON.stringify({ kind: "implementation", key: RK, value: "Okta", no_sensitive_data: true }) }), (() => { const e = env(pub); W._resetState(); return e; })());
  assert.equal(r.status, 409);
  const before = gh.pulls.length;
  gh.base["engagement/evidence/index.yaml"] = "evidence:\n  - id: EV-001\n    title: x\n    type: log\n    location: y\n    collected: 2026-01-01\nother: 1\n";
  r = await W.default.fetch(new Request(ORIGIN + "/api/edit", { method: "POST",
    headers: { "Content-Type": "application/json", Origin: ORIGIN, "Cf-Access-Jwt-Assertion": await mint(keys, { email: "y@client.example" }) },
    body: JSON.stringify({ kind: "evidence", key: RK, title: "t", type: "log", link: "https://x.example", no_sensitive_data: true }) }), (() => { const e = env(pub); W._resetState(); return e; })());
  assert.equal(r.status, 409);
  assert.match((await r.json()).error, /engagement team/);
  assert.equal(gh.pulls.length, before);
});

test("a GitHub failure after the branch exists removes the branch", async () => {
  const e = fresh();
  gh.fail["POST /repos/acme/client-repo/pulls"] = 500;
  const h = new Headers({ "Content-Type": "application/json", Origin: ORIGIN, "Cf-Access-Jwt-Assertion": await mint(keys) });
  const r = await W.default.fetch(new Request(ORIGIN + "/api/edit", { method: "POST", headers: h,
    body: JSON.stringify({ kind: "implementation", key: RK, value: "x", no_sensitive_data: true }) }), e);
  assert.equal(r.status, 502);
  assert.equal(gh.deleted.length, 1);
});

test("yamledit: block scalars, comments and quoting", () => {
  const block = "id: X\nowner: A\nimplementation: |\n  line one\n\n  line two\n# keep me\ntest:\n  documented: {}\n";
  assert.equal(Y.setImplementation(block, "new"), 'id: X\nowner: A\nimplementation: "new"\n# keep me\ntest:\n  documented: {}\n');
  assert.equal(Y.setImplementation("id: X\ntest: {}\n", "n"), 'id: X\nimplementation: "n"\ntest: {}\n');
  assert.throws(() => Y.setImplementation("owners: []\n", "n"), Y.EditError);
  assert.throws(() => Y.setOwnerEmail(OWNERS, "Nobody", "a@b.example"), Y.EditError);
  assert.throws(() => Y.setOwnerEmail(OWNERS + "  - role: Legal\n", "Legal", "a@b.example"), /twice/);
  assert.equal(Y.nextEvidenceId("evidence: []\n"), "EV-001");
  assert.equal(Y.addEvidence("evidence: []\n", { title: "t" }).text, 'evidence:\n\n  - id: EV-001\n    title: "t"\n');
  assert.equal(Y.scalar("'it''s'"), "it's");
  assert.equal(Y.scalar('"a\\"b" # c'), 'a"b');
});
