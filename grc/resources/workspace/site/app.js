// Yata workspace. Built with DOM text nodes only: nothing from the record is ever parsed as HTML.
"use strict";

const LEGS = { documented: "Documented", implemented: "Implemented", evidenced: "Evidence exists", tested: "Tested" };
const STATUS = { not_started: "Not started", claimed: "Claimed", partial: "Partial", verified: "Verified" };
const S = { login: "", record: null, filter: "" };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}

const main = () => document.getElementById("main");

async function getJson(path) {
  const res = await fetch(path, { credentials: "same-origin", cache: "no-store" });
  let body = {};
  try { body = await res.json(); } catch (_) { /* not JSON */ }
  if (res.status === 401 && body.signin) { signIn(); throw new Error("signin"); }
  if (!res.ok) throw new Error(body.error || "Couldn't load that. Try again.");
  return body;
}

function signIn() {
  document.getElementById("who").textContent = "";
  document.getElementById("signout").hidden = true;
  main().replaceChildren(h("section", { class: "signin" },
    h("h1", {}, "Sign in"),
    h("p", {}, "Sign in with your GitHub account. You'll see the client engagements you work on, and every change you make becomes a pull request in your name."),
    h("p", {}, h("a", { class: "btn", href: "/auth/login" }, "Sign in with GitHub"))));
}

async function boot() {
  document.getElementById("signout").addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" });
    signIn();
  });
  try {
    S.login = (await getJson("/api/me")).login;
  } catch (e) {
    if (e.message !== "signin") main().replaceChildren(h("p", { class: "msg err" }, e.message));
    return;
  }
  document.getElementById("who").textContent = `Signed in as ${S.login}`;
  document.getElementById("signout").hidden = false;
  window.addEventListener("hashchange", route);
  route();
}

function route() {
  const m = /^#\/e\/([A-Za-z0-9-]+\/[A-Za-z0-9._-]+)$/.exec(location.hash);
  return m ? engagement(decodeURIComponent(m[1])) : engagements();
}

async function engagements() {
  main().replaceChildren(h("h1", {}, "Engagements"), h("p", { class: "muted" }, "Loading…"));
  let repos;
  try { repos = (await getJson("/api/engagements")).repos; } catch (e) { if (e.message !== "signin") main().append(h("p", { class: "msg err" }, e.message)); return; }
  main().replaceChildren(h("h1", {}, "Engagements"),
    repos.length
      ? h("ul", { class: "cards" }, repos.map((r) => h("li", {}, h("a", { href: `#/e/${r}` }, r.split("/")[1], h("small", {}, r)))))
      : h("p", { class: "muted" }, "No engagements yet. The Yata Workspace GitHub App needs to be installed on a client repository you can push to."));
}

async function engagement(repo) {
  main().replaceChildren(h("p", {}, h("a", { href: "#/" }, "All engagements")), h("p", { class: "muted" }, "Loading the record…"));
  try { S.record = await getJson(`/api/engagement?repo=${encodeURIComponent(repo)}`); } catch (e) { if (e.message !== "signin") main().append(h("p", { class: "msg err" }, e.message)); return; }
  render();
}

function render() {
  const r = S.record;
  const search = h("input", { type: "search", placeholder: "Find a requirement by number, title or owner", "aria-label": "Find a requirement", value: S.filter });
  const list = h("ul", { class: "reqs" });
  const fill = () => {
    const q = S.filter.toLowerCase();
    const shown = r.requirements.filter((x) => !q || `${x.id} ${x.title} ${x.owner}`.toLowerCase().includes(q));
    list.replaceChildren(...shown.slice(0, 200).map((x) => h("li", {}, requirement(x))));
    if (shown.length > 200) list.append(h("li", { class: "muted" }, `Showing 200 of ${shown.length}. Narrow the search to see the rest.`));
  };
  search.addEventListener("input", () => { S.filter = search.value; fill(); });
  fill();
  const open = r.gaps.filter((g) => g.status === "open" || g.status === "in_progress");
  main().replaceChildren(
    h("p", {}, h("a", { href: "#/" }, "All engagements")),
    h("h1", {}, r.client || r.repo), h("p", { class: "muted" }, `${r.framework} · ${r.requirements.length} requirements · ${open.length} open gaps · ${r.repo}`),
    h("p", { class: "hint" }, "Each save opens a pull request in your name. Checks can be set to not started, claimed or partial here; marking one verified is the reviewer's edit in the pull request."),
    h("div", { class: "toolbar" }, search), list,
    h("datalist", { id: "evidence-ids" }, r.evidence.map((e) => h("option", { value: e.id }, `${e.id} ${e.title}`))),
    h("h2", {}, "Open gaps"),
    open.length ? h("div", { class: "wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Gap"), h("th", {}, "Area"), h("th", {}, "Severity"), h("th", {}, "Due"), h("th", {}, "Owner"))),
      h("tbody", {}, open.map((g) => h("tr", {}, h("td", {}, g.id), h("td", {}, g.area), h("td", {}, g.severity || "unrated"), h("td", {}, g.due || "no date"), h("td", {}, g.owner))))))
      : h("p", { class: "muted" }, "No open gaps."));
}

