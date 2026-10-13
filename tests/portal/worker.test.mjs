// node --test tests/portal/worker.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, copyFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { AUD, REPO, TEAM, env, fakeGitHub, installFetch, loadWorker, makeKeys, mint } from "./harness.mjs";

const W = await loadWorker();
const keys = await makeKeys();
const other = await makeKeys();
const KEY = "0123456789ab";
const ORIGIN = "https://site.example";

const pub = await mkdtemp(join(tmpdir(), "grc-pub-"));
const site = fileURLToPath(new URL("../../grc/resources/portal/site/", import.meta.url));
for (const f of ["index.html", "app.js", "app.css"]) await copyFile(join(site, f), join(pub, f));
await writeFile(join(pub, "portal.json"), JSON.stringify({ frameworks: [{ key: "iso42001", requests: [
  { key: KEY, kind: "Gap", ref: "GAP-02", title: "AI policy", framework: "iso42001", answerable: true },
  { key: "ffffffffffff", kind: "Requirements", ref: "3 without an owner", title: "", framework: "iso42001", answerable: false },
] }] }));

let gh;
function fresh(extra) {
  gh = fakeGitHub();
  installFetch(keys, gh);
  W._resetCertCache();
  return env(pub, extra);
}

async function req(path, { method = "GET", token, body, headers = {}, e } = {}) {
  const h = new Headers(headers);
  if (token !== null) h.set("Cf-Access-Jwt-Assertion", token || (await mint(keys)));
  if (body !== undefined) {
    if (!h.has("Content-Type")) h.set("Content-Type", "application/json");
    if (!h.has("Origin")) h.set("Origin", ORIGIN);
  }
  const r = new Request(ORIGIN + path, { method, headers: h, body: body === undefined ? undefined : (typeof body === "string" ? body : JSON.stringify(body)) });
  return W.default.fetch(r, e || fresh());
}

const good = { key: KEY, answer: "Policy v1.0 is in SharePoint; approved by the CTO.", links: ["https://sharepoint.example/ai-policy"], no_sensitive_data: true };

test("refuses everything when the Access settings are missing (fails closed)", async () => {
  for (const extra of [{ ACCESS_TEAM: "" }, { ACCESS_AUD: "" }, { ACCESS_AUD: "short" }, { ACCESS_TEAM: "Bad Team" }]) {
    const r = await req("/", { e: fresh(extra) });
    assert.equal(r.status, 503);
    assert.match(r.headers.get("Content-Security-Policy"), /default-src 'none'/);
  }
});

test("no token, someone else's key, wrong audience/issuer, expired, alg none -> 401", async () => {
  const now = Math.floor(Date.now() / 1000);
  const bad = [
    null,
    "not.a.jwt",
    await mint(other),
    await mint(keys, { aud: ["b".repeat(64)] }),
    await mint(keys, { iss: "https://evil.cloudflareaccess.com" }),
    await mint(keys, { exp: now - 3600 }),
    await mint(keys, { nbf: now + 3600 }),
    await mint(keys, { email: "not-an-email" }),
    await mint(keys, {}, { alg: "none" }),
    await mint(keys, {}, { kid: "k2" }),
  ];
  for (const token of bad) {
    const r = await req("/api/me", { token });
    assert.equal(r.status, 401, `token ${String(token).slice(0, 30)}`);
  }
  // tampered payload with the original signature
  const t = (await mint(keys)).split(".");
  const p = JSON.parse(Buffer.from(t[1], "base64url"));
  p.email = "mallory@evil.example";
  t[1] = Buffer.from(JSON.stringify(p)).toString("base64url");
  assert.equal((await req("/api/me", { token: t.join(".") })).status, 401);
});

test("valid login: pages served with security headers; /api/me returns the token's email", async () => {
  const r = await req("/");
  assert.equal(r.status, 200);
  assert.match(await r.text(), /app\.js/);
  assert.equal(r.headers.get("X-Frame-Options"), "DENY");
  const me = await (await req("/api/me", { token: await mint(keys, { email: "Jane@Larkspur.Example" }) })).json();
  assert.equal(me.email, "jane@larkspur.example");
});

