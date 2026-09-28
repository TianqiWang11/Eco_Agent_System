/* Session capabilities stay in request headers and are never placed in URLs. */
window.Agent = (() => {
  const storageKey = "agent.current-task.v4";
  let current = null;
  let busy = false;

  function save() {
    try {
      if (current) sessionStorage.setItem(storageKey, JSON.stringify(current));
      else sessionStorage.removeItem(storageKey);
    } catch (_) {
      // The agent remains usable when browser storage is unavailable.
    }
  }

  async function request(path, method = "GET", body, task = current) {
    const response = await fetch(path, {
      method,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(task ? { Authorization: `Bearer ${task.token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      let message = "Agent 请求失败，请稍后重试。";
      try {
        const data = await response.json();
        if (typeof data.detail === "string") message = data.detail;
      } catch (_) {
        // Keep the safe generic message for a non-JSON response.
      }
      throw new Error(message);
    }
    return response;
  }

  function publishProgress(event, task, onProgress) {
    task.cursor = event.id;
    save();
    if (typeof event.message === "string" && event.message !== task.lastProgress && typeof onProgress === "function") {
      task.lastProgress = event.message;
      onProgress(event.message);
    }
  }

  async function watch(task, onProgress) {
    const response = await request(
      `/agent/sessions/${task.id}/events?after=${task.cursor || 0}`,
      "GET",
      null,
      task,
    );
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const data = block.split("\n").find((line) => line.startsWith("data: "));
          if (data) publishProgress(JSON.parse(data.slice(6)), task, onProgress);
        }
        if (done) break;
      }
    } finally {
      reader.releaseLock();
    }
    const status = await (await request(`/agent/sessions/${task.id}`, "GET", null, task)).json();
    task.phase = status.phase;
    task.approval = status.approval || null;
    save();
    return status;
  }

  function publicResult(task) {
    if (task.final) return task.final;
    if (task.phase === "needs_approval" && task.approval) {
      return {
        answer: task.approval.summary || "继续执行这一步需要你的确认。",
        artifacts: [],
        approval: { digest: task.approval.digest },
      };
    }
    return {
      answer: task.phase === "error" ? "任务未能完成，请重试。" : "任务暂时中断，请重新发送请求。",
      artifacts: [],
    };
  }

  async function send(message, onProgress) {
    if (busy) throw new Error("当前请求仍在处理中。");
    busy = true;
    try {
      if (!current || ["error"].includes(current.phase)) {
        const data = await (await request("/agent/sessions", "POST", { message }, null)).json();
        current = { ...data, cursor: 0, phase: "working", approval: null };
      } else if (current.phase === "needs_approval") {
        throw new Error("请先确认或拒绝当前操作。");
      } else {
        await request(`/agent/sessions/${current.id}/turns`, "POST", { message });
        current.phase = "working";
      }
      save();
      return publicResult(await watch(current, onProgress));
    } finally {
      busy = false;
    }
  }

  async function approve(digest, allow, onProgress) {
    if (busy || !current) throw new Error("当前没有可确认的操作。");
    busy = true;
    try {
      await request(`/agent/sessions/${current.id}/approval`, "POST", { digest, allow });
      current.phase = "working";
      current.approval = null;
      save();
      return publicResult(await watch(current, onProgress));
    } finally {
      busy = false;
    }
  }

  function newTask() {
    if (busy) return;
    current = null;
    save();
  }

  document.addEventListener("DOMContentLoaded", () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (saved?.id && saved?.token) current = saved;
    } catch (_) {
      current = null;
    }
  });

  return { send, approve, newTask, get busy() { return busy; } };
})();
