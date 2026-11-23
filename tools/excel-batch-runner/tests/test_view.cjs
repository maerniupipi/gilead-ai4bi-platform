const assert = require("node:assert/strict");
const { test } = require("node:test");
function memoryStorage() {
  const items = new Map();
  return {getItem: key => items.get(key) ?? null, setItem: (key, value) => items.set(key, value),
    values: () => [...items.values()].join("")};
}
test("profiles retain versions, restore selection and never store headers", () => {
  const storage = memoryStorage();
  const profiles = view.createProfileStore(storage);
  const config = {url: "http://example.invalid/sse", app_id: 12, version_id: 35,
    headers: {Authorization: "SECRET"}, caller: "ignored"};
  const first = profiles.save(config, "测试版本");
  const second = profiles.save({...config, version_id: 36}, "新版本");
  assert.equal(profiles.read().items.length, 2);
  profiles.select(first.id);
  assert.equal(view.createProfileStore(storage).read().selected, first.id);
  assert.equal(profiles.save(config, "重命名").id, first.id);
  assert.equal(profiles.read().items.length, 2);
  assert.equal(profiles.read().items[0].name, "重命名");
  assert.ok(profiles.read().items.some(item => item.id === second.id));
  assert.ok(!storage.values().includes("SECRET"));
  assert.ok(!storage.values().includes("caller"));
});
test("profile switch applies selected endpoint even when remembering selection fails", async () => {
  const fs = require("node:fs"), vm = require("node:vm");
  const storage = memoryStorage(), store = view.createProfileStore(storage);
  const a = store.save({url: "http://a.invalid/sse", app_id: 1, version_id: 1}, "A");
  const b = store.save({url: "http://b.invalid/sse", app_id: 2, version_id: 2}, "B");
  store.select(a.id);
  const elements = new Map();
  const html = fs.readFileSync(require.resolve("../app/static/index.html"), "utf8");
  for (const match of html.matchAll(/id="([^"]+)"/g)) {
    elements.set(match[1], {value: "", textContent: "", children: [], listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      replaceChildren(...children) { this.children = children; },
      querySelectorAll() { return []; }, close() {}, classList: {toggle() {}}});
  }
  const calls = [];
  const defaults = {url: "http://default.invalid/", app_id: 12, version_id: 35};
  vm.runInNewContext(fs.readFileSync(require.resolve("../app/static/app.js"), "utf8"), {
    window: {BatchView: view, localStorage: storage},
    document: {getElementById(id) { assert.ok(elements.has(id), id); return elements.get(id); },
      createElement() { return {append() {}}; }},
    Option: function(text, value) { this.text = text; this.value = value; },
    fetch: async path => {
      calls.push(path);
      assert.ok(["/api/auth/me", "/api/defaults", "/api/jobs"].includes(path) || path.startsWith("/api/history?"));
      return {ok: true, json: async () => path === "/api/auth/me" ? {username: "admin", csrf: "test"} :
        path === "/api/defaults" ? defaults : path.startsWith("/api/history?") ? {items: [], total: 0} : []};
    },
    URLSearchParams, setTimeout() {}, clearTimeout() {}, console
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.get("url").value, a.url);
  storage.setItem = () => { throw Error("storage full"); };
  elements.get("endpoint-profile").value = b.id;
  elements.get("headers").value = '{"Authorization":"SECRET"}';
  elements.get("endpoint-profile").listeners.change();
  assert.equal(elements.get("url").value, b.url);
  assert.equal(elements.get("app_id").value, b.app_id);
  assert.equal(elements.get("version_id").value, b.version_id);
  assert.equal(elements.get("headers").value, "{}");
  assert.match(elements.get("profile-hint").textContent, /无法记住/);
  assert.deepEqual(calls.slice(0, 3), ["/api/auth/me", "/api/defaults", "/api/jobs"]);
  assert.ok(calls[3].startsWith("/api/history?"));
});

