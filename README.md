# AI4BI Platform

完整的数据分析平台：平台前端、后端、通用部署和 Excel 批量评测工具。

## 目录

- `backend/`：FastAPI 服务、智能体工作流、AutoBI 实验室、数据源与知识库、向量检索、表格问答、评测、服务调用、会话诊断与文件导出。
- `frontend/`：Vue 3 管理界面、工作流画布、实验室、模型和数据源管理、SQL 查询、评测、会话及系统日志。
- `deploy/`：平台前后端、MySQL 与 Redis 的 Docker Compose。
- `tools/excel-batch-runner/`：独立 Excel 批跑工具。
- `docs/`：通用服务接口、同步配置与验证记录。

## 本地启动

后端使用 Python 3.11+。创建虚拟环境并安装 `backend/requirements.txt`；测试另装 `backend/requirements-dev.txt`。复制 `backend/config/environments/dev.env.example` 为 `dev.env`，按需从 `backend/.env.example` 补充配置。

配置 MySQL 连接后，在 backend 下执行 `python scripts/init_database.py --env dev`，必须通过环境变量 `INIT_SUPER_ADMIN_PASSWORD` 提供初始密码。随后执行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。

前端在 frontend 下执行 `pnpm install --frozen-lockfile`、`pnpm dev`。复制 `.env.example` 为 `.env.local` 并填写与后端一致的加密密钥。完整容器部署见 [deploy/README.md](deploy/README.md)。

## 通用服务

管理中心创建服务 Key 并绑定已发布工作流版本。调用 `/api/service/chat-messages`，`user` 为调用方用户标识，`inputs` 接收业务参数；会话、结果、停止及导出均按服务 Key 和用户归属隔离。详见 [接口说明](docs/api/README.md)。

总结按最终可见分支实时输出，大块文本分片显示；对话关键词支持完整 TraceID。SQL 改写由实验室中选定的工作流处理，没有内置组织规则。同步任务由部署方配置，默认无任务，详见 [数据同步](docs/data-sync.md)。

## 验证

```sh
cd backend
AUDIT_LOG_DB_ENABLED=false python -m pytest -q --disable-warnings
cd ../frontend
node --test tests/*.test.js tests/*.test.mjs
pnpm build
pnpm build:share
```

验证范围与部署限制见 [迁移验证记录](docs/migration-validation.md)。真实模型、向量库和外部业务接口需要部署后按实际配置验收。运行凭证、业务数据、会话记录及生成文件不在源码仓库中。

最新通用增量及升级步骤见 [2026-11-18 同步记录](docs/updates/2026-11-18-platform-sync.md)。