async function save(body, msg, button) {
  button.disabled = true;
  msg.className = "msg";
  msg.textContent = "Opening a pull request…";
  try {
    const res = await fetch("/api/change", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ repo: S.record.repo }, body)) });
    let out = {};
    try { out = await res.json(); } catch (_) { /* not JSON */ }
    if (res.status === 401) { signIn(); return; }
    if (!res.ok || !out.ok) throw new Error(out.error || "That didn't go through. Nothing was changed.");
    msg.replaceChildren("Pull request ", /^https:\/\/github\.com\//.test(out.url) ? h("a", { href: out.url, target: "_blank", rel: "noopener" }, `#${out.number}`) : `#${out.number}`,
      " opened. The record changes when it's merged.");
  } catch (e) {
    msg.className = "msg err";
    msg.textContent = e.message === "Failed to fetch" ? "You appear to be offline. Nothing was sent." : e.message;
  } finally {
    button.disabled = false;
  }
}

function requirement(x) {
  const dots = h("span", { class: "legdots", "aria-label": Object.entries(LEGS).map(([k, n]) => `${n}: ${STATUS[x.legs[k].status] || x.legs[k].status}`).join(", ") },
    Object.keys(LEGS).map((k) => h("span", { class: `dot ${x.legs[k].status}`, title: `${LEGS[k]}: ${STATUS[x.legs[k].status] || x.legs[k].status}` })));
  const d = h("details", { class: "req" }, h("summary", {}, h("span", { class: "rid" }, x.id), h("span", { class: "rt" }, x.title || ""),
    h("span", { class: "muted" }, x.owner || "no owner"), dots));
  d.addEventListener("toggle", () => { if (d.open && d.children.length === 1) d.append(editor(x)); }, { once: false });
  return d;
}

function editor(x) {
  const id = x.id.replace(/[^A-Za-z0-9]/g, "_");
  const impl = h("textarea", { id: `impl-${id}`, maxlength: "4000" });
  impl.value = x.implementation;
  const implMsg = h("p", { class: "msg", role: "status", "aria-live": "polite" });
  const implBtn = h("button", { type: "button", class: "small" }, "Save statement");
  implBtn.addEventListener("click", () => save({ requirement: x.id, field: "implementation", value: impl.value }, implMsg, implBtn));

  const owner = h("select", { id: `owner-${id}` }, h("option", { value: "" }, "Choose…"), S.record.owners.map((o) => h("option", { value: o, selected: o === x.owner }, o)));
  const ownerMsg = h("p", { class: "msg", role: "status", "aria-live": "polite" });
  const ownerBtn = h("button", { type: "button", class: "small" }, "Save owner");
  ownerBtn.addEventListener("click", () => save({ requirement: x.id, field: "owner", value: owner.value }, ownerMsg, ownerBtn));

  const legs = Object.entries(LEGS).map(([k, name]) => {
    const leg = x.legs[k];
    const msg = h("p", { class: "msg", role: "status", "aria-live": "polite" });
    const status = h("select", { "aria-label": `${name} status` }, ["not_started", "claimed", "partial"].map((s) => h("option", { value: s, selected: s === leg.status }, STATUS[s])));
    const sBtn = h("button", { type: "button", class: "small" }, "Save status");
    sBtn.addEventListener("click", () => save({ requirement: x.id, field: "status", leg: k, value: status.value }, msg, sBtn));
    const ev = h("input", { type: "text", list: "evidence-ids", "aria-label": `${name} evidence`, placeholder: "EV-001, EV-004", value: leg.evidence.join(", ") });
    const eBtn = h("button", { type: "button", class: "small" }, "Save evidence");
    eBtn.addEventListener("click", () => save({ requirement: x.id, field: "evidence", leg: k, value: ev.value.split(/[\s,]+/).filter(Boolean) }, msg, eBtn));
    const note = h("input", { type: "text", "aria-label": `${name} note`, placeholder: "Note", value: leg.note, maxlength: "1000" });
    const nBtn = h("button", { type: "button", class: "small" }, "Save note");
    nBtn.addEventListener("click", () => save({ requirement: x.id, field: "note", leg: k, value: note.value }, msg, nBtn));
    return h("div", { class: "leg" }, h("span", { class: "legname" }, name),
      leg.status === "verified" ? h("span", { class: "verified" }, "Verified by a reviewer") : h("div", { class: "row" }, status, sBtn),
      h("div", { class: "row" }, ev, eBtn), h("div", { class: "row" }, note, nBtn), msg);
  });
  return h("div", { class: "body" },
    h("div", { class: "field" }, h("label", { for: `impl-${id}` }, "Implementation statement"), impl, h("div", { class: "row" }, implBtn), implMsg),
    h("div", { class: "field" }, h("label", { for: `owner-${id}` }, "Owner"), h("div", { class: "row" }, owner, ownerBtn), ownerMsg),
    h("div", { class: "field" }, h("span", { class: "legname" }, "Evidence checks"), h("div", { class: "legs" }, legs)));
}

boot();