test("profiles reject bad URLs and ids, and expose storage errors", () => {
  const profiles = view.createProfileStore(memoryStorage());
  const valid = {url: "http://example.invalid/sse", app_id: 1, version_id: 2};
  for (const extra of [{url: "javascript:alert(1)"}, {url: "http://user:pass@example.invalid/"},
                       {version_id: 0}, {app_id: 1.5}, {url: "http://example.invalid/#x"}]) {
    assert.throws(() => profiles.save({...valid, ...extra}));
  }
  assert.throws(() => profiles.select("missing"));
  const unavailable = view.createProfileStore({getItem() { throw Error("blocked"); }});
  assert.throws(() => unavailable.read(), /blocked/);
  const corrupt = view.createProfileStore({getItem() { return "broken"; }});
  assert.throws(() => corrupt.read());
  const full = view.createProfileStore({getItem() { return null; }, setItem() { throw Error("full"); }});
  assert.throws(() => full.save(valid), /full/);
});
let view;
try { view = require("../app/static/view.js"); } catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
}
test("build request maps all controls, including independent timeout and selected sheets", () => {
  assert.ok(view, "Frontend helpers are missing");
  const request = view.buildRequest({
    upload_id: "abc", sheets: ["销售", "市场"], start_row: "3", overwrite: true,
    url: "http://example.invalid/sse", app_id: "12", version_id: "35",
    caller: "debug", channel: "api-docs", concurrency: "4",
    connect_timeout: "15", read_timeout: "120", total_timeout: "600",
    headers: '{"Authorization":"test"}'
  });
  assert.deepEqual(request.sheets, ["销售", "市场"]);
  assert.equal(request.start_row, 3);
  assert.equal(request.config.concurrency, 4);
  assert.equal(request.config.headers.Authorization, "test");
});
test("reject invalid header JSON, empty selections and noninteger concurrency", () => {
  assert.ok(view, "Frontend helpers are missing");
  const valid = {upload_id:"x", sheets:["s"], start_row:2, overwrite:false,
    url:"http://example.invalid/sse", app_id:12, version_id:35, caller:"x",
    channel:"x", concurrency:3, connect_timeout:15, read_timeout:120, total_timeout:600, headers:"{}"};
  assert.throws(() => view.buildRequest({...valid, headers:"[]"}));
  assert.throws(() => view.buildRequest({...valid, headers:"not-json"}));
  assert.throws(() => view.buildRequest({...valid, sheets:[]}));
  assert.throws(() => view.buildRequest({...valid, concurrency:1.5}));
});
test("progress counts skipped and invalid rows and remains bounded", () => {
  assert.ok(view, "Frontend helpers are missing");
  assert.equal(view.progressPercent({finished:3, total:4}), 75);
  assert.equal(view.progressPercent({finished:0, total:0}), 0);
  assert.equal(view.progressPercent({finished:5, total:4}), 100);
  assert.equal(view.isActive("stopping"), true);
  assert.equal(view.isActive("interrupted"), false);
});


test("upload and preview progress never assigns a nonfinite HTML progress value", () => {
  const samples = [
    {total: 12, counts: {}}, {total: 12, counts: {pending: 10, skipped: 2}},
    {}, null, {total: Infinity, finished: 2}, {total: 2, finished: NaN},
    {total: 2, finished: Infinity}, {total: 2, finished: -1}
  ];
  for (const sample of samples) {
    const value = view.progressPercent(sample);
    assert.ok(Number.isFinite(value), "progress must be finite: " + JSON.stringify(sample));
    assert.equal(value, 0);
  }
});

test("an older filter response cannot replace the newest page", async () => {
  assert.equal(typeof view.createQueryGate, "function", "Query guard is missing");
  const gate = view.createQueryGate();
  let oldResolve, newResolve, displayed;
  const first = gate.run(() => new Promise(resolve => { oldResolve = resolve; }),
    value => { displayed = value; });
  const second = gate.run(() => new Promise(resolve => { newResolve = resolve; }),
    value => { displayed = value; });
  newResolve({page: 2, sheet: "市场"});
  assert.equal(await second, true);
  oldResolve({page: 1, sheet: "销售"});
  assert.equal(await first, false);
  assert.deepEqual(displayed, {page: 2, sheet: "市场"});
});
test("a stale filter error cannot overwrite a newer successful query", async () => {
  assert.equal(typeof view.createQueryGate, "function", "Query guard is missing");
  const gate = view.createQueryGate();
  let rejectOld;
  const first = gate.run(() => new Promise((_, reject) => { rejectOld = reject; }), () => {});
  await gate.run(() => Promise.resolve("new"), () => {});
  rejectOld(new Error("stale"));
  assert.equal(await first, false);
});

