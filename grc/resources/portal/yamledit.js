// Small, exact edits to the engagement's YAML files for changes proposed from the client site. Each changes one
// value and leaves every other line, comment and blank line as it was, so the pull request shows the reviewer
// exactly what changed. Values are written as JSON strings, which YAML reads as double-quoted scalars.
// Each function returns the new text, or throws EditError when the file isn't laid out as the engine writes it
// (then nothing is changed). CI validates the record again on the pull request.

export class EditError extends Error {}

const q = (s) => JSON.stringify(String(s));

// The file's own line endings and final newline are kept, so the pull request shows only the changed lines.
function lines(text) {
  const raw = String(text);
  const eol = /\r\n/.test(raw) ? "\r\n" : "\n";
  const t = raw.replace(/\r\n?/g, "\n");
  const final = t.endsWith("\n");
  const ls = (final ? t.slice(0, -1) : t).split("\n");
  ls.eol = eol;
  ls.final = final || t === "";
  return ls;
}

function join(ls) {
  return ls.join(ls.eol) + (ls.final ? ls.eol : "");
}

function topLevelKeys(ls) {
  const keys = [];
  for (const l of ls) {
    const m = /^([A-Za-z_][A-Za-z0-9_-]*):(\s|$)/.exec(l);
    if (m) keys.push(m[1]);
  }
  return keys;
}

// a key written twice would let a reviewed change to the first copy do nothing (YAML keeps the last)
function refuseDuplicates(ls) {
  const keys = topLevelKeys(ls);
  if (new Set(keys).size !== keys.length) throw new EditError("a top-level key appears twice");
  if (ls.some((l) => /^\{/.test(l))) throw new EditError("flow-style file");
}

// a top-level `key:` line, and the lines its value runs over (indented lines and blank lines between them)
function topLevelSpan(ls, key) {
  const re = new RegExp(`^${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:(\\s|$)`);
  const at = ls.findIndex((l) => re.test(l));
  if (at < 0) return null;
  let end = at + 1;
  let last = at;
  while (end < ls.length && (ls[end] === "" || /^\s/.test(ls[end]) || /^#/.test(ls[end]))) {
    if (ls[end].trim() && !/^\s*#/.test(ls[end])) last = end;
    end++;
  }
  return { at, end: last + 1 };
}

// a plain, single-quoted or double-quoted scalar, as written on one line
export function scalar(raw) {
  const s = String(raw).replace(/\s+#.*$/, "").trim();
  if (s.startsWith('"')) {
    try { return JSON.parse(s); } catch { return null; }
  }
  if (s.startsWith("'")) return s.endsWith("'") && s.length >= 2 ? s.slice(1, -1).replace(/''/g, "'") : null;
  return s;
}

// controls/<id>.yaml: set `implementation:`; added after `owner:` (or `id:`) when it isn't there yet
export function setImplementation(text, value) {
  const ls = lines(text);
  if (!ls.some((l) => /^id:\s/.test(l)) || !ls.some((l) => /^test:(\s|$)/.test(l))) {
    throw new EditError("not a requirement file");
  }
  refuseDuplicates(ls);
  const line = `implementation: ${q(value)}`;
  const span = topLevelSpan(ls, "implementation");
  if (span) {
    ls.splice(span.at, span.end - span.at, line);
  } else {
    const after = topLevelSpan(ls, "owner") || topLevelSpan(ls, "id");
    ls.splice(after.end, 0, line);
  }
  return join(ls);
}

// owners.yaml: set `email:` on the entry whose role matches exactly
export function setOwnerEmail(text, role, email) {
  const ls = lines(text);
  refuseDuplicates(ls);
  const list = topLevelSpan(ls, "owners");
  if (!list) throw new EditError("no owners list");
  if (ls.slice(list.at, list.end).some((l) => /^\s*-\s*\{/.test(l) || /^owners:\s*\[/.test(l))) throw new EditError("flow-style owners");
  let item = -1;
  let indent = "";
  for (let i = list.at + 1; i < list.end; i++) {
    const m = /^(\s*)- role:\s*(.*)$/.exec(ls[i]);
    if (m && scalar(m[2]) === role) {
      if (item >= 0) throw new EditError("that role is listed twice");
      item = i;
      indent = m[1];
    }
  }
  if (item < 0) throw new EditError("no such role");
  const keyIndent = indent + "  ";
  let end = item + 1;
  while (end < list.end && !new RegExp(`^${indent}- `).test(ls[end]) && (ls[end] === "" || ls[end].startsWith(keyIndent) || /^\s*#/.test(ls[end]))) end++;
  const line = `${keyIndent}email: ${q(email)}`;
  const hits = [];
  ls.slice(item + 1, end).forEach((l, i) => { if (l.startsWith(keyIndent + "email:")) hits.push(item + 1 + i); });
  if (hits.length > 1) throw new EditError("email appears twice");
  if (/^\s*email:\s*role:/.test(ls[item])) throw new EditError("unexpected layout");
  if (hits.length) {
    const at = hits[0];
    const v = ls[at].slice((keyIndent + "email:").length).trim();
    // one line only: a block, an empty value (continued below) or an unclosed quote spans more lines
    if (!v || /^[|>]/.test(v) || scalar(v) === null || (ls[at + 1] || "").startsWith(keyIndent + " ")) {
      throw new EditError("email is written over more than one line");
    }
    ls[at] = line;
  } else {
    ls.splice(item + 1, 0, line);
  }
  return join(ls);
}

// evidence/index.yaml: add an item at the end of the `evidence:` list, with the next free EV id
export function nextEvidenceId(text) {
  let max = 0;
  // any `id: EV-n`, in block or flow style, with or without quotes or a comment after it
  for (const m of String(text).matchAll(/\bid:\s*["']?EV-(\d+)/g)) max = Math.max(max, Number(m[1]));
  return `EV-${String(max + 1).padStart(3, "0")}`;
}

export function addEvidence(text, item) {
  const ls = lines(text);
  refuseDuplicates(ls);
  const list = topLevelSpan(ls, "evidence");
  if (!list) throw new EditError("no evidence list");
  const inline = /^evidence:\s*\[\s*\]\s*(#.*)?$/.test(ls[list.at]);
  if (!inline && !/^evidence:\s*(#.*)?$/.test(ls[list.at])) throw new EditError("the evidence list isn't written as a block");
  // the list must be the last thing in the file, or the item would land under another key
  for (let i = list.end; i < ls.length; i++) {
    if (ls[i].trim() && !/^\s*#/.test(ls[i])) throw new EditError("the evidence list isn't the last thing in the file");
  }
  const id = nextEvidenceId(text);
  const block = [
    "",
    `  - id: ${id}`,
    ...Object.entries(item).map(([k, v]) => Array.isArray(v) ? `    ${k}: [${v.map(q).join(", ")}]` : `    ${k}: ${q(v)}`),
  ];
  if (inline) ls[list.at] = "evidence:";
  ls.splice(list.end, 0, ...block);
  return { text: join(ls), id };
}
