const state = {
  operations: [],
  activeId: null,
  activePayload: null,
  activeInfoTab: "overview",
  activeVariant: "total",
  cacheBust: "",
};

const elements = {
  tabs: document.getElementById("operationTabs"),
  variantSection: document.getElementById("variantSection"),
  variantTabs: document.getElementById("variantTabs"),
  metricsGrid: document.getElementById("metricsGrid"),
  timeline: document.getElementById("timeline"),
  comparisonCards: document.getElementById("comparisonCards"),
  tableBody: document.getElementById("eventsTableBody"),
  sourceInfo: document.getElementById("sourceInfo"),
  refreshButton: document.getElementById("refreshButton"),
  statusPill: document.getElementById("statusPill"),
  operationBadge: document.getElementById("operationBadge"),
  activeOperationName: document.getElementById("activeOperationName"),
  activeOperationDescription: document.getElementById("activeOperationDescription"),
  identityGrid: document.getElementById("identityGrid"),
  infoPanelContent: document.getElementById("infoPanelContent"),
  heroMiniMetrics: document.getElementById("heroMiniMetrics"),
  paymentsChart: document.getElementById("paymentsChart"),
  balanceChart: document.getElementById("balanceChart"),
  compositionChart: document.getElementById("compositionChart"),
  comparisonChart: document.getElementById("comparisonChart"),
  paymentsTooltip: document.getElementById("paymentsTooltip"),
  balanceTooltip: document.getElementById("balanceTooltip"),
  compositionTooltip: document.getElementById("compositionTooltip"),
  comparisonTooltip: document.getElementById("comparisonTooltip"),
  infoTabs: Array.from(document.querySelectorAll(".info-tab")),
};

function parseBrDate(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const [day, month, year] = value.split("/");
  if (!day || !month || !year) {
    return null;
  }
  return new Date(Number(year), Number(month) - 1, Number(day));
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return Number.isNaN(value) ? null : value;
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  if (text.includes(",") && text.includes(".")) {
    return Number(text.replaceAll(".", "").replace(",", "."));
  }
  if (text.includes(",")) {
    return Number(text.replace(",", "."));
  }
  const numeric = Number(text);
  return Number.isNaN(numeric) ? null : numeric;
}

function formatCurrency(value) {
  const number = toNumber(value);
  if (number === null) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 2,
  }).format(number);
}

function formatCompactCurrency(value) {
  const number = toNumber(value);
  if (number === null) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(number);
}

function formatNumber(value, digits = 2) {
  const number = toNumber(value);
  if (number === null) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(number);
}

function setStatus(text, kind = "default") {
  elements.statusPill.textContent = text;
  elements.statusPill.style.color = kind === "error" ? "#ffb0b0" : "#f3f7fb";
}

function formatFieldValue(label, value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (value === "-") {
    return value;
  }

  const lower = label.toLowerCase();
  if (lower.includes("codigo") || lower.includes("emissor") || lower.includes("escopo") || lower.includes("tipos") || lower.includes("garantias") || lower.includes("distribuicao") || lower.includes("risco")) {
    return String(value);
  }
  if (lower.includes("data") || lower.includes("inicio")) {
    return String(value);
  }
  if (lower.includes("pu")) {
    return formatNumber(value, 8);
  }
  if (lower.includes("quantidade")) {
    return formatNumber(value, 0);
  }
  if (lower.includes("saldo") || lower.includes("principal") || lower.includes("pmt") || lower.includes("volume") || lower.includes("juros") || lower.includes("amortizacao")) {
    return formatCurrency(value);
  }
  return String(value);
}

function createMetricCard(title, value, subtitle) {
  const card = document.createElement("article");
  card.className = "metric-card tilt-card";
  card.innerHTML = `
    <p class="metric-title">${title}</p>
    <h3 class="metric-value">${value}</h3>
    <p class="metric-subtitle">${subtitle}</p>
  `;
  return card;
}

function renderHeroMiniMetrics(payload) {
  const summary = payload.summary;
  const metrics = [
    { label: "Indexador", value: payload.operation.indexer },
    { label: "Eventos", value: String(summary.event_count ?? "-") },
    { label: "Ultimo evento", value: summary.last_event_date || "-" },
    { label: "Proximo PMT", value: summary.next_payment_date || "-" },
  ];
  elements.heroMiniMetrics.innerHTML = metrics.map((item) => `
    <div class="hero-mini-card">
      <span>${item.label}</span>
      <strong>${item.value}</strong>
    </div>
  `).join("");
}

function renderIdentity(payload) {
  elements.identityGrid.innerHTML = payload.operation.identity_fields.map((item) => `
    <div class="identity-card">
      <span>${item.label}</span>
      <strong>${formatFieldValue(item.label, item.value)}</strong>
    </div>
  `).join("");
}

function renderInfoPanel(payload) {
  elements.infoTabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === state.activeInfoTab);
  });

  if (state.activeInfoTab === "sources") {
    const meta = payload.meta || {};
    const sourceBlocks = [
      { label: "Fonte principal", value: meta.primary_source || "-" },
      { label: "Fonte complementar", value: meta.secondary_source || "-" },
      { label: "Observacoes", value: meta.notes || "-" },
      { label: "Script", value: payload.operation.script_path || "-" },
    ];
    elements.infoPanelContent.innerHTML = `
      <div class="info-grid">
        ${sourceBlocks.map((item) => `
          <div class="data-pair">
            <label>${item.label}</label>
            <strong>${item.value}</strong>
          </div>
        `).join("")}
      </div>
    `;
    return;
  }

  const fields = state.activeInfoTab === "pu" ? payload.operation.pu_fields : payload.operation.overview_fields;
  elements.infoPanelContent.innerHTML = `
    <div class="info-grid">
      ${fields.map((item) => `
        <div class="data-pair">
          <label>${item.label}</label>
          <strong>${formatFieldValue(item.label, item.value)}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderMetrics(payload) {
  const summary = payload.summary;
  elements.metricsGrid.innerHTML = "";

  const cards = [
    createMetricCard("Saldo atual", formatCompactCurrency(summary.current_balance), "Saldo na data corrente da selecao."),
    createMetricCard("Principal atualizado", formatCompactCurrency(summary.current_principal), "Principal capturado na linha mais recente aplicavel."),
    createMetricCard("PU cheio", summary.current_pu_cheio !== null ? formatNumber(summary.current_pu_cheio, 2) : "-", "Arredondado para leitura rapida."),
    createMetricCard("PU vazio", summary.current_pu_vazio !== null ? formatNumber(summary.current_pu_vazio, 2) : "-", "Arredondado para leitura rapida."),
    createMetricCard("Juros acumulados", formatCompactCurrency(summary.total_interest), "Soma dos juros do fluxo calculado."),
    createMetricCard("Amortizacao acumulada", formatCompactCurrency(summary.total_amortization), "Soma das amortizacoes do fluxo calculado."),
  ];

  cards.forEach((card) => elements.metricsGrid.appendChild(card));
  applyTilt(elements.metricsGrid.querySelectorAll(".tilt-card"));
}

function renderTabs() {
  elements.tabs.innerHTML = "";
  state.operations.forEach((operation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `operation-tab${operation.id === state.activeId ? " active" : ""}`;
    button.innerHTML = `
      <strong>${operation.label}</strong>
      <span>${operation.indexer} - ${operation.badge}</span>
    `;
    button.addEventListener("click", () => {
      const nextVariant = operation.id === "axs02" ? "total" : "";
      loadOperation(operation.id, false, nextVariant);
    });
    elements.tabs.appendChild(button);
  });
}

