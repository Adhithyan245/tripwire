/* Tripwire replay: steps through one real Tripwire run (findings.json, optionally with a "replay" block from
   scripts/build_replay.py). Every number shown comes from that file; nothing is computed or invented here
   beyond layout. */
(() => {
  "use strict";

  const KIND = {
    sample_swap: "Swapped profiles",
    duplicate: "Copied profiles",
    membership_change: "Samples lost or added",
    label_change: "Changed labels",
    sample_type_change: "Sample type changed",
    id_format_change: "Reformatted IDs",
    value_shift: "Values shifted",
    coverage_loss: "Coverage lost",
  };
  const ICON = { Ready: "✓", Conditional: "!", Blocked: "✕", "Insufficient Evidence": "?" };
  const USE = { descriptive: "Describe the data", model_training: "Train a model" };
  const STAGES = [
    ["releases", "Two releases"],
    ["scan", "Scan every sample"],
    ["changes", "What changed"],
    ["impact", "What it touches"],
    ["rerun", "Rerun and compare"],
    ["questions", "Ready for which question?"],
    ["next", "What to do next"],
  ];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  let doc = null, stage = 0, playing = false, timer = null, kindColor = {}, scanDone = false;

  // ---------- tiny DOM helper (text is always set as text, never as HTML) ----------
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
  const svgNS = "http://www.w3.org/2000/svg";
  function s(tag, attrs) {
    const el = document.createElementNS(svgNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    return el;
  }
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : n);
  const firstSentence = (t) => (t || "").split(/(?<=\.)\s/)[0];

  function pill(verdict, big) {
    const cls = verdict === "Insufficient Evidence" ? "Insufficient" : verdict;
    return h("span", { class: `pill ${cls}${big ? " big" : ""}` }, h("i", { "aria-hidden": "true" }, ICON[verdict] || "•"), verdict);
  }
  function kindName(k) { return KIND[k] || (k || "change").replace(/_/g, " "); }
  function colorOf(k) { return kindColor[k] || "var(--c8)"; }
  function samplesOf(f) { return (f.evidence || []).filter((e) => e.kind === "sample"); }

  // ---------- data ----------
  function accept(d, label) {
    if (!d || !Array.isArray(d.findings) || !Array.isArray(d.analyses)) throw new Error("Not a Tripwire findings.json");
    doc = d;
    kindColor = {};
    let i = 1;
    for (const f of d.findings) if (!(f.kind in kindColor)) kindColor[f.kind] = i <= 8 ? `var(--c${i++})` : "var(--c8)";
    const rel = (d.data && d.data.releases) || [];
    $("relA").textContent = (d.replay && d.replay.release_a) || (rel[0] && rel[0].name) || "release A";
    $("relB").textContent = (d.replay && d.replay.release_b) || (rel[1] && rel[1].name) || "release B";
    const ov = $("overall");
    ov.replaceChildren(h("span", { class: "lbl" }, label || "Overall"), pill(d.verdict || "Ready", true));
    if (d.research_use_only) $("ruo").textContent = d.research_use_only;
    scanDone = false;
    go(0);
  }

  function filesOf(d) {
    if (d.replay && Array.isArray(d.replay.files)) return d.replay.files;
    // Plain findings.json: only the files the findings mention, sized by what is known.
    const names = new Set();
    for (const f of d.findings) for (const e of f.evidence || []) if (e.file) names.add(e.file);
    return [...names].map((file) => ({ file, n_a: null, n_b: null, in_b: true }));
  }

  function hitsIn(file) {
    const out = [];
    for (const f of doc.findings) for (const e of samplesOf(f)) if (e.file === file) out.push({ id: e.id, f, e });
    return out;
  }

  // ---------- navigation ----------
  function renderChips() {
    const nav = $("stages");
    nav.replaceChildren(...STAGES.map(([, label], i) =>
      h("button", { class: `chip${i === stage ? " on" : ""}${i < stage ? " done" : ""}`, type: "button",
        "aria-current": i === stage ? "step" : null, onclick: () => { stop(); go(i); } },
        h("b", {}, i + 1), label)));
    const on = nav.children[stage];
    if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "center", behavior: reduce ? "auto" : "smooth" });
    $("bar").style.width =`${((stage + 1) / STAGES.length) * 100}%`;
    $("prev").disabled = stage === 0;
    $("next").disabled = stage === STAGES.length - 1;
  }

  function go(i) {
    stage = Math.max(0, Math.min(STAGES.length - 1, i));
    renderChips();
    const root = $("stage");
    root.replaceChildren();
    const fn = { releases, scan, changes, impact, rerun, questions, next }[STAGES[stage][0]];
    const done = fn(root);
    if (playing) schedule(done);
  }

  function schedule(done) {
    clearTimeout(timer);
    if (stage >= STAGES.length - 1) { stop(); return; }
    const wait = STAGES[stage][0] === "scan" ? null : 6500;
    if (wait === null && done && done.then) done.then(() => { if (playing) timer = setTimeout(() => go(stage + 1), 2200); });
    else timer = setTimeout(() => go(stage + 1), wait || 6500);
  }
  function play() { playing = true; $("play").textContent = "❚❚ Pause"; if (stage === STAGES.length - 1) go(0); else go(stage); }
  function stop() { playing = false; clearTimeout(timer); $("play").textContent = "▶ Play"; }

  function lead(title, text, right) {
    return h("div", { class: "lead" }, h("div", {}, h("h2", {}, title), text ? h("p", {}, text) : null), right || null);
  }

  // ---------- 1. releases ----------
  function releases(root) {
    const files = filesOf(doc);
    const card = h("div", { class: "card fade-in" },
      lead("Two releases of the same dataset",
        "A trusted release the team already analysed, and a new one that looks the same from the outside. " +
        "Same files, same sample counts. Tripwire's job: find what changed inside, and whether it matters."),
      h("div", { class: "files" }, files.map((f) =>
        h("div", { class: `file${f.in_b === false ? " gone" : ""}` },
          h("div", { class: "fn" }, f.file),
          h("div", { class: "n" }, f.n_b != null ? fmt(f.n_b) : "–"),
          h("div", { class: "s" }, f.in_b === false ? "missing from the new release" :
            f.n_a != null ? (f.n_a === f.n_b ? "samples, same count as before" : `samples, was ${fmt(f.n_a)}`) : "samples")))));
    const same = files.length && files.every((f) => f.n_a != null && f.n_a === f.n_b);
    if (same) card.append(h("div", { class: "callout" }, h("b", {}, "A count check sees nothing. "),
      `Every file holds exactly as many samples as before. Whatever changed, it changed inside the data.`));
    root.append(card);
  }

  // ---------- 2. scan ----------
  function scan(root) {
    // clean files first, so the scan ends on the file where samples tripped the wire
    const files = filesOf(doc).filter((f) => f.in_b !== false)
      .sort((x, y) => (hitsIn(x.file).length > 0) - (hitsIn(y.file).length > 0));
    const total =doc.findings.reduce((n, f) => n + samplesOf(f).length, 0);
    const tabs = h("div", { class: "file-tabs" }, files.map((f) => h("span", { class: "ftab", "data-file": f.file }, f.file)));
    const fieldHead = h("div", { class: "field-head" }, h("span", { class: "fn" }, ""), h("span", { class: "count" }, ""));
    const holder = h("div", { class: "field-wrap" });
    const tally = h("div", { class: "tally" }, "0", h("small", {}, " samples tripped the wire"));
    const legend = h("div", { class: "legend" });
    const card = h("div", { class: "card fade-in" },
      lead("Scan every sample", "Each sample's data gets a fingerprint in both releases. A sample trips the wire when its " +
        "fingerprint moved to another sample, was copied, or disappeared. Unchanged samples pass quietly."),
      h("div", { class: "scan" },
        h("div", {}, tabs, fieldHead, holder),
        h("div", { class: "side" }, tally, h("div", { class: "sub" }, `of ${fmt(files.reduce((n, f) => n + (f.n_b || 0), 0)) || "all"} sample entries across ${files.length} files`), legend)));
    root.append(card);

    const counts = {};
    const bump = (k) => {
      counts[k] = (counts[k] || 0) + 1;
      legend.replaceChildren(...Object.keys(kindColor).map((kk) =>
        h("div", { class: "row" }, h("span", { class: "sw", style: `background:${colorOf(kk)}` }), kindName(kk), h("span", { class: "n" }, counts[kk] || 0))));
      tally.firstChild.textContent = String(Object.values(counts).reduce((a, b) => a + b, 0));
    };
    legend.replaceChildren(...Object.keys(kindColor).map((kk) =>
      h("div", { class: "row" }, h("span", { class: "sw", style: `background:${colorOf(kk)}` }), kindName(kk), h("span", { class: "n" }, 0))));

    let cancelled = false;
    const mine = stage;
    const alive = () => !cancelled && stage === mine && document.body.contains(card);

    return (async () => {
      for (const f of files) {
        if (!alive()) return;
        for (const t of tabs.children) t.classList.toggle("on", t.dataset.file === f.file);
        const hits = hitsIn(f.file);
        fieldHead.firstChild.textContent = f.file;
        fieldHead.lastChild.textContent = `${fmt(f.n_b || hits.length)} samples`;
        await sweep(holder, f, hits, bump, alive);
        const tab = [...tabs.children].find((t) => t.dataset.file === f.file);
        if (tab) tab.classList.add(hits.length ? "tripped" : "clean");
        if (hits.length && alive()) await wait(reduce ? 0 : 1600);
      }
      scanDone = true;
      if (alive() && total === 0) tally.lastChild.textContent = " samples tripped the wire: nothing changed";
    })();
  }

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  function sweep(holder, f, hits, bump, alive) {
    const n = Math.max(f.n_b || 0, hits.length, 1);
    const W = 640, gap = n > 900 ? 9 : n > 400 ? 11 : 16;
    const cols = Math.floor(W / gap), rows = Math.ceil(n / cols), H = rows * gap + 8;
    const svg = s("svg", { class: "field", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": `${f.file}: ${n} samples, ${hits.length} tripped` });
    // place changed samples at stable, distinct positions
    const pos = new Map(), taken = new Set();
    for (const hit of hits) {
      let p = [...hit.id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % n;
      while (taken.has(p)) p = (p + 1) % n;
      taken.add(p); pos.set(p, hit);
    }
    const dots = [];
    const r = Math.max(2, gap * 0.3);
    for (let i = 0; i < n; i++) {
      const c = s("circle", { cx: (i % cols) * gap + gap / 2, cy: Math.floor(i / cols) * gap + gap / 2 + 4, r });
      dots.push(c); svg.append(c);
    }
    const glow = s("line", { class: "wire-glow", x1: 0, x2: W, y1: 0, y2: 0 });
    const wire = s("line", { class: "wire", x1: 0, x2: W, y1: 0, y2: 0 });
    svg.append(glow, wire);
    holder.replaceChildren(svg);

    const trip = (i) => {
      const hit = pos.get(i), dot = dots[i];
      dot.classList.add("hit");
      dot.setAttribute("r", r * 1.9);
      dot.style.fill = colorOf(hit.f.kind);
      dot.addEventListener("mousemove", (ev) => tip(ev, `${hit.id} · ${kindName(hit.f.kind)} (${hit.f.id})`));
      dot.addEventListener("mouseleave", hideTip);
      bump(hit.f.kind);
      // link a swap's two samples
      const partner = hit.f.kind === "sample_swap" && hits.find((o) => o.f === hit.f && o.id !== hit.id);
      if (partner) {
        const j = [...pos.entries()].find(([, v]) => v === partner);
        if (j && dots[j[0]].classList.contains("hit")) {
          const a = dots[i], b = dots[j[0]];
          const x1 = +a.getAttribute("cx"), y1 = +a.getAttribute("cy"), x2 = +b.getAttribute("cx"), y2 = +b.getAttribute("cy");
          svg.insertBefore(s("path", { class: "trip", stroke: colorOf(hit.f.kind), "stroke-dasharray": "4 3",
            d: `M${x1},${y1} Q${(x1 + x2) / 2},${Math.min(y1, y2) - 30} ${x2},${y2}` }), dots[0]);
        }
      }
      wire.style.stroke = colorOf(hit.f.kind);
      setTimeout(() => { wire.style.stroke = ""; }, 260);
    };

    if (reduce) {
      dots.forEach((d) => d.classList.add("seen"));
      for (const i of pos.keys()) trip(i);
      wire.remove(); glow.remove();
      return Promise.resolve();
    }
    const dur = hits.length ? 2600 : 700;
    return new Promise((done) => {
      const t0 = performance.now();
      let row = -1;
      const frame = (now) => {
        if (!alive()) return done();
        const k = Math.min(1, (now - t0) / dur);
        const y = k * H;
        for (const el of [wire, glow]) { el.setAttribute("y1", y); el.setAttribute("y2", y); }
        const upto = Math.min(rows - 1, Math.floor((y - 4) / gap));
        while (row < upto) {
          row++;
          for (let i = row * cols; i < Math.min(n, (row + 1) * cols); i++) {
            dots[i].classList.add("seen");
            if (pos.has(i)) trip(i);
          }
        }
        if (k < 1) requestAnimationFrame(frame);
        else { wire.remove(); glow.remove(); done(); }
      };
      requestAnimationFrame(frame);
    });
  }

  // ---------- 3. changes ----------
  function changes(root) {
    const card = h("div", { class: "card fade-in" },
      lead(doc.findings.length ? `${doc.findings.length} change${doc.findings.length > 1 ? "s" : ""} found` : "Nothing changed",
        "Each finding names the exact samples, cites the evidence, and says how sure Tripwire is and what it can't know. " +
        "Sample IDs open the tissue slide in NCI's Imaging Data Commons viewer."),
      h("div", { class: "findings" }, doc.findings.map((f) =>
        h("article", { class: "finding" },
          h("div", { class: "bar", style: `background:${colorOf(f.kind)}` }),
          h("div", {},
            h("div", { class: "meta" }, h("span", { class: "id" }, f.id), h("span", { class: "kind" }, kindName(f.kind)),
              h("span", { class: `sev ${f.severity}` }, `${f.severity} severity`),
              f.needs_human_review ? h("span", { class: "sev" }, "needs a person") : null),
            h("p", {}, f.summary),
            f.severity_reason ? h("div", { class: "reason" }, `Why ${f.severity}: ${f.severity_reason}`) : null,
            h("div", { class: "samples" }, samplesOf(f).map((e) => e.url
              ? h("a", { class: "sample", href: e.url, target: "_blank", rel: "noopener", title: e.note || "Open the tissue slide" }, e.id)
              : h("span", { class: "sample", title: e.note || "" }, e.id))),
            f.limitation ? h("div", { class: "limit" }, `Limitation: ${f.limitation}`) : null)))));
    root.append(card);
  }

  // ---------- 4. impact ----------
  function impact(root) {
    const touchedFiles = new Set(doc.findings.flatMap((f) => samplesOf(f).map((e) => e.file)));
    const card = h("div", { class: "card fade-in" },
      lead("What each change touches",
        "Each analysis declares the files and fields it reads. A change only matters to an analysis that reads it, " +
        "and the analyses the map calls untouched are rerun anyway to prove it."),
      h("div", { class: "impact" }, doc.analyses.map((a) => {
        const by = doc.findings.filter((f) => (f.affects_analyses || []).includes(a.id));
        return h("div", { class: "analysis" },
          h("h3", {}, h("span", { class: "aid" }, a.id), a.title),
          h("div", { class: "reads" }, (a.inputs || []).map((x) => h("span", { class: touchedFiles.has(x) ? "hit" : "" }, x))),
          h("p", { class: "why" }, a.impact || a.why),
          by.length ? h("div", { class: "touch" }, by.map((f) => h("span", { style: `background:${colorOf(f.kind)}` }, `${f.id} ${kindName(f.kind)}`)))
            : h("div", { class: "touch" }, h("span", { style: "background:var(--ready)" }, "untouched")));
      })));
    root.append(card);
  }

  // ---------- 5. rerun ----------
  function rerun(root) {
    const st = doc.settings || {};
    const card = h("div", { class: "card fade-in" },
      lead("Rerun, then compare against the trusted release",
        "Only the numbers that could have moved are recomputed, then judged against a stated tolerance. " +
        "Inside the band: usable with care. Outside it: blocked."),
      h("div", { class: "rerun" }, doc.analyses.map((a) => panel(a, st))));
    root.append(card);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      card.querySelectorAll("[data-left]").forEach((el) => { el.style.left = el.dataset.left; });
      card.querySelectorAll("[data-w]").forEach((el) => { el.style.width = el.dataset.w; });
    }));
  }

  function panel(a, st) {
    const box = h("div", { class: "analysis" }, h("h3", {}, h("span", { class: "aid" }, a.id), a.title, pill(a.verdict)));
    const b = a.before || {}, n = a.after || {};
    if (typeof b.difference === "number" && typeof n.difference === "number") {
      const tol = st.A1_difference_rel_tolerance ?? 0.05;
      const lo = b.difference * (1 - 2.5 * tol), hi = b.difference * (1 + 2.5 * tol);
      const at = (v) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;
      box.append(h("div", { class: "meter", role: "img",
        "aria-label": `Difference ${b.difference} before, ${n.difference} after; tolerance ${Math.round(tol * 100)}%` },
        h("div", { class: "track" },
          h("div", { class: "axis" }),
          h("div", { class: "band", style: `left:${at(b.difference * (1 - tol))};right:${100 - parseFloat(at(b.difference * (1 + tol)))}%` }),
          h("div", { class: "mk a", style: `left:${at(b.difference)}` }),
          h("div", { class: "mk b", style: `left:${at(b.difference)}`, "data-left": at(n.difference) })),
        h("div", { class: "labels" }, h("span", {}, lo.toFixed(2)), h("span", {}, `±${Math.round(tol * 100)}% tolerance`), h("span", {}, hi.toFixed(2)))));
      box.append(h("dl", { class: "kv" },
        h("dt", {}, "Trusted"), h("dd", {}, `${b.difference} (${fmt(b.n_samples)} samples)`),
        h("dt", { style: "color:var(--wire)" }, "New"), h("dd", {}, `${n.difference} (${fmt(n.n_samples)} samples)`)));
    } else if (b.percent && n.percent) {
      const keys = Object.keys(b.percent);
      const max = Math.max(...keys.map((k) => Math.max(b.percent[k], n.percent[k] || 0)));
      box.append(h("div", { class: "bars", role: "img", "aria-label": "Share per group, trusted vs new" }, keys.map((k) =>
        h("div", { class: "brow" }, h("span", {}, k),
          h("div", { class: "b2" }, h("span", { class: "a", style: "width:0", "data-w": `${(b.percent[k] / max) * 100}%` }),
            h("span", { class: "b", style: "width:0", "data-w": `${((n.percent[k] || 0) / max) * 100}%` })),
          h("span", { class: "v" }, `${n.percent[k] ?? "–"}%`)))),
        h("div", { class: "key" }, h("span", { class: "ka" }, "Trusted"), h("span", { class: "kb" }, "New")));
    }
    box.append(h("p", { class: "why", style: "margin-top:12px" }, a.why));
    return box;
  }

  // ---------- 6. questions ----------
  function questions(root) {
    const qs = doc.questions || [];
    const card = h("div", { class: "card fade-in" },
      lead("Ready for which question?",
        "The same release can be fine for one research question and wrong for another. Each card shows its verdict, " +
        "the written reason, and which checks ran. A check that couldn't run never counts as a pass."),
      h("div", { class: "qgrid" }, qs.map((q, i) =>
        h("article", { class: "q reveal", style: `animation-delay:${i * 140}ms` },
          h("div", { class: "use" }, USE[q.intended_use] || q.intended_use || ""),
          h("h3", {}, q.title),
          pill(q.verdict),
          h("p", { class: "why" }, firstSentence(q.why)),
          (q.checks || []).length ? h("div", { class: "checks" }, q.checks.map((c) =>
            h("span", { class: c.status, title: c.summary || "" }, c.name.replace(/_/g, " ")))) : null))));
    if (!qs.length) card.append(h("p", {}, "This run has no question cards."));
    root.append(card);
  }

  // ---------- 7. next ----------
  function next(root) {
    const ns = doc.next_steps || {};
    const steps = ns.steps || [];
    const card = h("div", { class: "card fade-in" },
      lead("What to do next", "An ordered plan for the people involved. Nothing is changed until someone approves it.", pill(doc.verdict, true)),
      h("div", { class: "next" },
        h("div", {},
          h("ol", { class: "steps" }, steps.map((st, i) =>
            h("li", {}, h("span", { class: "num" }, st.step || i + 1),
              h("div", {}, h("div", { class: "who" }, st.who), h("div", { class: "act" }, st.action),
                st.why ? h("div", { class: "why" }, st.why) : null,
                st.effect ? h("div", { class: "eff" }, `If approved: ${st.effect}`) : null)))),
          ns.all_repairs_together ? h("div", { class: "callout together" }, h("b", {}, "All proposed repairs together: "), ns.all_repairs_together) : null),
        h("div", { class: "cant" }, h("h3", {}, "What Tripwire can't tell you"),
          h("ul", {}, (ns.cannot_tell || []).map((c) => h("li", {}, c))))));
    root.append(card);
  }

  // ---------- tooltip ----------
  function tip(ev, text) {
    const t = $("tip");
    t.textContent = text; t.hidden = false;
    t.style.left = `${Math.min(innerWidth - 290, ev.clientX + 12)}px`;
    t.style.top = `${ev.clientY + 14}px`;
  }
  function hideTip() { $("tip").hidden = true; }

  // ---------- theme ----------
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("tw-theme"); } catch (_) { /* storage blocked */ }
    if (saved) document.documentElement.dataset.theme = saved;
    $("theme").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme
        ? document.documentElement.dataset.theme === "dark"
        : matchMedia("(prefers-color-scheme: dark)").matches;
      const nextTheme = dark ? "light" : "dark";
      document.documentElement.dataset.theme = nextTheme;
      try { localStorage.setItem("tw-theme", nextTheme); } catch (_) { /* ignore */ }
    });
  }

  // ---------- loading ----------
  function readFile(file) {
    const rd = new FileReader();
    rd.onload = () => {
      try { stop(); accept(JSON.parse(rd.result), file.name); }
      catch (e) { $("stage").replaceChildren(h("div", { class: "card err" }, `Couldn't read ${file.name}: ${e.message}`)); }
    };
    rd.readAsText(file);
  }

  function init() {
    initTheme();
    $("prev").addEventListener("click", () => { stop(); go(stage - 1); });
    $("next").addEventListener("click", () => { stop(); go(stage + 1); });
    $("play").addEventListener("click", () => (playing ? stop() : play()));
    $("file").addEventListener("change", (e) => e.target.files[0] && readFile(e.target.files[0]));
    document.addEventListener("keydown", (e) => {
      if (e.target.closest && e.target.closest("input,textarea")) return;
      if (e.key === "ArrowRight") { stop(); go(stage + 1); }
      if (e.key === "ArrowLeft") { stop(); go(stage - 1); }
      if (e.key === " ") { e.preventDefault(); playing ? stop() : play(); }
    });
    let depth = 0;
    addEventListener("dragenter", (e) => { e.preventDefault(); depth++; $("drop").hidden = false; });
    addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("drop").hidden = true; } });
    addEventListener("dragover", (e) => e.preventDefault());
    addEventListener("drop", (e) => {
      e.preventDefault(); depth = 0; $("drop").hidden = true;
      const f = e.dataTransfer.files[0]; if (f) readFile(f);
    });
    const app = document.body.dataset.fullApp;
    if (app) $("fullApp").href = app;

    fetch("data/practice.replay.json")
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((d) => accept(d, "Practice run"))
      .catch(() => $("stage").replaceChildren(h("div", { class: "card" },
        "No recorded run found. Use Load a run to open a Tripwire findings.json.")));
  }

  init();
})();
