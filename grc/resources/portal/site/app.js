// Client site. Everything shown comes from portal.json (built from the engagement record) and
// the signed-in session (/api/me, /api/pending). Text from data is only ever set as text, never as HTML.
"use strict";

const S = { data: null, fw: null, me: "", pending: new Map(), connected: false, owner: "", show: "action" };
const LEG_NAMES = { documented: "Documented", implemented: "In use", evidenced: "Records", tested: "Tested" };

function store(k, v) {
  try {
    if (v === undefined) return localStorage.getItem("grc." + k) || "";
    localStorage.setItem("grc." + k, v);
  } catch (e) { /* storage unavailable: the choice just isn't remembered */ }
  return "";
}

// ------------------------------------------------------------------ tiny DOM helper (text only)
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}

// ------------------------------------------------------------------ dates and words
function day(s) { const [y, m, d] = String(s).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); }
function fmt(s, withYear) {
  if (!s) return "";
  return day(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: withYear ? "numeric" : undefined, timeZone: "UTC" });
}
function daysBetween(a, b) { return Math.round((day(b) - day(a)) / 86400000); }
function plural(n, one, many) { return `${n} ${n === 1 ? one : (many || one + "s")}`; }

function fwData() { return S.data.frameworks.find((f) => f.key === S.fw) || S.data.frameworks[0]; }
function allRequests() { return S.data.frameworks.flatMap((f) => f.requests.map((r) => Object.assign(r, { fwName: f.name }))); }

// Where a request stands from the client's point of view
function stateOf(r) {
  const p = S.pending.get(r.key);
  const s = r.submission;
  if (p && (!s || p.at >= s.at)) return { kind: "sent", label: "Sent, waiting for review", at: p.at };
  if (s && s.status === "received") return { kind: "sent", label: "Sent, waiting for review", at: s.at };
  if (s && s.status === "needs_more") return { kind: "more", label: "We need a bit more", at: s.at, note: s.note };
  if (s && s.status === "accepted") return { kind: "ok", label: "Accepted", at: s.at };
  return { kind: "open" };
}
function needsAction(r) { const k = stateOf(r).kind; return r.action && (k === "open" || k === "more"); }

