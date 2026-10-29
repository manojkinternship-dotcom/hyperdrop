// HyperDrop Dashboard Client
let socket = null;
const stateOrder = [
  "CREATED",
  "CALLING_CUSTOMER",
  "RESOLVED",
  "AWAITING_PAYMENT",
  "PAYMENT_CONFIRMED",
  "CALLING_RIDER",
  "RIDER_CONFIRMED",
  "HANDOVER_VERIFIED",
  "CLOSED",
  "NO_ANSWER",
  "RETRYING_CUSTOMER",
  "CALLING_ALT_PHONE",
  "FALLBACK_NOTIFICATION",
  "ESCALATED_TO_HUMAN"
];

function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
  
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    document.getElementById("statusDot").classList.add("connected");
    document.getElementById("statusText").innerText = "Connected";
  };

  socket.onclose = () => {
    document.getElementById("statusDot").classList.remove("connected");
    document.getElementById("statusText").innerText = "Reconnecting...";
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleLiveEvent(data);
    } catch (e) {
      console.error("Failed to parse event:", e);
    }
  };
}

function handleLiveEvent(data) {
  switch (data.event) {
    case "STATE_CHANGE":
      updateStateTimeline(data.new_state, data.details);
      break;

    case "TRANSCRIPT_UPDATE":
      appendTranscript(data.role, data.speaker, data.text, data.language, data.latency_ms);
      break;

    case "TOKEN_GENERATED":
      showGateToken(data.token, data.expires_at);
      break;

    case "PAYMENT_UPDATE":
      updatePayment(data.amount, data.status, data.link);
      break;

    case "KPI_UPDATE":
      updateKPIs(data.kpis);
      break;
  }
}

function updateStateTimeline(newState, details) {
  const steps = document.querySelectorAll(".timeline-step");
  let foundCurrent = false;

  steps.forEach(step => {
    const s = step.getAttribute("data-state");
    if (s === newState) {
      step.className = "timeline-step active";
      foundCurrent = true;
    } else if (!foundCurrent) {
      step.className = "timeline-step completed";
    } else {
      step.className = "timeline-step";
    }
  });

  // Handle special states like ESCALATED_TO_HUMAN or AWAITING_PAYMENT
  if (newState === "ESCALATED_TO_HUMAN") {
    const timeline = document.getElementById("timelineList");
    const escStep = document.createElement("div");
    escStep.className = "timeline-step active";
    escStep.innerHTML = `<span class="step-indicator" style="background:#ef4444;"></span><span style="color:#ef4444; font-weight:700;">ESCALATED_TO_HUMAN</span>`;
    timeline.appendChild(escStep);
  }
}

