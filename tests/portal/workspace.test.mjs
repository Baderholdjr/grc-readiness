// node --test tests/portal/workspace.test.mjs : the consultant workspace Worker (GitHub sign-in, record, changes)
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { assets, loadWorker } from "./harness.mjs";
import { installWorkspaceFake } from "./wsfake.mjs";

const W = await loadWorker("workspace/worker.js");
const ORIGIN = "https://ws.example";
const REPO = "acme/test-larch-grc";
const pub = await mkdtemp(join(tmpdir(), "grc-ws-"));
await writeFile(join(pub, "index.html"), "<!doctype html><title>ws</title>");

const CONTROL = "# A.5.15 Access control\n# Intent (paraphrased): ...\nid: A.5.15\nowner: Head of IT\ntest:\n  documented:\n    status: verified\n    evidence: [\"EV-001\"]\n  implemented:\n    status: not_started\n    evidence: []\n  evidenced:\n    status: not_started\n    evidence: []\n  tested:\n    status: not_started\n    evidence: []\n";

function env(extra = {}) {
  return { GITHUB_CLIENT_ID: "Iv23liEXAMPLE0001", GITHUB_CLIENT_SECRET: "test-secret-not-real", SESSION_KEY: "k".repeat(40),
    CONSULTANTS: "Dana-Lead,sam", BASE_BRANCH: "main", ASSETS: assets(pub), ...extra };
}

let gh;
const fakeGitHub = (opts) => installWorkspaceFake({ ...opts, CONTROL, REPO });

const cookieOf = (res, name) => (res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get("Set-Cookie")]).map((c) => c && c.split(";")[0]).find((c) => c && c.startsWith(name + "="));

async function signIn(e = env(), opts) {
  gh = fakeGitHub(opts);
  const start = await W.default.fetch(new Request(`${ORIGIN}/auth/login`), e);
  const to = new URL(start.headers.get("Location"));
  const oauth = cookieOf(start, "__Host-ws_oauth");
  const cb = await W.default.fetch(new Request(`${ORIGIN}/auth/callback?code=good-code-123&state=${to.searchParams.get("state")}`, { headers: { Cookie: oauth } }), e);
  return { start, to, cb, session: cookieOf(cb, "__Host-ws_session") };
}

async function call(path, session, { method = "GET", body, origin = ORIGIN } = {}) {
  const headers = new Headers({ Cookie: session || "" });
  if (body !== undefined) { headers.set("Content-Type", "application/json"); headers.set("Origin", origin); }
  return W.default.fetch(new Request(ORIGIN + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }), env());
}

test("not configured: refuses everything", async () => {
  for (const extra of [{ GITHUB_CLIENT_SECRET: "" }, { SESSION_KEY: "short" }, { CONSULTANTS: "" }, { GITHUB_CLIENT_ID: "x" }]) {
    const r = await W.default.fetch(new Request(`${ORIGIN}/auth/login`), env(extra));
    assert.equal(r.status, 503, JSON.stringify(extra));
  }
});

test("sign-in: state and PKCE, the code exchanged with the verifier, a sealed Strict session cookie", async () => {
  const { start, to, cb, session } = await signIn();
  assert.equal(start.status, 302);
  assert.equal(to.origin + to.pathname, "https://github.com/login/oauth/authorize");
  assert.equal(to.searchParams.get("code_challenge_method"), "S256");
  assert.equal(to.searchParams.get("redirect_uri"), `${ORIGIN}/auth/callback`);
  assert.match(start.headers.get("Set-Cookie"), /__Host-ws_oauth=.+; Path=\/; HttpOnly; Secure; SameSite=Lax; Max-Age=600/);
  assert.equal(cb.status, 200);
  assert.ok(session && !session.includes("ghu_user_token"));            // the token never appears in clear
  assert.match(cb.headers.getSetCookie().join("\n"), /__Host-ws_session=.+; HttpOnly; Secure; SameSite=Strict/);
  const v = gh.tokenBody.code_verifier;
  const digest = Buffer.from(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v))).toString("base64url");
  assert.equal(digest, to.searchParams.get("code_challenge"));             // the verifier matches the challenge sent
  const me = await (await call("/api/me", session)).json();
  assert.equal(me.login, "dana-lead");
});

test("sign-in refused: wrong state, no cookie, bad code, or not a listed consultant", async () => {
  gh = fakeGitHub();
  const start = await W.default.fetch(new Request(`${ORIGIN}/auth/login`), env());
  const oauth = cookieOf(start, "__Host-ws_oauth");
  const state = new URL(start.headers.get("Location")).searchParams.get("state");
  for (const [q, cookie] of [[`code=good-code-123&state=wrong`, oauth], [`code=good-code-123&state=${state}`, ""], [`code=bad-code-456&state=${state}`, oauth]]) {
    const r = await W.default.fetch(new Request(`${ORIGIN}/auth/callback?${q}`, { headers: { Cookie: cookie } }), env());
    assert.equal(r.status, 400, q);
    assert.equal(cookieOf(r, "__Host-ws_session"), undefined);
  }
  const { cb, session } = await signIn(env(), { login: "mallory" });
  assert.equal(cb.status, 400);
  assert.equal(session, undefined);
});

test("the API needs a valid, unexpired session from this key, for a listed consultant", async () => {
  assert.equal((await call("/api/me", "")).status, 401);
  const { session } = await signIn();
  const tampered = session.slice(0, -4) + (session.endsWith("AAAA") ? "BBBB" : "AAAA");
  assert.equal((await call("/api/me", tampered)).status, 401);
  const other = await W.default.fetch(new Request(`${ORIGIN}/api/me`, { headers: { Cookie: session } }), env({ SESSION_KEY: "z".repeat(40) }));
  assert.equal(other.status, 401);
  const removed = await W.default.fetch(new Request(`${ORIGIN}/api/me`, { headers: { Cookie: session } }), env({ CONSULTANTS: "sam" }));
  assert.equal(removed.status, 401);                                       // taken off the list: out at once
  const expired = await W.seal(env(), "session", { token: "ghu_user_token", login: "dana-lead", exp: Date.now() - 1 });
  assert.equal((await call("/api/me", `__Host-ws_session=${expired}`)).status, 401);
});

test("engagements: only repositories the consultant can push to; the record read without its paths trusted", async () => {
  const { session } = await signIn();
  assert.deepEqual((await (await call("/api/engagements", session)).json()).repos, [REPO]);
  assert.equal((await call(`/api/engagement?repo=acme/readonly`, session)).status, 403);
  const v = await (await call(`/api/engagement?repo=${REPO}`, session)).json();
  assert.equal(v.client, "Larch & Finch");
  assert.deepEqual(v.requirements.map((r) => [r.id, r.title, r.path]), [["A.5.15", "Access control", "engagement/controls/A.5.15.yaml"]]);
  assert.equal(v.requirements[0].legs.documented.status, "verified");
  assert.deepEqual(v.owners, ["Head of IT", "CISO"]);
});

test("a change becomes a pull request with the consultant's own token", async () => {
  const { session } = await signIn();
  const r = await call("/api/change", session, { method: "POST", body: { repo: REPO, requirement: "A.5.15", field: "status", leg: "implemented", value: "claimed" } });
  assert.equal(r.status, 200, await r.clone().text());
  assert.equal(gh.files["engagement/controls/A.5.15.yaml"], CONTROL.replace("  implemented:\n    status: not_started", '  implemented:\n    status: "claimed"'));
  assert.equal(gh.put.sha, "blob1");
  assert.match(Object.keys(gh.refs)[0], /^refs\/heads\/workspace\/dana-lead\/\d{8}T\d{6}Z-[A-Za-z0-9_-]{4}$/);
  assert.match(gh.pulls[0].title, /^Workspace: implemented check of A\.5\.15: claimed/);
  assert.ok(gh.calls.filter((c) => c.includes("api.github.com/repos")).every((c) => c.endsWith("Bearer ghu_user_token")));
});