// ------------------------------------------------------------------ shell
async function boot() {
  try {
    const res = await fetch("portal.json", { credentials: "same-origin", cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    S.data = await res.json();
  } catch (e) {
    main().replaceChildren(h("p", { class: "empty" }, "Your readiness information couldn't be loaded. Reload the page; if it keeps happening, contact your engagement lead."));
    return;
  }
  const saved = store("fw");
  S.fw = S.data.frameworks.some((f) => f.key === saved) ? saved : (S.data.frameworks[0] || {}).key;
  S.owner = store("owner");
  document.getElementById("client").textContent = S.data.client;
  document.title = `${S.data.client}: readiness`;
  document.getElementById("sandbox").hidden = !S.data.sandbox;
  document.getElementById("asof").textContent = `Information as of ${fmt(S.data.as_of, true)}.`;
  document.getElementById("contact").textContent = S.data.contact ? `Questions: ${S.data.contact}` : "";
  window.addEventListener("hashchange", render);
  render();
  loadSession();
}

async function loadSession() {
  try {
    const me = await (await fetch("api/me", { credentials: "same-origin" })).json();
    S.me = me.email || "";
    document.getElementById("me").textContent = S.me ? `Signed in as ${S.me}` : "";
  } catch (e) { /* preview without the Worker */ }
  await refreshPending();
}

async function refreshPending() {
  try {
    const res = await fetch("api/pending", { credentials: "same-origin", cache: "no-store" });
    const body = await res.json();
    S.connected = !!body.connected;
    S.pending = new Map((body.pending || []).map((p) => [p.key, p]));
  } catch (e) { S.connected = false; }
  render();
}

function main() { return document.getElementById("main"); }
function safeDecode(s) { try { return decodeURIComponent(s); } catch (e) { return ""; } }

function renderSwitch() {
  const sw = document.getElementById("fwswitch");
  sw.replaceChildren();
  if (S.data.frameworks.length < 2) return;
  for (const f of S.data.frameworks) {
    sw.append(h("button", { type: "button", role: "tab", "aria-selected": f.key === S.fw ? "true" : "false",
      onclick: () => { S.fw = f.key; store("fw", f.key); render(); } }, f.name));
  }
}

function render() {
  const route = (location.hash || "#/").slice(1);
  const [, page, arg] = route.split("/");
  renderSwitch();
  const open = allRequests().filter(needsAction).length;
  const nc = document.getElementById("navcount");
  nc.hidden = !open;
  nc.textContent = open;
  const name = page === "request" ? "requests" : (page || "overview");
  for (const a of document.querySelectorAll("nav a")) {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  const m = main();
  const routes = { "": overview, requests, request: () => request(safeDecode(arg || "")), progress, help };
  const view = Object.prototype.hasOwnProperty.call(routes, page || "") ? routes[page || ""] : overview;
  const keepScroll = m.dataset.route === route;
  m.dataset.route = route;
  m.replaceChildren(...[].concat(view()));
  if (!keepScroll) { window.scrollTo(0, 0); }
}

// ------------------------------------------------------------------ overview
function overview() {
  const f = fwData();
  const reqs = f.requests.filter(needsAction);
  const late = reqs.filter((r) => r.overdue).length;
  const stage1 = f.path.stages[0];
  const until = stage1 ? daysBetween(S.data.as_of, stage1.date) : null;
  // "Stage 1 audit is" (ISO) or "observation period starts" (SOC 2)
  const soon = (f.terms && f.terms.countdown) || "Stage 1 audit is";
  const head = stage1 && until >= 0
    ? `${until === 0 ? `Your ${f.name} ${soon} today.` : `Your ${f.name} ${soon} in ${plural(until, "day")}.`}`
    : `Your ${f.name} readiness`;
  const nextDue = reqs.filter((r) => r.due && !r.overdue).map((r) => r.due).sort()[0];
  const lede = h("p", { class: "lede" },
    reqs.length ? h("strong", {}, `${plural(reqs.length, "open request")} for your team.`) : "Nothing is waiting on your team right now.",
    late ? ` ${late} ${late === 1 ? "is" : "are"} overdue.` : (reqs.length ? " None are overdue." : ""),
    nextDue ? ` The next is due ${fmt(nextDue)}.` : "",
    ` ${f.ready} of ${f.applicable} requirements are fully ready.`);
  const out = [h("h1", {}, head), lede, pathView(f)];
  out.push(h("h2", {}, "Next for your team"));
  if (reqs.length) {
    out.push(h("p", { class: "section-note" }, "Start with these. Each one takes you to a short form; your answer goes to your engagement team for review."));
    out.push(rows(reqs.slice(0, 4)));
    if (reqs.length > 4) out.push(h("p", {}, h("a", { href: "#/requests" }, `See all ${reqs.length} requests`)));
  } else {
    out.push(h("p", { class: "empty" }, "You're all caught up. New requests appear here when the engagement team adds them."));
  }
  out.push(h("h2", {}, "At a glance"));
  out.push(h("dl", { class: "stats" }, f.stats.map((s) => h("div", {}, h("dt", {}, s.label), h("dd", {}, s.value)))));
  if (f.path.upcoming.length) {
    out.push(h("h2", {}, "Coming up"));
    out.push(h("ul", { class: "rows" }, f.path.upcoming.map((u) =>
      h("li", {}, h("div", { class: "row" }, h("span", { class: "row-title" }, u.text), h("span", { class: "row-side" }, fmt(u.date, true)))))));
  }
  return out;
}

function pathView(f) {
  const phases = f.path.phases;
  const stages = f.path.stages;
  if (!phases.length && !stages.length) return h("div");
  const today = S.data.as_of;
  const dates = [...phases.flatMap((p) => [p.start, p.end]), ...stages.map((s) => s.date), today].sort();
  const lo = day(dates[0]).getTime();
  const hi = day(dates[dates.length - 1]).getTime() + 86400000;
  const pct = (s) => (100 * (day(s).getTime() - lo)) / (hi - lo);
  const track = h("div", { class: "track", "aria-hidden": "true" });
  for (const p of phases) {
    const left = pct(p.start);
    const width = Math.max(pct(p.end) + 100 * 86400000 / (hi - lo) - left, 0.5);
    let cls = "seg";
    if (p.end < today) cls += " done";
    else if (p.start <= today) cls += " now";
    const fill = p.start <= today && today <= p.end ? (100 * (daysBetween(p.start, today) + 1)) / (daysBetween(p.start, p.end) + 1) : 0;
    track.append(h("div", { class: cls, style: { left: left + "%", width: width + "%", "--fill": fill + "%" } }));
    track.append(h("div", { class: "seg-label", style: { left: left + "%", width: width + "%" } }, h("b", {}, p.label || fmt(p.start)), p.name));
  }
  stages.forEach((s, i) => {
    track.append(h("div", { class: "pin" + (i === stages.length - 1 && pct(s.date) > 85 ? " last" : ""), style: { left: pct(s.date) + "%" } },
      h("span", {}, `${s.name}, ${fmt(s.date)}`), h("i")));
  });
  track.append(h("div", { class: "today", style: { left: pct(today) + "%" } }, h("span", {}, "Today")));
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches && !S.revealed) { track.classList.add("reveal"); S.revealed = true; }

  // the same journey as a list, for narrow screens and screen readers
  const items = phases.map((p) => ({ date: p.start, end: p.end, title: p.name, sub: `${fmt(p.start)} to ${fmt(p.end, true)}`, kind: "phase" }))
    .concat(stages.map((s) => ({ date: s.date, title: s.name, sub: fmt(s.date, true), kind: "stage" })))
    .sort((a, b) => (a.date < b.date ? -1 : 1));
  const goal = (f.terms && f.terms.goal) || "certification";
  const list = h("ol", { class: "path-list", "aria-label": `Path to ${goal}` }, items.map((it) => {
    let cls = it.kind === "stage" ? "stage" : "";
    if ((it.end || it.date) < today) cls += " done";
    else if (it.date <= today) cls += " now";
    return h("li", { class: cls.trim() }, h("b", {}, it.title), h("span", {}, it.sub + (cls.includes("now") ? " (now)" : "")));
  }));
  return h("section", { class: "path", "aria-label": `Path to ${goal}` }, track, list);
}

// ------------------------------------------------------------------ requests
function rows(list) {
  return h("ul", { class: "rows" }, list.map((r) => {
    const st = stateOf(r);
    const meta = [];
    if (r.owner) meta.push(h("span", {}, r.owner));
    if (r.due) meta.push(h("span", { class: r.overdue ? "due-late" : "" }, r.overdue ? `Overdue since ${fmt(r.due)}` : `Due ${fmt(r.due)}`));
    meta.push(h("span", {}, `${r.kind} ${r.ref}`));
    if (r.also && r.also.length) meta.push(h("span", {}, `Also counts toward ${r.also.join(", ")}`));
    if (S.data.frameworks.length > 1) meta.push(h("span", {}, r.fwName));
    let side;
    if (st.kind === "sent") side = h("span", { class: "pill sent" }, st.label);
    else if (st.kind === "more") side = h("span", { class: "pill more" }, st.label);
    else if (st.kind === "ok") side = h("span", { class: "pill ok" }, st.label);
    else if (!r.action) side = h("span", { class: "pill" }, "Nothing needed now");
    else side = h("span", { class: "go" }, r.answerable ? "Answer" : "View");
    return h("li", {}, h("a", { class: "row", href: `#/request/${encodeURIComponent(r.key)}` },
      h("span", { class: "row-title" }, r.title || `${r.kind} ${r.ref}`), h("span", { class: "row-meta" }, meta), h("span", { class: "row-side" }, side)));
  }));
}

function requests() {
  const f = fwData();
  const owners = [...new Set(f.requests.map((r) => r.owner))].sort((a, b) => a.localeCompare(b));
  if (S.owner && !owners.includes(S.owner)) S.owner = "";
  const pick = h("select", { "aria-label": "Show requests for", onchange: (e) => { S.owner = e.target.value; store("owner", S.owner); render(); } },
    h("option", { value: "" }, "Everyone"), owners.map((o) => h("option", { value: o, selected: o === S.owner }, o)));
  const showBtn = (key, label) => h("button", { type: "button", "aria-pressed": S.show === key ? "true" : "false", onclick: () => { S.show = key; render(); } }, label);
  const out = [h("h1", {}, "Requests"),
    h("p", { class: "lede" }, "What your engagement team needs from your organization. Open one to see why it matters and to send your answer."),
    h("div", { class: "filters" },
      h("label", {}, "Show requests for", pick),
      h("span", { class: "seg-ctl", role: "group", "aria-label": "Which requests" }, showBtn("action", "Needs action"), showBtn("sent", "Sent"), showBtn("all", "All")))];
  let list = f.requests.filter((r) => !S.owner || r.owner === S.owner);
  if (S.show === "action") list = list.filter(needsAction);
  if (S.show === "sent") list = list.filter((r) => ["sent", "ok"].includes(stateOf(r).kind));
  if (!list.length) {
    out.push(h("p", { class: "empty" }, S.show === "action" ? "Nothing needs action for this selection. Choose All to see everything, including requests you've answered." : "Nothing to show for this selection."));
    return out;
  }
  const soon = new Date(day(S.data.as_of).getTime() + 14 * 86400000).toISOString().slice(0, 10);
  const groups = [
    ["Overdue", (r) => r.overdue, "late"],
    ["Due in the next two weeks", (r) => !r.overdue && r.due && r.due <= soon],
    ["Due later", (r) => !r.overdue && r.due && r.due > soon],
    ["No date yet", (r) => !r.due && r.action],
    ["Nothing needed from you right now", (r) => !r.due && !r.action],
  ];
  for (const [title, test, cls] of groups) {
    const g = list.filter(test);
    if (!g.length) continue;
    out.push(h("h2", { class: "group-title" + (cls ? " " + cls : "") }, `${title} (${g.length})`));
    out.push(rows(g));
  }
  return out;
}

function request(key) {
  const r = allRequests().find((x) => x.key === key);
  if (!r) return [h("a", { class: "back", href: "#/requests" }, "Back to requests"), h("p", { class: "empty" }, "This request is no longer open. It may have been completed or replaced; the requests list shows what's current.")];
  const st = stateOf(r);
  const left = h("div", {},
    h("p", { class: "ref" }, `${r.kind} ${r.ref}${S.data.frameworks.length > 1 ? " · " + r.fwName : ""}`),
    h("h1", {}, r.title || `${r.kind} ${r.ref}`),
    h("p", { class: "facts" },
      h("span", {}, "Owner ", h("b", {}, r.owner)),
      r.due ? h("span", { class: r.overdue ? "due-late" : "" }, r.overdue ? `Overdue since ${fmt(r.due, true)}` : `Due ${fmt(r.due, true)}`) : h("span", {}, "No due date yet"),
      r.also && r.also.length ? h("span", {}, "Also counts toward ", h("b", {}, r.also.join(", "))) : null),
    h("div", { class: "block" }, h("h3", {}, "What we need"), h("ul", {}, r.asks.map((a) => h("li", {}, a)))),
    r.why ? h("div", { class: "block" }, h("h3", {}, "Why this matters"), h("p", {}, r.why)) : null,
    r.examples.length ? h("div", { class: "block" }, h("h3", {}, "What good evidence looks like"), h("ul", {}, r.examples.map((x) => h("li", {}, x)))) : null);
  return [h("a", { class: "back", href: "#/requests" }, "Back to requests"), h("div", { class: "detail" }, left, answerPanel(r, st))];
}

function answerPanel(r, st) {
  const panel = h("section", { class: "answer", "aria-labelledby": "answer-h" });
  const status = [];
  if (st.kind === "sent") status.push(h("div", { class: "status-box sent" }, h("b", {}, `Sent on ${fmt(st.at, true)}`), h("p", {}, "Your engagement team is reviewing it. You can send more if something changes.")));
  if (st.kind === "more") status.push(h("div", { class: "status-box more" }, h("b", {}, "We need a bit more"), st.note ? h("p", {}, st.note) : null));
  if (st.kind === "ok") status.push(h("div", { class: "status-box sent" }, h("b", {}, "Accepted"), h("p", {}, "Thank you. It counts as done once the remaining checks are complete.")));
  if (!r.answerable) {
    panel.append(h("h2", { id: "answer-h" }, "How to resolve this"), h("p", {}, "Your engagement lead will agree this with you directly. There's nothing to send here."));
    return panel;
  }
  if (!r.action && st.kind === "open") {
    panel.append(h("h2", { id: "answer-h" }, "Nothing needed right now"), h("p", {}, "The engagement team is working on this. If you have something to add, you can still send it."));
  } else {
    panel.append(h("h2", { id: "answer-h" }, st.kind === "open" ? "Send your answer" : "Send an update"));
  }
  panel.append(...status);
  const ta = h("textarea", { id: "ans", maxlength: "4000", "aria-describedby": "ans-hint" });
  const counter = h("span", { class: "charcount", "aria-live": "off" }, "0 / 4000");
  ta.addEventListener("input", () => { counter.textContent = `${ta.value.length} / 4000`; });
  const links = h("div", {}, h("input", { type: "url", inputmode: "url", placeholder: "https://", "aria-label": "Link 1" }));
  const add = h("button", { type: "button", class: "linkbtn", onclick: () => {
    const n = links.children.length;
    if (n < 5) links.append(h("input", { type: "url", inputmode: "url", placeholder: "https://", "aria-label": `Link ${n + 1}` }));
    if (links.children.length >= 5) add.hidden = true;
    links.lastChild.focus();
  } }, "Add another link");
  const ok = h("input", { type: "checkbox", id: "nophi" });
  const msg = h("p", { class: "msg", role: "status", "aria-live": "polite" });
  const send = h("button", { type: "submit", class: "primary" }, "Send to your engagement team");
  const form = h("form", { novalidate: true },
    h("label", { for: "ans" }, "Your answer", counter, h("span", { class: "hint", id: "ans-hint" }, "Say what you have, where it lives and who looks after it.")),
    ta,
    h("label", {}, "Links to documents or records", h("span", { class: "hint" }, "Optional. Share links from your own systems (SharePoint, Google Drive, Drata). Don't upload files here.")),
    links, add,
    h("label", { class: "confirm", for: "nophi" }, ok, h("span", {}, "My answer and these links contain no patient data or other personal information.")),
    send, msg);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.className = "msg err";
    const urls = [...links.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
    if (!ta.value.trim() && !urls.length) { msg.textContent = "Write an answer or add a link before sending."; ta.focus(); return; }
    if (urls.some((u) => !/^https:\/\/\S+$/i.test(u))) { msg.textContent = "Each link must be a full address starting with https://"; return; }
    if (!ok.checked) { msg.textContent = "Confirm there's no patient or personal data before sending."; ok.focus(); return; }
    send.disabled = true;
    msg.className = "msg";
    msg.textContent = "Sending…";
    try {
      const res = await fetch("api/submit", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: r.key, answer: ta.value, links: urls, no_sensitive_data: true }) });
      let body = {};
      try { body = await res.json(); } catch (_) { /* not JSON */ }
      if (!res.ok || !body.ok) throw new Error(body.error || "We couldn't send your answer. Nothing was saved. Try again in a minute.");
      S.pending.set(r.key, { key: r.key, id: body.id, at: body.at });
      const next = allRequests().filter((x) => needsAction(x) && x.key !== r.key)[0];
      panel.replaceChildren(h("div", { class: "done-panel" },
        h("h2", { id: "answer-h", tabindex: "-1" }, "Sent"),
        h("p", {}, "Your engagement team will review it. This request now shows as sent; if they need more, you'll see their note here."),
        next ? h("p", {}, h("a", { href: `#/request/${encodeURIComponent(next.key)}` }, `Next request: ${next.title || next.kind + " " + next.ref}`)) : h("p", {}, h("a", { href: "#/requests" }, "Back to requests"))));
      panel.querySelector("h2").focus();
      const nc = document.getElementById("navcount");
      const open = allRequests().filter(needsAction).length;
      nc.hidden = !open; nc.textContent = open;
    } catch (err) {
      send.disabled = false;
      msg.className = "msg err";
      msg.textContent = err.message === "Failed to fetch" ? "You appear to be offline. Nothing was sent; try again when you're connected." : err.message;
    }
  });
  panel.append(form);
  return panel;
}

// ------------------------------------------------------------------ progress
function progress() {
  const f = fwData();
  const showTech = store("tech") === "1";
  const tech = h("input", { type: "checkbox", checked: showTech, onchange: (e) => { store("tech", e.target.checked ? "1" : "0"); render(); } });
  // areas come grouped under headings chosen by the engine (ISO: clauses, then controls; SOC 2: by category)
  const groups = [];
  for (const a of f.areas) {
    const sec = a.section || "Requirements";
    let g = groups.find((x) => x[0] === sec);
    if (!g) groups.push(g = [sec, [], a.section_note || ""]);
    g[1].push(a);
  }
  const out = [h("h1", {}, `${f.name} progress`),
    h("p", { class: "lede" }, `${f.ready} of ${f.applicable} requirements are fully ready, and ${f.checks_pct}% of the evidence checks are complete. Open an area to see each requirement.`),
    h("p", { class: "legend" }, h("span", {}, h("i", { style: { background: "var(--pine)" } }), "Done"), h("span", {}, h("i", { style: { background: "var(--pine-mid)" } }), "Under way"), h("span", {}, h("i", { style: { background: "var(--paper)", border: "1px solid var(--rule)" } }), "Not started")),
    h("label", { class: "toggle" }, tech, "Show technical detail (requirement numbers and the four evidence checks)")];
  for (const [title, areas, note] of groups) {
    if (!areas.length) continue;
    out.push(h("h2", {}, title));
    if (note) out.push(h("p", { class: "section-note" }, note));
    out.push(h("ul", { class: "areas" }, areas.map((a) => {
      const total = a.total || 1;
      return h("li", {}, h("details", { class: "area" },
        h("summary", {}, h("span", { class: "area-title" }, a.title, showTech ? h("small", {}, a.id) : null),
          h("span", { class: "bar", role: "img", "aria-label": `${a.ready} done, ${a.underway} under way, of ${a.total}` },
            h("span", { class: "r", style: { width: (100 * a.ready) / total + "%" } }), h("span", { class: "u", style: { width: (100 * a.underway) / total + "%" } })),
          h("span", { class: "area-count" }, a.total ? `${a.ready} of ${a.total} done` : "Not applicable")),
        h("ul", { class: "reqs" }, a.requirements.map((q) => h("li", {},
          h("span", {}, showTech ? `${q.id} ` : "", q.title),
          h("span", { class: q.state === "Ready" ? "pill ok" : "pill" }, q.plain),
          showTech ? h("span", { class: "tech" }, `${q.kind_label || q.kind} · state: ${q.state} · ` +
            Object.entries(q.legs).map(([k, v]) => `${LEG_NAMES[k]}: ${v}`).join("; ")) : null)))));
    })));
  }
  return out;
}