function appendTranscript(role, speaker, text, language, latencyMs) {
  const container = role === "rider" 
    ? document.getElementById("riderTranscripts") 
    : document.getElementById("customerTranscripts");

  const bubble = document.createElement("div");
  const isAgent = speaker.toLowerCase().includes("agent");
  const isSystem = speaker.toLowerCase().includes("system") || speaker.toLowerCase().includes("bot");

  if (isSystem) {
    bubble.className = "transcript-bubble bubble-system";
  } else if (isAgent) {
    bubble.className = "transcript-bubble bubble-agent";
  } else {
    bubble.className = "transcript-bubble bubble-user";
  }

  let latencyBadge = "";
  if (latencyMs) {
    latencyBadge = `<span style="background:rgba(255,255,255,0.15); padding:1px 6px; border-radius:4px; font-weight:600;">⚡ ${latencyMs}ms</span>`;
  }

  bubble.innerHTML = `
    <div class="bubble-speaker">${speaker} <span style="font-weight:normal; opacity:0.75;">(${language})</span></div>
    <div class="bubble-text">${escapeHtml(text)}</div>
    <div class="bubble-meta">
      ${latencyBadge}
      <span>${new Date().toLocaleTimeString()}</span>
    </div>
  `;

  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function showGateToken(code, expiresAt) {
  const tokenEl = document.getElementById("tokenCode");
  const expiryEl = document.getElementById("tokenExpiry");
  tokenEl.innerText = code;
  tokenEl.style.color = "#60a5fa";
  expiryEl.innerText = `One-time valid until ${new Date(expiresAt).toLocaleTimeString()}`;
}

function updatePayment(amount, status, link) {
  const label = document.getElementById("paymentLabel");
  const linkText = document.getElementById("paymentLinkText");
  const badge = document.getElementById("paymentBadge");

  label.innerText = `COD Amount: ₹${amount.toFixed(2)}`;
  linkText.innerText = link || "UPI Link sent to customer";
  
  if (status === "confirmed") {
    badge.className = "status-badge badge-confirmed";
    badge.innerText = "CONFIRMED";
  } else {
    badge.className = "status-badge badge-pending";
    badge.innerText = "PENDING";
  }
}

function updateKPIs(kpis) {
  if (!kpis) return;
  document.getElementById("kpiResolution").innerText = `${kpis.avg_resolution_seconds}s`;
  document.getElementById("kpiLatency").innerText = `${kpis.avg_translation_latency_ms}ms`;
  document.getElementById("kpiSuccess").innerText = `${kpis.success_rate}%`;
  document.getElementById("kpiCost").innerText = `₹${kpis.cost_per_exception.toFixed(2)}`;
  document.getElementById("kpiCounts").innerText = `${kpis.resolved_exceptions} resolved / ${kpis.total_exceptions} total`;
}

async function loadKPIs() {
  try {
    const res = await fetch("/kpis");
    if (res.ok) {
      const data = await res.json();
      updateKPIs(data);
    }
  } catch (e) {
    console.error("Failed to fetch KPIs:", e);
  }
}

async function runScenario(scenario) {
  // Clear previous transcripts
  document.getElementById("customerTranscripts").innerHTML = "";
  document.getElementById("riderTranscripts").innerHTML = "";
  document.getElementById("tokenCode").innerText = "------";
  document.getElementById("paymentBadge").className = "status-badge badge-pending";
  document.getElementById("paymentBadge").innerText = "N/A";
  document.getElementById("paymentLabel").innerText = "No active COD payment";

  // Reset timeline
  const steps = document.querySelectorAll(".timeline-step");
  steps.forEach((s, idx) => {
    s.className = idx === 0 ? "timeline-step active" : "timeline-step";
  });

  // Update order preview based on scenario
  if (scenario === "S1") {
    document.getElementById("orderItem").innerText = "Groceries & Daily Essentials";
    document.getElementById("orderTypeBadge").innerText = "Prepaid";
    document.getElementById("orderValue").innerText = "₹650.00";
    document.getElementById("customerMeta").innerText = "Amit Verma (Hindi)";
    document.getElementById("riderMeta").innerText = "Raju Gowda (Kannada)";
  } else if (scenario === "S2") {
    document.getElementById("orderItem").innerText = "Smart Watch Pro (High-Value)";
    document.getElementById("orderTypeBadge").innerText = "Prepaid";
    document.getElementById("orderValue").innerText = "₹2,499.00";
    document.getElementById("customerMeta").innerText = "Priya Sharma (Hinglish)";
    document.getElementById("riderMeta").innerText = "Raju Gowda (Kannada)";
  } else if (scenario === "S3") {
    document.getElementById("orderItem").innerText = "Noise-Cancelling Earbuds";
    document.getElementById("orderTypeBadge").innerText = "Cash on Delivery";
    document.getElementById("orderValue").innerText = "₹1,299.00";
    document.getElementById("customerMeta").innerText = "Sneha Reddy (Telugu)";
    document.getElementById("riderMeta").innerText = "Muthu Kumar (Tamil)";
  } else if (scenario === "NO_ANSWER") {
    document.getElementById("orderItem").innerText = "Urgent Medicine Pack";
    document.getElementById("orderTypeBadge").innerText = "Prepaid";
    document.getElementById("orderValue").innerText = "₹850.00";
    document.getElementById("customerMeta").innerText = "Priya Sharma (+919876543210)";
    document.getElementById("riderMeta").innerText = "Raju Gowda (Kannada)";
  }

  try {
    const res = await fetch(`/demo/simulate/${scenario}`, {
      method: "POST"
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Simulation error: ${err.detail || 'Failed'}`);
    }
  } catch (e) {
    console.error("Simulation request error:", e);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

window.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  loadKPIs();
});
