// Test harness for the client-site Worker: runs worker.js in Node with
//   - a fake Cloudflare Access (an RSA key we control, served as the team's certs)
//   - a fake GitHub REST API (in memory)
//   - the static files of a built bundle as the ASSETS binding
//
// Used by worker.test.mjs, and by the end-to-end browser test:
//   node harness.mjs serve <bundle-dir> <port> <email> <state-file>
// serves the bundle as a signed-in user would see it (the "Access edge" adds the login token)
// and writes the fake GitHub's state to <state-file> after every change.
import { createServer } from "node:http";
import { readFile, readdir, copyFile, writeFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, extname, normalize } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

export const TEAM = "larkspur-test";
export const AUD = "a".repeat(64);
export const REPO = "acme/client-repo";

const enc = (o) => Buffer.from(typeof o === "string" ? o : JSON.stringify(o)).toString("base64url");

export async function makeKeys() {
  const pair = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  return { pair, jwk: { kty: "RSA", n: jwk.n, e: jwk.e, kid: "k1", alg: "RS256" } };
}

export async function mint(keys, claims = {}, header = {}) {
  const now = Math.floor(Date.now() / 1000);
  const h = enc({ alg: "RS256", kid: "k1", typ: "JWT", ...header });
  const p = enc({ aud: [AUD], iss: `https://${TEAM}.cloudflareaccess.com`, email: "jane@larkspur.example", iat: now, nbf: now, exp: now + 3600, ...claims });
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", keys.pair.privateKey, new TextEncoder().encode(`${h}.${p}`));
  return `${h}.${p}.${Buffer.from(sig).toString("base64url")}`;
}

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".zip": "application/zip", ".pdf": "application/pdf" };

export function assets(publicDir) {
  return {
    async fetch(req) {
      let path = decodeURIComponent(new URL(req.url).pathname);
      if (path === "/") path = "/index.html";
      const file = normalize(join(publicDir, path));
      if (!file.startsWith(normalize(publicDir))) return new Response("nope", { status: 404 });
      try {
        return new Response(await readFile(file), { headers: { "Content-Type": TYPES[extname(file)] || "application/octet-stream" } });
      } catch {
        return new Response("Not found", { status: 404 });
      }
    },
  };
}

// In-memory GitHub: refs, files and pull requests for one repository.
export function fakeGitHub(repo = REPO) {
  const st = { refs: { "heads/main": "base0sha" }, files: {}, base: {}, pulls: [], labels: {}, deleted: [], calls: [], fail: {}, puts: [] };
  st.handle = async (method, url, body) => {
    const u = new URL(url);
    const path = u.pathname;
    st.calls.push(`${method} ${path}`);
    const base = `/repos/${repo}`;
    const res = (code, obj) => new Response(JSON.stringify(obj), { status: code, headers: { "Content-Type": "application/json" } });
    for (const [k, code] of Object.entries(st.fail)) if (`${method} ${path}`.startsWith(k)) return res(code, { message: "forced" });
    if (!path.startsWith(base + "/")) return res(404, { message: "Not Found" });
    const rest = path.slice(base.length);
    if (method === "GET" && rest.startsWith("/git/ref/heads/")) {
      const sha = st.refs["heads/" + rest.slice("/git/ref/heads/".length)];
      return sha ? res(200, { object: { sha } }) : res(404, {});
    }
    if (method === "POST" && rest === "/git/refs") {
      const name = body.ref.replace(/^refs\//, "");
      if (st.refs[name]) return res(422, { message: "exists" });
      st.refs[name] = body.sha;
      return res(201, {});
    }
    if (method === "DELETE" && rest.startsWith("/git/refs/heads/")) {
      const name = "heads/" + rest.slice("/git/refs/heads/".length);
      delete st.refs[name];
      st.deleted.push(name);
      return new Response(null, { status: 204 });
    }
    if (method === "GET" && rest.startsWith("/contents/")) {
      const p = decodeURIComponent(rest.slice("/contents/".length));
      if (!(p in st.base)) return res(404, { message: "Not Found" });
      return res(200, { type: "file", sha: "blob-" + p, content: Buffer.from(st.base[p], "utf8").toString("base64").replace(/(.{60})/g, "$1\n") });
    }
    if (method === "PUT" && rest.startsWith("/contents/")) {
      st.puts.push({ path: decodeURIComponent(rest.slice("/contents/".length)), sha: body.sha || null, branch: body.branch });
      st.files[`${body.branch}:${decodeURIComponent(rest.slice("/contents/".length))}`] = Buffer.from(body.content, "base64").toString("utf8");
      return res(201, {});
    }
    if (method === "GET" && rest === "/pulls") return res(200, st.pulls.filter((p) => p.state === "open"));
    if (method === "POST" && rest === "/pulls") {
      const pr = { number: st.pulls.length + 1, state: "open", title: body.title, body: body.body, created_at: new Date().toISOString(),
        head: { ref: body.head, repo: { full_name: repo } }, base: { ref: body.base } };
      st.pulls.push(pr);
      return res(201, pr);
    }
    if (method === "POST" && /^\/issues\/\d+\/labels$/.test(rest)) {
      st.labels[rest.split("/")[2]] = body.labels;
      return res(200, []);
    }
    return res(404, { message: `unhandled ${method} ${rest}` });
  };
  return st;
}

export function installFetch(keys, gh, opts = {}) {
  globalThis.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init.method || "GET").toUpperCase();
    if (url === `https://${TEAM}.cloudflareaccess.com/cdn-cgi/access/certs`) {
      opts.certFetches = (opts.certFetches || 0) + 1;
      return new Response(JSON.stringify({ keys: [keys.jwk] }), { headers: { "Content-Type": "application/json" } });
    }
    if (url.startsWith("https://api.github.com/")) {
      if (!String((init.headers || {}).Authorization || "").startsWith("Bearer ")) return new Response("{}", { status: 401 });
      return gh.handle(method, url, init.body ? JSON.parse(init.body) : null);
    }
    throw new Error(`unexpected network call: ${url}`);
  };
}

