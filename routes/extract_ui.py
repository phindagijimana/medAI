"""MedAI-EPI single-page research UI (paper §21 framing).

`GET /extract/ui` renders a self-contained HTML page (no external assets,
no JS frameworks) that talks to the existing /extract/* API endpoints:

  1. Research-use acknowledgment modal on first visit per browser
  2. Left panel: paste source text; doc-type autodetected on blur via
     POST /extract/detect_doc_type; user can confirm or override
  3. Arm selector (M0 / M1 / M2)
  4. Extract button → POST /extract → renders phenotype tree with
     click-to-highlight-evidence in the source panel
  5. Health poll every 3 s until backend is ready (~30-60 s Med42 load)
  6. Download CSV (client-side flatten) and Download JSON buttons

The whole page is ~450 lines of HTML + CSS + vanilla JS. Deliberately
frameworkless so it works everywhere and reviewers can audit the client-side
logic in one file.

Framing (paper §21): all copy says "research phenotyping / structured
extraction", never "diagnostic support" or "clinical decision".
"""

from __future__ import annotations

from flask import Blueprint, Response, render_template_string


extract_ui_bp = Blueprint("extract_ui", __name__, url_prefix="/extract")


_UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>MedAI-EPI — Research Phenotyping Assistant</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f5f7fb;
    --panel: #ffffff;
    --ink: #1a2432;
    --muted: #667085;
    --accent: #004977;
    --accent-hover: #003354;
    --border: #e2e8f0;
    --highlight: #fef3c7;
    --highlight-active: #fbbf24;
    --danger: #b42318;
    --warn: #b54708;
    --ok: #067647;
    --certainty-def: #067647;
    --certainty-prob: #b54708;
    --certainty-poss: #7f56d9;
    --certainty-neg: #b42318;
    --certainty-unk: #667085;
    --certainty-nd: #94a3b8;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--ink);
    min-height: 100vh;
    font-size: 14px;
    line-height: 1.5;
  }
  header.nav {
    background: var(--accent);
    color: #fff;
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  }
  header.nav h1 { font-size: 18px; font-weight: 600; }
  header.nav .subtitle { font-size: 12px; opacity: 0.85; }
  header.nav a { color: #fff; text-decoration: none; margin-left: 18px; font-size: 13px; }
  header.nav a:hover { text-decoration: underline; }

  .disclaimer {
    background: #fff4e0;
    border-left: 4px solid #d97706;
    padding: 10px 24px;
    font-size: 13px;
    color: #422006;
  }

  .container { max-width: 1440px; margin: 0 auto; padding: 20px 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 960px) { .grid { grid-template-columns: 1fr; } }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.05);
  }
  .panel h2 { font-size: 14px; font-weight: 600; color: var(--muted);
               text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
  .panel .hint { font-size: 12px; color: var(--muted); margin-top: 6px; }

  .form-row { margin-bottom: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .form-row label { font-size: 13px; color: var(--muted); }
  select, input, textarea, button {
    font-family: inherit; font-size: 13px;
    border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 10px; background: #fff;
  }
  textarea {
    width: 100%;
    min-height: 400px;
    font-family: ui-monospace, SFMono-Regular, "Menlo", monospace;
    font-size: 12.5px;
    resize: vertical;
    line-height: 1.5;
  }
  button {
    background: var(--accent); color: #fff; border-color: var(--accent);
    cursor: pointer; font-weight: 500; padding: 8px 16px;
  }
  button:hover { background: var(--accent-hover); }
  button:disabled { background: #cbd5e0; border-color: #cbd5e0; cursor: not-allowed; }
  button.secondary { background: #fff; color: var(--accent); border-color: var(--border); }
  button.secondary:hover { background: #f5f7fb; }

  #status-badge {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500;
  }
  .status-loading { background: #fef3c7; color: #b54708; }
  .status-ready   { background: #d1fae5; color: #067647; }
  .status-error   { background: #fee4e2; color: #b42318; }

  /* Model-variant chip (base Med42 vs tuned MedAI-EPI adapter). */
  #model-chip {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500; margin-left: 8px;
    background: #eef2ff; color: #1e3a8a;
  }
  #model-chip.tuned { background: #dcfce7; color: #14532d; }
  #model-chip.base  { background: #e5e7eb; color: #1f2937; }
  #model-chip.hidden { display: none; }

  .source-view {
    background: #f8fafc; border: 1px solid var(--border); border-radius: 6px;
    padding: 12px; font-family: ui-monospace, SFMono-Regular, "Menlo", monospace;
    font-size: 12.5px; line-height: 1.6; max-height: 500px; overflow-y: auto;
    white-space: pre-wrap; word-wrap: break-word;
  }
  .source-view mark {
    background: var(--highlight); border-radius: 2px; padding: 0 1px;
  }
  .source-view mark.active {
    background: var(--highlight-active); outline: 2px solid #d97706;
  }

  .phenotype-tree { font-size: 13px; }
  .phenotype-module { margin-bottom: 14px; border-left: 3px solid var(--border); padding-left: 10px; }
  .phenotype-module h3 { font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: 6px; }
  .phenotype-field {
    padding: 4px 0; display: grid; grid-template-columns: 200px 1fr auto; gap: 10px;
    cursor: pointer; border-bottom: 1px dashed #f1f5f9; align-items: center;
  }
  .phenotype-field:hover { background: #f8fafc; }
  .phenotype-field.active { background: #fef9c3; }
  .field-name { color: var(--muted); font-family: ui-monospace, monospace; font-size: 12px; }
  .field-value { font-weight: 500; }
  .field-cert {
    font-size: 10px; padding: 2px 6px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600;
  }
  .cert-definite       { background: #d1fae5; color: var(--certainty-def); }
  .cert-probable       { background: #fef3c7; color: var(--certainty-prob); }
  .cert-possible       { background: #ede9fe; color: var(--certainty-poss); }
  .cert-negated        { background: #fee4e2; color: var(--certainty-neg); }
  .cert-unknown        { background: #f1f5f9; color: var(--certainty-unk); }
  .cert-not_documented { background: transparent; color: var(--certainty-nd); font-style: italic; }

  .phenotype-list-item { margin-left: 12px; margin-bottom: 4px; }
  .phenotype-empty { color: var(--muted); font-style: italic; padding: 4px 0; }

  .summary-row {
    display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 0; margin-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .summary-item { font-size: 12px; }
  .summary-item strong { color: var(--ink); }
  .summary-item.ok       { color: var(--ok); }
  .summary-item.warn     { color: var(--warn); }
  .summary-item.danger   { color: var(--danger); }

  #detect-suggestion {
    font-size: 12px; color: var(--muted); margin-left: 8px;
  }
  #detect-suggestion strong { color: var(--accent); }

  /* Disclaimer modal (first visit) */
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(15,23,42,0.65);
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }
  .modal {
    background: #fff; border-radius: 10px; padding: 28px 32px;
    max-width: 560px; box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  }
  .modal h2 { color: var(--accent); margin-bottom: 12px; font-size: 20px; }
  .modal p { margin-bottom: 12px; color: var(--ink); }
  .modal ul { margin: 8px 0 12px 20px; }
  .modal .ack { display: flex; align-items: center; gap: 8px; margin: 16px 0; font-size: 13px; }
  .modal .actions { display: flex; justify-content: flex-end; gap: 10px; }

  .hidden { display: none !important; }
</style>
</head>
<body>

<header class="nav">
  <div>
    <h1>MedAI-EPI — Research Phenotyping Assistant</h1>
    <div class="subtitle">Structured epilepsy phenotype extraction from clinical documents · research use only</div>
  </div>
  <div>
    <a href="/extract/registry" target="_blank">Prompt registry</a>
    <a href="/extract/ui/review">Review queue</a>
    <a href="/extract/health" target="_blank">Health</a>
    <span id="status-badge" class="status-loading">Loading backend…</span>
    <span id="model-chip" class="hidden" title="Which Med42 variant is currently serving requests"></span>
  </div>
</header>

<div class="disclaimer">
  <strong>Research use only.</strong> MedAI-EPI is a research information-extraction tool. It does <em>not</em> diagnose, does <em>not</em> recommend treatment, and is <em>not</em> clinical decision support. All extracted values must be reviewed by qualified clinicians. Use on real patient data requires IRB approval and institutionally-approved secure compute.
</div>

<div id="modal" class="modal-backdrop hidden">
  <div class="modal">
    <h2>Research use acknowledgment</h2>
    <p>MedAI-EPI extracts structured phenotype fields from clinical text for <strong>research purposes only</strong>. Before you proceed:</p>
    <ul>
      <li>Outputs are <strong>not</strong> diagnostic or treatment recommendations.</li>
      <li>Every extracted value must be reviewed by a qualified clinician.</li>
      <li>Use on real patient text requires IRB approval and institutionally-approved secure compute.</li>
      <li>The Med42-8B model runs locally in this deployment; no text leaves this server.</li>
    </ul>
    <div class="ack">
      <input type="checkbox" id="ack-checkbox" />
      <label for="ack-checkbox">I understand and agree.</label>
    </div>
    <div class="actions">
      <button id="ack-continue" disabled>Continue</button>
    </div>
  </div>
</div>

<div class="container">
  <div class="grid">

    <div class="panel">
      <h2>Source document</h2>
      <textarea id="source-text" placeholder="Paste a clinical document (MRI report, EEG report, progress note, EMU discharge summary, etc.). The doc type will be auto-detected. Nothing is sent anywhere until you click Extract."></textarea>
      <div class="form-row" style="margin-top:12px;">
        <label>Doc type</label>
        <select id="doc-type">
          <option value="">— select —</option>
        </select>
        <span id="detect-suggestion"></span>
      </div>
      <div class="form-row">
        <label>Prompting arm</label>
        <label><input type="radio" name="arm" value="M0" /> M0 (zero-shot)</label>
        <label><input type="radio" name="arm" value="M1" /> M1 (few-shot)</label>
        <label><input type="radio" name="arm" value="M2" checked /> M2 (few-shot + schema)</label>
      </div>
      <div class="form-row">
        <label><input type="checkbox" id="chunk-mode" /> auto-chunk long notes (&gt; 8000 chars)</label>
        <span id="chars-indicator" style="font-size:12px;color:var(--muted);"></span>
      </div>
      <div class="form-row">
        <button id="btn-extract">Extract phenotype</button>
        <button id="btn-clear" class="secondary">Clear</button>
        <span id="progress" style="font-size:12px; color:var(--muted);"></span>
      </div>
      <p class="hint">M0 is fastest but rarely produces valid JSON without repair. M2 (with schema injected in the prompt) is slower but reaches ~95% final validity. Enable <em>auto-chunk</em> for notes that exceed the model's context — chunks are extracted independently and merged with Evidence-aware rules.</p>
    </div>

    <div class="panel">
      <h2>Source view (with highlighted evidence)</h2>
      <div id="source-view" class="source-view">Paste text on the left, then click Extract.</div>
      <p class="hint">After extraction, click a field on the right → the source is scrolled and the evidence quote is highlighted.</p>
    </div>

  </div>

  <div class="panel" style="margin-top:20px;">
    <h2>Extracted phenotype</h2>
    <div id="summary" class="summary-row hidden"></div>
    <div id="phenotype" class="phenotype-tree">
      <div class="phenotype-empty">No extraction yet.</div>
    </div>
    <div class="form-row" style="margin-top:16px;">
      <button id="btn-download-json" class="secondary" disabled>Download JSON</button>
      <button id="btn-download-csv" class="secondary" disabled>Download CSV</button>
      <label style="font-size:12px;color:var(--muted);"><input type="checkbox" id="csv-include-nd" /> include not_documented</label>
      <label style="font-size:12px;color:var(--muted);"><input type="checkbox" id="csv-include-chat" checked /> include chat Q&amp;A rows</label>
    </div>
    <p class="hint" style="margin-top:6px;">
      CSV is long-format (one row per extracted field) with a
      <code>confidence</code> column and an <code>evidence_text</code>
      column next to each value — the standard tidy-data shape for
      downstream analysis in pandas / R / SQL.
    </p>
  </div>

  <div class="panel" style="margin-top:20px;">
    <h2>Chat — ask a freeform question about this note</h2>
    <p class="hint" style="margin-bottom:8px;">
      Ask anything the structured extraction did not cover
      (e.g. "was surgery mentioned?", "what was the reason for LTG discontinuation?").
      The model must ground its answer in a verbatim quote from the note.
      Answers can be appended to the CSV download.
    </p>
    <div class="form-row">
      <input id="chat-q" type="text" placeholder="Type your question and press Enter…" style="flex:1; min-width:280px;" disabled />
      <button id="btn-chat-send" disabled>Ask</button>
      <button id="btn-chat-clear" class="secondary" disabled>Clear history</button>
    </div>
    <div id="chat-history" style="margin-top:12px;"></div>
  </div>

</div>

<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    docTypes: [],
    lastPhenotype: null,
    lastSource: null,
    lastResponse: null,
    chatRows: [],   // {question, answer, evidence_text, confidence, csv_row}
  };

  // ---- Chat history persistence (localStorage) ----
  const CHAT_KEY_PREFIX = "medai-epi-chat-v1:";
  function chatKey(docId) { return CHAT_KEY_PREFIX + (docId || "__unspecified__"); }
  function saveChatHistory() {
    const doc_id = state.lastPhenotype?.document?.doc_id;
    if (!doc_id) return;
    try {
      localStorage.setItem(chatKey(doc_id), JSON.stringify(state.chatRows));
    } catch (e) { /* localStorage may be full or disabled — silent */ }
  }
  function loadChatHistory() {
    const doc_id = state.lastPhenotype?.document?.doc_id;
    if (!doc_id) return [];
    try {
      const raw = localStorage.getItem(chatKey(doc_id));
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  }
  function renderChatHistoryFromState() {
    const wrap = $("chat-history");
    wrap.innerHTML = "";
    for (const c of [...state.chatRows].reverse()) {
      const entry = document.createElement("div");
      entry.style.cssText = "border-left: 3px solid var(--accent); padding: 8px 12px; margin-bottom: 8px; background: #f8fafc;";
      const cert = c.confidence || "unknown";
      entry.innerHTML =
        `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">Q:</div>` +
        `<div style="font-weight:500;margin-bottom:6px;">${escapeHtml(c.question)}</div>` +
        `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">A:</div>` +
        `<div style="margin-bottom:6px;">${escapeHtml(c.answer || "—")} ` +
        `<span class="field-cert cert-${cert}" style="margin-left:6px;">${cert}</span></div>` +
        (c.evidence_text
          ? `<div style="font-size:12px;color:var(--muted);">Evidence:</div>` +
            `<div style="font-style:italic;color:#334155;">"${escapeHtml(c.evidence_text)}"</div>`
          : ``);
      wrap.appendChild(entry);
    }
  }

  // ---- Disclaimer modal ----
  const ACK_KEY = "medai-epi-ack-v1";
  if (!localStorage.getItem(ACK_KEY)) {
    $("modal").classList.remove("hidden");
  }
  $("ack-checkbox").addEventListener("change", (e) => {
    $("ack-continue").disabled = !e.target.checked;
  });
  $("ack-continue").addEventListener("click", () => {
    localStorage.setItem(ACK_KEY, new Date().toISOString());
    $("modal").classList.add("hidden");
  });

  // ---- Health polling ----
  function updateModelChip(d) {
    // Render a chip that says "Base Med42" or "Tuned MedAI-EPI (adapter: <tag>)"
    // based on /extract/health's lora_loaded field. Robust to missing fields —
    // if the endpoint doesn't return lora info yet, the chip stays hidden.
    const chip = $("model-chip");
    if (!d) { chip.classList.add("hidden"); return; }
    const loraLoaded = d.lora_loaded === true;
    const adapterDir = d.lora_adapter_dir || "";
    // Derive a short tag from the last path segment.
    const tag = adapterDir ? adapterDir.replace(/\/+$/, "").split("/").pop() : "";
    if (loraLoaded && tag) {
      chip.className = "tuned";
      chip.textContent = `Tuned MedAI-EPI (adapter: ${tag})`;
    } else if (d.backend_model) {
      chip.className = "base";
      chip.textContent = "Base Med42";
    } else {
      chip.classList.add("hidden");
      return;
    }
    chip.classList.remove("hidden");
  }

  async function pollHealth() {
    try {
      const r = await fetch("/extract/health");
      const d = await r.json();
      state.docTypes = d.doc_types_supported || [];
      populateDocTypes();
      updateModelChip(d);
      const badge = $("status-badge");
      const status = d.med42_load_status || "unknown";
      if (status === "ready") {
        badge.className = "status-ready";
        badge.textContent = "Backend ready";
        $("btn-extract").disabled = false;
      } else if (status.startsWith("load_failed") || status.startsWith("exception")) {
        badge.className = "status-error";
        badge.textContent = "Backend error";
        $("btn-extract").disabled = true;
      } else {
        badge.className = "status-loading";
        badge.textContent = `Loading Med42… (${status})`;
        $("btn-extract").disabled = true;
        setTimeout(pollHealth, 3000);
      }
    } catch (e) {
      const badge = $("status-badge");
      badge.className = "status-error";
      badge.textContent = "Backend unreachable";
      setTimeout(pollHealth, 5000);
    }
  }
  function populateDocTypes() {
    const sel = $("doc-type");
    if (sel.options.length > 1) return;   // already populated
    for (const dt of state.docTypes) {
      const opt = document.createElement("option");
      opt.value = dt;
      opt.textContent = dt;
      sel.appendChild(opt);
    }
  }
  pollHealth();

  // Trigger backend load by hitting /extract/health once — it doesn't
  // itself trigger, but /extract does. We could also add a POST here.

  // ---- NDJSON streaming client for /extract/stream ----
  async function streamedExtract(endpoint, body) {
    const r = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || r.statusText);
    }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let final = null;
    const perModuleStatus = {};
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line) continue;
        let evt;
        try { evt = JSON.parse(line); } catch (_) { continue; }
        if (evt.event === "module_start") {
          perModuleStatus[evt.module] = `starting (${evt.n_done + 1}/${evt.n_total})`;
        } else if (evt.event === "module_done") {
          perModuleStatus[evt.module] =
            (evt.final_valid ? "✓" : "✗") +
            (evt.repair_method && evt.repair_method !== "none" ? ` [${evt.repair_method}]` : ``) +
            `  ${evt.duration_s?.toFixed(1)}s`;
        } else if (evt.event === "final") {
          final = {
            phenotype: evt.phenotype,
            summary: evt.summary,
            arm: evt.arm,
            doc_type: evt.phenotype?.document?.doc_type,
            schema_version: evt.phenotype?.schema_version,
            manifests: Object.entries(evt.summary || {}).map(([mname, m]) => ({
              module: mname, ...m,
            })),
          };
        } else if (evt.event === "error") {
          throw new Error(evt.error);
        }
        // Live progress paint
        const lines = Object.entries(perModuleStatus).map(
          ([m, s]) => `${m}: ${s}`
        );
        $("progress").textContent = lines.join("  ·  ");
      }
    }
    if (!final) throw new Error("stream ended without a final event");
    return final;
  }

  // ---- Live character counter + auto-chunk suggestion ----
  function updateCharCount() {
    const n = $("source-text").value.length;
    const CHUNK_THRESHOLD = 8000;
    const el = $("chars-indicator");
    el.textContent = `${n.toLocaleString()} chars`;
    if (n > CHUNK_THRESHOLD) {
      el.textContent += `  — exceeds ${CHUNK_THRESHOLD} chars, auto-chunk recommended`;
      el.style.color = "var(--warn)";
    } else if (n > 0) {
      el.style.color = "var(--muted)";
    }
  }
  $("source-text").addEventListener("input", updateCharCount);

  // ---- Doc-type autodetect on textarea blur ----
  $("source-text").addEventListener("blur", async () => {
    const text = $("source-text").value.trim();
    if (text.length < 50) {
      $("detect-suggestion").textContent = "";
      return;
    }
    try {
      const r = await fetch("/extract/detect_doc_type", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source_text: text}),
      });
      const d = await r.json();
      if (d.doc_type) {
        $("doc-type").value = d.doc_type;
        $("detect-suggestion").innerHTML =
          `auto-detected: <strong>${d.doc_type}</strong> (${d.confidence}, ${d.reasons.length} signals)`;
      } else {
        $("detect-suggestion").innerHTML =
          `<em>no doc type auto-detected — please select manually</em>`;
      }
    } catch (e) {
      $("detect-suggestion").textContent = "";
    }
  });

  // ---- Extract action ----
  $("btn-extract").addEventListener("click", async () => {
    const text = $("source-text").value.trim();
    const doc_type = $("doc-type").value;
    const arm = document.querySelector('input[name="arm"]:checked').value;
    if (!text) return alert("Paste a document first.");
    if (!doc_type) return alert("Select or auto-detect a doc type.");

    const t0 = performance.now();
    $("btn-extract").disabled = true;
    $("progress").textContent = "Extracting… this typically takes 10–30 seconds per module.";
    $("phenotype").innerHTML = '<div class="phenotype-empty">Running…</div>';
    $("summary").classList.add("hidden");

    const useChunk = $("chunk-mode").checked;
    // Chunk mode → /extract/long (JSON). Non-chunk mode → /extract/stream
    // (NDJSON, per-module progress).
    const useStream = !useChunk;
    const endpoint = useChunk ? "/extract/long" : "/extract/stream";
    try {
      let d;
      if (useStream) {
        d = await streamedExtract(endpoint, {source_text: text, doc_type, arm});
      } else {
        const r = await fetch(endpoint, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({source_text: text, doc_type, arm}),
        });
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}));
          throw new Error(errBody.error || r.statusText);
        }
        d = await r.json();
      }
      const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
      $("progress").textContent = `Done in ${elapsed}s.`;
      if (!d || !d.phenotype) {
        $("phenotype").innerHTML =
          `<div class="phenotype-empty" style="color:var(--danger);">Error: no phenotype in response</div>`;
      } else {
        state.lastPhenotype = d.phenotype;
        state.lastResponse = d;
        state.lastSource = text;
        // Restore any persisted chat history for this doc_id
        state.chatRows = loadChatHistory();
        renderChatHistoryFromState();
        renderPhenotype(d);
        $("btn-download-json").disabled = false;
        $("btn-download-csv").disabled = false;
        $("chat-q").disabled = false;
        $("btn-chat-send").disabled = false;
        $("btn-chat-clear").disabled = state.chatRows.length === 0;
      }
    } catch (e) {
      $("phenotype").innerHTML =
        `<div class="phenotype-empty" style="color:var(--danger);">Network error: ${e.message}</div>`;
    } finally {
      $("btn-extract").disabled = false;
    }
  });

  $("btn-clear").addEventListener("click", () => {
    $("source-text").value = "";
    $("phenotype").innerHTML = '<div class="phenotype-empty">No extraction yet.</div>';
    $("source-view").textContent = "Paste text on the left, then click Extract.";
    $("summary").classList.add("hidden");
    $("detect-suggestion").textContent = "";
    state.lastPhenotype = null;
    state.lastResponse = null;
    state.lastSource = null;
    state.chatRows = [];
    $("chat-history").innerHTML = "";
    $("chat-q").value = "";
    $("chat-q").disabled = true;
    $("btn-chat-send").disabled = true;
    $("btn-download-json").disabled = true;
    $("btn-download-csv").disabled = true;
    $("chars-indicator").textContent = "";
  });

  // ---- Chat action ----
  async function sendChat() {
    const q = $("chat-q").value.trim();
    if (!q || !state.lastSource) return;
    const t0 = performance.now();
    $("btn-chat-send").disabled = true;
    const entry = document.createElement("div");
    entry.style.cssText = "border-left: 3px solid var(--accent); padding: 8px 12px; margin-bottom: 8px; background: #f8fafc;";
    entry.innerHTML =
      `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">Q:</div>` +
      `<div style="font-weight:500;margin-bottom:6px;">${escapeHtml(q)}</div>` +
      `<div style="font-size:12px;color:var(--muted);">Asking…</div>`;
    $("chat-history").prepend(entry);
    try {
      const r = await fetch("/extract/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          question: q,
          source_text: state.lastSource,
          doc_id: state.lastPhenotype?.document?.doc_id,
          patient_id: state.lastPhenotype?.document?.patient_id,
          doc_date: state.lastPhenotype?.document?.doc_date,
          doc_type: state.lastPhenotype?.document?.doc_type,
        }),
      });
      const d = await r.json();
      const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
      if (!r.ok) {
        entry.querySelector("div:last-child").innerHTML =
          `<span style="color:var(--danger);">Error: ${d.error || r.statusText}</span>`;
      } else {
        state.chatRows.push({
          question: q, answer: d.answer,
          evidence_text: d.evidence_text, confidence: d.confidence,
          csv_row: d.csv_row,
        });
        saveChatHistory();
        $("btn-chat-clear").disabled = false;
        const cert = d.confidence || "unknown";
        entry.innerHTML =
          `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">Q &nbsp;(${elapsed}s):</div>` +
          `<div style="font-weight:500;margin-bottom:6px;">${escapeHtml(q)}</div>` +
          `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">A:</div>` +
          `<div style="margin-bottom:6px;">${escapeHtml(d.answer || "—")} ` +
          `<span class="field-cert cert-${cert}" style="margin-left:6px;">${cert}</span></div>` +
          (d.evidence_text ? `<div style="font-size:12px;color:var(--muted);">Evidence:</div>` +
            `<div style="font-style:italic;color:#334155;">"${escapeHtml(d.evidence_text)}"</div>` : ``);
      }
    } catch (e) {
      entry.querySelector("div:last-child").innerHTML =
        `<span style="color:var(--danger);">Network error: ${e.message}</span>`;
    } finally {
      $("btn-chat-send").disabled = false;
      $("chat-q").value = "";
      $("chat-q").focus();
    }
  }
  $("btn-chat-send").addEventListener("click", sendChat);
  $("chat-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  $("btn-chat-clear").addEventListener("click", () => {
    const doc_id = state.lastPhenotype?.document?.doc_id;
    if (doc_id) {
      try { localStorage.removeItem(chatKey(doc_id)); } catch (_) {}
    }
    state.chatRows = [];
    $("chat-history").innerHTML = "";
    $("btn-chat-clear").disabled = true;
  });

  // ---- Phenotype rendering ----
  function renderPhenotype(response) {
    const p = response.phenotype;
    const summary = response.summary || {};
    const manifests = response.manifests || [];

    // Summary strip
    const rawValidTot = manifests.filter(m => m.raw_valid).length;
    const finalValidTot = manifests.filter(m => m.final_valid).length;
    $("summary").innerHTML = `
      <div class="summary-item"><strong>Arm:</strong> ${response.arm}</div>
      <div class="summary-item"><strong>Doc type:</strong> ${response.doc_type}</div>
      <div class="summary-item"><strong>Schema:</strong> ${response.schema_version}</div>
      <div class="summary-item ${rawValidTot === manifests.length ? 'ok' : 'warn'}"><strong>Raw valid:</strong> ${rawValidTot}/${manifests.length} modules</div>
      <div class="summary-item ${finalValidTot === manifests.length ? 'ok' : 'danger'}"><strong>Final valid:</strong> ${finalValidTot}/${manifests.length} modules</div>
      <div class="summary-item"><strong>Time:</strong> ${response.processing_time_s?.toFixed(1) || '?'}s</div>
    `;
    $("summary").classList.remove("hidden");

    // Render source with all evidence spans pre-highlighted
    renderSourceWithHighlights(state.lastSource, p);

    // Render phenotype tree
    const tree = $("phenotype");
    tree.innerHTML = "";
    const modules = ["clinical_seizure", "medication", "clinical_localization",
                     "eeg", "mri", "integrated"];
    let anyRendered = false;
    for (const mod of modules) {
      if (!p[mod]) continue;
      anyRendered = true;
      const div = document.createElement("div");
      div.className = "phenotype-module";
      div.innerHTML = `<h3>${mod}</h3>`;
      renderModuleFields(div, p[mod], mod);
      tree.appendChild(div);
    }
    if (!anyRendered) {
      tree.innerHTML = '<div class="phenotype-empty">No modules populated. The doc type may not have any applicable modules.</div>';
    }
  }

  function renderModuleFields(container, module, modName) {
    for (const [fname, val] of Object.entries(module)) {
      if (Array.isArray(val)) {
        const wrap = document.createElement("div");
        wrap.innerHTML = `<div class="field-name" style="margin-top:4px;">${fname} <span style="color:var(--muted); font-size:11px;">(list, ${val.length})</span></div>`;
        for (let i = 0; i < val.length; i++) {
          const li = document.createElement("div");
          li.className = "phenotype-list-item";
          renderEvidence(li, val[i], `${modName}.${fname}[${i}]`);
          wrap.appendChild(li);
        }
        container.appendChild(wrap);
      } else if (val && typeof val === "object" && "value" in val) {
        const row = document.createElement("div");
        row.className = "phenotype-field";
        renderEvidence(row, val, `${modName}.${fname}`);
        row.querySelector(".field-name-slot").textContent = fname;
        container.appendChild(row);
      }
    }
  }

  function renderEvidence(row, ev, path) {
    const value = ev.value;
    const cert = ev.certainty || "not_documented";
    let displayValue = value;
    if (value === null || value === undefined) displayValue = "—";
    else if (typeof value === "object") displayValue = JSON.stringify(value);
    else if (typeof value === "boolean") displayValue = value ? "yes" : "no";
    row.innerHTML = `
      <div class="field-name field-name-slot">${path.split(".").pop()}</div>
      <div class="field-value">${escapeHtml(String(displayValue))}</div>
      <div class="field-cert cert-${cert}">${cert.replace('_', ' ')}</div>
    `;
    if (ev.evidence_text && ev.char_start !== null && ev.char_start !== undefined) {
      row.dataset.evStart = ev.char_start;
      row.dataset.evEnd = ev.char_end;
      row.dataset.evText = ev.evidence_text;
      row.addEventListener("click", () => activateEvidence(row));
    }
  }

  function renderSourceWithHighlights(text, phenotype) {
    const spans = collectSpans(phenotype);
    // Merge overlapping spans, sort by start
    spans.sort((a, b) => a.start - b.start);
    const view = $("source-view");
    view.innerHTML = "";
    let cursor = 0;
    for (const span of spans) {
      if (span.start < cursor) continue;   // skip overlapping
      if (span.start > cursor) {
        view.appendChild(document.createTextNode(text.slice(cursor, span.start)));
      }
      const mark = document.createElement("mark");
      mark.textContent = text.slice(span.start, span.end);
      mark.dataset.start = span.start;
      view.appendChild(mark);
      cursor = span.end;
    }
    if (cursor < text.length) {
      view.appendChild(document.createTextNode(text.slice(cursor)));
    }
    if (spans.length === 0) {
      view.textContent = text;
    }
  }

  function collectSpans(phenotype) {
    const out = [];
    const walk = (obj) => {
      if (!obj || typeof obj !== "object") return;
      if (Array.isArray(obj)) { obj.forEach(walk); return; }
      if ("char_start" in obj && "char_end" in obj &&
          obj.char_start !== null && obj.char_end !== null &&
          obj.evidence_text) {
        out.push({start: obj.char_start, end: obj.char_end});
      }
      for (const v of Object.values(obj)) walk(v);
    };
    walk(phenotype);
    return out;
  }

  function activateEvidence(row) {
    document.querySelectorAll(".phenotype-field.active").forEach(e => e.classList.remove("active"));
    document.querySelectorAll("#source-view mark.active").forEach(e => e.classList.remove("active"));
    row.classList.add("active");
    const start = row.dataset.evStart;
    const marks = document.querySelectorAll(`#source-view mark[data-start="${start}"]`);
    if (marks.length) {
      marks[0].classList.add("active");
      marks[0].scrollIntoView({behavior: "smooth", block: "center"});
    }
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  // ---- Downloads ----
  $("btn-download-json").addEventListener("click", () => {
    if (!state.lastPhenotype) return;
    const blob = new Blob([JSON.stringify(state.lastPhenotype, null, 2)],
                          {type: "application/json"});
    downloadBlob(blob, `phenotype_${state.lastPhenotype.document.doc_id || 'doc'}.json`);
  });

  $("btn-download-csv").addEventListener("click", () => {
    if (!state.lastPhenotype) return;
    const includeNd = $("csv-include-nd").checked;
    const includeChat = $("csv-include-chat").checked;
    const rows = phenotypeToLongRows(state.lastPhenotype, includeNd);
    if (includeChat) rows.push(...state.chatRows.map(c => c.csv_row));
    const csv = rowsToCsv(LONG_COLS, rows);
    const blob = new Blob([csv], {type: "text/csv"});
    downloadBlob(blob, `phenotype_${state.lastPhenotype.document.doc_id || 'doc'}.csv`);
  });

  function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 100);
  }

  const LONG_COLS = [
    "doc_id", "patient_id", "doc_type", "doc_date", "visit_date",
    "module", "field",
    "value", "evidence_text", "confidence", "temporal_status",
    "char_start", "char_end", "source_doc_id", "chunk_index", "note",
  ];
  const MODULES = ["clinical_seizure", "medication", "clinical_localization",
                    "eeg", "mri", "integrated"];

  function renderVal(v) {
    if (v === null || v === undefined) return "";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "object") {
      return Object.entries(v).filter(([, val]) => val !== null && val !== undefined)
        .map(([k, val]) => `${k}=${typeof val === "boolean" ? (val ? "true" : "false") : val}`)
        .join("; ");
    }
    return String(v);
  }

  function evRow(docCols, mod, field, ev) {
    return {
      ...docCols, module: mod, field: field,
      value: renderVal(ev.value),
      evidence_text: ev.evidence_text || "",
      confidence: ev.certainty || "not_documented",
      temporal_status: ev.temporal_status || "unspecified",
      char_start: ev.char_start ?? "",
      char_end: ev.char_end ?? "",
      source_doc_id: ev.source_doc_id || "",
      chunk_index: "", note: "",
    };
  }

  function phenotypeToLongRows(p, includeNd) {
    const docCols = {
      doc_id: p.document.doc_id, patient_id: p.document.patient_id,
      doc_type: p.document.doc_type, doc_date: p.document.doc_date,
      visit_date: "",
    };
    const rows = [];
    for (const mod of MODULES) {
      const m = p[mod]; if (!m) continue;
      for (const [f, v] of Object.entries(m)) {
        if (Array.isArray(v)) {
          if (v.length === 0) {
            rows.push({...docCols, module: mod, field: f, value: "", evidence_text: "",
                       confidence: "not_documented", temporal_status: "unspecified",
                       char_start: "", char_end: "",
                       source_doc_id: docCols.doc_id, chunk_index: "", note: "(empty list)"});
            continue;
          }
          v.forEach((item, i) => {
            if (item && typeof item === "object" && "value" in item) {
              rows.push(evRow(docCols, mod, `${f}[${i}]`, item));
            }
          });
        } else if (v && typeof v === "object" && "value" in v) {
          rows.push(evRow(docCols, mod, f, v));
        }
      }
    }
    return includeNd ? rows : rows.filter(r => r.confidence !== "not_documented");
  }

  function rowsToCsv(headers, rows) {
    const lines = [headers.map(csvEscape).join(",")];
    for (const r of rows) {
      lines.push(headers.map(h => csvEscape(r[h] ?? "")).join(","));
    }
    return lines.join("\n") + "\n";
  }

  function csvEscape(v) {
    v = String(v ?? "");
    if (/[",\n]/.test(v)) return '"' + v.replace(/"/g, '""') + '"';
    return v;
  }

})();
</script>

</body>
</html>
"""


@extract_ui_bp.route("/ui", methods=["GET"])
def extract_ui() -> Response:
    """Single-page research UI for /extract."""
    resp = Response(render_template_string(_UI_HTML), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp
