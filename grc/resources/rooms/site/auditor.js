// Auditor room: the auditor package as downloads, with each file's size and SHA-256 from the package manifest
// (room.json, built by `grc rooms`). Every page shows who is viewing and when. Built with DOM text nodes only.
"use strict";

const SECTIONS = {
  "00": "Index", "01": "Overview", "02": "Applicability", "03": "Documented information", "04": "Risk and impact",
  "05": "Evidence", "06": "Internal audit", "07": "Management review", "08": "Source record",
  "09": "Machine-readable (OSCAL)",
};

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}

function size(n) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

// a path from the manifest becomes a link only if it is a plain relative path inside the package
function href(folder, path) {
  if (!/^[A-Za-z0-9._-]+$/.test(folder)) return null;
  const parts = String(path).split("/");
  if (!parts.length || parts.some((p) => !/^[A-Za-z0-9._ ()&,+-]+$/.test(p) || p === "." || p === "..")) return null;
  return "files/" + [folder, ...parts].map(encodeURIComponent).join("/");
}

function render(d) {
  document.getElementById("client").textContent = d.client || "Auditor room";
  document.title = `${d.client} · auditor room`;
  const main = document.getElementById("main");
  main.replaceChildren();
  main.append(el("h1", {}, `${d.framework}: auditor package`));
  main.append(el("p", {}, `Prepared from the record as of ${d.as_of} (commit ${String(d.commit || "").slice(0, 12)}, engine ${d.engine}). ` +
    `This room is open ${d.opens} to ${d.closes}.`));
  const zipHref = /^[A-Za-z0-9._-]+\.zip$/.test(d.package.name) ? `files/${encodeURIComponent(d.package.name)}` : null;
  if (zipHref) {
    main.append(el("p", {}, el("a", { class: "btn", href: zipHref, download: "" }, `Download the whole package (${size(d.package.bytes)})`)));
    main.append(el("p", { class: "note" }, "SHA-256 of the archive: ", el("span", { class: "hash" }, d.package.sha256)));
  }
  main.append(el("p", { class: "note" }, "Each file below is also in the archive. Its SHA-256 matches the package's manifest.json and SHA256SUMS. " +
    "Evidence itself stays in the client's systems; the evidence index says where each item is held."));
  const groups = new Map();
  for (const f of d.files) {
    const key = /^\d\d-/.test(String(f.path)) ? String(f.path).slice(0, 2) : "zz";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }
  for (const [key, files] of [...groups.entries()].sort()) {
    main.append(el("h2", {}, SECTIONS[key] || "Manifest and checksums"));
    const tb = el("tbody");
    for (const f of files) {
      const h = href(d.folder, f.path);
      tb.append(el("tr", {},
        el("td", {}, h ? el("a", { href: h, download: "" }, f.path) : f.path),
        el("td", { class: "num" }, size(f.bytes)),
        el("td", { class: "opt" }, el("span", { class: "hash" }, f.sha256))));
    }
    main.append(el("div", { class: "wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "File"), el("th", {}, "Size"), el("th", { class: "opt" }, "SHA-256"))), tb)));
  }
  document.getElementById("foot").textContent =
    "Read only. Views and downloads are logged with your email address. Nothing here can change the record.";
}

async function main() {
  const stamp = document.getElementById("stamp");
  try {
    const [me, data] = await Promise.all([fetch("/api/me").then((r) => r.json()), fetch("room.json").then((r) => r.json())]);
    stamp.textContent = me.email ? `Viewed by ${me.email} on ${String(me.at || "").slice(0, 10)}. Confidential: for this audit only.` : "";
    render(data);
  } catch (err) {
    document.getElementById("main").replaceChildren(el("p", { class: "empty" }, "The room couldn't be loaded. Reload the page."));
  }
}

main();
