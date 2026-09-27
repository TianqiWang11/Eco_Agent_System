const state = {
  config: {},
  streamUrl: "",
  isSending: false,
  autoConnectAttempts: 0,
  pendingUEActions: [],
  predictionFocusResolved: false,
  predictionReceived: false,
  playerReady: false,
  dataLoaded: false,
  dataPage: 1,
  dataPages: 1,
};

const ALLOWED_UE_ACTIONS = new Set(["highlight", "focus", "focus_prediction", "clear_highlight", "reset_scene", "apply_prediction"]);

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", async () => {
  bindNavigation();
  bindTwinControls();
  bindTwinMessageBridge();
  bindChat();
  bindDataCenter();
  updateClock();
  window.setInterval(updateClock, 1000);
  await loadPlatformConfig();
  await refreshStatus();
  startDataWarmup();
});

function updateClock() {
  const now = new Date();
  const text = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(now);
  $("#system-clock").textContent = text;
}

function bindNavigation() {
  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".nav-item").forEach((item) => item.classList.remove("active"));
      $$(".panel-view").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      $(`#panel-${button.dataset.panel}`).classList.add("active");
      if (button.dataset.panel === "data" && !state.dataLoaded) loadDataCenter();
    });
  });
  $("#refresh-status").addEventListener("click", refreshStatus);
}

async function loadPlatformConfig() {
  try {
    const response = await fetch("/platform/config");
    if (!response.ok) throw new Error("配置读取失败");
    state.config = await response.json();
    $("#platform-title").textContent = state.config.platform_name;

    const port = Number(state.config.pixel_streaming_port || 80);
    const defaultPort = window.location.protocol === "https:" ? 443 : 80;
    const portPart = port === defaultPort ? "" : `:${port}`;
    const fallbackUrl = `${window.location.protocol}//${window.location.hostname}${portPart}`;
    state.streamUrl = state.config.pixel_streaming_url || fallbackUrl;
    $("#stream-url").value = state.streamUrl;

    if (state.config.pixel_streaming_auto_connect !== false) {
      // Loading or reconnecting the portal must not restart the shared UE
      // process. Restarting is reserved for the explicit "reset scene" action.
      window.setTimeout(probeAndConnectTwin, 300);
    }
  } catch (error) {
    console.warn(error);
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/platform/status", { cache: "no-store" });
    if (!response.ok) throw new Error("服务状态读取失败");
    const status = await response.json();

    $("#api-status").textContent = "连接正常";
    $("#ai-status").textContent = "服务就绪";

    const source = status.data_source || {};
    const warmup = status.warmup || {};
    const dataLabel = source.mode === "database"
      ? (source.connected ? "PostgreSQL 已连接" : "PostgreSQL 连接异常")
      : warmup.state === "running"
        ? "表格数据预热中"
        : `表格数据 · ${source.file_count || 0}个文件`;
    $("#data-status").textContent = dataLabel;
    if ($("#database-state")) {
      $("#database-state").textContent = source.connected ? "已连接" : "未连接";
    }
    setDotState("#data-status-dot", source.state === "error" ? "error" : source.state === "warning" ? "standby" : "ready");
  } catch (error) {
    $("#api-status").textContent = "连接异常";
    $("#ai-status").textContent = "等待后端";
    setDotState("#data-status-dot", "error");
  }
}

async function startDataWarmup() {
  try {
    await fetch("/platform/warmup", { method: "POST" });
    let checks = 0;
    const timer = window.setInterval(async () => {
      checks += 1;
      await refreshStatus();
      if (checks >= 30) window.clearInterval(timer);
    }, 3000);
  } catch (error) {
    console.warn("数据预热未启动", error);
  }
}

function setDotState(selector, status) {
  const node = $(selector);
  node.classList.remove("ready", "standby", "error");
  node.classList.add(status);
}

function bindTwinControls() {
  $("#connect-twin").addEventListener("click", connectTwin);
  $("#reload-twin").addEventListener("click", connectTwin);
  $("#reset-twin").addEventListener("click", resetTwinScene);
  $("#open-twin").addEventListener("click", () => {
    const url = buildPlayerUrl($("#stream-url").value || state.streamUrl);
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  });
  $("#twin-frame").addEventListener("load", () => {
    state.playerReady = $("#twin-frame").src !== "about:blank";
    if (!state.playerReady) return;
    $("#twin-status").textContent = "正在等待视频画面";
    setDotState("#twin-status-dot", "standby");
    $("#twin-frame").focus({ preventScroll: true });
    flushPendingUEActions();
  });
}

function bindDataCenter() {
  $("#tree-query-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.dataPage = 1;
    await loadTrees();
  });
  $("#reset-tree-query").addEventListener("click", async () => {
    $("#tree-query-form").reset();
    state.dataPage = 1;
    $("#tree-detail").hidden = true;
    await loadTrees();
  });
  $("#tree-prev-page").addEventListener("click", async () => {
    if (state.dataPage <= 1) return;
    state.dataPage -= 1;
    await loadTrees();
  });
  $("#tree-next-page").addEventListener("click", async () => {
    if (state.dataPage >= state.dataPages) return;
    state.dataPage += 1;
    await loadTrees();
  });
}

async function loadDataCenter() {
  state.dataLoaded = true;
  await Promise.all([loadDataSummary(), loadTrees()]);
}

async function loadDataSummary() {
  try {
    const response = await fetch("/data/summary", { cache: "no-store" });
    if (!response.ok) throw new Error("数据库摘要读取失败");
    const summary = await response.json();
    $("#database-state").textContent = "已连接";
    $("#tree-count").textContent = Number(summary.tree_count).toLocaleString("zh-CN");
    $("#species-count").textContent = Number(summary.species_count).toLocaleString("zh-CN");
    $("#measurement-count").textContent = Number(summary.measurement_count).toLocaleString("zh-CN");
  } catch (error) {
    $("#database-state").textContent = "连接异常";
    showTreeTableMessage(error.message);
  }
}

function treeQueryParameters() {
  const params = new URLSearchParams({ page: String(state.dataPage), page_size: "25" });
  const values = {
    tree_id: $("#tree-id-filter").value.trim(),
    species: $("#species-filter").value.trim(),
    plot_id: $("#plot-filter").value.trim(),
    measurement_year: $("#year-filter").value,
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params;
}

async function loadTrees() {
  showTreeTableMessage("正在查询……");
  try {
    const response = await fetch(`/data/trees?${treeQueryParameters()}`, { cache: "no-store" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "单木数据查询失败");
    }
    const data = await response.json();
    state.dataPage = data.page;
    state.dataPages = data.pages;
    renderTreeRows(data.items);
    $("#tree-result-count").textContent = `共 ${Number(data.total).toLocaleString("zh-CN")} 棵树`;
    $("#tree-page-label").textContent = `第 ${data.page} / ${data.pages} 页`;
    $("#tree-prev-page").disabled = data.page <= 1;
    $("#tree-next-page").disabled = data.page >= data.pages;
  } catch (error) {
    showTreeTableMessage(error.message);
  }
}

function showTreeTableMessage(message) {
  const body = $("#tree-table-body");
  body.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 7;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined) return "--";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function addTableCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value ?? "--";
  row.appendChild(cell);
  return cell;
}

function renderTreeRows(items) {
  if (!items.length) {
    showTreeTableMessage("没有符合条件的树木");
    return;
  }
  const body = $("#tree-table-body");
  body.replaceChildren();
  items.forEach((tree) => {
    const row = document.createElement("tr");
    addTableCell(row, tree.tree_id);
    addTableCell(row, tree.species);
    addTableCell(row, tree.plot_id);
    addTableCell(row, tree.latest_year);
    addTableCell(row, formatNumber(tree.latest_dbh_m));
    addTableCell(row, formatNumber(tree.latest_tree_height_m));
    const actionCell = addTableCell(row, "");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-action";
    button.textContent = "详情";
    button.addEventListener("click", () => loadTreeDetail(tree.tree_id));
    actionCell.appendChild(button);
    body.appendChild(row);
  });
}

async function loadTreeDetail(treeId) {
  const panel = $("#tree-detail");
  panel.hidden = false;
  panel.textContent = "正在读取年度记录……";
  try {
    const response = await fetch(`/data/trees/${encodeURIComponent(treeId)}`, { cache: "no-store" });
    if (!response.ok) throw new Error("单木详情读取失败");
    renderTreeDetail(await response.json());
  } catch (error) {
    panel.textContent = error.message;
  }
}

function renderTreeDetail(data) {
  const panel = $("#tree-detail");
  panel.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = `${data.tree.tree_id} · ${data.tree.species} · ${data.tree.plot_id}`;
  const location = document.createElement("p");
  location.textContent = `坐标 X ${formatNumber(data.tree.tree_position_x_m)}，Y ${formatNumber(data.tree.tree_position_y_m)}，海拔 ${formatNumber(data.tree.elevation_m, 1)} m`;
  const table = document.createElement("table");
  table.className = "data-table detail-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
    ["年份", "胸径（m）", "树高（m）", "冠径（m）", "冠幅面积（m²）"].forEach((label) => addTableCell(headRow, label));
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  data.measurements.forEach((measurement) => {
    const row = document.createElement("tr");
    addTableCell(row, measurement.measurement_year);
    addTableCell(row, formatNumber(measurement.dbh_m));
    addTableCell(row, formatNumber(measurement.tree_height_m));
    addTableCell(row, formatNumber(measurement.crown_diameter_m));
    addTableCell(row, formatNumber(measurement.crown_area_m2));
    body.appendChild(row);
  });
  table.append(head, body);
  panel.append(title, location, table);
}

function validUEAction(action) {
  if (!action || !ALLOWED_UE_ACTIONS.has(action.type)) return false;
  if (["highlight", "focus", "focus_prediction", "apply_prediction"].includes(action.type)) {
    if (typeof action.target_id !== "string"
        || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(action.target_id)) return false;
  }
  if (action.type === "apply_prediction") {
    return Number.isInteger(action.year) && action.year >= 2026 && action.year <= 2100
      && typeof action.species === "string" && action.species.length <= 100
      && ["dbh_m", "tree_height_m", "crown_diameter_ns_m",
          "crown_diameter_ew_m", "crown_volume_m3"].every(
        (key) => Number.isFinite(action[key]) && action[key] > 0,
      );
  }
  return true;
}

function playerOrigin() {
  const source = $("#twin-frame").src;
  if (!source || source === "about:blank") return "";
  try {
    return new URL(source).origin;
  } catch (_) {
    return "";
  }
}

function dispatchUEActions(actions) {
  const safeActions = Array.isArray(actions) ? actions.filter(validUEAction) : [];
  if (!safeActions.length) return;
  if (safeActions.some((action) => action.type === "apply_prediction")) {
    state.predictionFocusResolved = false;
    state.predictionReceived = false;
    window.setTimeout(() => {
      if (!state.predictionReceived) {
        $("#scene-object").textContent = "未收到 UE 建模回执；当前运行的程序包可能尚未包含预测插件";
      }
    }, 20000);
  }
  state.pendingUEActions.push(...safeActions);
  if (!$("#twin-frame").src || $("#twin-frame").src === "about:blank") connectTwin();
  flushPendingUEActions();
}

function flushPendingUEActions() {
  const origin = playerOrigin();
  const frameWindow = $("#twin-frame").contentWindow;
  if (!state.playerReady || !origin || !frameWindow || !state.pendingUEActions.length) return;
  const actions = state.pendingUEActions.splice(0);
  frameWindow.postMessage({
    channel: "chebaling.portal.control",
    version: 1,
    actions,
  }, origin);
  $("#scene-object").textContent = "Agent 控制指令已发送，等待 UE 执行";
}

function bindTwinMessageBridge() {
  window.addEventListener("message", (event) => {
    if (event.source !== $("#twin-frame").contentWindow || event.origin !== playerOrigin()) return;
    const payload = event.data;
    if (payload?.channel === "chebaling.player.stream-status") {
      const labels = { loading: "正在加载场景", playing: "画面已连接", blocked: "点击画面开始播放", disconnected: "连接已断开，请重新连接", stalled: "画面暂时停顿，正在等待", error: "视频加载失败，请重新连接" };
      if (!labels[payload.status]) return;
      $("#twin-status").textContent = labels[payload.status];
      setDotState("#twin-status-dot", payload.status === "playing" ? "ready" : payload.status === "error" ? "error" : "standby");
      return;
    }
    if (!payload || payload.channel !== "chebaling.player.control-status") return;
    if (payload.action === "apply_prediction" && typeof payload.target_id === "string") {
      state.predictionReceived = true;
      $$(".prediction-tree-list-items button").forEach((button) => {
        if (button.dataset.treeId !== payload.target_id) return;
        button.disabled = payload.status !== "executed";
        button.title = payload.status === "executed"
          ? "点击聚焦到预测模型"
          : (payload.message || "UE 尚未完成该树木建模");
        button.classList.toggle("prediction-tree-unavailable", payload.status === "error");
      });
      if (payload.status === "executed" && !state.predictionFocusResolved) {
        state.predictionFocusResolved = true;
        dispatchUEActions([{ type: "focus_prediction", target_id: payload.target_id }]);
      }
    }
    if (payload.status === "queued") {
      $("#scene-object").textContent = "控制指令已排队，等待 UE 数据通道";
    } else if (payload.status === "sent") {
      $("#scene-object").textContent = "Agent 控制指令已送达 UE";
    } else if (payload.status === "executed") {
      $("#scene-object").textContent = payload.message || "UE 已执行 Agent 控制指令";
    } else if (payload.status === "error") {
      $("#scene-object").textContent = payload.message || "UE 控制指令执行失败";
    }
  });
}

async function requestTwinReset() {
  try {
    const response = await fetch("/platform/reset-twin", {
      method: "POST",
      cache: "no-store",
    });
    return response.ok;
  } catch (error) {
    console.warn("UE scene reset failed", error);
    return false;
  }
}

async function resetTwinScene() {
  const frame = $("#twin-frame");
  $("#reset-twin").disabled = true;
  $("#twin-status").textContent = "正在返回初始场景";
  setDotState("#twin-status-dot", "standby");
  frame.src = "about:blank";
  const reset = await requestTwinReset();
  if (reset) {
    connectTwin();
    $("#twin-status").textContent = "正在连接初始场景";
  } else {
    $("#twin-status").textContent = "返回失败，请重试";
    setDotState("#twin-status-dot", "error");
  }
  $("#reset-twin").disabled = false;
}

function normalizeUrl(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `http://${trimmed}`;
}

function buildPlayerUrl(value) {
  const normalized = normalizeUrl(value);
  if (!normalized) return "";

  try {
    const url = new URL(normalized);
    if (!url.pathname || url.pathname === "/") {
      url.pathname = state.config.pixel_streaming_player_path || "/uiless.html";
    }
    // Keep the cursor visible while preserving direct keyboard/mouse input to UE.
    url.searchParams.set("AutoConnect", "true");
    url.searchParams.set("AutoPlayVideo", "true");
    url.searchParams.set("StartVideoMuted", "true");
    url.searchParams.set("KeyboardInput", "true");
    url.searchParams.set("MouseInput", "true");
    url.searchParams.set("HoveringMouse", "true");
    url.searchParams.set("TimeoutIfIdle", "false");
    url.searchParams.set("WebRTCMinBitrate", "1500");
    url.searchParams.set("WebRTCMaxBitrate", "12000");
    return url.toString();
  } catch (error) {
    console.warn("Pixel Streaming 地址无效", error);
    return "";
  }
}

function connectTwin() {
  const url = buildPlayerUrl($("#stream-url").value || state.streamUrl);
  if (!url) return;
  const frame = $("#twin-frame");
  state.playerReady = false;
  $("#twin-placeholder").style.display = "none";
  $("#twin-stage").classList.add("connected");
  frame.style.display = "block";
  const playerUrl = new URL(url);
  playerUrl.searchParams.set("t", Date.now());
  frame.src = playerUrl.toString();
  $("#twin-status").textContent = "正在连接";
  setDotState("#twin-status-dot", "standby");
}

async function probeAndConnectTwin() {
  const url = buildPlayerUrl($("#stream-url").value || state.streamUrl);
  if (!url || $("#twin-frame").src) return;

  state.autoConnectAttempts += 1;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 2500);

  try {
    await fetch(url, {
      mode: "no-cors",
      cache: "no-store",
      signal: controller.signal,
    });
    connectTwin();
  } catch (error) {
    $("#twin-status").textContent = "等待UE场景";
    setDotState("#twin-status-dot", "standby");
    if (state.autoConnectAttempts < 24) {
      window.setTimeout(probeAndConnectTwin, 5000);
    }
  } finally {
    window.clearTimeout(timeout);
  }
}

function bindChat() {
  const form = $("#chat-form");
  const input = $("#chat-input");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendMessage(input.value);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  $$("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.prompt));
  });

  $("#clear-chat").addEventListener("click", () => {
    if (state.isSending || window.Agent.busy) return;
    window.Agent.newTask();
    $("#chat-messages").innerHTML = "";
    appendAssistantMessage("对话已清空。您可以继续查询生态数据或咨询样地信息。");
  });
}

async function sendMessage(message) {
  const text = String(message || "").trim();
  if (!text || state.isSending || window.Agent.busy) return;

  state.isSending = true;
  $("#send-button").disabled = true;
  $("#chat-input").value = "";
  appendUserMessage(text);
  const typingNode = appendTyping();

  try {
    const data = await window.Agent.send(text, (message) => updateTyping(typingNode, message));
    typingNode.remove();

    appendAssistantMessage(data.answer || "本次任务没有返回文字结果。", data);
    dispatchUEActions(data.ue_actions);
  } catch (error) {
    typingNode.remove();
    appendAssistantMessage(error.message || "任务连接中断，后台任务不会因此取消。可选择该任务重新查看。");
  } finally {
    state.isSending = false;
    $("#send-button").disabled = false;
    $("#chat-input").focus();
  }
}

function appendUserMessage(text) {
  const article = document.createElement("article");
  article.className = "message user-message";
  const body = document.createElement("div");
  body.className = "message-body";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  body.appendChild(paragraph);
  article.appendChild(body);
  appendChatNode(article);
}

function appendAssistantMessage(text, payload = {}) {
  const article = document.createElement("article");
  article.className = "message assistant-message";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "AI";

  const body = document.createElement("div");
  body.className = "message-body";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  body.appendChild(paragraph);

  renderArtifacts(body, payload.artifacts);
  renderPredictionTreeList(body, payload.ue_actions);
  renderInlineApproval(body, payload.approval);

  article.append(avatar, body);
  appendChatNode(article);
}

function appendTyping() {
  const article = document.createElement("article");
  article.className = "message assistant-message";
  article.innerHTML = '<div class="avatar">AI</div><div class="message-body"><span class="agent-progress">正在理解你的问题…</span></div>';
  appendChatNode(article);
  return article;
}

function updateTyping(article, message) {
  const progress = article?.querySelector(".agent-progress");
  if (progress && message) progress.textContent = message;
}

function renderInlineApproval(container, approval) {
  if (!approval?.digest) return;
  const controls = document.createElement("div");
  controls.className = "inline-approval";
  [[true, "确认继续"], [false, "拒绝"]].forEach(([allow, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = label;
    button.addEventListener("click", async () => {
      if (state.isSending || window.Agent.busy) return;
      state.isSending = true;
      controls.querySelectorAll("button").forEach((item) => { item.disabled = true; });
      const progress = document.createElement("span");
      progress.className = "agent-progress";
      progress.textContent = allow ? "正在继续处理…" : "正在取消操作…";
      container.appendChild(progress);
      try {
        const data = await window.Agent.approve(
          approval.digest,
          allow,
          (message) => { progress.textContent = message; },
        );
        progress.remove();
        controls.remove();
        appendAssistantMessage(data.answer, data);
        dispatchUEActions(data.ue_actions);
      } catch (error) {
        progress.textContent = error.message || "操作确认失败，请重试。";
        controls.querySelectorAll("button").forEach((item) => { item.disabled = false; });
      } finally {
        state.isSending = false;
      }
    });
    controls.appendChild(button);
  });
  container.appendChild(controls);
}

function renderArtifacts(container, artifacts) {
  if (!Array.isArray(artifacts)) return;
  artifacts.forEach((artifact) => {
    if (!artifact?.content_base64 || !artifact?.mime) return;
    const card = document.createElement("div");
    card.className = "artifact-card";
    const blobUrl = base64ToBlobUrl(artifact.content_base64, artifact.mime);
    const link = document.createElement("a");
    link.href = blobUrl;
    const isImage = artifact.mime.startsWith("image/");
    if (isImage) {
      const image = document.createElement("img");
      image.src = blobUrl;
      image.alt = artifact.title || artifact.filename || "分析图表";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = artifact.title || "打开分析图表";
      card.append(image);
    } else {
      link.download = artifact.filename || "agent-output";
      link.textContent = artifact.title || artifact.filename || "下载结果文件";
    }
    card.append(link);
    container.appendChild(card);
  });
}

function base64ToBlobUrl(base64, mime) {
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: mime }));
}

function renderPredictionTreeList(container, actions) {
  const trees = Array.isArray(actions)
    ? actions.filter((action) => action?.type === "apply_prediction" && validUEAction(action))
    : [];
  if (!trees.length) return;
  const panel = document.createElement("div");
  panel.className = "prediction-tree-list";
  const heading = document.createElement("p");
  heading.textContent = "预测树木 · 点击编号查看变化后的模型";
  panel.appendChild(heading);
  const list = document.createElement("div");
  list.className = "prediction-tree-list-items";
  trees.forEach((tree) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = `${tree.target_id} · ${tree.species} · ${tree.year}`;
    button.dataset.treeId = tree.target_id;
    button.disabled = true;
    button.title = "等待 UE 建模回执";
    button.addEventListener("click", () => {
      dispatchUEActions([{ type: "focus_prediction", target_id: tree.target_id }]);
    });
    list.appendChild(button);
  });
  panel.appendChild(list);
  container.appendChild(panel);
}

function appendChatNode(node) {
  const container = $("#chat-messages");
  container.appendChild(node);
  container.scrollTop = container.scrollHeight;
}
