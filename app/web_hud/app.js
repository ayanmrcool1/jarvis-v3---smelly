const root = document.getElementById("hudRoot");
const canvas = document.getElementById("reactorCanvas");
const ctx = canvas.getContext("2d");

const statusLabel = document.getElementById("statusLabel");
const subStatusLabel = document.getElementById("subStatusLabel");
const activityKicker = document.getElementById("activityKicker");
const activityTitle = document.getElementById("activityTitle");
const activityDetail = document.getElementById("activityDetail");
const widgetDock = document.getElementById("widgetDock");
const chatRail = document.getElementById("chatRail");
const clockLabel = document.getElementById("clockLabel");
const connectionBadge = document.getElementById("connectionBadge");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const closeWidgetsBtn = document.getElementById("closeWidgetsBtn");

const appState = {
  payload: null,
  status: "STANDBY",
  lastStateAt: 0,
  offline: true,
  canvasWidth: 0,
  canvasHeight: 0,
  dpr: 1,
  reactorX: null,
  reactorY: null,
  reactorBase: null,
  widgetPanels: new Map(),
  widgetPositions: new Map(),
  widgetBodyKeys: new Map(),
  dragging: null,
  widgetZ: 10,
};

const statusPalette = {
  STANDBY: ["#5fd4df", "#123d45", "#9f7d39"],
  LISTENING: ["#66e6bd", "#17483e", "#58cdd8"],
  THINKING: ["#d6a84d", "#4e3b18", "#a85270"],
  SPEAKING: ["#8f7bdf", "#342e62", "#55c7d3"],
  OFFLINE: ["#cf5f83", "#4d1b2b", "#a07b38"],
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(current, target, amount) {
  return current + (target - current) * amount;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatRole(role) {
  const clean = String(role || "jarvis").toUpperCase();
  return clean === "USER" ? "YOU" : "JARVIS";
}

function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function percent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return null;
  }

  return clamp(Math.round(number), 0, 100);
}

function colorWithAlpha(hex, alpha) {
  const clean = String(hex || "#ffffff").replace("#", "");
  const value = clean.length === 3
    ? clean.split("").map((char) => char + char).join("")
    : clean.padEnd(6, "f").slice(0, 6);
  const red = parseInt(value.slice(0, 2), 16);
  const green = parseInt(value.slice(2, 4), 16);
  const blue = parseInt(value.slice(4, 6), 16);

  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));

  if (
    appState.canvasWidth === width &&
    appState.canvasHeight === height &&
    appState.dpr === dpr
  ) {
    return;
  }

  appState.canvasWidth = width;
  appState.canvasHeight = height;
  appState.dpr = dpr;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawPolygon(cx, cy, radius, sides, rotation, stroke, fill, width = 1) {
  ctx.beginPath();

  for (let index = 0; index < sides; index += 1) {
    const angle = rotation + (Math.PI * 2 * index) / sides;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;

    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }

  ctx.closePath();

  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }

  if (stroke) {
    ctx.lineWidth = width;
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
}

function drawArcRing(cx, cy, radius, start, span, color, width) {
  ctx.beginPath();
  ctx.arc(cx, cy, radius, start, start + span);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.stroke();
}

