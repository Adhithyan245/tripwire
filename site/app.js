/* Driftwire web app. Opens a recorded Driftwire run (findings.json, optionally with the "replay" block written by
   scripts/build_replay.py) and lets a person walk it: run, scan, findings with review, questions, next steps.
   Every number on screen comes from that file. Review decisions are kept in this browser and exported in the
   shared format's `decisions` section (same shape as tripwire/review.py). */
(() => {
  "use strict";

  // ---------- vocabulary ----------
  const KIND = {
    sample_swap: "Swapped profiles", duplicate: "Copied profiles", membership_change: "Samples lost or added",
    label_change: "Changed labels", sample_type_change: "Sample type changed", id_format_change: "Reformatted IDs",
    value_shift: "Values shifted", coverage_loss: "Coverage lost", label_conflict: "Label contradicts its own data",
  };
  const ACTION = {
    restore_from_previous_release: "Restore from the trusted release", exclude: "Exclude from analyses",
    relabel: "Map back to the trusted IDs", flag_for_review: "Ask the data provider", other: "Other",
  };
  const DECISION = { approve: "Approved", reject: "Rejected", request_more_evidence: "More evidence asked" };
  const ICON = { Ready: "✓", Conditional: "!", Blocked: "✕", "Insufficient Evidence": "?" };
  const USE = { descriptive: "Describe the data", model_training: "Train a model" };
  const ROLES = ["Curator", "Data provider", "Analyst", "Principal investigator"];
  const ROUTES = [
    ["run", "Run", '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v10h12V10"/>'],
    ["scan", "Scan", '<path d="M3 12h18"/><circle cx="7" cy="7" r="1.3"/><circle cx="17" cy="7" r="1.3"/><circle cx="7" cy="17" r="1.3"/><circle cx="12" cy="17" r="1.3"/><circle cx="17" cy="17" r="1.3"/><circle cx="12" cy="7" r="1.3"/>'],
    ["findings", "Findings", '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/>'],
    ["questions", "Questions", '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.6"/><circle cx="12" cy="17" r=".6"/>'],
    ["next", "Next steps", '<path d="M5 7l2 2 3-3M5 15l2 2 3-3"/><path d="M13 8h6M13 16h6"/>'],
  ];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- state ----------
  let doc = null, key = "", kindColor = {}, decisions = {}, ticks = {}, scanToken = 0;

  // ---------- helpers ----------
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "style") el.style.cssText = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }
  const NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs) { const el = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v); return el; }
  function icon(paths) { const sv = s("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }); sv.innerHTML = paths; return sv; } // static, trusted markup
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : n ?? "–");
  const firstSentence = (t) => (t || "").split(/(?<=\.)\s/)[0];
  const wait = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* storage unavailable */ } },
  };
  const kindName = (k) => KIND[k] || (k || "change").replace(/_/g, " ");
  const colorOf = (k) => kindColor[k] || "var(--c8)";
  const samplesOf = (f) => (f.evidence || []).filter((e) => e.kind === "sample");
  const repairsFor = (f) => (doc.repairs || []).filter((r) => (r.addresses || []).includes(f.id));
  function pill(v) {
    const cls = v === "Insufficient Evidence" ? "Insufficient" : v;
    return h("span", { class: `pill ${cls}` }, h("i", { "aria-hidden": "true" }, ICON[v] || "•"), v);
  }
  function toast(msg) {
    const t = $("toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 2600);
  }
  function tip(ev, text) { const t = $("tip"); t.textContent = text; t.hidden = false; t.style.left = `${Math.min(innerWidth - 290, ev.clientX + 12)}px`; t.style.top = `${ev.clientY + 14}px`; }
  const hideTip = () => { $("tip").hidden = true; };

  // ---------- data ----------
  function fingerprint(d) {
    const content = JSON.stringify([
      d.findings.map((f) => [f.id, f.kind, f.summary, (f.evidence || []).map((e) => [e.kind, e.id, e.file, e.note])]),
      (d.repairs || []).map((r) => [r.id, r.action, (r.targets || []).map((t) => [t.id, t.file, t.release])]),
    ]);
    let x = 5381;
    for (let i = 0; i < content.length; i++) x = ((x << 5) + x + content.charCodeAt(i)) >>> 0;
    return x.toString(36) + content.length.toString(36);
  }
  function relNames() {
    const rel = (doc.data && doc.data.releases) || [];
    return [(doc.replay && doc.replay.release_a) || (rel[0] && rel[0].name) || "release A",
            (doc.replay && doc.replay.release_b) || (rel[1] && rel[1].name) || "release B"];
  }
  function filesOf() {
    if (doc.replay && Array.isArray(doc.replay.files)) return doc.replay.files;
    const names = new Set();
    for (const f of doc.findings) for (const e of f.evidence || []) if (e.file) names.add(e.file);
    return [...names].map((file) => ({ file, n_a: null, n_b: null, in_b: true }));
  }
  const hitsIn = (file) => doc.findings.flatMap((f) => samplesOf(f).filter((e) => e.file === file).map((e) => ({ id: e.id, f, e })));

  function accept(d) {
    if (!d || !Array.isArray(d.findings) || !Array.isArray(d.analyses)) throw new Error("this isn't a Driftwire findings.json");
    doc = d;
    kindColor = {}; let i = 1;
    for (const f of d.findings) if (!(f.kind in kindColor)) kindColor[f.kind] = `var(--c${Math.min(i++, 8)})`;
    const [a, b] = relNames();
    // Saved reviews belong to this exact content: if any finding's evidence or any repair's targets change, even with
    // the same IDs, earlier decisions must not carry over to it.
    key = `${a}->${b}:${fingerprint(d)}`;
    decisions = store.get(`tw-dec:${key}`, {});
    for (const x of d.decisions || []) if (!decisions[x.repair_id]) decisions[x.repair_id] = x;
    ticks = store.get(`tw-todo:${key}`, {});
    const cr = $("crumbs");
    cr.replaceChildren(h("span", { class: "mono" }, a), h("span", { class: "vs" }, "→"), h("span", { class: "mono" }, b), pill(d.verdict || "Ready"));
    updateBell();
  }

  function openReviews() {
    return doc.findings.filter((f) => f.needs_human_review && repairsFor(f).some((r) => !decisions[r.id]));
  }
  function updateBell() {
    const n = doc ? openReviews().length : 0;
    const b = $("bellCount"); b.hidden = !n; b.textContent = n;
    $("bell").setAttribute("aria-label", n ? `${n} finding(s) waiting for review` : "No reviews waiting");
    const fl = document.querySelector('.nav-btn[data-r="findings"]');
    if (fl) { let d = fl.querySelector(".dotc"); if (n && !d) fl.append(h("span", { class: "dotc" })); if (!n && d) d.remove(); }
  }

  // ---------- routing ----------
  function renderNav() {
    $("nav").replaceChildren(...ROUTES.map(([r, label, paths]) => {
      const a = h("a", { class: "nav-btn", href: `#${r}`, "data-r": r, "aria-label": label }, icon(paths), h("span", { class: "lbl" }, label));
      return a;
    }));
  }
  function route() {
    const r = (location.hash || "#run").slice(1).split("?")[0];
    const name = ROUTES.some(([x]) => x === r) ? r : "run";
    document.querySelectorAll(".nav-btn[data-r]").forEach((n) => { n.classList.toggle("on", n.dataset.r === name); n.setAttribute("aria-current", n.dataset.r === name ? "page" : "false"); });
    scanToken++;
    const v = $("view"); v.replaceChildren();
    if (!doc) { v.append(h("div", { class: "card pad" }, "Loading the recorded run…")); return; }
    ({ run: viewRun, scan: viewScan, findings: viewFindings, questions: viewQuestions, next: viewNext })[name](v);
    updateBell();
    v.focus({ preventScroll: true }); scrollTo({ top: 0 });
  }
  const go = (r) => { if (location.hash === `#${r}`) route(); else location.hash = r; };

  function head(eyebrow, title, text, right) {
    return h("div", { class: "head enter" }, h("div", {}, h("div", { class: "eyebrow" }, eyebrow), h("h1", {}, title), text ? h("p", {}, text) : null), right || null);
  }

  // ---------- run ----------
  function viewRun(v) {
    const [a, b] = relNames();
    const files = filesOf();
    const zone = (label, name, side) => h("div", { class: "zone filled enter", "data-zone": side },
      h("div", { class: "zh" }, folder(), h("div", {}, h("div", { class: "zt" }, label), h("div", { class: "zn" }, name))),
      h("div", { class: "zfiles" }, files.map((f, i) => h("div", { class: "zf", style: `animation-delay:${i * 60}ms` },
        h("span", { class: "mono" }, f.file), h("b", {}, side === "a" ? fmt(f.n_a) : f.in_b === false ? "missing" : fmt(f.n_b))))),
      h("div", { class: "hint" }, side === "a" ? "The release the team already trusts and analysed." : "The new delivery. Same files, same counts from the outside."));

    const fill = h("div", { class: "fill" });
    const label = h("span", {}, "Ready when you are");
    const secs = h("span", {}, doc.replay && doc.replay.seconds ? `recorded run: ${doc.replay.seconds} s` : "");
    const btn = h("button", { class: "runbtn", type: "button", onclick: () => run() }, "Run Driftwire");

    async function run() {
      btn.disabled = true; btn.textContent = "Running…";
      const nf = files.reduce((n, f) => n + (f.n_b || 0), 0);
      const steps = [
        [`Fingerprinting ${nf ? fmt(nf) + " sample entries" : "every sample"} in ${files.length} files`, 22],
        ["Comparing fingerprints between releases", 45],
        [`Mapping ${doc.findings.length} change(s) to what reads them`, 64],
        [`Rerunning ${doc.analyses.map((x) => x.id).join(" and ")} against tolerance`, 82],
        [`Checking ${(doc.questions || []).length} research questions`, 100],
      ];
      for (const [t, p] of steps) { label.textContent = t; fill.style.width = `${p}%`; await wait(620); }
      label.textContent = `Done: ${doc.verdict}`; await wait(450);
      go("scan");
    }

    v.append(
      h("section", { class: "hero" },
        h("div", { class: "enter" },
          h("div", { class: "eyebrow" }, "Cohort Control Tower · TCGA-BRCA"),
          h("h1", {}, "Catch what ", h("em", {}, "silently changed"), " in a data release, before it reaches a result."),
          h("p", {}, "Driftwire compares a new release with the one you trust, sample by sample. It finds swapped, copied and missing samples, reruns only the analyses they touch, and tells you which research questions the release is still ready for. A person makes every call.")),
        miniScene()),
      h("div", { class: "zones" }, zone("TRUSTED", a, "a"), zone("NEW", b, "b")),
      h("div", { class: "runrow" }, btn,
        h("div", { class: "prog" }, h("div", { class: "track" }, fill), h("div", { class: "stage-l" }, label, secs)),
        h("div", { class: "alt" }, "Ran Driftwire on your own releases? ",
          h("button", { type: "button", onclick: () => $("file").click() }, "Open its findings.json"), " or drop it anywhere.")),
      h("section", { class: "how" }, [
        ["Fingerprint every sample", "Each sample's data gets a fingerprint in both releases, so a swap, a copy or a lost sample shows up even when the counts don't change."],
        ["Follow each change to what reads it", "Analyses declare their files and fields. Only the ones a change touches are rerun, and the rest are rerun anyway to prove it."],
        ["Verdict, plan, and a person decides", "Ready, Conditional, Blocked or Insufficient Evidence, with the reason written down. Repairs are previewed, never applied."],
      ].map(([t, p], i) => h("div", { class: "card enter", style: `animation-delay:${120 + i * 80}ms` }, h("span", { class: "n" }, i + 1), h("div", {}, h("h3", {}, t), h("p", {}, p))))),
      footer());
  }

  function folder() {
    const sv = s("svg", { class: "folder", viewBox: "0 0 46 40", "aria-hidden": "true" });
    sv.append(s("path", { d: "M3 8a3 3 0 0 1 3-3h11l4 5h19a3 3 0 0 1 3 3v21a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z" }));
    return sv;
  }

  function miniScene() {
    // decorative loop: a laser sweeps a small grid and a few samples light up
    const W = 520, H = 230, cols = 26, rows = 10, g = 18, x0 = 26, y0 = 26;
    const sv = s("svg", { viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true", preserveAspectRatio: "xMidYMid slice" });
    const hits = { 33: 1, 58: 2, 71: 3, 112: 2, 140: 1, 167: 3, 199: 2, 214: 3, 236: 2 };
    for (let i = 0; i < cols * rows; i++) {
      const cx = x0 + (i % cols) * g, cy = y0 + Math.floor(i / cols) * g;
      const c = s("circle", { cx, cy, r: hits[i] ? 4.5 : 2.4, fill: hits[i] ? `var(--c${hits[i]})` : "var(--dot)" });
      if (hits[i] && !reduce) {
        const t = ((cy - y0) / (rows * g)) * 3.2;
        c.append(s("animate", { attributeName: "opacity", values: "0;0;1;1;0", keyTimes: `0;${(t / 4).toFixed(3)};${(t / 4 + 0.02).toFixed(3)};0.92;1`, dur: "4s", repeatCount: "indefinite" }));
      }
      sv.append(c);
    }
    if (!reduce) {
      const ln = s("line", { x1: 10, x2: W - 10, y1: 0, y2: 0, stroke: "var(--wire)", "stroke-width": 2.5 });
      const gl = s("line", { x1: 10, x2: W - 10, y1: 0, y2: 0, stroke: "var(--wire)", "stroke-opacity": .2, "stroke-width": 14 });
      for (const el of [gl, ln]) {
        el.append(s("animate", { attributeName: "y1", values: `${y0 - 10};${y0 + rows * g};${y0 + rows * g}`, keyTimes: "0;0.8;1", dur: "4s", repeatCount: "indefinite" }));
        el.append(s("animate", { attributeName: "y2", values: `${y0 - 10};${y0 + rows * g};${y0 + rows * g}`, keyTimes: "0;0.8;1", dur: "4s", repeatCount: "indefinite" }));
        sv.append(el);
      }
    }
    return h("div", { class: "mini enter", style: "animation-delay:.1s" }, sv);
  }

  // ---------- scan ----------
  function viewScan(v) {
    const token = scanToken;
    const alive = () => token === scanToken;
    const files = filesOf().filter((f) => f.in_b !== false).sort((x, y) => (hitsIn(x.file).length > 0) - (hitsIn(y.file).length > 0));
    const total = doc.findings.reduce((n, f) => n + samplesOf(f).length, 0);
    const counterN = h("span", {}, "0");
    const counter = h("div", { class: "counter", "aria-live": "polite" }, counterN, h("small", {}, "samples tripped the wire"));
    const tabs = h("div", { class: "tabs" }, files.map((f) => h("span", { class: "tab", "data-file": f.file }, f.file)));
    const field = h("div", {});
    const fname = h("div", { class: "fname" }, h("span", { class: "mono" }, ""), h("span", {}, ""));
    const counts = {};
    const legend = h("div", { class: "legend" });
    const drawLegend = () => legend.replaceChildren(...Object.keys(kindColor).map((k) =>
      h("span", {}, h("i", { style: `background:${colorOf(k)}` }), kindName(k), h("b", {}, counts[k] || 0))));
    drawLegend();

    const cards = doc.analyses.map((a) => analysisCard(a));
    const panel = h("div", { class: "panel" }, h("div", { class: "eyebrow" }, "What reads this data"), cards.map((c) => c.el));
    const flows = s("svg", { class: "flows", "aria-hidden": "true" });
    const wrap = h("div", { class: "scanwrap" },
      h("div", { class: "card gridcard enter" }, h("div", { class: "gridtop" }, counter, tabs), field, fname, legend,
        h("div", { class: "scan-actions" },
          h("button", { class: "btn small", type: "button", onclick: () => route() }, "↻ Replay scan"),
          h("button", { class: "btn small navy", type: "button", onclick: () => go("findings") }, `See the ${doc.findings.length} finding${doc.findings.length === 1 ? "" : "s"} →`))),
      panel, flows);

    v.append(head("Step 1 · Scan", "Every sample, fingerprinted and compared",
      "A sample trips the wire when its data moved to another sample, was copied, or disappeared. Unchanged samples pass quietly; a count check would see nothing at all."), wrap, footer());

    let last = null;
    (async () => {
      for (const f of files) {
        if (!alive()) return;
        tabs.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.file === f.file));
        const hits = hitsIn(f.file);
        fname.firstChild.textContent = f.file;
        fname.lastChild.textContent = `${fmt(f.n_b || hits.length)} samples`;
        last = await sweep(field, f, hits, alive, (k) => {
          counts[k] = (counts[k] || 0) + 1; drawLegend();
          counterN.textContent = Object.values(counts).reduce((x, y) => x + y, 0);
        });
        const t = tabs.querySelector(`[data-file="${CSS.escape(f.file)}"]`); if (t) t.classList.add(hits.length ? "hit" : "ok");
      }
      if (!alive()) return;
      if (!total) counter.lastChild.textContent = "samples tripped the wire: nothing changed";
      await wait(500);
      if (!alive() || !last) return;
      drawFlows(wrap, flows, last, cards);
      const redraw = () => { if (alive() && document.body.contains(flows)) drawFlows(wrap, flows, last, cards, true); else removeEventListener("resize", redraw); };
      addEventListener("resize", redraw);
    })();
  }

  function analysisCard(a) {
    const touched = doc.findings.filter((f) => (f.affects_analyses || []).includes(a.id));
    const el = h("div", { class: "card acard", "data-a": a.id },
      h("div", { class: "t" }, h("span", { class: "aid" }, a.id), pill(a.verdict)),
      h("h3", {}, a.title));
    const b = a.before || {}, n = a.after || {};
    let marker = null, target = null;
    if (typeof b.difference === "number" && typeof n.difference === "number") {
      const tol = (doc.settings && doc.settings.A1_difference_rel_tolerance) ?? 0.05;
      const lo = b.difference * (1 - 2.5 * tol), hi = b.difference * (1 + 2.5 * tol);
      const at = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
      marker = h("div", { class: "m new", style: `left:${at(b.difference)}%` });
      target = `${at(n.difference)}%`;
      el.append(h("div", { class: "gauge", role: "img", "aria-label": `${b.difference} before, ${n.difference} now, tolerance ±${Math.round(tol * 100)}%` },
        h("div", { class: "ax" }), h("div", { class: "band", style: `left:${at(b.difference * (1 - tol))}%;right:${100 - at(b.difference * (1 + tol))}%` }),
        h("div", { class: "m", style: `left:${at(b.difference)}%` }), marker),
        h("div", { class: "gl" }, h("span", {}, `was ${b.difference}`), h("span", {}, `±${Math.round(tol * 100)}%`), h("span", {}, `now ${n.difference}`)));
    }
    if (!touched.length) el.append(h("span", { class: "untouched" }, "✓ untouched"));
    el.append(h("p", {}, firstSentence(a.why)));
    return { el, a, touched, light() {
      el.classList.add(touched.length ? (a.verdict === "Ready" ? "lit-green" : "lit-amber") : "lit-green");
      if (marker && target) requestAnimationFrame(() => { marker.style.left = target; });
    } };
  }

  function sweep(holder, f, hits, alive, bump) {
    const n = Math.max(f.n_b || 0, hits.length, 1);
    const W = 720, gap = n > 900 ? 10 : n > 400 ? 13 : 18;
    const cols = Math.floor(W / gap), rows = Math.ceil(n / cols), H = rows * gap + 10;
    const svg = s("svg", { class: "field", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${f.file}: ${n} samples, ${hits.length} tripped the wire` });
    const pos = new Map(), taken = new Set();
    for (const hit of hits) {
      let p = [...hit.id].reduce((acc, c) => (acc * 31 + c.charCodeAt(0)) >>> 0, 7) % n;
      while (taken.has(p)) p = (p + 1) % n;
      taken.add(p); pos.set(p, hit);
    }
    const r = Math.max(2, gap * 0.26), dots = [];
    const xy = (i) => [(i % cols) * gap + gap / 2, Math.floor(i / cols) * gap + gap / 2 + 5];
    for (let i = 0; i < n; i++) { const [cx, cy] = xy(i); const c = s("circle", { class: "d", cx, cy, r }); dots.push(c); svg.append(c); }
    const top = s("g"); svg.append(top);
    const glow = s("line", { class: "laser-glow", x1: -6, x2: W + 6, y1: 0, y2: 0 });
    const laser = s("line", { class: "laser", x1: -6, x2: W + 6, y1: 0, y2: 0 });
    svg.append(glow, laser);
    holder.replaceChildren(svg);
    const placed = [];

    const trip = (i) => {
      const hit = pos.get(i), [cx, cy] = xy(i), col = colorOf(hit.f.kind);
      dots[i].style.display = "none";
      const g = s("g", { tabindex: "0", role: "img", "aria-label": `${hit.id}: ${kindName(hit.f.kind)}` });
      g.append(s("circle", { class: "halo", cx, cy, r: r * 2.2, stroke: col }));
      g.append(s("circle", { class: "hit-core", cx, cy, r: r * 2.2, fill: col }));
      g.addEventListener("mousemove", (ev) => tip(ev, `${hit.id} · ${kindName(hit.f.kind)} (${hit.f.id})`));
      g.addEventListener("mouseleave", hideTip);
      g.addEventListener("click", () => openSample(hit.id));
      top.append(g);
      placed.push({ hit, el: g.lastChild });
      bump(hit.f.kind);
      if (hit.f.kind === "sample_swap") {
        const mate = placed.find((p) => p.hit.f === hit.f && p.hit.id !== hit.id);
        if (mate) {
          const x2 = +mate.el.getAttribute("cx"), y2 = +mate.el.getAttribute("cy");
          top.insertBefore(s("path", { class: "arc", stroke: col, d: `M${cx},${cy} Q${(cx + x2) / 2},${Math.min(cy, y2) - 34} ${x2},${y2}` }), top.firstChild);
        }
      }
      laser.style.stroke = col; setTimeout(() => { laser.style.stroke = ""; }, 240);
    };

    if (reduce) {
      dots.forEach((d) => d.classList.add("seen")); for (const i of pos.keys()) trip(i);
      laser.remove(); glow.remove();
      return Promise.resolve({ svg, placed });
    }
    const dur = hits.length ? 2800 : 650;
    return new Promise((done) => {
      const t0 = performance.now(); let row = -1;
      const frame = (now) => {
        if (!alive()) return done(null);
        const k = Math.min(1, (now - t0) / dur), y = k * H;
        for (const el of [laser, glow]) { el.setAttribute("y1", y); el.setAttribute("y2", y); }
        const upto = Math.min(rows - 1, Math.floor((y - 5) / gap));
        while (row < upto) { row++; for (let i = row * cols; i < Math.min(n, (row + 1) * cols); i++) { dots[i].classList.add("seen"); if (pos.has(i)) trip(i); } }
        if (k < 1) requestAnimationFrame(frame);
        else { laser.remove(); glow.remove(); done({ svg, placed }); }
      };
      requestAnimationFrame(frame);
    });
  }

  function drawFlows(wrap, flows, scan, cards, instant) {
    flows.replaceChildren();
    const box = wrap.getBoundingClientRect();
    flows.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
    const stacked = getComputedStyle(wrap).gridTemplateColumns.split(" ").length < 2;
    if (stacked) { cards.forEach((c, k) => setTimeout(() => c.light(), instant ? 0 : 300 + k * 250)); return; } // no room for curves
    let i = 0;
    for (const c of cards) {
      if (!c.touched.length) { setTimeout(() => c.light(), instant ? 0 : 900); continue; }
      const cb = c.el.getBoundingClientRect();
      const tx = stacked ? cb.left + cb.width / 2 - box.left : cb.left - box.left;
      const ty = stacked ? cb.top - box.top : cb.top + cb.height * 0.62 - box.top;
      for (const p of scan.placed) {
        if (!c.touched.includes(p.hit.f)) continue;
        const db = p.el.getBoundingClientRect();
        const sx = db.left + db.width / 2 - box.left, sy = db.top + db.height / 2 - box.top;
        const d = stacked ? `M${sx},${sy} C${sx},${(sy + ty) / 2} ${tx},${(sy + ty) / 2} ${tx},${ty}`
                          : `M${sx},${sy} C${(sx + tx) / 2},${sy} ${(sx + tx) / 2},${ty} ${tx},${ty}`;
        const path = s("path", { d, stroke: colorOf(p.hit.f.kind) });
        flows.append(path);
        if (!instant && !reduce) {
          const L = path.getTotalLength();
          path.style.strokeDasharray = L; path.style.strokeDashoffset = L;
          path.style.transition = `stroke-dashoffset 1.1s cubic-bezier(.4,0,.2,1) ${i * 70}ms`;
          requestAnimationFrame(() => requestAnimationFrame(() => { path.style.strokeDashoffset = 0; }));
        }
        i++;
      }
      setTimeout(() => c.light(), instant || reduce ? 0 : 1100 + i * 70);
    }
  }

  // ---------- findings ----------
  function viewFindings(v, focusId) {
    const q = ($("search").value || "").trim().toUpperCase();
    const open = openReviews().length;
    v.append(head("Step 2 · Findings", doc.findings.length ? `${doc.findings.length} change${doc.findings.length > 1 ? "s" : ""}, each with its evidence` : "Nothing changed",
      "Every finding names the exact samples, says how sure Driftwire is and what it can't know, and waits for a person. Sample IDs open the tissue slide in NCI's Imaging Data Commons viewer.",
      h("span", { class: "pill" }, h("i", { style: `background:${open ? "var(--wire)" : "var(--ready)"}` }, open ? open : "✓"), open ? `${open} waiting for review` : "All reviewed")));
    const list = h("div", { class: "flist" });
    doc.findings.forEach((f, i) => {
      const reps = repairsFor(f);
      const dec = reps.map((r) => decisions[r.id]).filter(Boolean);
      const card = h("article", { class: "card fcard enter", id: `f-${f.id}`, style: `animation-delay:${i * 70}ms` },
        h("div", { class: "stripe", style: `background:${colorOf(f.kind)}` }),
        h("div", { class: "body" },
          h("div", { class: "ftop" },
            h("span", { class: "kchip", style: `background:${colorOf(f.kind)}` }, kindName(f.kind)),
            h("span", { class: "idchip" }, f.id), h("span", { class: "grow" }),
            dec.length ? dec.map((d) => h("span", { class: `decided ${d.decision}` }, DECISION[d.decision])) : f.needs_human_review ? h("span", { class: "idchip" }, "needs a person") : null),
          h("p", { class: "fsum" }, f.summary),
          h("dl", { class: "fgrid" },
            h("div", {}, h("dt", {}, "Severity"), h("dd", {}, `${f.severity}. ${f.severity_reason || ""}`)),
            h("div", {}, h("dt", {}, "Confidence"), h("dd", {}, f.confidence || "–")),
            h("div", {}, h("dt", {}, "Affects"), h("dd", {}, (f.affects_analyses || []).join(", ") || "no reference analysis")),
            h("div", {}, h("dt", {}, "Proposed repair"), h("dd", {}, reps.map((r) => ACTION[r.action] || r.action).join("; ") || "none"))),
          h("div", { class: "chips" }, samplesOf(f).map((e) => {
            const m = q && e.id.toUpperCase().includes(q) ? " match" : "";
            return e.url ? h("a", { class: `sid${m}`, href: e.url, target: "_blank", rel: "noopener", title: e.note || "Open the tissue slide" }, e.id)
                         : h("span", { class: `sid${m}`, title: e.note || "" }, e.id);
          })),
          f.limitation ? h("div", { class: "lim" }, `Can't know: ${f.limitation}`) : null,
          reps.length ? h("div", { class: "fact" }, h("button", { class: `btn small${dec.length ? "" : " navy"}`, type: "button", onclick: () => openDrawer(f) }, dec.length ? "Change review" : "Review")) : null));
      list.append(card);
    });
    v.append(list, footer());
    if (focusId) {
      const el = $(`f-${focusId}`);
      if (el) { setTimeout(() => { el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1800); }, 120); }
    }
  }

  function openSample(id) {
    const f = doc.findings.find((x) => samplesOf(x).some((e) => e.id === id));
    $("search").value = id;
    if (f) { location.hash = "findings"; setTimeout(() => { $("view").replaceChildren(); viewFindings($("view"), f.id); }, 0); }
  }

  // ---------- reviewer drawer ----------
  function openDrawer(f) {
    const reps = repairsFor(f);
    const dr = $("drawer"), scrim = $("scrim");
    const close = () => { dr.hidden = true; scrim.hidden = true; document.removeEventListener("keydown", esc); };
    const esc = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", esc);
    scrim.onclick = close;
    const blocks = reps.map((r) => {
      const prev = decisions[r.id] || {};
      const role = h("select", { "aria-label": "Your role" }, ROLES.map((x) => h("option", { value: x, selected: prev.reviewer_role === x || null }, x)));
      if (!prev.reviewer_role) role.value = r.action === "flag_for_review" ? "Data provider" : "Curator";
      const reason = h("textarea", { placeholder: "Why? (required, saved with the decision)" });
      reason.value = prev.reason || "";
      const err = h("div", { class: "err", "aria-live": "polite" });
      const eff = r.preview && (r.preview.analyses || []).map((x) => x.summary).join(" ") || (r.preview && r.preview.note) || "";
      const choose = (d) => {
        if (!reason.value.trim()) { err.textContent = "Add a reason first: every decision is saved with one."; reason.focus(); return; }
        decisions[r.id] = { repair_id: r.id, decision: d, reason: reason.value.trim(), reviewer_role: role.value, original_preserved: true };
        store.set(`tw-dec:${key}`, decisions);
        updateBell(); toast(`${r.id}: ${DECISION[d]} by ${role.value}. Nothing was changed in the data.`);
        close(); route();
      };
      const b = (d, cls, text) => h("button", { class: `btn ${cls}${prev.decision === d ? " sel" : ""}`, type: "button", onclick: () => choose(d) }, text);
      return h("div", { class: "repair-block" },
        h("div", { class: "repair" }, h("div", { class: "eyebrow" }, `${r.id} · proposed repair`), h("div", { class: "act" }, ACTION[r.action] || r.action),
          h("p", {}, r.justification), h("p", {}, `${(r.targets || []).length} sample(s): ${(r.targets || []).map((t) => t.id).join(", ")}`),
          eff ? h("p", { class: "eff" }, `If approved: ${eff}`) : null),
        h("label", { class: "field-l" }, "Your role", role),
        h("label", { class: "field-l" }, "Reason", reason), err,
        h("div", { class: "dbtns" }, b("approve", "go", "✓ Approve"), b("reject", "", "Reject"), b("request_more_evidence", "", "Ask for evidence")));
    });
    dr.replaceChildren(
      h("div", { class: "dhead" }, h("div", {}, h("div", { class: "eyebrow" }, `${f.id} · ${kindName(f.kind)}`), h("h2", {}, "Reviewer")),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: close }, "✕")),
      h("div", { class: "dbody" }, h("p", { style: "margin:0;color:var(--ink-2);font-size:14px" }, f.summary), blocks,
        h("p", { class: "note" }, "A decision is a record, not an action: the data is never changed here. Export puts your decisions into findings.json.")));
    dr.hidden = false; scrim.hidden = false;
    const first = dr.querySelector("textarea"); if (first) setTimeout(() => first.focus(), 50);
  }

  // ---------- questions ----------
  function viewQuestions(v) {
    const qs = doc.questions || [];
    const counts = qs.reduce((m, q) => ((m[q.verdict] = (m[q.verdict] || 0) + 1), m), {});
    let filter = "all";
    const grid = h("div", { class: "qgrid" });
    const draw = () => {
      const show = qs.filter((q) => filter === "all" || q.intended_use === filter || q.verdict === filter);
      grid.replaceChildren(...show.map((q, i) => {
        const card = h("button", { class: "card q", type: "button", "aria-expanded": "false", style: `animation-delay:${i * 90}ms` },
          h("div", { class: "use" }, USE[q.intended_use] || q.intended_use || ""),
          h("h3", {}, q.title), h("div", {}, pill(q.verdict)),
          h("p", { class: "why" }, firstSentence(q.why)),
          (q.checks || []).length ? h("div", { class: "checks" }, q.checks.map((c) => h("span", { class: `ck ${c.status}` }, c.name.replace(/_/g, " ")))) : null,
          h("div", { class: "more" }, h("div", {}, q.why),
            (q.checks || []).length ? h("ul", {}, q.checks.map((c) => h("li", {}, h("b", {}, `${c.name.replace(/_/g, " ")} (${c.status}): `), c.summary || ""))) : null,
            q.acceptable_limitations ? h("p", { style: "margin:8px 0 0" }, h("b", {}, "Acceptable: "), q.acceptable_limitations) : null));
        card.addEventListener("click", () => { const o = card.classList.toggle("open"); card.setAttribute("aria-expanded", String(o)); });
        return card;
      }));
    };
    const fb = (val, label) => h("button", { class: `fbtn${filter === val ? " on" : ""}`, type: "button", onclick: (e) => {
      filter = val; e.currentTarget.parentElement.querySelectorAll(".fbtn").forEach((b) => b.classList.remove("on")); e.currentTarget.classList.add("on"); draw(); } }, label);
    v.append(head("Step 3 · Questions", "Same release, different answers",
      "Whether a release is usable depends on what you want to do with it. Each question card has its own verdict, a written reason, and the checks that ran. A check that couldn't run never counts as a pass. Click a card for the detail."),
      h("div", { class: "filters" }, fb("all", `All ${qs.length}`), fb("descriptive", "Describe the data"), fb("model_training", "Train a model"),
        ...["Ready", "Conditional", "Blocked", "Insufficient Evidence"].filter((x) => counts[x]).map((x) => fb(x, `${x} (${counts[x]})`))),
      grid, footer());
    draw();
  }

  // ---------- next ----------
  function viewNext(v) {
    const ns = doc.next_steps || {};
    const steps = ns.steps || [];
    const reps = doc.repairs || [];
    const decided = reps.filter((r) => decisions[r.id]).length;
    const auto = (st) => (st.refs || []).some((r) => decisions[r]);
    const list = h("ol", { class: "todo" }, steps.map((st, i) => {
      const k = String(st.step || i + 1);
      const on = !!ticks[k] || auto(st);
      const li = h("li", { class: on ? "done" : "" },
        h("span", { class: "num" }, k),
        h("div", {}, h("div", { class: "who" }, st.who), h("div", { class: "act" }, st.action),
          st.why ? h("div", { class: "why" }, st.why) : null, st.effect ? h("div", { class: "eff" }, `If approved: ${st.effect}`) : null),
        h("button", { class: `tick${on ? " on" : ""}`, type: "button", "aria-pressed": String(on), "aria-label": `Mark step ${k} done`,
          title: auto(st) ? "Done: a review decision was recorded" : "Mark done",
          onclick: () => { ticks[k] = !ticks[k]; store.set(`tw-todo:${key}`, ticks); route(); } }, "✓"));
      return li;
    }));
    const sev = doc.findings.reduce((m, f) => ((m[f.severity] = (m[f.severity] || 0) + 1), m), {});
    const qv = (doc.questions || []).reduce((m, q) => ((m[q.verdict] = (m[q.verdict] || 0) + 1), m), {});
    const done = steps.filter((st, i) => ticks[String(st.step || i + 1)] || auto(st)).length;
    v.append(head("Step 4 · Next", "What to do next",
      "An ordered plan for the people involved, most serious first. Steps tick themselves when you record a review decision.", h("div", {}, pill(doc.verdict))),
      h("div", { class: "nextgrid" },
        h("div", { class: "card pad enter" }, h("div", { class: "eyebrow", style: "margin-bottom:6px" }, `What to do next · ${done} of ${steps.length} done`), list,
          ns.all_repairs_together ? h("div", { class: "together" }, h("b", {}, "If every proposed repair were approved: "), ns.all_repairs_together) : null),
        h("div", { class: "card pad enter", style: "animation-delay:.08s" }, h("div", { class: "eyebrow" }, "Review"),
          h("div", { class: "meter2" }, h("span", { style: `width:${reps.length ? (decided / reps.length) * 100 : 100}%` })),
          h("div", { class: "stat" }, h("span", {}, "Repairs decided"), h("b", {}, `${decided} / ${reps.length}`)),
          ...["high", "medium", "low"].filter((x) => sev[x]).map((x) => h("div", { class: "stat" }, h("span", {}, `${x[0].toUpperCase() + x.slice(1)}-severity findings`), h("b", {}, sev[x]))),
          ...Object.entries(qv).map(([k, n]) => h("div", { class: "stat" }, h("span", {}, pill(k)), h("b", {}, `${n} question${n > 1 ? "s" : ""}`))),
          h("div", { style: "margin-top:14px;display:flex;gap:8px;flex-wrap:wrap" },
            h("button", { class: "btn small navy", type: "button", onclick: exportDoc }, "Export findings.json"),
            openReviews().length ? h("button", { class: "btn small", type: "button", onclick: () => go("findings") }, "Review findings") : null)),
        h("div", { class: "cant enter", style: "animation-delay:.16s" }, cantIcon(), h("h3", {}, "What Driftwire can't tell you"),
          h("ul", {}, (ns.cannot_tell || []).map((c) => h("li", {}, c))))),
      footer());
  }
  function cantIcon() {
    return icon('<rect x="4" y="5" width="16" height="15" rx="2.5" fill="none" stroke="var(--ink-2)" stroke-width="1.5"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4" stroke="var(--ink-2)" stroke-width="1.5" stroke-linecap="round"/><circle cx="17.5" cy="17.5" r="4.2" fill="var(--ready)"/><path d="m15.6 17.6 1.3 1.3 2.4-2.6" stroke="#fff" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 13h5M8 16h3" stroke="var(--muted)" stroke-width="1.5" stroke-linecap="round"/>');
  }

  function footer() {
    return h("footer", { class: "foot" },
      h("div", {}, doc.research_use_only || "Research use only. Not a diagnosis, treatment advice, risk score or clinical claim."),
      h("div", {}, "Data: TCGA-BRCA frozen release via the OncoSys challenge. Slides: NCI Imaging Data Commons (CC BY 3.0). This page opens recorded runs; Driftwire itself runs on your machine: python -m driftwire diff <trusted> <new>."));
  }

  // ---------- export ----------
  function exportDoc() {
    const order = (doc.repairs || []).map((r) => r.id);
    const out = JSON.parse(JSON.stringify(doc));
    delete out.replay;
    out.decisions = Object.values(decisions).filter((d) => order.includes(d.repair_id))
      .map((d) => ({ repair_id: d.repair_id, decision: d.decision, reason: d.reason, reviewer_role: d.reviewer_role, original_preserved: true }))
      .sort((a, b) => order.indexOf(a.repair_id) - order.indexOf(b.repair_id));
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
    const a = h("a", { href: URL.createObjectURL(blob), download: "findings.reviewed.json" });
    document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    toast(`Exported with ${out.decisions.length} review decision${out.decisions.length === 1 ? "" : "s"}.`);
  }

  // ---------- loading & wiring ----------
  function readFile(file) {
    const rd = new FileReader();
    rd.onload = () => {
      try { accept(JSON.parse(rd.result)); toast(`Opened ${file.name}`); go("run"); }
      catch (e) { toast(`Couldn't open ${file.name}: ${e.message}`); }
    };
    rd.readAsText(file);
  }

  function initTheme() {
    const saved = store.get("tw-theme", null);
    if (saved) document.documentElement.dataset.theme = saved;
    $("theme").addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const nx = cur === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = nx; store.set("tw-theme", nx);
      if ((location.hash || "#run") === "#scan") route();
    });
  }

  function init() {
    renderNav(); initTheme();
    addEventListener("hashchange", route);
    $("file").addEventListener("change", (e) => { if (e.target.files[0]) readFile(e.target.files[0]); e.target.value = ""; });
    $("export").addEventListener("click", () => doc && exportDoc());
    $("bell").addEventListener("click", () => {
      if (!doc) return;
      const f = openReviews()[0];
      if (!f) { toast("Nothing is waiting for review."); return; }
      go("findings"); setTimeout(() => openDrawer(f), 80);
    });
    $("search").addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || !doc) return;
      const q = e.target.value.trim().toUpperCase(); if (!q) return;
      const f = doc.findings.find((x) => samplesOf(x).some((s2) => s2.id.toUpperCase().includes(q)));
      if (!f) { toast(`No finding involves a sample matching "${e.target.value.trim()}".`); return; }
      if (location.hash !== "#findings") location.hash = "findings";
      setTimeout(() => { $("view").replaceChildren(); viewFindings($("view"), f.id); }, 0);
    });
    let depth = 0;
    addEventListener("dragenter", (e) => { e.preventDefault(); depth++; $("drop").hidden = false; });
    addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("drop").hidden = true; } });
    addEventListener("dragover", (e) => e.preventDefault());
    addEventListener("drop", (e) => { e.preventDefault(); depth = 0; $("drop").hidden = true; const f = e.dataTransfer.files[0]; if (f) readFile(f); });

    route();
    fetch("data/practice.replay.json")
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((d) => { accept(d); route(); })
      .catch(() => { $("view").replaceChildren(h("div", { class: "card pad" }, "No recorded run found. Drop a Driftwire findings.json on the page to open it.")); });
  }
  init();
})();
