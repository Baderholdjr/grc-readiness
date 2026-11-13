// The second check on every change the client site or the workspace writes: parse the record file as it was and
// as it will be, and refuse unless the ONLY difference is the value the person asked to change, and no evidence
// check has become verified. yamledit.js changes text; this proves what that text now means, so a file laid out
// in an unexpected way (a quoted value carried over lines, a hidden key, a stray continuation line) can't make a
// one-line diff do something else when merged.
import { CORE_SCHEMA, load } from "./js-yaml.mjs";

function parse(text) {
  try {
    return { ok: true, value: load(String(text), { schema: CORE_SCHEMA, json: false }) };
  } catch {
    return { ok: false };
  }
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// every path (a.b.0.c) whose value differs between the two documents
export function changedPaths(a, b, at = "", out = []) {
  const isObj = (x) => x && typeof x === "object";
  if (isObj(a) && isObj(b) && Array.isArray(a) === Array.isArray(b)) {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) changedPaths(a[k], b[k], at ? `${at}.${k}` : k, out);
  } else if (!same(a, b)) {
    out.push(at);
  }
  return out;
}

function verifiedLegs(doc) {
  const t = doc && typeof doc === "object" && doc.test && typeof doc.test === "object" ? doc.test : {};
  return Object.keys(t).filter((k) => t[k] && typeof t[k] === "object" && t[k].status === "verified").sort();
}

// `allowed`: the paths that may change (an exact path, or a prefix ending in "."). Returns null when the edit is
// exactly that, else a short reason.
export function checkEdit(before, after, allowed) {
  const a = parse(before), b = parse(after);
  if (!a.ok) return "the file doesn't read as YAML now";
  if (!b.ok) return "the change wouldn't read as YAML";
  const changed = changedPaths(a.value, b.value);
  if (!changed.length) return "nothing would change";
  const ok = (p) => allowed.some((x) => (x.endsWith(".") ? p.startsWith(x) : p === x));
  const stray = changed.filter((p) => !ok(p));
  if (stray.length) return `it would also change ${stray.slice(0, 3).join(", ")}`;
  const vb = verifiedLegs(a.value), va = verifiedLegs(b.value);
  if (va.some((l) => !vb.includes(l))) return "it would mark a check verified";
  return null;
}

export function parsed(text) {
  const p = parse(text);
  return p.ok ? p.value : null;
}