function drawReactor(now) {
  resizeCanvas();

  const w = appState.canvasWidth;
  const h = appState.canvasHeight;
  const t = now / 1000;
  const status = appState.status || "STANDBY";
  const palette = statusPalette[status] || statusPalette.STANDBY;
  const hasWidgets = root.classList.contains("has-widgets");
  const wideWidgetMode = hasWidgets && w >= 760;
  const targetBase = wideWidgetMode
    ? clamp(Math.min(w, h) * 0.12, 78, 138)
    : Math.max(110, Math.min(w, h) * 0.19);
  const targetCx = wideWidgetMode
    ? w - targetBase * 1.55 - 34
    : w / 2;
  const targetCy = wideWidgetMode
    ? h - targetBase * 1.45 - 32
    : h / 2;

  if (appState.reactorX === null) {
    appState.reactorX = targetCx;
    appState.reactorY = targetCy;
    appState.reactorBase = targetBase;
  }

  appState.reactorX = lerp(appState.reactorX, targetCx, 0.12);
  appState.reactorY = lerp(appState.reactorY, targetCy, 0.12);
  appState.reactorBase = lerp(appState.reactorBase, targetBase, 0.12);

  const cx = appState.reactorX;
  const cy = appState.reactorY;
  const base = appState.reactorBase;
  const energy =
    status === "LISTENING" ? 1.22 :
    status === "THINKING" ? 1.34 :
    status === "SPEAKING" ? 1.46 :
    status === "OFFLINE" ? 0.72 :
    0.92;
  const pulse = 1 + Math.sin(t * 3.2) * 0.018 * energy;

  ctx.clearRect(0, 0, w, h);

  ctx.save();
  ctx.globalAlpha = wideWidgetMode ? 0.76 : 0.9;

  const halo = ctx.createRadialGradient(cx, cy, base * 0.12, cx, cy, base * 2.0);
  halo.addColorStop(0, colorWithAlpha(palette[0], 0.2));
  halo.addColorStop(0.42, colorWithAlpha(palette[1], 0.13));
  halo.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = halo;
  ctx.beginPath();
  ctx.arc(cx, cy, base * 2.04, 0, Math.PI * 2);
  ctx.fill();

  for (let index = 0; index < 72; index += 1) {
    const angle = (Math.PI * 2 * index) / 72 + t * 0.04;
    const major = index % 6 === 0;
    const inner = base * (1.58 + (major ? 0.02 : 0));
    const outer = inner + base * (major ? 0.11 : 0.058);

    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner);
    ctx.lineTo(cx + Math.cos(angle) * outer, cy + Math.sin(angle) * outer);
    ctx.strokeStyle = major ? "rgba(242,196,109,0.5)" : "rgba(128,231,244,0.28)";
    ctx.lineWidth = major ? 2 : 1;
    ctx.stroke();
  }

  const ringSpecs = [
    [1.62, 0.92, 0.56, 1.2, -1],
    [1.42, 1.35, 0.42, 2.4, 1],
    [1.22, 1.72, 0.36, 1.8, -1],
    [0.98, 1.1, 0.5, 1.5, 1],
    [0.76, 1.5, 0.3, 1.2, -1],
    [0.58, 0.74, 0.48, 1.1, 1],
  ];

  ringSpecs.forEach(([scale, span, gap, width, dir], index) => {
    const radius = base * scale * pulse;
    const start = t * dir * (0.48 + index * 0.13) + index * 0.72;
    drawArcRing(cx, cy, radius, start, span, `rgba(128,231,244,${0.33 + index * 0.1})`, width);
    drawArcRing(cx, cy, radius, start + span + gap, 0.38 + index * 0.11, `rgba(242,196,109,${0.24 + index * 0.05})`, Math.max(1, width - 0.6));
  });

  const rotation = t * 0.45;
  drawPolygon(cx, cy, base * 0.72 * pulse, 6, rotation + Math.PI / 6, "rgba(128,231,244,0.7)", "rgba(4,20,26,0.82)", 2);
  drawPolygon(cx, cy, base * 0.5 * pulse, 6, -rotation * 0.8, "rgba(120,240,194,0.42)", "rgba(7,36,42,0.72)", 1.5);
  drawPolygon(cx, cy, base * 0.36 * pulse, 3, rotation * -1.2, "rgba(214,168,77,0.48)", "rgba(0,0,0,0)", 1.1);

  for (let index = 0; index < 6; index += 1) {
    const angle = rotation + (Math.PI * 2 * index) / 6;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * base * 0.2, cy + Math.sin(angle) * base * 0.2);
    ctx.lineTo(cx + Math.cos(angle) * base * 0.65, cy + Math.sin(angle) * base * 0.65);
    ctx.strokeStyle = "rgba(230,250,252,0.42)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  const corePulse = 0.62 + Math.abs(Math.sin(t * 4.5)) * 0.22 * energy;
  drawPolygon(cx, cy, base * 0.26 * corePulse, 6, rotation * 1.35, palette[0], "rgba(230,250,252,0.14)", 2.3);

  ctx.beginPath();
  ctx.arc(cx, cy, base * 0.055 * corePulse, 0, Math.PI * 2);
  ctx.fillStyle = palette[0];
  ctx.fill();

  if (wideWidgetMode) {
    ctx.restore();
    return;
  }

  const waveY = cy + base * 1.85;
  const bars = 52;
  const totalWidth = Math.min(w * 0.48, 680);
  const gap = 5;
  const barW = Math.max(3, (totalWidth - gap * (bars - 1)) / bars);
  const x0 = cx - totalWidth / 2;

  for (let index = 0; index < bars; index += 1) {
    const phase = t * (status === "SPEAKING" ? 8.5 : 4.2) + index * 0.38;
    const noise = Math.sin(phase) * 0.5 + Math.sin(phase * 0.57) * 0.5;
    const height = 10 + Math.abs(noise) * 36 * energy;
    const x = x0 + index * (barW + gap);

    ctx.fillStyle = index % 9 === 0 ? "rgba(242,196,109,0.48)" : "rgba(128,231,244,0.36)";
    ctx.fillRect(x, waveY - height / 2, barW, height);
  }

  ctx.restore();
}

function renderStatus(payload) {
  const state = payload?.state || {};
  const status = String(state.status || "STANDBY").toUpperCase();
  const subStatus = state.sub_status || "Awaiting wake phrase";
  const detail = state.detail || subStatus;

  appState.status = status;
  root.dataset.status = status;
  statusLabel.textContent = status;
  subStatusLabel.textContent = subStatus;
  activityKicker.textContent =
    status === "LISTENING" ? "AUDIO INPUT" :
    status === "THINKING" ? "INTENT RESOLUTION" :
    status === "SPEAKING" ? "VOICE OUTPUT" :
    status === "OFFLINE" ? "CORE OFFLINE" :
    "LOCAL CORE";
  activityTitle.textContent = status;
  activityDetail.textContent = detail;
}

function renderChatRail(messages) {
  const recent = (messages || []).slice(-4);

  if (!recent.length) {
    chatRail.innerHTML = '<div class="empty-copy">No recent conversation.</div>';
    return;
  }

  chatRail.innerHTML = recent.map((message) => `
    <article class="rail-message">
      <div class="role">${escapeHtml(formatRole(message.role))}</div>
      <div class="text">${escapeHtml(message.text)}</div>
    </article>
  `).join("");
}

function taskRows(tasks) {
  if (!tasks.length) {
    return '<div class="empty-copy">No tasks yet.</div>';
  }

  return tasks.map((task) => `
    <div class="todo-row ${task.done ? "done" : ""}">
      ${escapeHtml(task.text)}
    </div>
  `).join("");
}

function chatRows(messages) {
  if (!messages.length) {
    return '<div class="empty-copy">No conversation captured yet.</div>';
  }

  return messages.slice(-10).map((message) => {
    const role = String(message.role || "jarvis").toLowerCase();
    return `
      <div class="chat-row ${escapeHtml(role)}">
        <div class="chat-role">${escapeHtml(formatRole(role))}</div>
        <div>${escapeHtml(message.text)}</div>
      </div>
    `;
  }).join("");
}

function metricRow(label, value) {
  const clean = percent(value);

  if (clean === null) {
    return "";
  }

  return `
    <div class="metric-row">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-bar"><div class="metric-fill" style="width: ${clean}%"></div></div>
      <div class="metric-value">${clean}%</div>
    </div>
  `;
}

function systemRows(system) {
  if (!system || !system.available) {
    return '<div class="empty-copy">System telemetry unavailable.</div>';
  }

  return [
    metricRow("CPU", system.cpu_percent),
    metricRow("RAM", system.ram_percent),
    metricRow("DISK", system.disk_percent),
    metricRow("BATTERY", system.battery_percent),
  ].filter(Boolean).join("");
}

function gapRows(gaps) {
  if (!gaps.length) {
    return '<div class="empty-copy">No capability gaps logged yet.</div>';
  }

  return gaps.slice(0, 6).map((gap) => `
    <div class="gap-row">
      <div class="gap-category">${escapeHtml(gap.category || "other")}</div>
      <div>${escapeHtml(gap.original_request || "Unknown request")}</div>
      <div class="small-copy">${escapeHtml(gap.failure_reason || "")}</div>
    </div>
  `).join("");
}

function genericContent(content) {
  if (!content || (typeof content === "object" && !Object.keys(content).length)) {
    return '<div class="empty-copy">No content.</div>';
  }

  return `<pre class="small-copy">${escapeHtml(JSON.stringify(content, null, 2))}</pre>`;
}

function widgetBody(widget, payload) {
  const type = String(widget.widget_type || "").toLowerCase();

  if (type === "todo") {
    return taskRows(payload.todo?.tasks || []);
  }

  if (type === "chat") {
    return chatRows(payload.chat_history || []);
  }

  if (type === "system") {
    return systemRows(payload.system);
  }

  if (type === "spotify") {
    return `
      <div class="empty-copy">Spotify is not connected yet.</div>
      <div class="small-copy">Open Spotify to show playback data here.</div>
    `;
  }

  if (type === "capability_gaps") {
    return gapRows(payload.capability_gaps || []);
  }

  return genericContent(widget.content);
}