test("open request trims the path and enforces the start row", () => {
  assert.ok(view, "Frontend helpers are missing");
  assert.deepEqual(view.openRequest("  D:\\data\\问题.xlsx  ", "3"),
    {path: "D:\\data\\问题.xlsx", start_row: 3});
  assert.throws(() => view.openRequest("   ", "2"), /绝对路径/);
  assert.throws(() => view.openRequest("D:\\a.xlsx", "0"), /起始行/);
});

test("detail sections split rows into SQL, answer and process with gap labels", () => {
  assert.equal(view.detailSections({output_format: "trace", output: "x"}), null);
  const sections = view.detailSections({output_format: "split", sql: "SELECT 1",
    answer: "答案", output: "过程"});
  assert.deepEqual(sections.map(section => section.title), ["SQL", "最终回答", "完整过程"]);
  assert.equal(sections[0].content, "SELECT 1");
  const gaps = view.detailSections({output_format: "split", sql: "", answer: "",
    output: "", status: "failed", error: "断流"});
  assert.equal(gaps[0].content, "未返回 SQL");
  assert.equal(gaps[1].content, "未完成：断流");
  assert.equal(gaps[2].content, "未返回完整过程");
});

test("preview gate drops stale responses and invalidates on selection change", () => {
  const gate = view.createPreviewGate();
  const first = gate.begin();
  assert.equal(gate.isCurrent(first), true);
  gate.invalidate();
  assert.equal(gate.isCurrent(first), false);
  const second = gate.begin();
  assert.equal(gate.isCurrent(second), true);
  assert.equal(gate.isCurrent(first), false);
});

test("partial answers keep their content and show failure or interruption", () => {
  for (const status of ["failed", "interrupted"]) {
    const sections = view.detailSections({output_format: "split", status,
      error: "未收到结束标记", answer: "已收到的部分回答", sql: "SELECT 1", output: "过程"});
    assert.match(sections[1].content, /未完成：未收到结束标记/);
    assert.match(sections[1].content, /已收到的部分回答/);
    assert.equal(sections[0].content, "SELECT 1");
  }
  const sections = view.detailSections({output_format: "split", status: "success", answer: "完整回答"});
  assert.equal(sections[1].content, "完整回答");
});

test("auto preview triggers only with a loaded workbook and no loaded job", () => {
  assert.equal(view.shouldAutoPreview({upload: {upload_id: "a"}, job: null}), true);
  assert.equal(view.shouldAutoPreview({upload: null, job: null}), false);
  assert.equal(view.shouldAutoPreview({upload: {upload_id: "a"}, job: {job_id: "j"}}), false);
  assert.equal(view.shouldAutoPreview(null), false);
});

test("dialog closes only on backdrop, not on content clicks", () => {
  const dialog = {};
  const inner = {};
  assert.equal(view.isDialogBackdrop({target: dialog}, dialog), true);
  assert.equal(view.isDialogBackdrop({target: inner}, dialog), false);
  assert.equal(view.isDialogBackdrop(null, dialog), false);
  assert.equal(view.isDialogBackdrop({target: dialog}, null), false);
});

test("new trace format exposes all lab ids separately while historical split stays unchanged", () => {
  const row = {output_format: "split_trace", sql: "SELECT 1", answer: "answer", output: "process",
    lab_trace_ids: ["lab-one", "nested-lab", "failed-lab"]};
  const sections = view.detailSections(row);
  assert.equal(sections[3].title, "实验室 TraceID / J");
  assert.equal(sections[3].content, "lab-one\nnested-lab\nfailed-lab");
  assert.equal(view.detailSections({...row, output_format: "split"}).length, 3);
  assert.equal(view.detailSections({...row, lab_trace_ids: []})[3].content, "未返回实验室 TraceID");
});
