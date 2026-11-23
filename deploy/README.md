# 部署

此目录仅部署平台后端、平台前端、MySQL 与 Redis。向量库、模型、对象存储和业务数据源通过平台配置接入。

1. `cp .env.example .env`，填写随机数据库密码和加密密钥；数据库密码使用 URL 安全字符。
2. `cp ../backend/.env.example env/platform-backend.env`，填写同一个 `PASSWORD_ENCRYPTION_KEY`、`INIT_SUPER_ADMIN_PASSWORD` 和独立的 `CHATBI_DOWNLOAD_SIGNING_KEY`。其他服务仅在需要时配置。Compose 会覆盖数据库与 Redis 连接到同组容器。
3. `docker compose up -d mysql redis`，然后 `docker compose build`。
4. `docker compose run --rm platform-backend python scripts/init_database.py` 创建表、管理员、默认空间和通用模板。
5. `docker compose up -d`。平台默认 `http://localhost:8080`，分享页使用 3840 端口，后端健康检查为 `/health`。

平台服务 Key 在管理中心创建并绑定本环境已发布的工作流版本。外部调用使用 `/api/service`。未配置 `DATA_SYNC_TASKS` 时不创建数据同步任务，也不会启动任何业务拉数。

`backend/init_tables.sql` 为当前 ORM 生成的 MySQL 表结构，不包含账号、业务数据、模型凭证或客户配置；推荐使用初始化脚本补齐通用种子数据。外部服务、模型及真实数据库的连接验收需要在部署环境完成。

环境文件和持久卷均不入库。备份需同时覆盖 MySQL、Redis、平台文件卷和运行环境配置。

## 更新已有部署

本次通用更新新增两张 TraceID 索引表和会话轮次复合索引。更新镜像后，可先执行 `docker compose run --rm platform-backend python scripts/init_chatbi_tables.py`，再重启服务；脚本只补建表/索引，不删除或改写会话内容。后台进程会分批建立历史诊断记录的 TraceID 索引，尚未迁完的记录仍可查询。

后端镜像入口为 `python -m app.runtime`：先串行检查结构，再启动多个 API 进程和一个独立后台进程。评测、同步、文件导出和索引回填由后台执行，数据库锁防止多个后台进程同时运行。普通本地开发使用 uvicorn 时保留内嵌后台模式。

执行/检索/数据库线程池、工作流总并发及脚本进程容量见 `backend/.env.example`。这些上限按进程生效；调整 API 进程数时应同时核对数据库连接数。脚本排队或执行超过配置时限会终止脚本进程并释放槽位；这属于运行隔离，不是对不可信脚本的完整安全沙箱。

平台后端容器保留 60 秒关闭窗口，以覆盖 API 和后台进程的有序退出。