test("optional email-domain allowlist", async () => {
  const e = fresh({ ALLOWED_EMAIL_DOMAINS: "larkspur.example, other.example" });
  assert.equal((await req("/api/me", { e })).status, 200);
  assert.equal((await req("/api/me", { e, token: await mint(keys, { email: "x@gmail.com" }) })).status, 403);
});

test("certs are cached between requests", async () => {
  const opts = {};
  gh = fakeGitHub();
  installFetch(keys, gh, opts);
  W._resetCertCache();
  const e = env(pub);
  for (let i = 0; i < 3; i++) await req("/api/me", { e });
  assert.equal(opts.certFetches, 1);
});

test("submit: creates a branch, the submission file and a labelled pull request", async () => {
  const e = fresh();
  const r = await req("/api/submit", { method: "POST", body: good, e });
  const body = await r.json();
  assert.equal(r.status, 200, JSON.stringify(body));
  assert.match(body.id, /^SUB-\d{8}-[0-9a-f]{6}$/);
  const branch = `portal/${KEY}/${body.id}`;
  assert.ok(gh.refs[`heads/${branch}`]);
  const file = gh.files[`${branch}:engagement/submissions/${body.id}.yaml`];
  assert.match(file, /status: received/);
  assert.match(file, /submitted_by: "jane@larkspur.example"/);
  assert.match(file, /kind: "Gap"/);          // from portal.json, not from the form
  assert.equal(gh.pulls.length, 1);
  assert.equal(gh.pulls[0].head.ref, branch);
  assert.match(gh.pulls[0].body, /Submitted by: `jane@larkspur.example`/);
  assert.deepEqual(gh.labels["1"], ["client-submission"]);
  const pending = await (await req("/api/pending", { e })).json();
  assert.deepEqual(pending.pending.map((p) => p.key), [KEY]);
});

test("submit: the client cannot choose status, submitter or request details", async () => {
  const e = fresh();
  const r = await req("/api/submit", { method: "POST", e, body: { ...good, status: "accepted", submitted_by: "ceo@larkspur.example", kind: "X", ref: "Y" } });
  const { id } = await r.json();
  const file = Object.values(gh.files)[0];
  assert.match(file, /status: received/);
  assert.doesNotMatch(file, /ceo@|status: accepted|"X"|"Y"/);
  assert.ok(id);
});

test("submit: cross-site and non-JSON requests are refused", async () => {
  assert.equal((await req("/api/submit", { method: "POST", body: good, headers: { Origin: "https://evil.example" } })).status, 403);
  assert.equal((await req("/api/submit", { method: "POST", body: good, headers: { "Sec-Fetch-Site": "cross-site" } })).status, 403);
  assert.equal((await req("/api/submit", { method: "POST", body: "key=x", headers: { "Content-Type": "application/x-www-form-urlencoded" } })).status, 415);
  assert.equal((await req("/api/submit", { method: "GET" })).status, 405);
  assert.equal(gh.pulls.length, 0);
});

test("submit: validation", async () => {
  const cases = [
    [{ ...good, no_sensitive_data: false }, 400],
    [{ ...good, no_sensitive_data: "true" }, 400],
    [{ ...good, key: "../../etc" }, 400],
    [{ ...good, key: "abcdefabcdef" }, 409],          // not an open request
    [{ ...good, key: "ffffffffffff" }, 409],          // not answerable
    [{ ...good, links: ["http://plain.example/x"] }, 400],
    [{ ...good, links: ["javascript:alert(1)"] }, 400],
    [{ ...good, links: ["https://user:pw@x.example/"] }, 400],
    [{ ...good, links: ["https://a.example/ b"] }, 400],
    [{ ...good, links: Array(6).fill("https://a.example/") }, 400],
    [{ ...good, answer: "x".repeat(4001) }, 413],
    [{ ...good, answer: { a: 1 } }, 400],
    [{ ...good, answer: "   ", links: [] }, 400],
  ];
  for (const [body, code] of cases) {
    const r = await req("/api/submit", { method: "POST", body });
    assert.equal(r.status, code, JSON.stringify(body).slice(0, 80));
  }
  assert.equal((await req("/api/submit", { method: "POST", body: "{not json" })).status, 400);
  assert.equal((await req("/api/submit", { method: "POST", body: "x".repeat(17000) })).status, 413);
});

test("submit: text is cleaned so the YAML stays safe", async () => {
  const e = fresh();
  const nasty = 'line1\r\nline2\u2028"quoted" \\ back\u0000\u0007 \u202Ereversed\ud800 emoji 😀\nkey: value\n---\n- list';
  await req("/api/submit", { method: "POST", e, body: { ...good, answer: nasty } });
  const file = Object.values(gh.files)[0];
  const line = file.split("\n").find((l) => l.startsWith("answer: "));
  const val = JSON.parse(line.slice("answer: ".length));
  assert.equal(val, 'line1\nline2\n"quoted" \\ back reversed emoji 😀\nkey: value\n---\n- list');
  assert.equal(file.split("\n").filter((l) => /^[a-z_]+:/.test(l)).length, 8);   // no injected top-level keys
});

test("submit: GitHub failure leaves nothing behind", async () => {
  const e = fresh();
  gh.fail["POST /repos/" + REPO + "/pulls"] = 422;
  const r = await req("/api/submit", { method: "POST", e, body: good });
  assert.equal(r.status, 502);
  assert.equal(gh.deleted.length, 1);
  assert.equal(Object.keys(gh.refs).length, 1);
  assert.doesNotMatch(await r.text(), /forced|token/);
});

test("submit: not connected (no token or repo) -> 503, pending says not connected", async () => {
  const e = fresh({ GITHUB_TOKEN: "" });
  assert.equal((await req("/api/submit", { method: "POST", e, body: good })).status, 503);
  assert.deepEqual(await (await req("/api/pending", { e })).json(), { pending: [], connected: false });
});

test("throttle: too many answers waiting for review", async () => {
  const e = fresh();
  for (let i = 0; i < 15; i++) assert.equal((await req("/api/submit", { method: "POST", e, body: good })).status, 200);
  assert.equal((await req("/api/submit", { method: "POST", e, body: good })).status, 429);   // per person
  const r = await req("/api/submit", { method: "POST", e, body: good, token: await mint(keys, { email: "bob@larkspur.example" }) });
  assert.equal(r.status, 200);
});

test("pending ignores pull requests the site did not make", async () => {
  const e = fresh();
  gh.pulls.push({ number: 9, state: "open", body: "", created_at: "2026-10-01T00:00:00Z", head: { ref: "feature/x", repo: { full_name: REPO } } });
  gh.pulls.push({ number: 10, state: "open", body: "", created_at: "2026-10-01T00:00:00Z", head: { ref: `portal/${KEY}/SUB-20261001-abcdef`, repo: { full_name: "evil/fork" } } });
  const p = await (await req("/api/pending", { e })).json();
  assert.deepEqual(p.pending, []);
});

test("unknown API path -> 404; non-GET page -> 405", async () => {
  assert.equal((await req("/api/nope")).status, 404);
  assert.equal((await req("/", { method: "DELETE" })).status, 405);
});

test("cleanLink / cleanText helpers", () => {
  assert.equal(W.cleanLink("https://x.example/a?b=1#c"), "https://x.example/a?b=1#c");
  assert.equal(W.cleanLink(""), null);
  assert.equal(W.cleanLink("ftp://x"), undefined);
  assert.equal(W.cleanText("a\u202Eb\u2066c", 10), "abc");
  assert.equal(W.cleanText("x".repeat(50), 10).length, 10);
  assert.ok(TEAM && AUD);
});
