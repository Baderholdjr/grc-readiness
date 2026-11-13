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

function requirementLines(text) {
  const ls = lines(text);
  if (!ls.some((l) => /^id:\s/.test(l)) || !ls.some((l) => /^test:(\s|$)/.test(l))) {
    throw new EditError("not a requirement file");
  }
  refuseDuplicates(ls);
  return ls;
}

// controls/<id>.yaml: set a top-level text value (`implementation`, `owner`), added after `owner:` or `id:`
export function setRequirementField(text, key, value) {
  if (!["implementation", "owner"].includes(key)) throw new EditError("not a field the site changes");
  const ls = requirementLines(text);
  const line = `${key}: ${q(value)}`;
  const span = topLevelSpan(ls, key);
  if (span) {
    ls.splice(span.at, span.end - span.at, line);
  } else {
    const after = (key === "implementation" && topLevelSpan(ls, "owner")) || topLevelSpan(ls, "id");
    ls.splice(after.end, 0, line);
  }
  return join(ls);
}

export function setImplementation(text, value) {
  return setRequirementField(text, "implementation", value);
}

const LEGS = ["documented", "implemented", "evidenced", "tested"];
// what the workspace may set a check's status to: never "verified", which stays a reviewer's own edit
export const WORKSPACE_STATUSES = ["not_started", "claimed", "partial"];

// controls/<id>.yaml: one field of one evidence check under `test:` (status, note, or the evidence it cites)
export function setLegField(text, leg, field, value) {
  if (!LEGS.includes(leg)) throw new EditError("no such check");
  if (field === "status" && !WORKSPACE_STATUSES.includes(value)) throw new EditError("that status is set by a reviewer");
  if (!["status", "note", "evidence"].includes(field)) throw new EditError("not a field the site changes");
  const ls = requirementLines(text);
  const test = topLevelSpan(ls, "test");
  if (/^test:\s*\{/.test(ls[test.at])) throw new EditError("flow-style test");
  const legAt = ls.findIndex((l, i) => i > test.at && i < test.end && new RegExp(`^  ${leg}:\\s*$`).test(l));
  if (legAt < 0) throw new EditError("that check isn't written as a block");
  let end = legAt + 1;
  while (end < test.end && (ls[end] === "" || /^    /.test(ls[end]) || /^\s*#/.test(ls[end]))) end++;
  const hits = [];
  for (let i = legAt + 1; i < end; i++) if (new RegExp(`^    ${field}:`).test(ls[i])) hits.push(i);
  if (hits.length > 1) throw new EditError("that field appears twice");
  let line;
  if (field === "evidence") {
    const ids = Array.isArray(value) ? value : [];
    if (!ids.every((x) => /^([a-z0-9]+:)?(EV-[0-9]{3,}|AUD-\d{4}-\d{2}\/WP-\d{2,3}|IA-\d{3,}|DOC-[A-Z0-9]+(-[A-Z0-9]+)*|MR-\d{4}-\d{2})$/.test(x))) {
      throw new EditError("not an evidence reference");
    }
    line = `    evidence: [${ids.map(q).join(", ")}]`;
  } else {
    line = `    ${field}: ${q(value)}`;
  }
  if (hits.length) {
    const at = hits[0];
    const rest = ls[at].replace(/^    [a-z]+:/, "").trim();
    const next = ls[at + 1] || "";
    // one line only: a value carried on to the next lines (a block list, folded text) is refused
    if (!rest || /^[|>]/.test(rest) || (rest.startsWith("[") && !rest.includes("]")) || (/^["']/.test(rest) && scalar(rest) === null) ||
        /^     /.test(next) || /^    - /.test(next)) {
      throw new EditError("that field is written over more than one line");
    }
    ls[at] = line;
  } else {
    // only insert into a check whose fields are all one line each (no block lists or carried-over values)
    for (let i = legAt + 1; i < end; i++) if (/^     /.test(ls[i]) || /^    - /.test(ls[i])) throw new EditError("that check has values over more than one line");
    // keep the order the engine writes: status, evidence, note
    const order = ["status", "evidence", "note"];
    let insertAt = legAt + 1;
    for (let i = legAt + 1; i < end; i++) {
      const m = /^    ([a-z]+):/.exec(ls[i]);
      if (m && order.indexOf(m[1]) < order.indexOf(field)) insertAt = i + 1;
    }
    ls.splice(insertAt, 0, line);
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
