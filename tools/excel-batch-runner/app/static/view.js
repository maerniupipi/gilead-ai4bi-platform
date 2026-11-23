(function (root) {
  "use strict";
  const labels = {
    pending: "待执行", running: "执行中", stopping: "正在停止", success: "成功",
    failed: "失败", skipped: "已跳过", invalid: "不可执行", cancelled: "未执行",
    interrupted: "已中断", completed: "批次完成", stopped: "已停止"
  };
  function positiveNumber(value, name, integer = false, max = Infinity) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0 || number > max ||
        (integer && !Number.isInteger(number))) throw new Error(name + "无效");
    return number;
  }
  function buildRequest(values) {
    if (!values.upload_id || !values.sheets.length) throw new Error("请先加载工作簿并选择 sheet");
    let headers;
    try { headers = JSON.parse(values.headers || "{}"); }
    catch (_) { throw new Error("自定义请求头必须是有效 JSON 对象"); }
    if (!headers || Array.isArray(headers) || typeof headers !== "object" ||
        Object.values(headers).some(value => typeof value !== "string")) {
      throw new Error("请求头必须是名称和值均为字符串的 JSON 对象");
    }
    const url = new URL(values.url);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("接口地址必须为无内嵌认证的 HTTP/HTTPS URL");
    }
    if (!String(values.caller).trim()) throw new Error("caller 不能为空");
    return {
      upload_id: values.upload_id, sheets: values.sheets,
      start_row: positiveNumber(values.start_row, "起始行", true, 1048576),
      overwrite: Boolean(values.overwrite),
      config: {
        url: values.url.trim(),
        app_id: positiveNumber(values.app_id, "app_id", true),
        version_id: positiveNumber(values.version_id, "version_id", true),
        caller: values.caller.trim(), channel: values.channel,
        concurrency: positiveNumber(values.concurrency, "并发数", true, 32),
        connect_timeout: positiveNumber(values.connect_timeout, "连接超时", false, 3600),
        read_timeout: positiveNumber(values.read_timeout, "读取超时", false, 86400),
        total_timeout: positiveNumber(values.total_timeout, "总时限", false, 86400),
        headers
      }
    };
  }
  function openRequest(path, startRow) {
    const trimmed = String(path ?? "").trim();
    if (!trimmed) throw new Error("请输入原始 .xlsx 的本地绝对路径");
    return {path: trimmed, start_row: positiveNumber(startRow, "起始行", true, 1048576)};
  }
  function detailSections(row) {
    if (!row || !["split", "split_trace"].includes(row.output_format)) return null;
    let answer = row.answer || "未返回回答";
    if (row.status === "failed" || row.status === "interrupted") {
      answer = "未完成：" + (row.error || row.status) +
        (row.answer ? "\n" + row.answer : "");
    }
    const sections = [
      {title: "SQL", content: row.sql || "未返回 SQL"},
      {title: "最终回答", content: answer},
      {title: "完整过程", content: row.output || "未返回完整过程"}
    ];
    if (row.output_format === "split_trace") sections.push({
      title: "实验室 TraceID / J", content: (row.lab_trace_ids || []).join("\n") || "未返回实验室 TraceID"
    });
    return sections;
  }
  function createPreviewGate() {
    let latest = 0;
    return {
      begin() { return ++latest; },
      isCurrent(version) { return version === latest; },
      invalidate() { latest += 1; }
    };
  }
  function shouldAutoPreview(state) {
    return Boolean(state && state.upload && !state.job);
  }
  function isDialogBackdrop(event, dialog) {
    return Boolean(event && dialog && event.target === dialog);
  }
  function progressPercent(job) {
    const total = Number(job?.total);
    const finished = Number(job?.finished ?? 0);
    if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(finished)) return 0;
    return Math.max(0, Math.min(100, Math.round(finished / total * 100)));
  }
  function isActive(status) { return status === "running" || status === "stopping"; }
  function createQueryGate() {
    let latest = 0;
    return {
      async run(read, apply) {
        const version = ++latest;
        try {
          const data = await read();
          if (version !== latest) return false;
          await apply(data);
          return true;
        } catch (error) {
          if (version !== latest) return false;
          throw error;
        }
      }
    };
  }
  function createProfileStore(storage) {
    const key = "batch-endpoint-profiles-v1";
    function profile(values, name) {
      const url = new URL(String(values.url).trim());
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.hash) {
        throw new Error("接口配置需要无内嵌认证和片段的 HTTP/HTTPS URL");
      }
      const app_id = positiveNumber(values.app_id, "app_id", true, Number.MAX_SAFE_INTEGER);
      const version_id = positiveNumber(values.version_id, "version_id", true, Number.MAX_SAFE_INTEGER);
      const endpoint = {url: String(values.url).trim(), app_id, version_id};
      return {id: JSON.stringify([endpoint.url, app_id, version_id]),
        name: String(name || "").trim() || url.host + " · app " + app_id + " / v" + version_id,
        ...endpoint};
    }
    function read() {
      const raw = storage.getItem(key);
      if (raw === null) return {items: [], selected: ""};
      const saved = JSON.parse(raw);
      if (saved.version !== 1 || !Array.isArray(saved.items)) throw new Error("已保存配置格式损坏");
      const items = saved.items.map(item => profile(item, item.name));
      return {items, selected: items.some(item => item.id === saved.selected) ? saved.selected : ""};
    }
    function write(value) {
      storage.setItem(key, JSON.stringify({version: 1, ...value}));
    }
    return {
      read,
      save(values, name) {
        const data = read();
        const item = profile(values, name);
        const index = data.items.findIndex(existing => existing.id === item.id);
        if (index === -1) data.items.push(item);
        else {
          if (!String(name || "").trim()) item.name = data.items[index].name;
          data.items[index] = item;
        }
        write({items: data.items, selected: item.id});
        return item;
      },
      select(id) {
        const data = read();
        const item = data.items.find(existing => existing.id === id);
        if (!item) throw new Error("接口配置不存在");
        write({...data, selected: id});
        return item;
      }
    };
  }
  const api = { labels, buildRequest, openRequest, detailSections, createPreviewGate,
    shouldAutoPreview, isDialogBackdrop, progressPercent, isActive, createQueryGate,
    createProfileStore };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BatchView = api;
})(typeof window !== "undefined" ? window : globalThis);