// ------------------------------------------------------------------ help
function help() {
  const terms = [
    ["Readiness", "How close your organization is to passing its audit.", "Measured per requirement of the standard: a requirement is ready when all four evidence checks pass."],
    ["The four checks", "For each requirement we confirm that it's written down, that it happens, that there are records, and that someone has checked it works.", "Documented, Implemented (In use), Evidenced (Records), Tested. Only the engagement team's review marks a check as passed."],
    ["Request", "Something we need from someone at your organization: an answer, a document or a link to records.", "Generated from open gaps, evidence checks, policies awaiting approval, assessments, audit findings and management review actions."],
    ["Sending an answer", "Your answer goes to your engagement team, who review it before anything changes. You'll see 'Sent', then 'Accepted' or a note asking for more.", "Each answer becomes a reviewed change (a pull request) in the engagement record. It never marks a requirement as ready on its own."],
    ["Gap", "Something missing that needs to be put in place before the audit.", "An item in the gap register, with an owner, due date and closing evidence."],
    ["Policy or procedure", "A document that says how your organization does something, approved by the right person.", "Documented information required by the standard; tracked with owner, approver, version and review date."],
    ...(S.data.frameworks.some((f) => f.impact_assessments) ? [["Impact assessment", "A written look at how one of your AI systems could affect people, and what you do about it.", "AI system impact assessment (ISO/IEC 42001 clause 6.1.4 and Annex A.5)."]] : []),
    ["Internal audit finding", "Something your internal audit found that needs correcting, or an optional suggestion.", "Nonconformity (major or minor) or opportunity for improvement, with root cause and corrective action."],
    ["Management review", "A regular meeting where your leadership looks at how the program is doing and agrees actions.", "Management review with required inputs, decisions and actions (ISO clause 9.3; SOC 2 board and management oversight)."],
  ];
  // terms that belong to one framework (ISO audit stages, SOC 2 observation period ...) come from its playbook
  const seen = new Set(terms.map((t) => t[0]));
  S.data.frameworks.forEach((f) => (f.glossary || []).forEach((g) => {
    if (!seen.has(g.term)) { seen.add(g.term); terms.push([g.term, g.plain, g.tech]); }
  }));
  const out = [h("h1", {}, "Help"),
    h("p", { class: "lede" }, "What the words on this site mean. The first line is the plain version; the smaller line is the technical one your specialists may use."),
    h("dl", { class: "terms" }, terms.map(([t, plain, techTxt]) => h("div", {}, h("dt", {}, t), h("dd", {}, plain), h("dd", { class: "techterm" }, techTxt)))),
    h("h2", {}, "Keeping data safe"),
    h("p", { class: "block" }, "Never put patient information or other personal data in an answer or a link. Share links to documents in your own systems rather than copying their contents. The engagement team only needs to see that a record exists and where it lives.")];
  if (S.data.contact) out.push(h("h2", {}, "Questions"), h("p", {}, S.data.contact));
  return out;
}

document.addEventListener("DOMContentLoaded", boot);
