const METRIC_HELP = {
  "Saldo atual": "Saldo devedor da linha mais recente aplicavel a data atual. Para visoes consolidadas, soma os saldos dos instrumentos ativos na mesma data.",
  "Principal atualizado": "Base principal corrigida do fluxo na linha atual. Em geral corresponde ao VNA ou ao principal remanescente antes do proximo evento.",
  Duration: "Prazo medio financeiro gerencial, ponderado pelos PMTs futuros. Formula usada: soma de (tempo em anos x PMT futuro) dividida pela soma dos PMTs futuros.",
  "Vida media": "WAL da divida, ponderada apenas pelas amortizacoes futuras. Formula usada: soma de (tempo em anos x amortizacao futura) dividida pela soma das amortizacoes futuras.",
  "PU cheio": "PU com juros corridos embutidos, arredondado apenas nos cards superiores para leitura rapida.",
  "PU vazio": "PU base sem juros corridos, arredondado apenas nos cards superiores para leitura rapida.",
  "Juros acumulados": "Soma de todos os juros projetados ou calculados ao longo do fluxo da selecao atual.",
  "Amortizacao acumulada": "Soma de toda a amortizacao projetada ou calculada ao longo do fluxo da selecao atual.",
};

const OPERATION_HINTS = [
  { id: "geral", aliases: ["visao geral", "carteira", "consolidado", "geral"] },
  { id: "axs01", aliases: ["axs 01", "axs01", "refi 01", "axsa11", "axsa21", "unidade 01"] },
  { id: "axs02", aliases: ["axs 02", "axs02", "axsd11", "cri axs 02", "deb axs 02", "unidade 02"] },
  { id: "axs03", aliases: ["axs 03", "axs03", "axs iii", "22k1397969", "emissao 78"] },
  { id: "axs04", aliases: ["axs 04", "axs04", "axs 4", "23f0046476", "emissao 139"] },
  { id: "axs05", aliases: ["axs 05", "axs05", "axsc12", "axsc22", "unidade 05"] },
  { id: "axs06", aliases: ["axs 06", "axs06", "axse12", "unidade 06"] },
  { id: "axs07", aliases: ["axs 07", "axs07", "axsu11", "unidade 07"] },
  { id: "axs08", aliases: ["axs 08", "axs08", "axs811", "unidade 08"] },
  { id: "axs09", aliases: ["axs 09", "axs09", "axs911", "unidade 09"] },
  { id: "axs10", aliases: ["axs 10", "axs10", "axs411", "unidade 10"] },
  { id: "axs11", aliases: ["axs 11", "axs11", "axsi11", "unidade 11"] },
  { id: "axsgoias", aliases: ["axs goias", "goias", "goias spe", "axs311"] },
];

const state = {
  operations: [],
  activeId: null,
  activePayload: null,
  activeInfoTab: "overview",
  activeVariant: "",
  cacheBust: "",
  payloadCache: new Map(),
  knowledgeChunks: null,
  assistantOpen: false,
};

const elements = {
  tabs: document.getElementById("operationTabs"),
  variantSection: document.getElementById("variantSection"),
  variantTabs: document.getElementById("variantTabs"),
  variantHeaderTitle: document.getElementById("variantHeaderTitle"),
  variantHeaderNote: document.getElementById("variantHeaderNote"),
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

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

function formatYears(value) {
  const number = toNumber(value);
  if (number === null) {
    return "-";
  }
  return `${formatNumber(number, 2)} anos`;
}

function setStatus(text, kind = "default") {
  elements.statusPill.textContent = text;
  elements.statusPill.style.color = kind === "error" ? "#ffb0b0" : "#f3f7fb";
}

function getOperationDefinition(operationId) {
  return state.operations.find((item) => item.id === operationId) || null;
}

function defaultVariantForOperation(operationId) {
  const operation = getOperationDefinition(operationId);
  const options = operation?.variant_options || [];
  return options.length ? options[0].id : "";
}

function operationDataPath(operationId, variantId = null) {
  const operation = getOperationDefinition(operationId);
  const options = operation?.variant_options || [];
  const effectiveVariant = variantId || defaultVariantForOperation(operationId);
  if (options.length && effectiveVariant && effectiveVariant !== "total") {
    return `data/operations/${operationId}--${effectiveVariant}.json`;
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

function buildSiteUrl(relativePath) {
  const url = new URL(relativePath, document.baseURI);
  if (state.cacheBust) {
    url.searchParams.set("t", state.cacheBust);
  }
  return url.toString();
}

function formatFieldValue(label, value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (value === "-") {
    return value;
  }
  const lower = normalizeText(label);
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
  if (lower.includes("duration") || lower.includes("vida media")) {
    return formatYears(value);
  }
  if (lower.includes("saldo") || lower.includes("principal") || lower.includes("pmt") || lower.includes("volume") || lower.includes("juros") || lower.includes("amortizacao")) {
    return formatCurrency(value);
  }
  return String(value);
}

function createMetricCard(title, value, subtitle, tooltip) {
  const card = document.createElement("article");
  card.className = "metric-card tilt-card";
  const tooltipMarkup = tooltip
    ? `
      <div class="metric-help">
        <button class="metric-help-button" type="button" aria-label="Explicar ${title}">i</button>
        <div class="metric-help-bubble">${escapeHtml(tooltip)}</div>
      </div>
    `
    : "";
  card.innerHTML = `
    <div class="metric-head">
      <p class="metric-title">${title}</p>
      ${tooltipMarkup}
    </div>
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
    { label: "Duration", value: summary.duration_years !== null && summary.duration_years !== undefined ? formatYears(summary.duration_years) : "-" },
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
            <strong>${escapeHtml(item.value)}</strong>
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
    createMetricCard("Saldo atual", formatCompactCurrency(summary.current_balance), "Saldo na data corrente da selecao.", METRIC_HELP["Saldo atual"]),
    createMetricCard("Principal atualizado", formatCompactCurrency(summary.current_principal), "Principal capturado na linha mais recente aplicavel.", METRIC_HELP["Principal atualizado"]),
    createMetricCard("Duration", formatYears(summary.duration_years), "Prazo medio ponderado pelos PMTs futuros.", METRIC_HELP.Duration),
    createMetricCard("Vida media", formatYears(summary.wal_years), "Prazo medio ponderado pelas amortizacoes futuras.", METRIC_HELP["Vida media"]),
    createMetricCard("PU cheio", summary.current_pu_cheio !== null ? formatNumber(summary.current_pu_cheio, 2) : "-", "Arredondado para leitura rapida.", METRIC_HELP["PU cheio"]),
    createMetricCard("PU vazio", summary.current_pu_vazio !== null ? formatNumber(summary.current_pu_vazio, 2) : "-", "Arredondado para leitura rapida.", METRIC_HELP["PU vazio"]),
    createMetricCard("Juros acumulados", formatCompactCurrency(summary.total_interest), "Soma dos juros do fluxo calculado.", METRIC_HELP["Juros acumulados"]),
    createMetricCard("Amortizacao acumulada", formatCompactCurrency(summary.total_amortization), "Soma das amortizacoes do fluxo calculado.", METRIC_HELP["Amortizacao acumulada"]),
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
      loadOperation(operation.id, false, defaultVariantForOperation(operation.id) || null);
    });
    elements.tabs.appendChild(button);
  });
}

function variantHeaderText(payload) {
  const options = payload.variant_options || [];
  const optionIds = options.map((item) => item.id);
  if (optionIds.includes("cri") || optionIds.includes("deb")) {
    return {
      title: `Visao da ${payload.operation.label}`,
      note: "Sem selecao extra, o dashboard mostra o total consolidado entre CRI e Debenture.",
    };
  }
  return {
    title: `Visao da ${payload.operation.label}`,
    note: "Sem selecao extra, o dashboard mostra o consolidado somado das series da emissao.",
  };
}

function renderVariantSelector(payload) {
  const options = payload.variant_options || [];
  const show = options.length > 0;
  elements.variantSection.classList.toggle("hidden", !show);
  if (!show) {
    elements.variantTabs.innerHTML = "";
    return;
  }
  const header = variantHeaderText(payload);
  if (elements.variantHeaderTitle) {
    elements.variantHeaderTitle.textContent = header.title;
  }
  if (elements.variantHeaderNote) {
    elements.variantHeaderNote.textContent = header.note;
  }
  elements.variantTabs.innerHTML = options.map((option) => `
    <button type="button" class="variant-tab${option.id === payload.selected_variant ? " active" : ""}" data-variant="${option.id}">
      ${option.label}
    </button>
  `).join("");

  Array.from(elements.variantTabs.querySelectorAll(".variant-tab")).forEach((button) => {
    button.addEventListener("click", () => {
      loadOperation(payload.operation.id, false, button.dataset.variant || defaultVariantForOperation(payload.operation.id));
    });
  });
}

function renderTimeline(payload) {
  const items = payload.timeline && payload.timeline.length ? payload.timeline : payload.series.slice(0, 6);
  elements.timeline.innerHTML = items.map((item) => `
    <article class="timeline-item">
      <h3>${item.date || "-"}</h3>
      <p>${item.label || "Evento"}<br>PMT: ${formatCurrency(item.payment)}<br>Saldo apos evento: ${formatCurrency(item.balance)}</p>
    </article>
  `).join("");
}

function renderComparisonCards(payload) {
  const rows = payload.comparison || [];
  elements.comparisonCards.innerHTML = rows.slice(0, 10).map((item) => `
    <article class="comparison-card">
      <h3>${item.label}</h3>
      <p>${item.indexer}<br>Saldo atual: ${formatCurrency(item.current_balance)}<br>Proximo PMT: ${formatCurrency(item.next_payment_amount)}<br>Juros acumulados: ${formatCompactCurrency(item.total_interest)}</p>
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
    `<div><strong>Fonte principal:</strong> ${escapeHtml(meta.primary_source || "-")}</div>`,
    meta.secondary_source ? `<div><strong>Fonte complementar:</strong> ${escapeHtml(meta.secondary_source)}</div>` : "",
    meta.notes ? `<div><strong>Observacoes:</strong> ${escapeHtml(meta.notes)}</div>` : "",
    `<div><strong>Script:</strong> ${escapeHtml(payload.operation.script_path || "-")}</div>`,
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
  state.activeVariant = payload.selected_variant || defaultVariantForOperation(payload.operation.id) || "";
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
    data: (payload.comparison || []).slice(0, 8),
    activeId: payload.operation.id,
  });
}

function normalizePoint(value, min, max, size) {
  if (max === min) {
    return size / 2;
  }
  return ((value - min) / (max - min)) * size;
}

function sampleYearEntries(entries, maxLabels = 6) {
  if (entries.length <= maxLabels) {
    return entries;
  }
  const sampled = [entries[0]];
  const step = Math.ceil((entries.length - 2) / (maxLabels - 2));
  for (let index = step; index < entries.length - 1; index += step) {
    sampled.push(entries[index]);
  }
  sampled.push(entries[entries.length - 1]);
  return sampled.slice(0, maxLabels);
}

function buildYearEntries(data, getX) {
  const entries = [];
  let lastYear = null;
  data.forEach((item, index) => {
    const parsed = parseBrDate(item.date);
    if (!parsed) {
      return;
    }
    const year = String(parsed.getFullYear());
    if (year !== lastYear) {
      entries.push({ year, x: getX(item, index) });
      lastYear = year;
    }
  });
  return sampleYearEntries(entries);
}

function appendYearAxis(svg, entries, yBase, color = "rgba(243,247,251,0.58)") {
  entries.forEach((entry) => {
    const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
    tick.setAttribute("x1", String(entry.x));
    tick.setAttribute("x2", String(entry.x));
    tick.setAttribute("y1", String(yBase - 8));
    tick.setAttribute("y2", String(yBase - 2));
    tick.setAttribute("stroke", color);
    tick.setAttribute("stroke-width", "1");
    svg.appendChild(tick);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(entry.x));
    label.setAttribute("y", String(yBase + 16));
    label.setAttribute("fill", color);
    label.setAttribute("font-size", "12");
    label.setAttribute("text-anchor", "middle");
    label.textContent = entry.year;
    svg.appendChild(label);
  });
}

function drawLineChart({ svg, tooltip, data, key, lineColor, areaColor, valueFormatter }) {
  const width = 760;
  const height = 320;
  const padding = { top: 24, right: 18, bottom: 42, left: 18 };
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

  const baseLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  baseLine.setAttribute("x1", String(padding.left));
  baseLine.setAttribute("x2", String(width - padding.right));
  baseLine.setAttribute("y1", String(height - padding.bottom));
  baseLine.setAttribute("y2", String(height - padding.bottom));
  baseLine.setAttribute("stroke", "rgba(255,255,255,0.12)");
  baseLine.setAttribute("stroke-width", "1");
  svg.appendChild(baseLine);

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

  appendYearAxis(svg, buildYearEntries(points, (item) => item.x), height - padding.bottom);

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
  const padding = { top: 20, right: 18, bottom: 44, left: 18 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const safeData = data.filter((item) => typeof item[leftKey] === "number" || typeof item[rightKey] === "number");
  svg.innerHTML = "";
  if (!safeData.length) {
    return;
  }

  const maxValue = Math.max(...safeData.flatMap((item) => [item[leftKey] || 0, item[rightKey] || 0]), 1);
  const groupWidth = innerWidth / safeData.length;
  const barWidth = Math.max(8, groupWidth * 0.28);

  const baseLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  baseLine.setAttribute("x1", String(padding.left));
  baseLine.setAttribute("x2", String(width - padding.right));
  baseLine.setAttribute("y1", String(height - padding.bottom));
  baseLine.setAttribute("y2", String(height - padding.bottom));
  baseLine.setAttribute("stroke", "rgba(255,255,255,0.12)");
  baseLine.setAttribute("stroke-width", "1");
  svg.appendChild(baseLine);

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

  appendYearAxis(
    svg,
    buildYearEntries(safeData, (_, index) => padding.left + index * groupWidth + groupWidth * 0.5),
    height - padding.bottom,
  );
}

function drawHorizontalBarChart({ svg, tooltip, data, activeId }) {
  const width = 760;
  const height = 320;
  const padding = { top: 20, right: 20, bottom: 20, left: 148 };
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

async function loadOperations() {
  const data = await fetchJson(buildSiteUrl("data/operations.json"));
  state.operations = data.operations;
  state.activeId = state.activeId || data.operations[0]?.id || null;
  renderTabs();
}

async function ensurePayload(operationId, variantId = null, refresh = false) {
  const effectiveVariant = variantId || defaultVariantForOperation(operationId) || "";
  const key = `${operationId}::${effectiveVariant || "base"}`;
  if (!refresh && state.payloadCache.has(key)) {
    return state.payloadCache.get(key);
  }
  const payload = await fetchJson(buildSiteUrl(operationDataPath(operationId, effectiveVariant)));
  state.payloadCache.set(key, payload);
  return payload;
}

async function loadOperation(operationId, refresh = false, variant = null) {
  state.activeId = operationId;
  const operation = getOperationDefinition(operationId);
  if (operation?.variant_options?.length) {
    state.activeVariant = variant || defaultVariantForOperation(operationId);
  } else {
    state.activeVariant = "";
  }
  renderTabs();
  setStatus(refresh ? "Atualizando dados..." : "Carregando dados...");
  const payload = await ensurePayload(operationId, state.activeVariant || null, refresh);
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

function buildAssistant() {
  const shell = document.createElement("div");
  shell.innerHTML = `
    <button id="assistantLauncher" class="assistant-launcher" type="button" aria-label="Abrir assistente">
      <span>IA</span>
    </button>
    <section id="assistantPanel" class="assistant-panel hidden">
      <header class="assistant-header">
        <div>
          <strong>Assistente do dashboard</strong>
          <small>Documentos + calculos da carteira</small>
        </div>
        <button id="assistantClose" class="assistant-close" type="button" aria-label="Fechar assistente">x</button>
      </header>
      <div id="assistantMessages" class="assistant-messages"></div>
      <form id="assistantForm" class="assistant-form">
        <textarea id="assistantInput" class="assistant-input" rows="2" placeholder="Ex.: quanto sera a PMT da AXS 05 em 15/05/2026?"></textarea>
        <button class="assistant-send" type="submit">Enviar</button>
      </form>
    </section>
  `;
  document.body.appendChild(shell);

  const assistant = {
    launcher: document.getElementById("assistantLauncher"),
    panel: document.getElementById("assistantPanel"),
    close: document.getElementById("assistantClose"),
    messages: document.getElementById("assistantMessages"),
    form: document.getElementById("assistantForm"),
    input: document.getElementById("assistantInput"),
  };

  assistant.launcher.addEventListener("click", () => toggleAssistant(true));
  assistant.close.addEventListener("click", () => toggleAssistant(false));
  assistant.form.addEventListener("submit", handleAssistantSubmit);

  addAssistantMessage(
    "assistant",
    "Consigo responder com base na documentacao da emissao e tambem nos valores calculados do dashboard. Tente perguntar sobre PMT, saldo, duration, vencimento, remuneracao ou garantias.",
  );

  return assistant;
}

function toggleAssistant(forceOpen) {
  state.assistantOpen = typeof forceOpen === "boolean" ? forceOpen : !state.assistantOpen;
  if (!state.assistant) {
    return;
  }
  state.assistant.panel.classList.toggle("hidden", !state.assistantOpen);
}

function addAssistantMessage(role, content, allowHtml = false) {
  if (!state.assistant) {
    return;
  }
  const item = document.createElement("article");
  item.className = `assistant-message ${role}`;
  item.innerHTML = allowHtml ? content : escapeHtml(content);
  state.assistant.messages.appendChild(item);
  state.assistant.messages.scrollTop = state.assistant.messages.scrollHeight;
}

function detectOperationId(normalizedQuestion) {
  const matches = [];
  OPERATION_HINTS.forEach((entry) => {
    entry.aliases.forEach((alias) => {
      const normalizedAlias = normalizeText(alias);
      if (normalizedQuestion.includes(normalizedAlias)) {
        matches.push({ id: entry.id, size: normalizedAlias.length });
      }
    });
  });
  matches.sort((left, right) => right.size - left.size);
  return matches[0]?.id || null;
}

function detectVariantId(operationId, normalizedQuestion) {
  if (operationId === "axs02") {
    if (normalizedQuestion.includes("debenture") || normalizedQuestion.includes(" deb ")) {
      return "deb";
    }
    if (normalizedQuestion.includes("cri")) {
      return "cri";
    }
    return "total";
  }
  if (operationId === "axs01" || operationId === "axs05") {
    if (
      normalizedQuestion.includes("primeira serie") ||
      normalizedQuestion.includes("1a serie") ||
      normalizedQuestion.includes("serie 1") ||
      normalizedQuestion.includes("axsa11") ||
      normalizedQuestion.includes("axsc12")
    ) {
      return "primeira";
    }
    if (
      normalizedQuestion.includes("segunda serie") ||
      normalizedQuestion.includes("2a serie") ||
      normalizedQuestion.includes("serie 2") ||
      normalizedQuestion.includes("axsa21") ||
      normalizedQuestion.includes("axsc22")
    ) {
      return "segunda";
    }
    return "total";
  }
  return "";
}

function detectDateInQuestion(question) {
  const match = String(question || "").match(/\b(\d{2}\/\d{2}\/\d{4})\b/);
  return match ? match[1] : null;
}

function detectIntent(normalizedQuestion) {
  if (normalizedQuestion.includes("duration")) {
    return "duration";
  }
  if (normalizedQuestion.includes("vida media") || normalizedQuestion.includes("wal")) {
    return "wal";
  }
  if ((normalizedQuestion.includes("pmt") || normalizedQuestion.includes("pagamento") || normalizedQuestion.includes("pagar")) && detectDateInQuestion(normalizedQuestion)) {
    return "payment_on_date";
  }
  if (normalizedQuestion.includes("proximo pmt") || normalizedQuestion.includes("proximo pagamento")) {
    return "next_payment";
  }
  if (normalizedQuestion.includes("saldo") && detectDateInQuestion(normalizedQuestion)) {
    return "balance_on_date";
  }
  if (normalizedQuestion.includes("saldo")) {
    return "current_balance";
  }
  if (normalizedQuestion.includes("juros acumul")) {
    return "total_interest";
  }
  if (normalizedQuestion.includes("amortizacao acumul")) {
    return "total_amortization";
  }
  if (normalizedQuestion.includes("pu cheio")) {
    return "pu_cheio";
  }
  if (normalizedQuestion.includes("pu vazio")) {
    return "pu_vazio";
  }
  if (normalizedQuestion.includes("principal")) {
    return "principal";
  }
  if (normalizedQuestion.includes("vencimento") || normalizedQuestion.includes("vence")) {
    return "maturity";
  }
  if (normalizedQuestion.includes("emissao")) {
    return "issue";
  }
  if (normalizedQuestion.includes("remuneracao") || normalizedQuestion.includes("taxa")) {
    return "remuneration";
  }
  if (normalizedQuestion.includes("quantidade")) {
    return "quantity";
  }
  if (normalizedQuestion.includes("volume")) {
    return "volume";
  }
  if (normalizedQuestion.includes("garantia")) {
    return "guarantees";
  }
  return "document_search";
}

function getFieldByLabel(payload, labelText) {
  const labels = normalizeText(labelText);
  const fields = [
    ...(payload.operation.identity_fields || []),
    ...(payload.operation.overview_fields || []),
    ...(payload.operation.pu_fields || []),
  ];
  return fields.find((field) => normalizeText(field.label) === labels) || null;
}

function findExactRow(series, dateText) {
  return series.find((item) => item.date === dateText) || null;
}

function findRowAtOrBefore(series, dateText) {
  const target = parseBrDate(dateText);
  if (!target) {
    return null;
  }
  const candidates = series
    .map((item) => ({ ...item, parsed: parseBrDate(item.date) }))
    .filter((item) => item.parsed && item.parsed <= target);
  return candidates.length ? candidates[candidates.length - 1] : null;
}

function findNextPaymentRow(series) {
  const today = new Date();
  return series.find((item) => {
    const parsed = parseBrDate(item.date);
    return parsed && parsed >= today && toNumber(item.payment) > 0;
  }) || null;
}

function buildCalculatedAnswer(intent, payload, dateText) {
  const summary = payload.summary || {};
  const operationName = payload.operation.full_name || payload.operation.label;
  switch (intent) {
    case "duration":
      return `A duration gerencial da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatYears(summary.duration_years)}</strong>, ponderada pelos PMTs futuros.`;
    case "wal":
      return `A vida media da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatYears(summary.wal_years)}</strong>, ponderada pelas amortizacoes futuras.`;
    case "next_payment": {
      const nextDate = summary.next_payment_date || "-";
      return `O proximo PMT da <strong>${escapeHtml(operationName)}</strong> esta previsto para <strong>${escapeHtml(nextDate)}</strong>, no valor de <strong>${formatCurrency(summary.next_payment_amount)}</strong>. Juros esperados: <strong>${formatCurrency(summary.next_interest_amount)}</strong>. Amortizacao esperada: <strong>${formatCurrency(summary.next_amortization_amount)}</strong>.`;
    }
    case "payment_on_date": {
      const row = findExactRow(payload.series || [], dateText);
      if (!row) {
        return `Nao ha PMT programado para <strong>${escapeHtml(dateText)}</strong> na <strong>${escapeHtml(operationName)}</strong>. Pela leitura do fluxo, o valor de PMT nessa data e <strong>${formatCurrency(0)}</strong>.`;
      }
      return `Na data <strong>${escapeHtml(dateText)}</strong>, o PMT da <strong>${escapeHtml(operationName)}</strong> esta calculado em <strong>${formatCurrency(row.payment)}</strong>, sendo juros de <strong>${formatCurrency(row.interest)}</strong> e amortizacao de <strong>${formatCurrency(row.amortization)}</strong>.`;
    }
    case "balance_on_date": {
      const row = findRowAtOrBefore(payload.series || [], dateText);
      if (!row) {
        return `Nao encontrei uma linha aplicavel ate <strong>${escapeHtml(dateText)}</strong> para a <strong>${escapeHtml(operationName)}</strong>.`;
      }
      return `O saldo devedor da <strong>${escapeHtml(operationName)}</strong> na referencia de <strong>${escapeHtml(dateText)}</strong> esta em <strong>${formatCurrency(row.balance)}</strong>.`;
    }
    case "current_balance":
      return `O saldo atual da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatCurrency(summary.current_balance)}</strong>.`;
    case "total_interest":
      return `Os juros acumulados da <strong>${escapeHtml(operationName)}</strong> somam <strong>${formatCurrency(summary.total_interest)}</strong>.`;
    case "total_amortization":
      return `A amortizacao acumulada da <strong>${escapeHtml(operationName)}</strong> soma <strong>${formatCurrency(summary.total_amortization)}</strong>.`;
    case "pu_cheio":
      return `O PU cheio atual da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatNumber(summary.current_pu_cheio, 8)}</strong>.`;
    case "pu_vazio":
      return `O PU vazio atual da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatNumber(summary.current_pu_vazio, 8)}</strong>.`;
    case "principal":
      return `O principal atualizado da <strong>${escapeHtml(operationName)}</strong> esta em <strong>${formatCurrency(summary.current_principal)}</strong>.`;
    case "maturity": {
      const field = getFieldByLabel(payload, "Data de vencimento");
      return `A data de vencimento da <strong>${escapeHtml(operationName)}</strong> e <strong>${escapeHtml(field?.value || "-")}</strong>.`;
    }
    case "issue": {
      const field = getFieldByLabel(payload, "Data de emissao");
      return `A data de emissao da <strong>${escapeHtml(operationName)}</strong> e <strong>${escapeHtml(field?.value || "-")}</strong>.`;
    }
    case "remuneration": {
      const field = getFieldByLabel(payload, "Remuneracao");
      return `A remuneracao da <strong>${escapeHtml(operationName)}</strong> esta cadastrada como <strong>${escapeHtml(field?.value || payload.operation.indexer || "-")}</strong>.`;
    }
    case "quantity": {
      const field = getFieldByLabel(payload, "Quantidade emitida");
      return `A quantidade emitida da <strong>${escapeHtml(operationName)}</strong> e <strong>${formatFieldValue("Quantidade emitida", field?.value || "-")}</strong>.`;
    }
    case "volume": {
      const field = getFieldByLabel(payload, "Volume emitido");
      return `O volume emitido da <strong>${escapeHtml(operationName)}</strong> e <strong>${formatFieldValue("Volume emitido", field?.value || "-")}</strong>.`;
    }
    case "guarantees": {
      const field = getFieldByLabel(payload, "Garantias");
      return `As garantias informadas para a <strong>${escapeHtml(operationName)}</strong> sao: <strong>${escapeHtml(field?.value || "-")}</strong>.`;
    }
    default:
      return "";
  }
}

async function loadKnowledgeChunks() {
  if (state.knowledgeChunks !== null) {
    return state.knowledgeChunks;
  }
  try {
    const chunks = await fetchJson(buildSiteUrl("data/chunks.json"));
    state.knowledgeChunks = Array.isArray(chunks) ? chunks : [];
  } catch (error) {
    console.warn("Nao foi possivel carregar chunks.json", error);
    state.knowledgeChunks = [];
  }
  return state.knowledgeChunks;
}

function tokenizeForSearch(text) {
  return normalizeText(text)
    .split(/[^a-z0-9]+/)
    .filter((token) => token && token.length > 2 && !["que", "para", "com", "por", "uma", "das", "dos", "sera", "qual", "quais", "sobre"].includes(token));
}

function findRelevantChunks(question, operationId) {
  const chunks = state.knowledgeChunks || [];
  const tokens = tokenizeForSearch(question);
  if (!tokens.length || !chunks.length) {
    return [];
  }
  return chunks
    .map((chunk) => {
      const haystack = normalizeText(`${chunk.arquivo || ""} ${chunk.conteudo || chunk.texto || ""}`);
      let score = 0;
      tokens.forEach((token) => {
        if (haystack.includes(token)) {
          score += token.length > 5 ? 3 : 1;
        }
      });
      if (operationId) {
        const opHints = OPERATION_HINTS.find((item) => item.id === operationId);
        if (opHints?.aliases.some((alias) => haystack.includes(normalizeText(alias)))) {
          score += 6;
        }
      }
      return { chunk, score };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 3);
}

function formatChunkSnippet(chunk) {
  const source = chunk.arquivo || "Documento";
  const position = chunk.posicao !== undefined ? `Trecho ${chunk.posicao}` : "Trecho";
  const content = String(chunk.conteudo || chunk.texto || "").replace(/\s+/g, " ").trim().slice(0, 420);
  return `
    <div class="assistant-source">
      <strong>${escapeHtml(source)}</strong>
      <span>${escapeHtml(position)}</span>
      <p>${escapeHtml(content)}...</p>
    </div>
  `;
}

async function answerAssistantQuestion(question) {
  const normalized = normalizeText(question);
  const detectedOperation = detectOperationId(normalized) || state.activeId || "geral";
  const variantId = detectVariantId(detectedOperation, normalized) || defaultVariantForOperation(detectedOperation) || "";
  const dateText = detectDateInQuestion(question);
  const intent = detectIntent(normalized);
  const payload = await ensurePayload(detectedOperation, variantId || null, false);
  const direct = buildCalculatedAnswer(intent, payload, dateText);
  if (direct) {
    return direct;
  }

  await loadKnowledgeChunks();
  const matches = findRelevantChunks(question, detectedOperation);
  if (matches.length) {
    const intro = `Encontrei trechos da documentacao que podem ajudar sobre <strong>${escapeHtml(payload.operation.full_name || payload.operation.label)}</strong>:`; 
    return `${intro}${matches.map((item) => formatChunkSnippet(item.chunk)).join("")}`;
  }

  return "Nao encontrei uma resposta direta para essa pergunta. Tente citar a operacao e, se quiser valor calculado, informe tambem a data no formato dd/mm/aaaa.";
}

async function handleAssistantSubmit(event) {
  event.preventDefault();
  const question = state.assistant?.input.value.trim();
  if (!question) {
    return;
  }
  addAssistantMessage("user", question);
  state.assistant.input.value = "";
  addAssistantMessage("assistant", "Analisando...");
  const thinkingNode = state.assistant.messages.lastElementChild;
  try {
    const answer = await answerAssistantQuestion(question);
    thinkingNode.remove();
    addAssistantMessage("assistant", answer, true);
  } catch (error) {
    console.error(error);
    thinkingNode.remove();
    addAssistantMessage("assistant", `Nao consegui responder agora. Erro: ${escapeHtml(error.message)}`);
  }
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
    state.assistant = buildAssistant();
    await loadOperations();
    if (state.activeId) {
      await loadOperation(state.activeId);
    }
  } catch (error) {
    console.error(error);
    setStatus("Falha ao carregar dados", "error");
    elements.sourceInfo.innerHTML = `<div><strong>Erro:</strong> ${escapeHtml(error.message)}</div>`;
  }
}

elements.refreshButton.addEventListener("click", async () => {
  if (!state.activeId) {
    return;
  }
  try {
    state.cacheBust = `${Date.now()}`;
    state.payloadCache.clear();
    await loadOperations();
    await loadOperation(state.activeId, true, state.activeVariant || null);
  } catch (error) {
    console.error(error);
    setStatus("Falha ao atualizar dados", "error");
  }
});

bootstrap();
