# Batch Runner Implementation Plan

> 执行方式：本会话按 superpowers:executing-plans 自行实现；用户已批准设计并授权进入编码。遵循项目限制，不创建 Git 工作树、不提交、不读取已有其他文件。

**Goal:** 本地网页批量执行 Excel G 列问题，将完整 SSE 过程写到 H 列。
**Architecture:** FastAPI 同源页面与任务管理；独立工作簿、流解析、客户端、队列和存储模块。
**Tech Stack:** Python 3.11+、FastAPI、httpx、openpyxl、uvicorn、原生 JavaScript。
**Spec:** docs/batch-runner-design.md

## Global Constraints
- 不访问真实接口或运行网络接口测试；HTTP 流仅通过内存 transport 模拟。
- 仅操作本任务创建的文件；不用 Git 查询仓库或提交。
- G 输入、H 输出，默认第 2 行、并发 3，1 至 32 可调；按行独立会话。
- end=true 才成功，失败不自动重试，超长结果不截断。
- 对已有文件仅用通过 check 的上下文补丁修改。
- 验证仅显式运行本任务的测试模块，避免 discover 读取其他已有测试。

## Review Focus
- 公式注入、非法 XML 字符、UTF-16 单元格长度：由工作簿测试锁定文本及超限标志。
- SSE 多行、UTF-8 分块及最后一帧无换行：由解析/客户端测试锁定完整事件。
- 取消、保存失败及单行异常不能让整个任务永远运行：由 runner 测试锁定终态。
- 恶意文件名、无效 sheet、合并 H 区域：由 workbook 和 service 直接调用测试验证。
- 重启后的运行中记录：由 storage 测试验证标记中断、保留日志、绝不重发。

## Task 1: Workbook and SSE
Files: app/__init__.py, app/models.py, app/workbook.py, app/sse.py, tests/__init__.py, tests/test_core.py。
Interfaces: inspect_workbook(bytes, start_row), select_rows(bytes, sheets, start_row, overwrite), export_workbook(bytes, rows) -> bytes；SSEDecoder.feed(bytes)/finish() -> list[SSEFrame]；format_frame(frame, number) -> str。
- [x] 写构造工作簿和 SSE 样例测试，验证原 sheet/行号及全文事件。
- [x] 运行 python -B -m unittest tests.test_core -v，确认功能缺失导致失败。
- [x] 实现配置验证、工作簿映射与 SSE 解码。
- [x] 同命令通过；记录结果。

## Task 2: Client, storage and runner
Files: app/client.py, app/storage.py, app/runner.py, tests/test_execution.py。
Interfaces: AgentClient.execute(config, row, on_frame)；Storage.create/load/save/append_event；Runner.start/stop/wait/snapshot。
- [x] 测试内存 transport 请求映射、超时、HTTP 错误、断流、并发上限与停止。
- [x] 运行 python -B -m unittest tests.test_execution -v，确认缺失功能。
- [x] 实现队列、逐事件日志、逐行快照；终态清除认证配置。
- [x] 两个测试模块全部通过。

## Task 3: Local service and page
Files: app/api.py, app/main.py, app/static/index.html, app/static/style.css, app/static/app.js, app/static/view.js, tests/test_service.py, tests/test_view.cjs。
Interfaces: raw upload POST /api/uploads；preview POST /api/preview；start POST /api/jobs；GET job/rows/log/export；POST stop。
- [x] 对服务层直接调用编写测试，不使用 TestClient、不建立网络。
- [x] JavaScript 纯函数测试覆盖筛选、状态和请求配置。
- [x] 实现同源页面：上传、选择、配置、执行、轮询、详情和下载。
- [x] python -B -m unittest tests.test_core tests.test_execution tests.test_service -v；node --test tests/test_view.cjs；node --check app/static/app.js。

## Task 4: Delivery and review
Files: pyproject.toml, README.md, runtime/.gitignore, docs/implementation-progress.md。
- [x] 编写项目级安装、启动与离线验证步骤，不执行依赖安装或服务启动。
- [x] 独立审查本次新增文件；修复实质问题并补回归测试。
- [x] 运行完整显式测试及语法校验，记录结果与未进行的真实接口验收。

## Task 5: 源文件逐题回写与 SQL/回答分列（文档同步）
- [x] 同步 README.md 与 docs/implementation-progress.md：原路径加载、H/I 分列、逐题回写与 writeback.json 哈希校验；清除单列 H 与源文件不覆盖的旧措辞。

## Task 6: 页面收敛为单一路径加载（文档同步）
- [x] 同步 README.md 与 docs/implementation-progress.md：页面唯一入口为原文件绝对路径加载，删除上传模式、路径回显与页头流程图说明，补充详情弹窗点击外部关闭。