function renderVariantSelector(payload) {
  const options = payload.variant_options || [];
  const show = payload.operation.id === "axs02" && options.length > 0;
  elements.variantSection.classList.toggle("hidden", !show);
  if (!show) {
    elements.variantTabs.innerHTML = "";
    return;
  }
  elements.variantTabs.innerHTML = options.map((option) => `
    <button type="button" class="variant-tab${option.id === payload.selected_variant ? " active" : ""}" data-variant="${option.id}">
      ${option.label}
    </button>
  `).join("");

  Array.from(elements.variantTabs.querySelectorAll(".variant-tab")).forEach((button) => {
    button.addEventListener("click", () => {
      loadOperation("axs02", false, button.dataset.variant || "total");
    });
  });
}

function renderTimeline(payload) {
  const items = payload.timeline && payload.timeline.length ? payload.timeline : payload.series.slice(0, 6);
  elements.timeline.innerHTML = items.map((item) => `
    <article class="timeline-item">
      <h3>${item.date || "-"}</h3>
      <p>${item.label || "Evento"}<br>${formatCurrency(item.payment)} de PMT<br>Saldo apos evento: ${formatCurrency(item.balance)}</p>
    </article>
  `).join("");
}

function renderComparisonCards(payload) {
  const rows = payload.comparison || [];
  elements.comparisonCards.innerHTML = rows.slice(0, 8).map((item) => `
    <article class="comparison-card">
      <h3>${item.label}</h3>
      <p>${item.indexer}<br>Saldo atual: ${formatCurrency(item.current_balance)}<br>Proximo PMT: ${formatCurrency(item.next_payment_amount)}</p>
    </article>
  `).join("");
}

function getFocusSlice(series, maxItems = 24) {
  if (!series.length) {
    return [];
  }
  const today = new Date();
  const futureIndex = series.findIndex((item) => {
    const parsed = parseBrDate(item.date);
    return parsed && parsed >= today;
  });
  if (futureIndex === -1) {
    return series.slice(Math.max(0, series.length - maxItems));
  }
  const start = Math.max(0, futureIndex - 8);
  return series.slice(start, start + maxItems);
}

function renderTable(payload) {
  const tableSeries = payload.table_series || payload.series;
  const rows = getFocusSlice(tableSeries, 18);
  elements.tableBody.innerHTML = rows.map((item) => `
    <tr>
      <td>${item.date || "-"}</td>
      <td>${item.component_label || "-"}</td>
      <td>${item.label || "-"}</td>
      <td>${item.pu_cheio !== null ? formatNumber(item.pu_cheio, 8) : "-"}</td>
      <td>${item.pu_vazio !== null ? formatNumber(item.pu_vazio, 8) : "-"}</td>
      <td>${item.pu_juros !== null ? formatNumber(item.pu_juros, 8) : "-"}</td>
      <td>${item.pu_amort !== null ? formatNumber(item.pu_amort, 8) : "-"}</td>
      <td>${formatCurrency(item.interest)}</td>
      <td>${formatCurrency(item.amortization)}</td>
      <td>${formatCurrency(item.payment)}</td>
      <td>${formatCurrency(item.principal)}</td>
      <td>${formatCurrency(item.balance)}</td>
    </tr>
  `).join("");
}

function renderSources(payload) {
  const meta = payload.meta || {};
  const lines = [
    `<div><strong>Fonte principal:</strong> ${meta.primary_source || "-"}</div>`,
    meta.secondary_source ? `<div><strong>Fonte complementar:</strong> ${meta.secondary_source}</div>` : "",
    meta.notes ? `<div><strong>Observacoes:</strong> ${meta.notes}</div>` : "",
    `<div><strong>Script:</strong> ${payload.operation.script_path}</div>`,
  ].filter(Boolean);
  elements.sourceInfo.innerHTML = lines.join("");
}

function updateHero(payload) {
  elements.operationBadge.textContent = payload.operation.badge;
  elements.activeOperationName.textContent = payload.operation.full_name;
  elements.activeOperationDescription.textContent = payload.operation.description;
  renderHeroMiniMetrics(payload);
  renderIdentity(payload);
  renderInfoPanel(payload);
  renderVariantSelector(payload);
}

function renderPayload(payload) {
  state.activePayload = payload;
  state.activeVariant = payload.selected_variant || "";
  updateHero(payload);
  renderTabs();
  renderMetrics(payload);
  renderTimeline(payload);
  renderComparisonCards(payload);
  renderTable(payload);
  renderSources(payload);

  const focusSlice = getFocusSlice(payload.series, 24);
  drawLineChart({
    svg: elements.paymentsChart,
    tooltip: elements.paymentsTooltip,
    data: focusSlice,
    key: "payment",
    lineColor: "#73f0c5",
    areaColor: "rgba(115, 240, 197, 0.16)",
    valueFormatter: formatCurrency,
  });
  drawLineChart({
    svg: elements.balanceChart,
    tooltip: elements.balanceTooltip,
    data: focusSlice,
    key: "balance",
    lineColor: "#ffb36b",
    areaColor: "rgba(255, 179, 107, 0.14)",
    valueFormatter: formatCurrency,
  });
  drawGroupedBarChart({
    svg: elements.compositionChart,
    tooltip: elements.compositionTooltip,
    data: focusSlice.slice(0, 16),
    leftKey: "interest",
    rightKey: "amortization",
    leftColor: "#82b5ff",
    rightColor: "#73f0c5",
  });
  drawHorizontalBarChart({
    svg: elements.comparisonChart,
    tooltip: elements.comparisonTooltip,
    data: (payload.comparison || []).slice(0, 7),
    activeId: payload.operation.id,
  });
}

function normalizePoint(value, min, max, size) {
  if (max === min) {
    return size / 2;
  }
  return ((value - min) / (max - min)) * size;
}

function drawLineChart({ svg, tooltip, data, key, lineColor, areaColor, valueFormatter }) {
  const width = 760;
  const height = 320;
  const padding = { top: 24, right: 18, bottom: 36, left: 18 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const safeData = data.filter((item) => typeof item[key] === "number");
  svg.innerHTML = "";
  if (!safeData.length) {
    return;
  }

  const minValue = Math.min(...safeData.map((item) => item[key]));
  const maxValue = Math.max(...safeData.map((item) => item[key]));
  const points = safeData.map((item, index) => {
    const x = padding.left + (safeData.length === 1 ? innerWidth / 2 : (index / (safeData.length - 1)) * innerWidth);
    const y = height - padding.bottom - normalizePoint(item[key], minValue, maxValue, innerHeight);
    return { ...item, x, y };
  });

  for (let i = 0; i < 4; i += 1) {
    const y = padding.top + (innerHeight / 3) * i;
    const guide = document.createElementNS("http://www.w3.org/2000/svg", "line");
    guide.setAttribute("x1", String(padding.left));
    guide.setAttribute("x2", String(width - padding.right));
    guide.setAttribute("y1", String(y));
    guide.setAttribute("y2", String(y));
    guide.setAttribute("stroke", "rgba(255,255,255,0.08)");
    guide.setAttribute("stroke-width", "1");
    svg.appendChild(guide);
  }

  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${height - padding.bottom} L ${points[0].x} ${height - padding.bottom} Z`;

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", areaColor);
  svg.appendChild(area);

  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", linePath);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", lineColor);
  line.setAttribute("stroke-width", "3");
  line.setAttribute("stroke-linecap", "round");
  svg.appendChild(line);

  points.forEach((point) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(point.x));
    circle.setAttribute("cy", String(point.y));
    circle.setAttribute("r", "5");
    circle.setAttribute("fill", lineColor);
    circle.setAttribute("stroke", "#08111f");
    circle.setAttribute("stroke-width", "2");
    circle.style.cursor = "pointer";
    circle.addEventListener("mouseenter", () => {
      tooltip.classList.remove("hidden");
      tooltip.innerHTML = `
        <strong>${point.date || "-"}</strong>
        <div>${point.label || "Evento"}</div>
        <div>${valueFormatter(point[key])}</div>
      `;
    });
    circle.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      tooltip.style.left = `${event.clientX - rect.left}px`;
      tooltip.style.top = `${event.clientY - rect.top}px`;
    });
    circle.addEventListener("mouseleave", () => {
      tooltip.classList.add("hidden");
    });
    svg.appendChild(circle);
  });
}

function drawGroupedBarChart({ svg, tooltip, data, leftKey, rightKey, leftColor, rightColor }) {
  const width = 760;
  const height = 320;
  const padding = { top: 20, right: 18, bottom: 40, left: 18 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const safeData = data.filter((item) => typeof item[leftKey] === "number" || typeof item[rightKey] === "number");
  svg.innerHTML = "";
  if (!safeData.length) {
    return;
  }

  const maxValue = Math.max(...safeData.flatMap((item) => [item[leftKey] || 0, item[rightKey] || 0]));
  const groupWidth = innerWidth / safeData.length;
  const barWidth = Math.max(8, groupWidth * 0.28);

  safeData.forEach((item, index) => {
    const xBase = padding.left + index * groupWidth + groupWidth * 0.18;
    const interestHeight = ((item[leftKey] || 0) / maxValue) * innerHeight;
    const amortHeight = ((item[rightKey] || 0) / maxValue) * innerHeight;
    const bars = [
      { x: xBase, height: interestHeight, color: leftColor, label: "Juros", value: item[leftKey] || 0 },
      { x: xBase + barWidth + 6, height: amortHeight, color: rightColor, label: "Amortizacao", value: item[rightKey] || 0 },
    ];

    bars.forEach((bar) => {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(bar.x));
      rect.setAttribute("y", String(height - padding.bottom - bar.height));
      rect.setAttribute("width", String(barWidth));
      rect.setAttribute("height", String(bar.height));
      rect.setAttribute("rx", "6");
      rect.setAttribute("fill", bar.color);
      rect.style.cursor = "pointer";
      rect.addEventListener("mouseenter", () => {
        tooltip.classList.remove("hidden");
        tooltip.innerHTML = `
          <strong>${item.date || "-"}</strong>
          <div>${bar.label}</div>
          <div>${formatCurrency(bar.value)}</div>
        `;
      });
      rect.addEventListener("mousemove", (event) => {
        const rectBox = svg.getBoundingClientRect();
        tooltip.style.left = `${event.clientX - rectBox.left}px`;
        tooltip.style.top = `${event.clientY - rectBox.top}px`;
      });
      rect.addEventListener("mouseleave", () => {
        tooltip.classList.add("hidden");
      });
      svg.appendChild(rect);
    });
  });
}

function drawHorizontalBarChart({ svg, tooltip, data, activeId }) {
  const width = 760;
  const height = 320;
  const padding = { top: 20, right: 20, bottom: 20, left: 140 };
  const innerWidth = width - padding.left - padding.right;
  const rowHeight = Math.max(28, (height - padding.top - padding.bottom) / Math.max(data.length, 1));
  const maxValue = Math.max(...data.map((item) => item.current_balance || 0), 1);
  svg.innerHTML = "";

  data.forEach((item, index) => {
    const y = padding.top + index * rowHeight;
    const barWidth = ((item.current_balance || 0) / maxValue) * innerWidth;
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "8");
    label.setAttribute("y", String(y + rowHeight * 0.65));
    label.setAttribute("fill", "rgba(243,247,251,0.92)");
    label.setAttribute("font-size", "13");
    label.textContent = item.label;
    svg.appendChild(label);

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(padding.left));
    rect.setAttribute("y", String(y + 6));
    rect.setAttribute("width", String(barWidth));
    rect.setAttribute("height", String(rowHeight * 0.62));
    rect.setAttribute("rx", "9");
    rect.setAttribute("fill", item.id === activeId ? "#73f0c5" : "rgba(130,181,255,0.55)");
    rect.style.cursor = "pointer";
    rect.addEventListener("mouseenter", () => {
      tooltip.classList.remove("hidden");
      tooltip.innerHTML = `
        <strong>${item.full_name || item.label}</strong>
        <div>Saldo atual: ${formatCurrency(item.current_balance)}</div>
        <div>Proximo PMT: ${formatCurrency(item.next_payment_amount)}</div>
      `;
    });
    rect.addEventListener("mousemove", (event) => {
      const rectBox = svg.getBoundingClientRect();
      tooltip.style.left = `${event.clientX - rectBox.left}px`;
      tooltip.style.top = `${event.clientY - rectBox.top}px`;
    });
    rect.addEventListener("mouseleave", () => {
      tooltip.classList.add("hidden");
    });
    svg.appendChild(rect);
  });
}

function buildSiteUrl(relativePath) {
  const url = new URL(relativePath, document.baseURI);
  if (state.cacheBust) {
    url.searchParams.set("t", state.cacheBust);
  }
  return url.toString();
}

function operationDataPath(operationId) {
  if (operationId === "axs02") {
    const variant = state.activeVariant || "total";
    return variant === "total"
      ? `data/operations/${operationId}.json`
      : `data/operations/${operationId}--${variant}.json`;
  }
  return `data/operations/${operationId}.json`;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Erro ${response.status}`);
  }
  return response.json();
}