function markerColor(type) {
  if (type === "todo") return "#78f0c2";
  if (type === "chat") return "#80e7f4";
  if (type === "system") return "#f2c46d";
  if (type === "spotify") return "#a98cff";
  return "#ef7ea8";
}

function clampWidgetPosition(x, y, panel) {
  const margin = 18;
  const width = panel.offsetWidth || 560;
  const height = panel.offsetHeight || 260;
  const maxX = Math.max(margin, window.innerWidth - width - margin);
  const maxY = Math.max(margin, window.innerHeight - height - margin);
  const safeTop = window.innerWidth <= 560 ? 150 : 114;

  return {
    x: clamp(x, margin, maxX),
    y: clamp(y, safeTop, maxY),
  };
}

function defaultWidgetPosition(panel, index, total = 1) {
  const width = panel.offsetWidth || 560;
  const height = panel.offsetHeight || 260;
  const safeTop = window.innerWidth <= 560 ? 150 : 114;
  const safeBottom = window.innerWidth <= 560 ? 24 : 132;
  const gap = 18;

  if (total > 1 && window.innerWidth >= 1180) {
    const columns = Math.min(2, total);
    const rows = Math.ceil(total / columns);
    const column = index % columns;
    const row = Math.floor(index / columns);
    const gridWidth = columns * width + (columns - 1) * gap;
    const gridHeight = rows * height + (rows - 1) * gap;
    const x = (window.innerWidth - gridWidth) / 2 + column * (width + gap);
    const y = Math.max(
      safeTop,
      (window.innerHeight - safeBottom + safeTop - gridHeight) / 2 + row * (height + gap),
    );

    return clampWidgetPosition(x, y, panel);
  }

  const availableBottom = Math.max(safeTop + height, window.innerHeight - safeBottom);
  const centerY = safeTop + (availableBottom - safeTop - height) / 2;
  const x = (window.innerWidth - width) / 2 + index * 42;
  const y = centerY + index * 34;

  return clampWidgetPosition(x, y, panel);
}

function applyWidgetPosition(panel, position) {
  const safe = clampWidgetPosition(position.x, position.y, panel);
  panel.style.left = `${safe.x}px`;
  panel.style.top = `${safe.y}px`;
  appState.widgetPositions.set(panel.dataset.widgetId, safe);
}

function createWidgetPanel(widget, payload, index, total) {
  const id = widget.widget_id || widget.widget_type || "widget";
  const type = String(widget.widget_type || "widget").toLowerCase();
  const title = widget.title || type;
  const panel = document.createElement("article");

  panel.className = "widget-panel";
  panel.dataset.widgetId = id;
  panel.dataset.widgetType = type;
  panel.innerHTML = `
    <header class="widget-head" data-drag-handle="true">
      <div class="widget-type"></div>
      <div class="widget-title"></div>
      <button class="widget-close" type="button" data-close-widget="${escapeHtml(id)}" title="Close">X</button>
    </header>
    <div class="widget-body"></div>
  `;

  widgetDock.appendChild(panel);
  appState.widgetPanels.set(id, panel);
  updateWidgetPanel(panel, widget, payload);

  const savedPosition = appState.widgetPositions.get(id);
  applyWidgetPosition(panel, savedPosition || defaultWidgetPosition(panel, index, total));

  return panel;
}

function updateWidgetPanel(panel, widget, payload) {
  const type = String(widget.widget_type || "widget").toLowerCase();
  const title = widget.title || type;
  const bodyHtml = widgetBody(widget, payload);
  const bodyKey = `${type}:${bodyHtml}`;

  panel.dataset.widgetType = type;
  panel.querySelector(".widget-type").style.background = markerColor(type);
  panel.querySelector(".widget-title").textContent = title;

  if (appState.widgetBodyKeys.get(panel.dataset.widgetId) !== bodyKey) {
    panel.querySelector(".widget-body").innerHTML = bodyHtml;
    appState.widgetBodyKeys.set(panel.dataset.widgetId, bodyKey);
  }
}

