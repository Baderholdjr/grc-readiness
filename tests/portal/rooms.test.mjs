// node --test tests/portal/rooms.test.mjs : the read-only rooms Worker (auditor room, executive dashboard)
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AUD, TEAM, assets, fakeGitHub, installFetch, loadWorker, makeKeys, mint } from "./harness.mjs";

const W = await loadWorker("rooms/worker.js");
const keys = await makeKeys();
const other = await makeKeys();

const pub = await mkdtemp(join(tmpdir(), "grc-room-"));
await writeFile(join(pub, "index.html"), "<!doctype html><title>room</title>");
await writeFile(join(pub, "data.json"), "{}");
await mkdir(join(pub, "files", "pkg"), { recursive: true });
await writeFile(join(pub, "files", "pkg", "brief.html"), "<script>alert(1)</script>");

const today = new Date().toISOString().slice(0, 10);
const day = (n) => new Date(Date.now() + n * 86400_000).toISOString().slice(0, 10);

function env(extra = {}) {
  installFetch(keys, fakeGitHub());
  W._resetCertCache();
  return { ROOM: "auditor", ACCESS_TEAM: TEAM, ACCESS_AUD: AUD, ALLOWED_EMAIL_DOMAINS: "", AUDITORS: "ann@audit.example, bo@audit.example",
    ROOM_OPENS: day(-1), ROOM_CLOSES: day(1), ASSETS: assets(pub), ...extra };
}

async function get(path, e, { email = "ann@audit.example", token, method = "GET" } = {}) {
  const headers = new Headers();
  const t = token === undefined ? await mint(keys, { email }) : token;
  if (t) headers.set("Cf-Access-Jwt-Assertion", t);
  return W.default.fetch(new Request(`https://room.example${path}`, { method, headers }), e);
}

test("a named auditor inside the window gets the page, with no-store and the security headers", async () => {
  const r = await get("/", env());
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Cache-Control"), "private, no-store");
  assert.match(r.headers.get("Content-Security-Policy"), /script-src 'self'/);
  const me = await (await get("/api/me", env())).json();
  assert.equal(me.email, "ann@audit.example");
  assert.equal(me.room, "auditor");
});

test("no login, a forged login, or another audience: refused", async () => {
  assert.equal((await get("/", env(), { token: "" })).status, 401);
  assert.equal((await get("/", env(), { token: await mint(other, { email: "ann@audit.example" }) })).status, 401);
  assert.equal((await get("/", env(), { token: await mint(keys, { email: "ann@audit.example", aud: ["b".repeat(64)] }) })).status, 401);
  assert.equal((await get("/files/pkg/brief.html", env(), { token: "" })).status, 401);
});

test("someone Access let in who isn't a named auditor: refused", async () => {
  const r = await get("/", env(), { email: "eve@audit.example" });
  assert.equal(r.status, 403);
  assert.match(await r.text(), /isn't on the list of auditors/);
  assert.equal((await get("/files/pkg/brief.html", env(), { email: "eve@audit.example" })).status, 403);
});

test("the room is shut before it opens and after it closes", async () => {
  let r = await get("/", env({ ROOM_OPENS: day(1), ROOM_CLOSES: day(5) }));
  assert.equal(r.status, 403);
  assert.match(await r.text(), /opens on/);
  r = await get("/api/me", env({ ROOM_OPENS: day(-9), ROOM_CLOSES: day(-1) }));
  assert.equal(r.status, 403);
  assert.match((await r.json()).error, /closed on/);
  assert.equal((await get("/", env({ ROOM_OPENS: today, ROOM_CLOSES: today }))).status, 200);   // both ends inclusive
});

test("missing room settings fail closed", async () => {
  for (const extra of [{ ROOM: "" }, { ROOM: "staff" }, { AUDITORS: "" }, { ROOM_OPENS: "soon" }, { ACCESS_AUD: "" }]) {
    const r = await get("/", env(extra));
    assert.ok([401, 403, 503].includes(r.status) && r.status !== 200, JSON.stringify(extra));
    assert.equal(r.status === 200, false);
  }
  assert.equal((await get("/", env({ ROOM: "" }))).status, 503);
});

test("files download, never render in the room's origin", async () => {
  const r = await get("/files/pkg/brief.html", env());
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Content-Disposition"), "attachment");
  assert.equal(r.headers.get("Content-Type"), "application/octet-stream");
  assert.equal(r.headers.get("X-Content-Type-Options"), "nosniff");
});

test("the rooms are read only", async () => {
  for (const m of ["POST", "PUT", "DELETE", "PATCH"]) {
    assert.equal((await get("/api/me", env(), { method: m })).status, 405, m);
    assert.equal((await get("/", env(), { method: m })).status, 405, m);
  }
});

test("the executive dashboard: any Access-approved person, no date window, and no files", async () => {
  const e = env({ ROOM: "executive", AUDITORS: "", ROOM_OPENS: "", ROOM_CLOSES: "" });
  assert.equal((await get("/", e, { email: "ceo@client.example" })).status, 200);
  assert.equal((await get("/data.json", e, { email: "ceo@client.example" })).status, 200);
  assert.equal((await get("/files/pkg/brief.html", e, { email: "ceo@client.example" })).status, 404);
  const domain = env({ ROOM: "executive", ALLOWED_EMAIL_DOMAINS: "client.example" });
  assert.equal((await get("/", domain, { email: "ceo@elsewhere.example" })).status, 403);
});

test("roomCheck compares whole days in UTC", () => {
  const e = { ROOM: "auditor", AUDITORS: "a@x.example", ROOM_OPENS: "2027-01-10", ROOM_CLOSES: "2027-01-20" };
  assert.equal(W.roomCheck(e, "a@x.example", new Date("2027-01-09T23:59:59Z")).ok, false);
  assert.equal(W.roomCheck(e, "a@x.example", new Date("2027-01-10T00:00:00Z")).ok, true);
  assert.equal(W.roomCheck(e, "a@x.example", new Date("2027-01-20T23:59:59Z")).ok, true);
  assert.equal(W.roomCheck(e, "a@x.example", new Date("2027-01-21T00:00:00Z")).ok, false);
  assert.equal(W.roomCheck(e, "A@X.EXAMPLE".toLowerCase(), new Date("2027-01-15T00:00:00Z")).ok, true);
});