export async function loadWorker(name = "portal/worker.js") {
  // The Workers are ES modules without a package.json "type": copy them, and the shared access.js they import,
  // into a folder that says "type": "module", as the bundle does for Cloudflare.
  const res = fileURLToPath(new URL("../../grc/resources/", import.meta.url));
  const dir = await mkdtemp(join(tmpdir(), "grc-worker-"));
  await writeFile(join(dir, "package.json"), '{"type": "module"}');
  await copyFile(join(res, "portal", "access.js"), join(dir, "access.js"));
  await copyFile(join(res, "portal", "yamledit.js"), join(dir, "yamledit.js"));
  await copyFile(join(res, "portal", "recordcheck.js"), join(dir, "recordcheck.js"));
  await copyFile(join(res, "workspace", "vendor", "js-yaml.mjs"), join(dir, "js-yaml.mjs"));
  await copyFile(join(res, name), join(dir, "worker.js"));
  return import(pathToFileURL(join(dir, "worker.js")).href);
}

export function env(publicDir, extra = {}) {
  return { ACCESS_TEAM: TEAM, ACCESS_AUD: AUD, GITHUB_REPO: REPO, BASE_BRANCH: "main", GITHUB_TOKEN: "test-token",
    ALLOWED_EMAIL_DOMAINS: "", ASSETS: assets(publicDir), ...extra };
}

// ------------------------------------------------------------------ serve for the browser test
async function serve(bundle, port, email, stateFile, repoRoot) {
  const W = await loadWorker();
  const keys = await makeKeys();
  const gh = fakeGitHub();
  if (repoRoot) {     // the record the site was built from, as the fake GitHub's main branch
    const walk = async (dir, rel) => {
      for (const ent of await readdir(dir, { withFileTypes: true })) {
        if (ent.isDirectory()) await walk(join(dir, ent.name), `${rel}${ent.name}/`);
        else if (ent.name.endsWith(".yaml")) gh.base[`${rel}${ent.name}`] = await readFile(join(dir, ent.name), "utf8");
      }
    };
    await walk(join(repoRoot, "engagement"), "engagement/");
  }
  installFetch(keys, gh);
  const e = env(join(bundle, "public"));
  const save = () => writeFile(stateFile, JSON.stringify({ files: gh.files, pulls: gh.pulls, labels: gh.labels }, null, 1));
  await save();
  createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") headers.set(k, v);
    headers.set("Cf-Access-Jwt-Assertion", await mint(keys, { email }));   // what the Access edge adds
    const url = `http://localhost:${port}${req.url}`;
    const r = new Request(url, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(chunks) });
    const out = await W.default.fetch(r, e);
    const outHeaders = {};
    out.headers.forEach((v, k) => { outHeaders[k] = v; });
    res.writeHead(out.status, outHeaders);
    res.end(Buffer.from(await out.arrayBuffer()));
    if (req.method === "POST") await save();
  }).listen(Number(port), "127.0.0.1", () => console.log(`serving ${bundle} on http://localhost:${port}`));
}

// node harness.mjs serve-room <bundle-dir> <port> <email> : a built room, with the [vars] from its wrangler.toml
async function serveRoom(bundle, port, email) {
  const W = await loadWorker("rooms/worker.js");
  const keys = await makeKeys();
  installFetch(keys, fakeGitHub());
  const vars = {};
  for (const m of (await readFile(join(bundle, "wrangler.toml"), "utf8")).matchAll(/^([A-Z_]+) = (".*")$/gm)) vars[m[1]] = JSON.parse(m[2]);
  const e = { ...vars, ACCESS_TEAM: TEAM, ACCESS_AUD: AUD, ASSETS: assets(join(bundle, "public")) };
  createServer(async (req, res) => {
    const headers = new Headers();
    headers.set("Cf-Access-Jwt-Assertion", await mint(keys, { email }));
    const out = await W.default.fetch(new Request(`http://localhost:${port}${req.url}`, { method: req.method, headers }), e);
    const outHeaders = {};
    out.headers.forEach((v, k) => { outHeaders[k] = v; });
    res.writeHead(out.status, outHeaders);
    res.end(Buffer.from(await out.arrayBuffer()));
  }).listen(Number(port), "127.0.0.1", () => console.log(`serving ${bundle} on http://localhost:${port}`));
}

// node harness.mjs serve-workspace <bundle-dir> <port> <control-yaml-file> : the workspace against a fake GitHub,
// already signed in as dana-lead (the session cookie is set by GET /__test/session)
async function serveWorkspace(bundle, port, controlFile) {
  const W = await loadWorker("workspace/worker.js");
  const { installWorkspaceFake } = await import("./wsfake.mjs");
  const REPO = "acme/test-larch-grc";
  const st = installWorkspaceFake({ CONTROL: await readFile(controlFile, "utf8"), REPO });
  const e = { GITHUB_CLIENT_ID: "Iv23liEXAMPLE0001", GITHUB_CLIENT_SECRET: "test", SESSION_KEY: "k".repeat(40), CONSULTANTS: "dana-lead",
    BASE_BRANCH: "main", ASSETS: assets(join(bundle, "public")) };
  createServer(async (req, res) => {
    if (req.url === "/__test/state") { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify({ pulls: st.pulls, files: st.files })); return; }
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") headers.set(k, v);
    let out;
    if (req.url === "/__test/session") {
      const sealed = await W.seal(e, "session", { token: "ghu_user_token", login: "dana-lead", exp: Date.now() + 3600_000 });
      out = new Response("ok", { headers: { "Set-Cookie": `__Host-ws_session=${sealed}; Path=/; HttpOnly; Secure; SameSite=Strict` } });
    } else {
      // the browser talks plain http to this test server; the Worker sees https, as on Cloudflare
      if (headers.get("origin")) headers.set("origin", `https://localhost:${port}`);
      out = await W.default.fetch(new Request(`https://localhost:${port}${req.url}`, { method: req.method, headers,
        body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(chunks) }), e);
    }
    const outHeaders = {};
    out.headers.forEach((v, k) => { outHeaders[k] = v; });
    const cookies = out.headers.getSetCookie ? out.headers.getSetCookie() : [];
    if (cookies.length) outHeaders["set-cookie"] = cookies;   // Chromium treats http://localhost as secure
    res.writeHead(out.status, outHeaders);
    res.end(Buffer.from(await out.arrayBuffer()));
  }).listen(Number(port), "127.0.0.1", () => console.log(`serving ${bundle} on http://localhost:${port}`));
}

if (process.argv[2] === "serve-workspace") serveWorkspace(process.argv[3], process.argv[4], process.argv[5]);
if (process.argv[2] === "serve") serve(process.argv[3], process.argv[4], process.argv[5], process.argv[6], process.argv[7]);
if (process.argv[2] === "serve-room") serveRoom(process.argv[3], process.argv[4], process.argv[5]);