async function loadOperations() {
  const data = await fetchJson(buildSiteUrl("data/operations.json"));
  state.operations = data.operations;
  state.activeId = state.activeId || data.operations[0]?.id || null;
  renderTabs();
}

async function loadOperation(operationId, refresh = false, variant = null) {
  state.activeId = operationId;
  if (operationId !== "axs02") {
    state.activeVariant = "";
  } else if (variant) {
    state.activeVariant = variant;
  } else if (!state.activeVariant) {
    state.activeVariant = "total";
  }

  renderTabs();
  setStatus(refresh ? "Atualizando dados..." : "Carregando dados...");
  const payload = await fetchJson(buildSiteUrl(operationDataPath(operationId)));
  renderPayload(payload);
  setStatus(`Analise ${payload.operation.label} atualizada em ${payload.generated_at}`);
}

function applyTilt(nodes) {
  nodes.forEach((node) => {
    node.addEventListener("mousemove", (event) => {
      const rect = node.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      node.style.transform = `perspective(1200px) rotateX(${(-y * 6).toFixed(2)}deg) rotateY(${(x * 7).toFixed(2)}deg) translateY(-2px)`;
    });
    node.addEventListener("mouseleave", () => {
      node.style.transform = "";
    });
  });
}

async function bootstrap() {
  try {
    applyTilt(document.querySelectorAll(".tilt-card"));
    elements.infoTabs.forEach((button) => {
      button.addEventListener("click", () => {
        state.activeInfoTab = button.dataset.panel;
        if (state.activePayload) {
          renderInfoPanel(state.activePayload);
        }
      });
    });
    await loadOperations();
    if (state.activeId) {
      await loadOperation(state.activeId);
    }
  } catch (error) {
    console.error(error);
    setStatus("Falha ao carregar dados", "error");
    elements.sourceInfo.innerHTML = `<div><strong>Erro:</strong> ${error.message}</div>`;
  }
}

elements.refreshButton.addEventListener("click", async () => {
  if (!state.activeId) {
    return;
  }
  try {
    state.cacheBust = `${Date.now()}`;
    await loadOperations();
    await loadOperation(state.activeId, true, state.activeVariant || null);
  } catch (error) {
    console.error(error);
    setStatus("Falha ao atualizar dados", "error");
  }
});

bootstrap();
