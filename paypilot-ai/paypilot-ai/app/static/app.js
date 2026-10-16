/* PayPilot AI dashboard */
const $ = (s) => document.querySelector(s);

function toast(msg, ok = true) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + (ok ? "ok" : "err");
  setTimeout(() => t.classList.add("hidden"), 4500);
  t.classList.remove("hidden");
}

function showModal(text) {
  $("#modal-text").textContent = text;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }

const STATUS_BADGE = {
  CREATED: "st-created", APPROVED: "st-approved", SAVED: "st-created",
  COMPLETED: "st-captured", CAPTURED: "st-captured",
  VOIDED: "st-voided", PAYER_ACTION_REQUIRED: "st-created",
};

async function api(path, opts) {
  const r = await fetch(path, opts && {
    method: opts.method || "POST",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

/* ---------------- config badges ---------------- */
async function loadConfig() {
  try {
    const c = await api("/api/config");
    $("#config-badges").innerHTML = `
      <span class="badge ${c.paypal_ready ? "ok" : "warn"}">PayPal ${c.paypal_ready ? "Sandbox ✓" : "⚠ not configured"}</span>
      <span class="badge ok">AI: ${c.ai_provider}</span>`;
  } catch { /* ignore */ }
}

/* ---------------- create payment ---------------- */
async function createPayment(payload) {
  $("#create-result").classList.add("hidden");
  try {
    const p = await api("/api/payments", { body: payload });
    const box = $("#create-result");
    box.innerHTML = `
      <p>✅ Order <b>${p.paypal_order_id}</b> — ${p.amount.toFixed(2)} ${p.currency}</p>
      <p class="muted">${p.description}</p>
      <a class="paylink" href="${p.approve_link}" target="_blank">👉 Open PayPal Sandbox approval</a>
      <p class="muted small">Log in with a <b>sandbox buyer</b> account, approve, then press “Sync” on the payment row.</p>`;
    box.classList.remove("hidden");
    toast("PayPal order created ⚡");
    loadPayments();
  } catch (e) {
    toast(e.message, false);
  }
}

$("#create-btn").onclick = () => {
  const prompt = $("#prompt").value.trim();
  if (prompt) createPayment({ prompt });
};
$("#prompt").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#create-btn").click();
});
document.querySelectorAll(".chip").forEach((c) =>
  c.onclick = () => { $("#prompt").value = c.dataset.prompt; $("#create-btn").click(); });

$("#manual-btn").onclick = () => createPayment({
  amount: parseFloat($("#m-amount").value),
  currency: $("#m-currency").value || "USD",
  description: $("#m-desc").value,
  recipient_email: $("#m-email").value || null,
});

/* ---------------- payments table ---------------- */
async function loadPayments() {
  const rows = await api("/api/payments");
  const tb = $("#payments tbody");
  tb.innerHTML = "";
  $("#empty").style.display = rows.length ? "none" : "block";
  for (const p of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="muted small">${p.created_at}</td>
      <td>${esc(p.description)}</td>
      <td><b>${p.amount.toFixed(2)}</b> ${p.currency}</td>
      <td><span class="badge ${STATUS_BADGE[p.status] || "st-created"}">${p.status}</span></td>
      <td class="muted small">${esc(p.payer_email || p.recipient_email || "—")}</td>
      <td class="actions"></td>`;
    const td = tr.querySelector(".actions");
    if (p.approve_link && (p.status === "CREATED" || p.status === "SAVED")) {
      td.appendChild(actionBtn("Approve ↗", () => window.open(p.approve_link, "_blank")));
    }
    td.appendChild(actionBtn("Sync", async () => {
      try { await api(`/api/payments/${p.id}/refresh`, { body: {} }); loadPayments(); }
      catch (e) { toast(e.message, false); }
    }));
    td.appendChild(actionBtn("Receipt", async () => {
      try {
        const r = await api(`/api/payments/${p.id}/receipt?regenerate=${p.status === "CAPTURED" ? "true" : "false"}`);
        showModal(r.receipt);
      } catch (e) { toast(e.message, false); }
    }));
    tb.appendChild(tr);
  }
}

function actionBtn(label, fn) {
  const b = document.createElement("button");
  b.className = "ghost small"; b.textContent = label; b.onclick = fn;
  return b;
}

$("#refresh-all").onclick = async () => {
  const rows = await api("/api/payments");
  for (const p of rows) {
    if (["CREATED", "APPROVED", "SAVED"].includes(p.status)) {
      try { await api(`/api/payments/${p.id}/refresh`, { body: {} }); } catch {}
    }
  }
  loadPayments(); toast("Synced with PayPal ↻");
};

/* ---------------- insights / webhooks / outbox ---------------- */
$("#insights-btn").onclick = async () => {
  $("#insights").textContent = "Thinking…";
  try {
    const d = await api("/api/insights");
    $("#insights").textContent = `Provider: ${d.provider}

${d.insights}`;
    $("#insights").classList.remove("muted");
  } catch (e) { $("#insights").textContent = e.message; }
};

async function loadWebhooks() {
  const rows = await api("/api/webhooks");
  $("#webhooks").innerHTML = rows.length
    ? rows.map((r) => `<li><b>${esc(r.event_type)}</b><span class="muted small"> ${r.received_at} · order ${esc(r.order_id || "—")}</span></li>`).join("")
    : '<li class="muted">No events yet. Add the webhook URL in the PayPal dashboard (see README §4) or use the Sandbox webhook simulator.</li>';
}

async function loadOutbox() {
  const rows = await api("/api/outbox");
  $("#outbox").innerHTML = rows.length
    ? rows.map((r) => `<li><b>${esc(r.subject)}</b><span class="muted small"> → ${esc(r.recipient || "")} · ${r.created_at}</span></li>`).join("")
    : '<li class="muted">Receipts appear here after capture.</li>';
}

$("#wh-refresh").onclick = loadWebhooks;
$("#ob-refresh").onclick = loadOutbox;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* deep-link after PayPal redirect */
const params = new URLSearchParams(location.search);
if (params.get("cancelled")) toast("Payment cancelled by buyer.", false);
if (params.get("approved")) { toast("Buyer returned — press Sync to capture 💰"); loadPayments(); }

loadConfig(); loadPayments(); loadWebhooks(); loadOutbox();
setInterval(loadPayments, 15000);
