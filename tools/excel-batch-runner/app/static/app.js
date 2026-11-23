/* All requests below target the local service. Remote execution starts only on #run. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const view = window.BatchView;
  const configKeys = ["url", "app_id", "version_id", "caller", "channel", "concurrency",
    "connect_timeout", "read_timeout", "total_timeout"];
  const state = {upload: null, job: null, preview: null, busy: false, initialized: false,
    offset: 0, total: 0, timer: null, epoch: 0, detail: null, csrf: ""};
  const historyState = {offset: 0, limit: 20, total: 0, epoch: 0, renameId: null};
  const limit = 100;
  const rowQueries = view.createQueryGate();
  const previewGate = view.createPreviewGate();

  function profileStore() { return view.createProfileStore(window.localStorage); }

  function renderProfiles() {
    const saved = profileStore().read();
    $("endpoint-profile").replaceChildren(new Option("新配置 / 当前输入", ""),
      ...saved.items.map(item => new Option(item.name + " · app " + item.app_id +
        " / v" + item.version_id, item.id)));
    $("endpoint-profile").value = saved.selected;
    return saved.items.find(item => item.id === saved.selected);
  }

  function applyProfile(item) {
    for (const key of ["url", "app_id", "version_id"]) $(key).value = item[key];
    $("profile-name").value = item.name;
    $("headers").value = "{}";
  }

  function profileError(error) {
    $("profile-hint").textContent = "配置未保存或无法读取：" + error.message +
      "。可继续手动填写并执行；当前任务不受影响。";
  }

  function saveProfile() {
    try {
      const item = profileStore().save({url: $("url").value, app_id: $("app_id").value,
        version_id: $("version_id").value}, $("profile-name").value);
      renderProfiles();
      $("profile-name").value = item.name;
      $("profile-hint").textContent = "已保存：" + item.name +
        "。同一浏览器、地址和端口下可恢复，不保存请求头。";
    } catch (error) { profileError(error); }
  }

  function notice(message, error = false) {
    $("notice").textContent = message;
    $("notice").classList.toggle("error", error);
    $("notice").hidden = !message;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: {"X-Local-Request": "1", "X-CSRF-Token": state.csrf, ...(options.headers || {})}
    });
    if (response.status === 401) {
      clearTimeout(state.timer);
      window.location.replace("/login");
      throw new Error("登录已过期，请重新登录");
    }
    if (!response.ok) {
      let message = "服务返回错误 " + response.status;
      try { message = (await response.json()).detail || message; } catch (_) {}
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return response;
  }

  async function json(path, body) {
    const options = body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    };
    return (await api(path, options)).json();
  }

  function selectedSheets() {
    return [...$("sheets").querySelectorAll("input:checked")].map(input => input.value);
  }

  function selection() {
    return {upload_id: state.upload?.upload_id, sheets: selectedSheets(),
      start_row: Number($("start_row").value), overwrite: $("overwrite").checked};
  }

  function requestValues() {
    const values = {...selection(), headers: $("headers").value};
    for (const key of configKeys) values[key] = $(key).value;
    return values;
  }

  function setControls() {
    const active = !!state.job && view.isActive(state.job.status);
    const locked = active || state.busy;
    for (const key of [...configKeys, "start_row", "overwrite", "headers", "history",
      "endpoint-profile", "profile-name", "save-profile", "source_path", "load-path", "workbook-file"]) {
      $(key).disabled = locked;
    }
    $("save-profile").disabled = locked || !state.initialized;
    $("endpoint-profile").disabled = locked || !state.initialized;
    $("refresh-history").disabled = locked;
    for (const checkbox of $("sheets").querySelectorAll("input")) checkbox.disabled = locked;
    $("select-all").disabled = locked || !state.upload;
    const ready = !locked && state.initialized && !!state.upload && selectedSheets().length > 0;
    $("preview").disabled = !ready;
    $("run").disabled = !ready;
    $("stop").disabled = !active || state.busy || state.job?.status === "stopping";
    $("export").disabled = !state.job || state.busy;
    $("logs").disabled = !state.job || active || state.busy;
  }

  function sheetCheckboxes(sheets) {
    $("sheets").replaceChildren();
    for (const sheet of sheets) {
      const label = document.createElement("label");
      label.className = "sheet-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = sheet.name;
      checkbox.checked = true;
      checkbox.addEventListener("change", selectionChanged);
      const name = document.createElement("span");
      name.textContent = sheet.name;
      const count = document.createElement("small");
      count.textContent = sheet.questions + " 个问题";
      count.title = "计数基于加载时起始行；实际执行数量以预览为准";
      label.append(checkbox, name, count);
      $("sheets").append(label);
    }
    $("select-all").checked = sheets.length > 0;
    $("select-all").indeterminate = false;
  }

  function selectionChanged() {
    const boxes = [...$("sheets").querySelectorAll("input")];
    const checked = boxes.filter(box => box.checked).length;
    $("select-all").checked = boxes.length > 0 && checked === boxes.length;
    $("select-all").indeterminate = checked > 0 && checked < boxes.length;
    previewGate.invalidate();
    state.preview = null;
    if (view.shouldAutoPreview(state)) runPreview();
    else setControls();
  }

  async function runPreview() {
    if (!state.upload) return;
    const version = previewGate.begin();
    state.busy = true;
    setControls();
    try {
      const selected = selection();
      if (!selected.sheets.length) return;
      const data = await json("/api/preview", selected);
      if (!previewGate.isCurrent(version)) return;
      resetView();
      state.preview = data;
      renderSummary(data);
      renderRows(data.items);
      notice("已预览 " + data.total + " 个问题，可执行 " + (data.counts.pending || 0) + " 个。");
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; setControls(); }
  }

  function resetView() {
    state.epoch += 1;
    clearTimeout(state.timer);
    state.job = null;
    state.detail = null;
    state.offset = 0;
    $("detail").close();
    $("history").value = "";
    $("sheet-filter").replaceChildren(new Option("全部 sheet", ""));
    $("status-filter").value = "";
    $("search").value = "";
    try { sessionStorage.removeItem("batch-job-id"); } catch (_) {}
  }

  function renderSummary(job) {
    const counts = job.counts || {};
    $("job-title").textContent = view.labels[job.status] || "待执行预览";
    $("job-subtitle").textContent = job.error || (job.job_id
      ? (job.title || job.filename) + " · 任务 " + job.job_id.slice(0, 8) +
        (job.status === "stopping" ? " · 等待在途请求完成或超时" : "") +
        (job.source_path ? " · 逐题回写原文件" :
          (job.result_file ? " · 已保存结果副本" : ""))
      : "预览前 100 条问题。配置完成后点击开始执行。");
    $("metric-total").textContent = job.total;
    $("metric-success").textContent = counts.success || 0;
    $("metric-failed").textContent = (counts.failed || 0) + (counts.interrupted || 0);
    $("metric-running").textContent = counts.running || 0;
    $("progress").value = view.progressPercent(job);
    $("progress-text").textContent = job.job_id
      ? "已处理 " + job.finished + " / " + job.total + " · 跳过 " + (counts.skipped || 0) +
        " · 不可执行 " + (counts.invalid || 0) + " · 未执行 " + (counts.cancelled || 0)
      : "可执行 " + (counts.pending || 0) + " · 跳过 " + (counts.skipped || 0) +
        " · 不可执行 " + (counts.invalid || 0);
    $("overflow-text").textContent = job.overflow ? job.overflow + " 条结果超限，请下载完整日志" : "";
    setControls();
  }

  function renderRows(rows) {
    $("rows").replaceChildren();
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "empty";
      td.textContent = "没有符合条件的记录";
      tr.append(td);
      $("rows").append(tr);
    }
    for (const row of rows) {
      const tr = document.createElement("tr");
      const position = document.createElement("td");
      position.className = "location";
      const sheet = document.createElement("strong");
      sheet.textContent = row.sheet;
      position.append(sheet, "第 " + row.row + " 行");
      const question = document.createElement("td");
      question.className = "question";
      question.textContent = row.question || "（无有效问题）";
      const status = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "tag " + row.status;
      badge.textContent = view.labels[row.status] || row.status;
      badge.title = row.error || row.export_warning || "";
      status.append(badge);
      const elapsed = document.createElement("td");
      elapsed.textContent = row.elapsed ? row.elapsed.toFixed(2) + "s" : "—";
      const trace = document.createElement("td");
      if (state.job) {
        const button = document.createElement("button");
        button.className = "trace-btn";
        button.textContent = row.export_warning ? "查看超限结果" :
          (["split", "split_trace"].includes(row.output_format) ? "查看结果" : "查看过程");
        button.addEventListener("click", () => openDetail(row.row_id));
        trace.append(button);
      } else {
        trace.textContent = row.error || "等待执行";
        trace.className = "muted";
      }
      tr.append(position, question, status, elapsed, trace);
      $("rows").append(tr);
    }
    $("row-count").textContent = state.job
      ? (state.total ? (state.offset + 1) + "–" + (state.offset + rows.length) + " / " + state.total : "0") + " 条记录"
      : "预览 " + rows.length + " 条（最多 100 条）";
    $("prev").disabled = !state.job || state.offset === 0;
    $("next").disabled = !state.job || state.offset + limit >= state.total;
  }

  async function loadRows(epoch = state.epoch) {
    if (!state.job) return;
    const jobId = state.job.job_id;
    const offset = state.offset;
    const params = new URLSearchParams({sheet: $("sheet-filter").value,
      status: $("status-filter").value, query: $("search").value, offset, limit});
    return rowQueries.run(() => json("/api/jobs/" + jobId + "/rows?" + params), data => {
      if (epoch !== state.epoch || state.job?.job_id !== jobId) return;
      state.total = data.total;
      if (offset >= data.total && offset > 0) {
        state.offset = Math.max(0, Math.floor((data.total - 1) / limit) * limit);
        return loadRows(epoch);
      }
      state.offset = offset;
      $("sheet-filter").replaceChildren(new Option("全部 sheet", ""),
        ...data.sheets.map(name => new Option(name, name)));
      $("sheet-filter").value = params.get("sheet");
      renderRows(data.items);
    });
  }

  async function updateDetail() {
    if (!state.detail || !state.job || !$("detail").open) return;
    const rowId = state.detail, jobId = state.job.job_id;
    const row = await json("/api/jobs/" + jobId + "/rows/" + rowId);
    if (state.detail !== rowId || state.job?.job_id !== jobId) return;
    $("detail-title").textContent = row.sheet + " · 第 " + row.row + " 行";
    $("detail-question").textContent = row.question;
    $("detail-meta").textContent = (view.labels[row.status] || row.status) +
      " · " + row.event_count + " 个事件 · 会话 " + row.conversation_id +
      (row.export_warning ? " · " + row.export_warning : "");
    const sections = view.detailSections(row);
    if (sections) {
      $("detail-split").hidden = false;
      $("detail-output").hidden = true;
      $("detail-sql").textContent = sections[0].content;
      $("detail-answer").textContent = sections[1].content;
      $("detail-process").textContent = sections[2].content;
      $("detail-traces-block").hidden = sections.length < 4;
      $("detail-traces").textContent = sections[3]?.content || "";
    } else {
      $("detail-split").hidden = true;
      $("detail-output").hidden = false;
      $("detail-output").textContent = row.output || row.error || "等待事件返回…";
    }
  }

  async function openDetail(rowId) {
    state.detail = rowId;
    $("detail-split").hidden = true;
    $("detail-output").hidden = false;
    $("detail-output").textContent = "正在加载…";
    if (!$("detail").open) $("detail").showModal();
    try { await updateDetail(); } catch (error) { notice(error.message, true); }
  }

  async function poll(epoch = state.epoch) {
    if (!state.job || epoch !== state.epoch) return;
    const jobId = state.job.job_id;
    try {
      const job = await json("/api/jobs/" + jobId);
      if (epoch !== state.epoch) return;
      state.job = job;
      renderSummary(job);
      await loadRows(epoch);
      await updateDetail();
      if (!view.isActive(job.status)) {
        await refreshHistory(false);
        return;
      }
    } catch (error) {
      if (epoch !== state.epoch) return;
      notice("读取任务状态失败，将继续尝试刷新：" + error.message, true);
    }
    if (epoch === state.epoch) state.timer = setTimeout(() => poll(epoch), 1500);
  }

  async function showJob(jobId) {
    state.epoch += 1;
    clearTimeout(state.timer);
    state.offset = 0;
    state.detail = null;
    $("detail").close();
    $("sheet-filter").replaceChildren(new Option("全部 sheet", ""));
    $("status-filter").value = "";
    $("search").value = "";
    state.job = {job_id: jobId, status: "running", counts: {}, total: 0, finished: 0};
    setControls();
    try { sessionStorage.setItem("batch-job-id", jobId); } catch (_) {}
    await poll(state.epoch);
  }

  async function refreshHistory(restore = false) {
    const selected = state.job?.job_id || $("history").value;
    const jobs = await json("/api/jobs");
    $("history").replaceChildren(new Option("选择历史任务", ""),
      ...jobs.map(job => new Option((job.title || job.filename) + " · " +
        new Date(job.created_at).toLocaleString() + " · " +
        (view.labels[job.status] || job.status), job.job_id)));
    $("history").value = selected;
    await loadManagedHistory();
    if (restore && jobs.length) {
      let saved;
      try { saved = sessionStorage.getItem("batch-job-id"); } catch (_) {}
      const active = jobs.find(job => view.isActive(job.status));
      const target = active || jobs.find(job => job.job_id === saved);
      if (target) {
        $("history").value = target.job_id;
        await showJob(target.job_id);
      }
    }
  }

  async function download(kind, selectedJobId = null) {
    if (!selectedJobId && !state.job) return;
    state.busy = true;
    setControls();
    try {
      const jobId = selectedJobId || state.job.job_id;
      const response = await api("/api/jobs/" + jobId + "/" + kind);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = (kind === "export" ? "batch-" : kind === "source" ? "source-" : "logs-") + jobId +
        (kind === "logs" ? ".zip" : ".xlsx");
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; setControls(); }
  }

  async function editHistory(jobId, changes) {
    await api("/api/jobs/" + jobId, {method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(changes)});
    if (state.job?.job_id === jobId) Object.assign(state.job, changes);
    await refreshHistory();
    if (state.job) renderSummary(state.job);
  }

  async function loadManagedHistory() {
    const epoch = ++historyState.epoch;
    const params = new URLSearchParams({query: $("history-query").value,
      status: $("history-status").value, archived: $("history-archive").value,
      offset: historyState.offset, limit: historyState.limit});
    const data = await json("/api/history?" + params);
    if (epoch !== historyState.epoch) return;
    if (data.total && historyState.offset >= data.total) {
      historyState.offset = Math.floor((data.total - 1) / historyState.limit) * historyState.limit;
      return loadManagedHistory();
    }
    historyState.total = data.total;
    $("history-total").textContent = "· " + data.total;
    $("history-rows").replaceChildren();
    if (!data.items.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 5; td.className = "empty";
      td.textContent = $("history-query").value || $("history-status").value
        ? "没有符合条件的任务" : $("history-archive").value === "true" ? "暂无归档记录" : "暂无历史任务，上传评测文件开始第一次跑批";
      tr.append(td); $("history-rows").append(tr);
    }
    for (const job of data.items) {
      const tr = document.createElement("tr"), task = document.createElement("td");
      task.className = "history-task";
      const title = document.createElement("strong"), subtitle = document.createElement("small");
      title.textContent = job.title || job.filename;
      subtitle.textContent = job.filename + " · " + job.job_id.slice(0, 8) +
        (job.target?.app_id ? " · App " + job.target.app_id + " / V" + job.target.version_id : "");
      task.append(title, subtitle);
      const date = document.createElement("td"); date.className = "history-date";
      date.textContent = new Date(job.created_at).toLocaleString("zh-CN", {hour12: false});
      const status = document.createElement("td"), tag = document.createElement("span");
      tag.className = "tag " + job.status; tag.textContent = view.labels[job.status] || job.status; status.append(tag);
      const count = document.createElement("td"); count.textContent = (job.counts.success || 0) + " / " + job.total;
      const actions = document.createElement("td"), group = document.createElement("div"); group.className = "history-actions";
      function action(label, handler, disabled = false, className = "") {
        const button = document.createElement("button"); button.type = "button"; button.textContent = label;
        button.disabled = disabled; button.className = className;
        button.addEventListener("click", async () => {
          button.disabled = true;
          try { await handler(); } catch (error) { notice(error.message, true); }
          finally { button.disabled = disabled; }
        });
        group.append(button);
      }
      action("查看", async () => { await showJob(job.job_id); $("job-title").scrollIntoView({behavior: "smooth", block: "center"}); });
      action("Excel ↓", () => download("export", job.job_id), false, "download-action");
      action("日志 ↓", () => download("logs", job.job_id), view.isActive(job.status), "download-action");
      action("原文件 ↓", () => download("source", job.job_id));
      action("重命名", () => {
        historyState.renameId = job.job_id; $("rename-title").value = job.title || job.filename;
        $("rename-error").hidden = true; $("rename-dialog").showModal(); $("rename-title").focus();
      });
      action(job.archived ? "恢复" : "归档", async () => {
        await editHistory(job.job_id, {archived: !job.archived});
        notice(job.archived ? "记录已恢复到最近任务。" : "记录已归档，文件保留，可从「已归档」恢复。");
      }, view.isActive(job.status));
      actions.append(group); tr.append(task, date, status, count, actions); $("history-rows").append(tr);
    }
    $("history-page").textContent = data.total ? (historyState.offset + 1) + "–" +
      (historyState.offset + data.items.length) + " / " + data.total + " 条记录" : "0 条记录";
    $("history-prev").disabled = historyState.offset === 0;
    $("history-next").disabled = historyState.offset + historyState.limit >= data.total;
  }

  let historyTimer;
  function historyChanged() {
    historyState.offset = 0;
    loadManagedHistory().catch(error => notice(error.message, true));
  }
  $("history-query").addEventListener("input", () => { clearTimeout(historyTimer); historyTimer = setTimeout(historyChanged, 250); });
  $("history-status").addEventListener("change", historyChanged);
  $("history-archive").addEventListener("change", historyChanged);
  $("history-refresh").addEventListener("click", () => loadManagedHistory().catch(error => notice(error.message, true)));
  $("history-prev").addEventListener("click", () => { historyState.offset = Math.max(0, historyState.offset - historyState.limit); loadManagedHistory().catch(error => notice(error.message, true)); });
  $("history-next").addEventListener("click", () => { historyState.offset += historyState.limit; loadManagedHistory().catch(error => notice(error.message, true)); });
  $("rename-cancel").addEventListener("click", () => $("rename-dialog").close());
  $("rename-form").addEventListener("submit", async event => {
    event.preventDefault(); $("rename-save").disabled = true;
    try {
      await editHistory(historyState.renameId, {title: $("rename-title").value.trim()});
      $("rename-dialog").close(); notice("任务名称已保存。");
    } catch (error) { $("rename-error").textContent = error.message; $("rename-error").hidden = false; }
    finally { $("rename-save").disabled = false; }
  });
  $("logout").addEventListener("click", async () => {
    try {
      await json("/api/auth/logout", {});
      clearTimeout(state.timer); window.location.replace("/login");
    } catch (error) { notice(error.message, true); }
  });
  $("workbook-file").addEventListener("change", async () => {
    const file = $("workbook-file").files[0];
    if (!file || state.busy) return;
    state.busy = true; setControls(); notice("正在上传并检查工作簿…");
    try {
      if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 20 * 1024 * 1024) throw new Error("请选择 20 MB 以内的 .xlsx 文件");
      const response = await api("/api/uploads?start_row=" + Number($("start_row").value), {
        method: "POST", headers: {"X-Filename": encodeURIComponent(file.name), "Content-Type": "application/octet-stream"}, body: file});
      const opened = await response.json();
      resetView(); state.upload = opened; state.preview = null; sheetCheckboxes(opened.sheets);
      notice("已上传「" + opened.filename + "」，共 " + opened.sheets.length + " 个工作表。");
      await runPreview();
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; $("workbook-file").value = ""; setControls(); }
  });

  $("save-profile").addEventListener("click", saveProfile);
  $("endpoint-profile").addEventListener("change", () => {
    $("headers").value = "{}";
    if (!$("endpoint-profile").value) {
      $("profile-name").value = "";
      return;
    }
    try {
      const id = $("endpoint-profile").value;
      const item = profileStore().read().items.find(profile => profile.id === id);
      if (!item) throw new Error("接口配置不存在");
      applyProfile(item);
      try {
        profileStore().select(id);
        $("profile-hint").textContent = "已切换配置；认证请求头已清空，需要时请重新填写。";
      } catch (error) {
        $("profile-hint").textContent = "当前已切换为 " + item.name +
          "，但无法记住此选择：" + error.message + "。刷新后可能恢复旧配置。";
      }
    } catch (error) {
      $("endpoint-profile").value = "";
      profileError(error);
    }
  });
  for (const key of ["url", "app_id", "version_id"]) {
    $(key).addEventListener("input", () => {
      $("endpoint-profile").value = "";
      $("profile-name").value = "";
    });
  }

  $("select-all").addEventListener("change", () => {
    for (const input of $("sheets").querySelectorAll("input")) input.checked = $("select-all").checked;
    selectionChanged();
  });
  $("start_row").addEventListener("change", selectionChanged);
  $("overwrite").addEventListener("change", selectionChanged);

  $("source_path").addEventListener("keydown", event => {
    if (event.key === "Enter") $("load-path").click();
  });
  $("load-path").addEventListener("click", async () => {
    if (state.busy) return;
    state.busy = true;
    setControls();
    notice("");
    try {
      const request = view.openRequest($("source_path").value, $("start_row").value);
      const opened = await json("/api/workbooks/open", request);
      resetView();
      state.upload = opened;
      state.preview = null;
      sheetCheckboxes(opened.sheets);
      notice("已加载 " + opened.sheets.length + " 个 sheet。");
      await runPreview();
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; setControls(); }
  });

  $("preview").addEventListener("click", () => runPreview());

  $("run").addEventListener("click", async () => {
    state.busy = true;
    setControls();
    try {
      const request = view.buildRequest(requestValues());
      const job = await json("/api/jobs", request);
      saveProfile();
      $("headers").value = "{}";
      notice("任务已启动。每题结果自动保存，原始文件保留备份；关闭页面后服务器会继续执行。");
      state.preview = null;
      await refreshHistory();
      await showJob(job.job_id);
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; setControls(); }
  });

  $("stop").addEventListener("click", async () => {
    if (!state.job) return;
    state.busy = true;
    setControls();
    try {
      state.job = await json("/api/jobs/" + state.job.job_id + "/stop", {});
      renderSummary(state.job);
      notice("已停止派发新请求，正在等待已发出请求完成或超时。");
    } catch (error) { notice(error.message, true); }
    finally { state.busy = false; setControls(); }
  });

  let searchTimer;
  function filterChanged() {
    state.offset = 0;
    if (state.job) loadRows().catch(error => notice(error.message, true));
    else if (state.preview) {
      const query = $("search").value.toLowerCase();
      renderRows(state.preview.items.filter(row =>
        (!$("status-filter").value || row.status === $("status-filter").value) &&
        (!$("sheet-filter").value || row.sheet === $("sheet-filter").value) &&
        (!query || row.question.toLowerCase().includes(query))));
    }
  }
  $("search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(filterChanged, 250);
  });
  $("sheet-filter").addEventListener("change", filterChanged);
  $("status-filter").addEventListener("change", filterChanged);
  $("prev").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - limit);
    loadRows().catch(error => notice(error.message, true));
  });
  $("next").addEventListener("click", () => {
    state.offset += limit;
    loadRows().catch(error => notice(error.message, true));
  });
  $("history").addEventListener("change", () => {
    if ($("history").value) showJob($("history").value).catch(error => notice(error.message, true));
  });
  $("refresh-history").addEventListener("click", () =>
    refreshHistory().catch(error => notice(error.message, true)));
  $("close-detail").addEventListener("click", () => { state.detail = null; $("detail").close(); });
  $("detail").addEventListener("close", () => { state.detail = null; });
  $("detail").addEventListener("click", event => {
    if (view.isDialogBackdrop(event, $("detail"))) $("detail").close();
  });
  $("export").addEventListener("click", () => download("export"));
  $("logs").addEventListener("click", () => download("logs"));

  (async function boot() {
    try {
      const account = await json("/api/auth/me");
      state.csrf = account.csrf;
      $("account-status").textContent = account.username + " · " + (account.database === "postgresql" ? "PostgreSQL 已连接" : "本地数据库");
      $("local-path-section").hidden = !account.allow_local_paths;
      const defaults = await json("/api/defaults");
      for (const key of configKeys) $(key).value = defaults[key];
      try {
        const saved = renderProfiles();
        if (saved) applyProfile(saved);
      } catch (error) { profileError(error); }
      state.initialized = true;
      await refreshHistory(true);
    } catch (error) { notice("无法连接工作台：" + error.message, true); }
    finally { setControls(); }
  })();
})();
