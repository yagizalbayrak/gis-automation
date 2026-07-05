/* Autonomous GIS Workbench - operational panel.
 *
 * Thin client over the task API: submit text, stream trace events (SSE),
 * render output layers on a MapLibre map. No state lives here that the
 * server does not also know - the UI is a viewer, not an executor.
 */
"use strict";

const LAYER_COLORS = {
  all_roads: "#8b99ab",
  selected_roads: "#4da3ff",
  buffered: "#ff8c1a",
};
const FALLBACK_COLORS = ["#3ecf8e", "#c792ea", "#ffcc4d", "#ff5d5d"];

const el = (id) => document.getElementById(id);

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  },
  center: [29.98, 39.42], // Kutahya
  zoom: 11,
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

const state = {
  taskId: null,
  eventSource: null,
  mapLayerIds: [],
  catalog: null,
  reportLang: "en",
};

for (const button of document.querySelectorAll(".lang-btn")) {
  button.addEventListener("click", () => {
    state.reportLang = button.dataset.lang;
    for (const other of document.querySelectorAll(".lang-btn")) {
      other.classList.toggle("active", other === button);
    }
    if (state.taskId) loadReport(state.taskId, state.reportLang);
  });
}

async function loadReport(taskId, lang) {
  const response = await fetch(`/tasks/${taskId}/report?lang=${lang}`);
  if (!response.ok) return;
  const payload = await response.json();
  el("report-body").textContent = payload.report;
  el("report-card").classList.remove("hidden");
}

el("run-btn").addEventListener("click", () => submitTask({}));
el("task-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitTask({});
});
for (const chip of document.querySelectorAll(".example-chip")) {
  chip.addEventListener("click", () => {
    el("task-input").value = chip.dataset.text;
    el("task-input").focus();
  });
}

/* ---------------- LLM settings panel ---------------- */

const settingsState = { providers: {}, keySaved: false };

el("settings-toggle").addEventListener("click", () => {
  el("settings-card").classList.toggle("hidden");
});
el("llm-provider").addEventListener("change", () => renderModelOptions(null));
el("llm-model").addEventListener("change", () => {
  const custom = el("llm-model").value === "__custom__";
  el("llm-model-custom").classList.toggle("hidden", !custom);
  el("llm-model-custom-label").classList.toggle("hidden", !custom);
});
el("llm-save").addEventListener("click", saveLlmSettings);
el("llm-test").addEventListener("click", testLlmSettings);

async function loadLlmSettings() {
  const settings = await (await fetch("/settings/llm")).json();
  settingsState.providers = settings.providers;
  settingsState.keySaved = Boolean(settings.api_key_masked);

  const providerSelect = el("llm-provider");
  providerSelect.innerHTML = "";
  for (const [id, meta] of Object.entries(settings.providers)) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = meta.label;
    providerSelect.appendChild(option);
  }
  providerSelect.value = settings.provider || "gemini";
  renderModelOptions(settings.model);

  if (settings.api_key_masked) {
    el("llm-key").placeholder = `saved ${settings.api_key_masked} - paste to replace`;
  }
  if (settings.api_base) el("llm-base").value = settings.api_base;
  renderAiStatus(settings);
}

function renderModelOptions(selectedModel) {
  const provider = el("llm-provider").value;
  const models = (settingsState.providers[provider] || {}).models || [];
  const modelSelect = el("llm-model");
  modelSelect.innerHTML = "";
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    modelSelect.appendChild(option);
  }
  const custom = document.createElement("option");
  custom.value = "__custom__";
  custom.textContent = "custom model id...";
  modelSelect.appendChild(custom);

  let selected;
  if (selectedModel && models.includes(selectedModel)) selected = selectedModel;
  else if (selectedModel) selected = "__custom__";
  else selected = models[0] || "__custom__";
  modelSelect.value = selected;
  const customActive = modelSelect.value === "__custom__";
  el("llm-model-custom").classList.toggle("hidden", !customActive);
  el("llm-model-custom-label").classList.toggle("hidden", !customActive);
  if (customActive && selectedModel) el("llm-model-custom").value = selectedModel;

  const showBase = provider === "custom";
  el("llm-base").classList.toggle("hidden", !showBase);
  el("llm-base-label").classList.toggle("hidden", !showBase);
  const hint = (settingsState.providers[provider] || {}).key_hint;
  if (hint) el("llm-key").placeholder = settingsState.keySaved
    ? el("llm-key").placeholder : hint;
}

function selectedModelId() {
  const value = el("llm-model").value;
  return value === "__custom__" ? el("llm-model-custom").value.trim() : value;
}

async function saveLlmSettings({ silent = false } = {}) {
  const model = selectedModelId();
  if (!model) {
    showLlmFeedback(false, "Choose or enter a model id first.");
    return false;
  }
  const body = {
    provider: el("llm-provider").value,
    model,
    api_base: el("llm-base").value.trim() || null,
  };
  const key = el("llm-key").value.trim();
  if (key) body.api_key = key;  // omit -> keep previously saved key

  const response = await fetch("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    showLlmFeedback(false, "Save failed.");
    return false;
  }
  const settings = await response.json();
  settingsState.keySaved = Boolean(settings.api_key_masked);
  el("llm-key").value = "";
  if (settings.api_key_masked) {
    el("llm-key").placeholder = `saved ${settings.api_key_masked} - paste to replace`;
  }
  renderAiStatus(settings);
  if (!silent) {
    showLlmFeedback(true, `Saved: ${settings.model}${settings.api_key_masked ? " with API key" : " (no key yet)"}.`);
  }
  return true;
}

async function testLlmSettings() {
  el("llm-test").disabled = true;
  try {
    // Whatever is currently in the form is what the user means to test:
    // save it first so Test never silently runs against stale settings.
    showLlmFeedback(true, "Saving settings...");
    const saved = await saveLlmSettings({ silent: true });
    if (!saved) return;

    showLlmFeedback(true, "Testing connection...");
    const result = await (await fetch("/settings/llm/test", { method: "POST" })).json();
    showLlmFeedback(
      result.ok,
      result.ok
        ? `${result.model} answered in ${result.latency_ms} ms. ${result.message}`
        : result.message
    );
  } finally {
    el("llm-test").disabled = false;
  }
}

function showLlmFeedback(ok, message) {
  const feedback = el("llm-feedback");
  feedback.textContent = message;
  feedback.className = `llm-feedback ${ok ? "ok" : "err"}`;
}

function renderAiStatus(settings) {
  const status = el("ai-status");
  if (settings.configured && settings.model) {
    status.textContent = `AI: ${settings.model}`;
    status.className = "ai-status ok";
  } else {
    status.textContent = "AI: not configured - open settings to enable composed plans";
    status.className = "ai-status off";
  }
}

loadLlmSettings();

async function submitTask(params) {
  const text = el("task-input").value.trim();
  if (!text) return;
  resetUi();
  el("run-btn").disabled = true;

  const response = await fetch("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, params }),
  });
  const task = await response.json();
  state.taskId = task.task_id;
  renderTask(task);

  if (task.status === "running") {
    streamTrace(task.task_id);
  } else {
    el("run-btn").disabled = false;
  }
}

function streamTrace(taskId) {
  el("trace-card").classList.remove("hidden");
  const source = new EventSource(`/tasks/${taskId}/events`);
  state.eventSource = source;

  source.onmessage = (event) => appendTraceItem(JSON.parse(event.data));
  source.addEventListener("done", async () => {
    source.close();
    state.eventSource = null;
    const task = await (await fetch(`/tasks/${taskId}`)).json();
    renderTask(task);
    if (task.status === "succeeded") await loadOutputs(task);
    await loadReport(taskId, state.reportLang);
    el("run-btn").disabled = false;
  });
  source.onerror = () => {
    source.close();
    el("run-btn").disabled = false;
  };
}

function appendTraceItem(event) {
  const item = document.createElement("li");
  item.className = event.phase;
  const detail = summarizeDetail(event.detail);
  item.innerHTML =
    `<strong>${event.phase}</strong> &middot; ${event.subject}` +
    (detail ? `<span class="detail">${detail}</span>` : "");
  el("trace-list").appendChild(item);
  item.scrollIntoView({ block: "nearest" });
}

function summarizeDetail(detail) {
  if (!detail) return "";
  if (detail.message) return escapeHtml(detail.message);
  if (detail.error) return escapeHtml(detail.error);
  if (detail.crs) return `input=${detail.input} crs=${escapeHtml(detail.crs)}`;
  const compact = JSON.stringify(detail);
  return escapeHtml(compact.length > 160 ? compact.slice(0, 157) + "..." : compact);
}

function renderTask(task) {
  el("status-row").classList.remove("hidden");
  const chip = el("status-chip");
  chip.textContent = task.status.replace("_", " ");
  chip.className = `chip ${task.status}`;
  el("workflow-name").textContent =
    (task.workflow || "") + (task.mode === "composed" ? "  [composed]" : "");
  renderPlan(task);

  const understood = el("understood");
  const body = el("understood-body");
  body.innerHTML = "";
  addKv(body, "request", task.text);
  if (task.workflow) addKv(body, "workflow", task.workflow);
  if (Object.keys(task.params).length) {
    addKv(body, "parameters", JSON.stringify(task.params));
  }
  if (task.explanation) addKv(body, "planner", task.explanation);
  understood.classList.remove("hidden");

  renderAssumptions(task);
  if (task.status === "needs_input") renderQuestions(task);
  if (task.status === "failed" && task.error) {
    el("error-body").textContent = task.error;
    el("error-box").classList.remove("hidden");
  }
  if (task.status === "unmatched") {
    el("error-body").textContent =
      "No registered workflow matches this request yet. Try a road fetch/buffer, " +
      "a quality check on a file, or a CRS conversion.";
    el("error-box").classList.remove("hidden");
  }
}

function renderPlan(task) {
  if (!task.plan || !task.plan.length) return;
  const list = el("plan-list");
  list.innerHTML = "";
  for (const step of task.plan) {
    const item = document.createElement("li");
    const params = JSON.stringify(step.params);
    item.innerHTML =
      `<strong>${escapeHtml(step.id)}</strong> &middot; ${escapeHtml(step.tool)}` +
      `<span class="plan-params">${escapeHtml(params.length > 140 ? params.slice(0, 137) + "..." : params)}</span>`;
    list.appendChild(item);
  }
  el("plan-card").classList.remove("hidden");
}

function addKv(parent, key, value) {
  const row = document.createElement("div");
  row.className = "kv";
  row.innerHTML = `<span class="k">${key}</span><code>${escapeHtml(String(value))}</code>`;
  parent.appendChild(row);
}

async function renderQuestions(task) {
  const form = el("questions-form");
  form.innerHTML = "";
  if (task.questions && task.questions.length) {
    renderStructuredQuestions(task.questions, form);
  } else {
    await renderCatalogQuestions(task, form);
  }
  el("questions").classList.remove("hidden");
  el("answer-btn").onclick = () => {
    const params = {};
    for (const input of form.querySelectorAll("input")) {
      if (!input.value.trim()) continue;
      params[input.name] =
        input.dataset.kind === "float" || input.dataset.kind === "int"
          ? Number(input.value)
          : input.value.trim();
    }
    el("questions").classList.add("hidden");
    submitTask(params);
  };
}

function renderStructuredQuestions(questions, form) {
  for (const q of questions) {
    const label = document.createElement("label");
    label.textContent = q.text[state.reportLang] || q.text.en;
    const recommended = (q.options || []).find((o) => o.recommended);
    if (recommended) {
      const hint = document.createElement("span");
      hint.className = "q-hint";
      hint.textContent = ` (recommended: ${recommended.value})`;
      label.appendChild(hint);
    }
    const input = document.createElement("input");
    input.name = q.param;
    input.dataset.kind = q.kind || "string";
    input.placeholder = q.kind === "float" ? "e.g. 25" : "";
    // Prefill the default so answering a strict_confirm question carries
    // the value explicitly - an empty resubmit would loop back here.
    if (q.default_if_skipped !== null && q.default_if_skipped !== undefined) {
      input.value = String(q.default_if_skipped);
    }
    form.appendChild(label);
    form.appendChild(input);
  }
}

async function renderCatalogQuestions(task, form) {
  if (!state.catalog) {
    state.catalog = await (await fetch("/catalog")).json();
  }
  const workflow = state.catalog.workflows.find((w) => w.name === task.workflow);
  for (const name of task.missing_params) {
    const meta = workflow?.params.find((p) => p.name === name);
    const label = document.createElement("label");
    label.textContent = `${name} - ${meta?.description || meta?.kind || ""}`;
    const input = document.createElement("input");
    input.name = name;
    input.dataset.kind = meta?.kind || "string";
    input.placeholder = meta?.kind === "float" ? "e.g. 25" : "";
    form.appendChild(label);
    form.appendChild(input);
  }
}

function renderAssumptions(task) {
  const list = el("assumptions-list");
  list.innerHTML = "";
  if (!task.assumptions || !task.assumptions.length) {
    el("assumptions-box").classList.add("hidden");
    return;
  }
  for (const assumption of task.assumptions) {
    const item = document.createElement("li");
    item.textContent =
      (assumption.text && (assumption.text[state.reportLang] || assumption.text.en)) ||
      `Assumed: ${assumption.param} = ${assumption.value}`;
    list.appendChild(item);
  }
  el("assumptions-box").classList.remove("hidden");
}

async function loadOutputs(task) {
  const list = el("outputs-list");
  list.innerHTML = "";
  const bounds = new maplibregl.LngLatBounds();
  let colorIndex = 0;

  for (const name of Object.keys(task.outputs)) {
    const response = await fetch(`/tasks/${task.task_id}/layers/${name}`);
    if (!response.ok) continue;
    const layer = await response.json();
    const color =
      LAYER_COLORS[name] || FALLBACK_COLORS[colorIndex++ % FALLBACK_COLORS.length];
    addGeoJsonLayer(name, layer.feature_collection, color);
    extendBounds(bounds, layer.feature_collection);

    const item = document.createElement("li");
    item.innerHTML =
      `<span class="swatch" style="background:${color}"></span>` +
      `<span>${name}</span>` +
      `<span class="output-meta">${layer.feature_count} features &middot; ` +
      `source ${layer.source_srid || "?"}</span>`;
    list.appendChild(item);
  }

  el("outputs-card").classList.remove("hidden");
  if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
}

function addGeoJsonLayer(name, featureCollection, color) {
  const sourceId = `out-${name}`;
  map.addSource(sourceId, { type: "geojson", data: featureCollection });

  const geometryTypes = new Set(
    featureCollection.features.map((f) => f.geometry && f.geometry.type)
  );
  if (has(geometryTypes, "Polygon")) {
    addMapLayer(`${sourceId}-fill`, {
      type: "fill", source: sourceId,
      paint: { "fill-color": color, "fill-opacity": 0.35 },
      filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
    });
    addMapLayer(`${sourceId}-outline`, {
      type: "line", source: sourceId,
      paint: { "line-color": color, "line-width": 1.5 },
      filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
    });
  }
  if (has(geometryTypes, "LineString")) {
    addMapLayer(`${sourceId}-line`, {
      type: "line", source: sourceId,
      paint: { "line-color": color, "line-width": 2.5 },
      filter: ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false],
    });
  }
  if (has(geometryTypes, "Point")) {
    addMapLayer(`${sourceId}-circle`, {
      type: "circle", source: sourceId,
      paint: { "circle-color": color, "circle-radius": 5 },
      filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
    });
  }
}

function addMapLayer(id, definition) {
  map.addLayer({ id, ...definition });
  state.mapLayerIds.push(id);
}

function has(types, base) {
  return types.has(base) || types.has(`Multi${base}`);
}

function extendBounds(bounds, featureCollection) {
  for (const feature of featureCollection.features) {
    walkCoordinates(feature.geometry?.coordinates, (lon, lat) =>
      bounds.extend([lon, lat])
    );
  }
}

function walkCoordinates(node, visit) {
  if (!Array.isArray(node)) return;
  if (typeof node[0] === "number") {
    visit(node[0], node[1]);
    return;
  }
  for (const child of node) walkCoordinates(child, visit);
}

function resetUi() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = null;
  el("trace-list").innerHTML = "";
  el("outputs-list").innerHTML = "";
  el("questions").classList.add("hidden");
  el("assumptions-box").classList.add("hidden");
  el("assumptions-list").innerHTML = "";
  el("error-box").classList.add("hidden");
  el("outputs-card").classList.add("hidden");
  el("trace-card").classList.add("hidden");
  el("report-card").classList.add("hidden");
  el("plan-card").classList.add("hidden");
  el("plan-list").innerHTML = "";

  for (const layerId of state.mapLayerIds) {
    if (map.getLayer(layerId)) map.removeLayer(layerId);
  }
  state.mapLayerIds = [];
  for (const name of Object.keys(LAYER_COLORS)) {
    const sourceId = `out-${name}`;
    if (map.getSource(sourceId)) map.removeSource(sourceId);
  }
  // remove any fallback-named sources left behind
  for (const sourceId of Object.keys(map.getStyle().sources)) {
    if (sourceId.startsWith("out-") && map.getSource(sourceId)) {
      map.removeSource(sourceId);
    }
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
