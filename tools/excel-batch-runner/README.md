# 评测集批量执行台

服务器版提供单一 `admin` 账号登录、浏览器上传 Excel、数据库历史管理和结果直接下载。G 列为问题，H 列写完整 SQL、I 列写最终回答、J 列写实验室 TraceID。原始 SSE 和完整过程另外留档。

## 接口配置

默认本机服务为 `http://127.0.0.1:8866`。默认目标接口为 `http://localhost:8000/api/external/agent-chat/sse`，应用和版本初始值均为 1；运行前选择本环境的实际应用、版本和访问地址。请求头只用于当前执行，不保存到接口配置、任务元数据或日志。

## 使用

1. 登录后选择本机 `.xlsx` 文件，最大 20 MB。服务端检查工作簿，解压大小不超过 100 MB，每个选中工作表使用区域不超过 100000 行。
2. 设置问题起始行（默认 2）和并发数（默认 3，最大 32），勾选需要的工作表。
3. 查看预览并核对接口配置。G 列为空的行忽略，H/I/J 任一已有内容默认整行跳过；选择覆盖后会改写结果副本对应三列。
4. 点击「开始执行」。只有此操作会调用远端智能体；刷新、预览、历史查询和下载均不会重新调用。
5. 每题结束自动更新结果 Excel 与数据库记录，运行中可以下载最近一次保存的 Excel。关闭浏览器后服务端继续执行。
6. 历史表格可以搜索名称/文件名/ID、按状态筛选和分页，直接查看任务或下载 Excel、完整日志 ZIP、原始上传文件。可重命名、归档和恢复；归档保留所有文件。
7. 「停止派发」停止新的请求，已发出的请求继续到结束或超时。

服务器版不会读取用户电脑上的绝对路径，也不会改写电脑上的原文件。需要本机原路径逐题回写时，单独启动本地服务并设置 `BATCH_ALLOW_LOCAL_PATHS=true`；上传模式始终保留原始上传文件。

## 数据与恢复

服务器数据库为独立的 PostgreSQL `batch_runner`，数据库角色同名，最大 3 个连接。复用服务器现有 PostgreSQL 服务与 TLS，不使用平台业务表。

数据库表：

- `batch_accounts`：唯一 admin 账号与 scrypt 密码散列。
- `batch_sessions`：服务端会话，仅保存会话令牌的 SHA256 摘要，12 小时到期；退出登录立即撤销。
- `batch_jobs`：任务、接口应用/版本、名称、状态、归档信息。
- `batch_rows`：逐题问题、SQL、回答、TraceID 和完整过程。

`BATCH_DATA_DIR` 持久保存上传、`source.xlsx`、`result.xlsx`、原始事件 JSONL 和文件镜像。数据库负责查询与历史状态，Excel/原始事件保存在磁盘。旧版 runtime 中的文件历史在首次连接空数据库时导入。

重启后运行中任务标为中断，保留已保存结果；不会自动重发。重试前应检查远端执行情况。单次仅运行一个批次，所有工作表共享并发上限；不要使用多 worker、多实例或自动重载。

## 本机开发

需要 Python 3.11+：

```bash
cd tools/excel-batch-runner
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -B -m app.main
```

默认地址 `http://127.0.0.1:8866`。未设置 `BATCH_ADMIN_PASSWORD` 时首次启动会生成随机初始密码，保存到 `runtime/admin-login.txt`，仅当前用户可读。设置的初始密码只用于首次建号；后续启动继续使用数据库中的密码散列。

本地默认使用 `runtime/batch.sqlite3`；设置 `BATCH_DATABASE_URL=postgresql+psycopg://...` 可连接 PostgreSQL。密码等配置通过环境注入，不提交 `.env`。示例见 `.env.example`。`--host` 与 `--port` 或 `BATCH_HOST`、`BATCH_PORT` 控制监听。

## Docker

复制 `.env.example` 为 `.env` 并填写初始密码、数据库连接及允许的访问域名，运行 `docker compose up -d --build`。使用独立 `batch-data` 文件卷，默认不依赖外部 Docker 网络。目标平台地址必须能从批跑容器访问；容器中的 localhost 指批跑容器自身。

健康检查为 `/healthz`。备份应同时保存批跑数据库、文件卷和运行环境配置。HTTPS 代理部署时启用 `BATCH_COOKIE_SECURE` 并填写 `BATCH_ALLOWED_HOSTS`。

## 请求与输出

每个问题创建独立 conversation_id；G 列文本同时映射到 `message`、`inputs.input`、`inputs.question`。默认连接超时 15 秒、流读取空闲超时 120 秒、总时限 600 秒。HTTP 错误、超时、格式错误或未收到 `data.end=true` 的断流均算失败；已接收内容保留，不自动重试。

完整日志 ZIP 包含 `results.json`、`rows/<row_id>.txt`、`events/<row_id>.jsonl`。SQL/回答/TraceID 分列独立检查 Excel 单元格容量（UTF-16 32767 单位）；超限时保留完整日志，绝不静默截断。以 `=` 开头的输出按文本写入；非法 XML 控制字符可逆转义。保留原工作表、行号和普通公式；openpyxl 不重算公式缓存，复杂 Excel 扩展对象需要核对导出。

TraceID 来源于实际 SSE，不使用 conversation_id 代替；接口未返回时明确标记。text 按增量原样拼接；rewriteQuestion 为累计快照，不重复写入正文。查看完成批次时需同时检查成功/失败/未执行计数。

## 验证

```bash
.venv/bin/python -B -m unittest tests.test_core tests.test_execution tests.test_service tests.test_traces tests.test_auth_history -v
node --test tests/test_view.cjs
node --check app/static/app.js
node --check app/static/login.js
```

Python 测试使用构造工作簿、HTTPX 内存传输和禁止真实 socket 的保护；覆盖登录、会话撤销与过期、CSRF、限速、上传、历史搜索/重命名/归档/恢复、下载和数据库恢复。真实平台连通性在部署环境单独验收。