test("what a change may not do", async () => {
  const { session } = await signIn();
  const bad = [
    [{ requirement: "A.5.15", field: "status", leg: "documented", value: "verified" }, 400, /reviewer/],
    [{ requirement: "A.5.15", field: "owner", value: "Someone New" }, 400, /owner roles/],
    [{ requirement: "A.5.15", field: "evidence", leg: "tested", value: ["EV-999"] }, 400, /evidence index/],
    [{ requirement: "A.9.99", field: "implementation", value: "x" }, 400, /isn't in the record/],
    [{ requirement: "A.5.15", field: "applicable", value: false }, 400, /can't be changed/],
    [{ requirement: "A.5.15", field: "path", value: "engagement/gaps.yaml" }, 400, /can't be changed/],
  ];
  for (const [b, code, msg] of bad) {
    const r = await call("/api/change", session, { method: "POST", body: { repo: REPO, ...b } });
    assert.equal(r.status, code, JSON.stringify(b));
    assert.match((await r.json()).error, msg);
  }
  const x = await call("/api/change", session, { method: "POST", origin: "https://evil.example", body: { repo: REPO, requirement: "A.5.15", field: "implementation", value: "x" } });
  assert.equal(x.status, 403);
  const ro = await call("/api/change", session, { method: "POST", body: { repo: "acme/readonly", requirement: "A.5.15", field: "implementation", value: "x" } });
  assert.equal(ro.status, 403);
  assert.equal(gh.pulls.length, 0);
});

test("evidence and owner changes, and sign-out", async () => {
  const { session } = await signIn();
  let r = await call("/api/change", session, { method: "POST", body: { repo: REPO, requirement: "A.5.15", field: "evidence", leg: "tested", value: ["EV-002", "EV-001"] } });
  assert.equal(r.status, 200);
  assert.match(gh.files["engagement/controls/A.5.15.yaml"], /  tested:\n    status: not_started\n    evidence: \["EV-002", "EV-001"\]\n/);
  r = await call("/api/change", session, { method: "POST", body: { repo: REPO, requirement: "A.5.15", field: "owner", value: "CISO" } });
  assert.equal(r.status, 200);
  assert.match(gh.files["engagement/controls/A.5.15.yaml"], /^owner: "CISO"$/m);
  const out = await call("/auth/logout", session, { method: "POST", body: {} });
  assert.match(out.headers.get("Set-Cookie"), /__Host-ws_session=; .*Max-Age=0/);
  assert.deepEqual(gh.revoked, { access_token: "ghu_user_token" });          // revoked at GitHub, not just forgotten
});

test("review cases: verified checks are left alone, hidden keys are caught, tokens must expire", async () => {
  const { session } = await signIn();
  for (const b of [{ field: "evidence", leg: "documented", value: ["EV-002"] }, { field: "note", leg: "documented", value: "x" },
    { field: "status", leg: "documented", value: "claimed" }]) {
    const r = await call("/api/change", session, { method: "POST", body: { repo: REPO, requirement: "A.5.15", ...b } });
    assert.equal(r.status, 400, JSON.stringify(b));
    assert.match((await r.json()).error, /verified/);
  }
  const R = await import(new URL("../../grc/resources/portal/recordcheck.js", import.meta.url).href).catch(() => null);
  const Y = await import(new URL("../../grc/resources/portal/yamledit.js", import.meta.url).href);
  const hidden = 'id: X\ntest:\n  documented:\n    status: not_started\n  implemented:\n    status: not_started\n  evidenced:\n    status: not_started\n  tested:\n    note: "Waiting on the\n    status: verified\n    #"\n';
  assert.throws(() => Y.setLegField(hidden, "tested", "note", "Scan uploaded"), /more than one line/);
  const legLines = 'id: X\ntest:\n  documented:\n    status: not_started\n    evidence:\n    - EV-001\n  implemented: {status: not_started}\n  evidenced:\n    status: not_started\n  tested:\n    status: not_started\n';
  assert.throws(() => Y.setLegField(legLines, "documented", "note", "x"), /more than one line/);
  if (R) {
    assert.match(R.checkEdit("a: 1\ntest: {t: {status: claimed}}\n", "a: 2\ntest: {t: {status: verified}}\n", ["a", "test.t.status"]), /verified/);
    assert.match(R.checkEdit("a: 1\nb: 1\n", "a: 2\nb: 2\n", ["a"]), /also change b/);
    assert.equal(R.checkEdit("a: 1\nb: 1\n", "a: 2\nb: 1\n", ["a"]), null);
  }
  // a token that never expires (the App setting is off) is refused and revoked
  gh = fakeGitHub();
  const start = await W.default.fetch(new Request(`${ORIGIN}/auth/login`), env());
  const state = new URL(start.headers.get("Location")).searchParams.get("state");
  const cb = await W.default.fetch(new Request(`${ORIGIN}/auth/callback?code=forever-code-1&state=${state}`, { headers: { Cookie: cookieOf(start, "__Host-ws_oauth") } }), env());
  assert.equal(cb.status, 400);
  assert.match(await cb.text(), /Expire user authorization tokens/);
  assert.deepEqual(gh.revoked, { access_token: "ghu_user_token" });
});
