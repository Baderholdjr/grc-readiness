// Executive dashboard: summary numbers only (data.json, built by `grc rooms`). Everything is built with DOM text
// nodes: nothing from the data is ever parsed as HTML.
"use strict";

const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}

function svg(tag, attrs) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
  return e;
}

function days(n, what) {
  if (n === null || n === undefined) return null;
  if (n < 0) return [`${-n}`, `days since ${what}`];
  return [`${n}`, n === 1 ? `day to ${what}` : `days to ${what}`];
}

function tile(n, t, late) {
  return el("div", { class: "tile" + (late ? " late" : "") }, el("div", { class: "n" }, n), el("div", { class: "t" }, t));
}

function trendChart(points) {
  const box = el("div", { class: "trend" });
  if (points.length < 2) {
    box.append(el("p", { class: "note" }, "The trend appears once the record has a few weeks of history."));
    return box;
  }
  const W = 640, H = 160, L = 34, R = 8, T = 10, B = 24;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Requirements ready rose from ${points[0].ready_pct}% to ${points[points.length - 1].ready_pct}% over ${points.length} weeks` });
  const x = (i) => L + (i * (W - L - R)) / (points.length - 1);
  const y = (v) => T + (H - T - B) * (1 - Math.max(0, Math.min(100, v)) / 100);
  for (const v of [0, 50, 100]) {
    s.append(svg("line", { class: "axis", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    const t = svg("text", { x: 2, y: y(v) + 4 }); t.textContent = `${v}%`; s.append(t);
  }
  const path = (key) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  s.append(svg("path", { class: "line2", d: path("checks_pct") }));
  s.append(svg("path", { class: "line", d: path("ready_pct") }));
  for (const [i, p] of [[0, points[0]], [points.length - 1, points[points.length - 1]]]) {
    const t = svg("text", { x: x(i), y: H - 6, "text-anchor": i ? "end" : "start" }); t.textContent = p.week; s.append(t);
  }
  box.append(s, el("div", { class: "legend" }, el("span", {}, "Requirements ready"), el("span", { class: "b" }, "Evidence checks complete")));
  return box;
}

function render(d) {
  document.getElementById("client").textContent = d.client || "Readiness summary";
  document.title = `${d.client} · readiness summary`;
  const main = document.getElementById("main");
  main.replaceChildren();
  main.append(el("h1", {}, `${d.framework} readiness`));
  main.append(el("div", { class: "hero" },
    el("div", { class: "big" }, `${d.ready_pct}%`),
    el("div", { class: "label" }, `of requirements are ready (${d.ready} of ${d.applicable}), with evidence checked.`)));
  const tiles = el("div", { class: "tiles" });
  for (const [n, what] of [[d.days_to_stage1, "the Stage 1 audit"], [d.days_to_stage2, "the Stage 2 audit"]]) {
    const t = days(n, what);
    if (t) tiles.append(tile(t[0], t[1]));
  }
  tiles.append(tile(`${d.checks_pct}%`, "of evidence checks complete"));
  tiles.append(tile(String(d.gaps_open), d.gaps_open === 1 ? "open gap" : "open gaps"));
  tiles.append(tile(String(d.gaps_overdue), "gaps past their due date", d.gaps_overdue > 0));
  tiles.append(tile(String(d.gaps_by_severity.high || 0), "high-severity gaps", (d.gaps_by_severity.high || 0) > 0));
  if (d.evidence_stale) tiles.append(tile(String(d.evidence_stale), "evidence items out of date", true));
  main.append(tiles);

  main.append(el("h2", {}, "Trend"));
  main.append(trendChart(d.trend || []));

  main.append(el("h2", {}, "Top open gaps"));
  if (!d.top_gaps.length) {
    main.append(el("p", { class: "empty" }, "No open gaps."));
  } else {
    const tb = el("tbody");
    for (const g of d.top_gaps) {
      tb.append(el("tr", {},
        el("td", {}, g.area),
        el("td", {}, el("span", { class: `sev ${g.severity}` }, g.severity)),
        el("td", { class: "num" + (g.overdue ? " late-text" : "") }, g.due ? (g.overdue ? `${g.due} (overdue)` : g.due) : "no date"),
        el("td", { class: "opt" }, g.status === "in_progress" ? "in progress" : "open")));
    }
    main.append(el("div", { class: "wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Area"), el("th", {}, "Severity"), el("th", {}, "Due"), el("th", { class: "opt" }, "Status"))),
      tb)));
  }
  document.getElementById("foot").textContent =
    `Record as of ${d.as_of}. Summary only: the full record, evidence and documents stay with the engagement team.`;
}

async function main() {
  const stamp = document.getElementById("stamp");
  try {
    const [me, data] = await Promise.all([fetch("/api/me").then((r) => r.json()), fetch("data.json").then((r) => r.json())]);
    stamp.textContent = me.email ? `Viewed by ${me.email} on ${String(me.at || "").slice(0, 10)}. Confidential to the organisation.` : "";
    render(data);
  } catch (err) {
    document.getElementById("main").replaceChildren(el("p", { class: "empty" }, "The summary couldn't be loaded. Reload the page."));
  }
}

main();