function renderWidgets(payload) {
  const widgets = payload?.state?.active_widgets || [];
  const activeIds = new Set();

  root.classList.toggle("has-widgets", widgets.length > 0);

  widgets.forEach((widget, index) => {
    const id = widget.widget_id || widget.widget_type || "widget";
    activeIds.add(id);

    const existingPanel = appState.widgetPanels.get(id);

    if (existingPanel) {
      updateWidgetPanel(existingPanel, widget, payload);
      const savedPosition = appState.widgetPositions.get(id);

      if (savedPosition) {
        applyWidgetPosition(existingPanel, savedPosition);
      }

      return;
    }

    createWidgetPanel(widget, payload, index, widgets.length);
  });

  for (const [id, panel] of appState.widgetPanels.entries()) {
    if (activeIds.has(id)) {
      continue;
    }

    panel.remove();
    appState.widgetPanels.delete(id);
    appState.widgetBodyKeys.delete(id);
  }
}

function startWidgetDrag(event) {
  const handle = event.target.closest("[data-drag-handle]");
  const panel = event.target.closest(".widget-panel");

  if (!handle || !panel || event.target.closest(".widget-close")) {
    return;
  }

  const rect = panel.getBoundingClientRect();
  appState.widgetZ += 1;
  panel.style.zIndex = String(appState.widgetZ);
  panel.classList.add("is-dragging");
  appState.dragging = {
    widgetId: panel.dataset.widgetId,
    panel,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: rect.left,
    originY: rect.top,
  };

  try {
    panel.setPointerCapture(event.pointerId);
  } catch (error) {
    // Pointer capture is best effort; document listeners below still handle drag.
  }

  event.preventDefault();
}

function dragWidget(event) {
  const drag = appState.dragging;

  if (!drag) {
    return;
  }

  const x = drag.originX + event.clientX - drag.startX;
  const y = drag.originY + event.clientY - drag.startY;
  applyWidgetPosition(drag.panel, { x, y });
}

function endWidgetDrag() {
  const drag = appState.dragging;

  if (!drag) {
    return;
  }

  drag.panel.classList.remove("is-dragging");
  appState.dragging = null;
}

async function closeWidget(widgetId) {
  try {
    await fetch(`/api/widgets/${encodeURIComponent(widgetId)}/close`, {
      method: "POST",
    });
    await pollState();
  } catch (error) {
    console.warn("Failed to close widget", error);
  }
}

async function closeAllWidgets() {
  try {
    await fetch("/api/widgets/close-all", {
      method: "POST",
    });
    await pollState();
  } catch (error) {
    console.warn("Failed to close widgets", error);
  }
}

function renderPayload(payload) {
  appState.payload = payload;
  renderStatus(payload);
  renderChatRail(payload.chat_history || []);
  renderWidgets(payload);
}

async function pollState() {
  try {
    const response = await fetch(`/api/state?ts=${Date.now()}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();

    appState.offline = false;
    appState.lastStateAt = Date.now();
    root.classList.remove("is-offline");
    connectionBadge.textContent = "LOCAL LINK";
    renderPayload(payload);
  } catch (error) {
    appState.offline = true;
    root.classList.add("is-offline");
    connectionBadge.textContent = "DISCONNECTED";
    appState.status = "OFFLINE";
    root.dataset.status = "OFFLINE";
  }
}

function animationLoop(now) {
  drawReactor(now);
  requestAnimationFrame(animationLoop);
}

function updateClock() {
  clockLabel.textContent = formatTime();
}

fullscreenBtn.addEventListener("click", async () => {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  } catch (error) {
    console.warn("Fullscreen failed", error);
  }
});

closeWidgetsBtn.addEventListener("click", closeAllWidgets);

widgetDock.addEventListener("click", (event) => {
  const button = event.target.closest("[data-close-widget]");

  if (!button) {
    return;
  }

  closeWidget(button.dataset.closeWidget);
});

widgetDock.addEventListener("pointerdown", startWidgetDrag);
document.addEventListener("pointermove", dragWidget);
document.addEventListener("pointerup", endWidgetDrag);
document.addEventListener("pointercancel", endWidgetDrag);

window.addEventListener("resize", () => {
  resizeCanvas();

  for (const panel of appState.widgetPanels.values()) {
    const position = appState.widgetPositions.get(panel.dataset.widgetId);

    if (position) {
      applyWidgetPosition(panel, position);
    }
  }
});

updateClock();
setInterval(updateClock, 1000);
pollState();
setInterval(pollState, 500);
requestAnimationFrame(animationLoop);
