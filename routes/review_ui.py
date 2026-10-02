"""Minimal review queue UI for the LEO chain (Chain-of-Three spec P1.5)."""

from __future__ import annotations

from flask import Blueprint, Response, render_template_string

review_ui_bp = Blueprint("review_ui", __name__, url_prefix="/extract")

_REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>MedAI-EPI — LEO claim review queue</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #f5f7fb; color: #1a2432; }
  header { background: #004977; color: #fff; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }
  header a { color: #fff; }
  main { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .muted { color: #667085; font-size: 13px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button { padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; background: #004977; color: #fff; }
  button.secondary { background: #e2e8f0; color: #1a2432; }
  button.danger { background: #b42318; }
  pre { background: #f8fafc; padding: 12px; overflow: auto; font-size: 12px; border-radius: 6px; max-height: 220px; }
  .badge { display: inline-block; background: #fef3c7; color: #b54708; padding: 2px 8px; border-radius: 999px; font-size: 12px; }
</style>
</head>
<body>
<header>
  <div><strong>Claim review queue</strong> <span class="badge">research only</span></div>
  <div><a href="/extract/ui">← Extraction UI</a></div>
</header>
<main>
  <p class="muted">Pending claims flagged by the LEO chain's verifier. Accept, reject, or edit (JSON) — each action appends to the evidence ledger.</p>
  <div class="row">
    <button id="btn-refresh">Refresh</button>
    <span id="counts" class="muted"></span>
  </div>
  <div id="list"></div>
</main>
<script>
(async function () {
  const list = document.getElementById("list");
  const countsEl = document.getElementById("counts");

  async function loadCounts() {
    try {
      const r = await fetch("/extract/ledger/counts");
      const j = await r.json();
      const c = j.counts || {};
      countsEl.textContent = `Accepted: ${c.accepted ?? 0} · Pending: ${c.pending_review ?? 0} · Rejects: ${c.rejects ?? 0}`;
    } catch (e) {
      countsEl.textContent = "";
    }
  }

  async function loadPending() {
    list.innerHTML = "<p class='muted'>Loading…</p>";
    const r = await fetch("/extract/review/pending?limit=50");
    const j = await r.json();
    const items = j.pending || [];
    if (!items.length) {
      list.innerHTML = "<p class='muted'>No pending reviews.</p>";
      return;
    }
    list.innerHTML = "";
    for (const c of items) {
      const card = document.createElement("div");
      card.className = "card";
      const reasons = (c.reason_codes || []).join(", ");
      card.innerHTML = `
        <div><strong>${c.concept?.label || c.concept?.id || "?"}</strong>
          <span class="muted"> · ${c.section} · ${c.document_id}</span></div>
        <div class="muted">Reasons: ${reasons || "—"}</div>
        <div class="muted">Mention: “${(c.mention?.text || "").slice(0, 120)}”</div>
        <textarea class="claim-json" rows="12" style="width:100%;font-family:monospace;font-size:12px;"></textarea>
        <div class="row">
          <button data-act="accept" data-id="${c.claim_id}">Accept as-is</button>
          <button class="danger" data-act="reject" data-id="${c.claim_id}">Reject</button>
          <button class="secondary" data-act="edit" data-id="${c.claim_id}">Save edited JSON</button>
        </div>
      `;
      card.querySelector(".claim-json").value = JSON.stringify(c, null, 2);
      list.appendChild(card);
    }
    list.querySelectorAll("button[data-act]").forEach(btn => {
      btn.addEventListener("click", () => resolve(btn.dataset.id, btn.dataset.act, btn.closest(".card")));
    });
  }

  async function resolve(claimId, action, card) {
    const reviewer = prompt("Reviewer ID (pseudonym):", "reviewer-1") || "reviewer-1";
    let body = { action, reviewer, notes: "" };
    if (action === "edit") {
      try {
        body.claim = JSON.parse(card.querySelector(".claim-json").value);
        body.action = "edit";
      } catch (e) {
        alert("Invalid JSON in claim block");
        return;
      }
    }
    if (action === "accept") body.action = "accept_as_is";
    if (action === "reject") body.action = "reject";
    const r = await fetch("/extract/review/" + encodeURIComponent(claimId) + "/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) {
      alert(j.error || "Resolve failed");
      return;
    }
    await loadCounts();
    await loadPending();
  }

  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadCounts();
    loadPending();
  });
  loadCounts();
  loadPending();
})();
</script>
</body>
</html>
"""


@review_ui_bp.route("/ui/review", methods=["GET"])
def review_ui() -> Response:
    resp = Response(render_template_string(_REVIEW_HTML), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp
