// A fake GitHub for the consultant workspace: OAuth token exchange, the user, installations, GraphQL and the
// contents, refs and pulls endpoints the Worker calls. Shared by workspace.test.mjs and the harness.
export function installWorkspaceFake({ login = "dana-lead", push = true, CONTROL, REPO } = {}) {
  const st = { calls: [], pulls: [], files: {}, refs: {}, deleted: [], tokenBody: null };
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url);
    const method = (init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : null;
    const auth = (init.headers && (init.headers.Authorization || init.headers.authorization)) || "";
    st.calls.push(`${method} ${url.host}${url.pathname} ${auth}`);
    const res = (code, obj) => new Response(JSON.stringify(obj), { status: code, headers: { "Content-Type": "application/json" } });
    if (url.host === "github.com" && url.pathname === "/login/oauth/access_token") {
      st.tokenBody = body;
      if (body.code === "forever-code-1") return res(200, { access_token: "ghu_user_token" });
      return body.code === "good-code-123" ? res(200, { access_token: "ghu_user_token", expires_in: 28800 }) : res(200, { error: "bad_verification_code" });
    }
    if (method === "DELETE" && url.pathname.startsWith("/applications/") && auth.startsWith("Basic ")) { st.revoked = body; return new Response(null, { status: 204 }); }
    if (auth !== "Bearer ghu_user_token") return res(401, { message: "Bad credentials" });
    if (url.pathname === "/user") return res(200, { login });
    if (url.pathname === "/user/installations") return res(200, { installations: [{ id: 7 }] });
    if (url.pathname === "/user/installations/7/repositories") return res(200, { repositories: [{ full_name: REPO, permissions: { push } }, { full_name: "acme/readonly", permissions: { push: false } }] });
    if (url.pathname === "/graphql") {
      return res(200, { data: { repository: {
        controls: { entries: [{ name: "A.5.15.yaml", object: { text: CONTROL, byteSize: CONTROL.length } }, { name: "../x.yaml", object: { text: "id: X" } }] },
        engagement: { text: "client: Larch & Finch\nframework: iso27001\n" },
        gaps: { text: "gaps:\n  - id: GAP-01\n    area: Access reviews\n    severity: high\n    status: open\n    due: 2026-12-01\n" },
        owners: { text: "owners:\n  - role: Head of IT\n  - role: CISO\n" },
        evidence: { text: "evidence:\n  - id: EV-001\n    title: Policy\n    type: document\n  - id: EV-002\n    title: Log\n    type: log\n" },
        ref: { target: { oid: "a".repeat(40) } } } } });
    }
    if (method === "GET" && url.pathname === `/repos/${REPO}`) return res(200, { full_name: REPO, permissions: { push } });
    if (method === "GET" && url.pathname === "/repos/acme/readonly") return res(200, { full_name: "acme/readonly", permissions: { push: false } });
    const base = `/repos/${REPO}`;
    if (!url.pathname.startsWith(base)) return res(404, {});
    const rest = url.pathname.slice(base.length);
    if (method === "GET" && rest === "/git/ref/heads/main") return res(200, { object: { sha: "base0" } });
    if (method === "GET" && rest === "/contents/engagement/controls/A.5.15.yaml") return res(200, { sha: "blob1", content: Buffer.from(CONTROL).toString("base64") });
    if (method === "POST" && rest === "/git/refs") { st.refs[body.ref] = body.sha; return res(201, {}); }
    if (method === "DELETE") { st.deleted.push(rest); return new Response(null, { status: 204 }); }
    if (method === "PUT" && rest.startsWith("/contents/")) { st.files[decodeURIComponent(rest.slice(10))] = Buffer.from(body.content, "base64").toString(); st.put = body; return res(201, {}); }
    if (method === "POST" && rest === "/pulls") { const pr = { number: st.pulls.length + 1, html_url: `https://github.com/${REPO}/pull/1`, ...body }; st.pulls.push(pr); return res(201, pr); }
    return res(404, { message: `unhandled ${method} ${rest}` });
  };
  return st;
}

