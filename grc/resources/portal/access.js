// Shared by the GRC Workers (client site, auditor room, executive dashboard): the Cloudflare Access login check
// and the security headers every response carries. Every request must carry a valid Access token; the Worker
// verifies it itself (signature against the team's keys, audience, issuer, expiry), so a Worker accidentally
// left without an Access application refuses everyone instead of opening up.

const SKEW = 60;                 // seconds of clock tolerance on token times

export const SECURITY_HEADERS = {
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; " +
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Strict-Transport-Security": "max-age=31536000",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cache-Control": "no-store",
};

// ------------------------------------------------------------------ login check (Cloudflare Access)
let certCache = { team: "", keys: new Map(), fetchedAt: 0 };

export function _resetCertCache() {
  certCache = { team: "", keys: new Map(), fetchedAt: 0 };
}

function b64urlBytes(s) {
  if (!/^[A-Za-z0-9_-]*$/.test(s)) throw new Error("bad base64url");
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlJson(s) {
  return JSON.parse(new TextDecoder().decode(b64urlBytes(s)));
}

async function accessKey(team, kid) {
  const now = Date.now();
  if (certCache.team !== team) certCache = { team, keys: new Map(), fetchedAt: 0 };
  if (certCache.keys.has(kid) && now - certCache.fetchedAt < 3600_000) return certCache.keys.get(kid);
  if (now - certCache.fetchedAt < 30_000 && certCache.keys.size) return certCache.keys.get(kid); // don't hammer on unknown kids
  const res = await fetch(`https://${team}.cloudflareaccess.com/cdn-cgi/access/certs`);
  if (!res.ok) throw new Error(`certs ${res.status}`);
  const body = await res.json();
  const keys = new Map();
  for (const jwk of body.keys || []) {
    if (jwk.kty !== "RSA" || !jwk.kid) continue;
    const key = await crypto.subtle.importKey("jwk", { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    keys.set(jwk.kid, key);
  }
  certCache = { team, keys, fetchedAt: now };
  return keys.get(kid);
}

export async function authenticate(request, env) {
  const team = String(env.ACCESS_TEAM || "");
  const aud = String(env.ACCESS_AUD || "");
  if (!/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/.test(team) || !/^[0-9a-f]{64}$/.test(aud)) {
    return { ok: false, status: 503, reason: "This site isn't set up yet: its sign-in settings are missing." };
  }
  const token = request.headers.get("Cf-Access-Jwt-Assertion") || "";
  const parts = token.split(".");
  if (parts.length !== 3) return { ok: false, status: 401, reason: "Sign in through the link your engagement team sent you." };
  try {
    const header = b64urlJson(parts[0]);
    const claims = b64urlJson(parts[1]);
    if (header.alg !== "RS256" || typeof header.kid !== "string") throw new Error("alg");
    const key = await accessKey(team, header.kid);
    if (!key) throw new Error("unknown kid");
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlBytes(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`));
    if (!ok) throw new Error("signature");
    const now = Math.floor(Date.now() / 1000);
    const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (!auds.includes(aud)) throw new Error("aud");
    if (claims.iss !== `https://${team}.cloudflareaccess.com`) throw new Error("iss");
    if (typeof claims.exp !== "number" || claims.exp < now - SKEW) throw new Error("exp");
    if (typeof claims.nbf === "number" && claims.nbf > now + SKEW) throw new Error("nbf");
    const email = String(claims.email || "").toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || email.length > 254) throw new Error("email");
    const domains = String(env.ALLOWED_EMAIL_DOMAINS || "").split(",").map((d) => d.trim().toLowerCase()).filter(Boolean);
    if (domains.length && !domains.includes(email.split("@")[1])) {
      return { ok: false, status: 403, reason: "This email address isn't on the list for this site. Ask your engagement team to add you." };
    }
    return { ok: true, email };
  } catch (err) {
    console.warn("login rejected:", err && err.message);
    return { ok: false, status: 401, reason: "Your sign-in has expired or isn't valid. Reload the page to sign in again." };
  }
}


// ------------------------------------------------------------------ responses
export function withHeaders(res) {
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) res.headers.set(k, v);
  return res;
}

export function json(obj, status = 200) {
  return withHeaders(new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8" } }));
}

export function plain(text, status) {
  return withHeaders(new Response(text, { status, headers: { "Content-Type": "text/plain; charset=utf-8" } }));
}
