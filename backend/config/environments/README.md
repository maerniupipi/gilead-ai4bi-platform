# 后端环境配置（dev / uat / prod）

根目录单文件 `.env` 已弃用。本地仅保留 **MySQL**、**Redis** 及少量运行参数；向量库、大模型、ES、OSS 等在系统「项目管理」中维护。

## 文件

| 模板（可提交） | 本地密钥文件（勿提交） |
|----------------|------------------------|
| `dev.env.example` | `dev.env` |
| `uat.env.example` | `uat.env` |
| `prod.env.example` | `prod.env` |

从模板复制后填写真实连接串：

```bash
cp config/environments/dev.env.example config/environments/dev.env
```

## 如何选择环境

由环境变量 **`APP_ENV`** 决定加载哪一个文件（仅允许 `dev` / `uat` / `prod`，默认 `dev`）：

- 读取路径：`config/environments/{APP_ENV}.env`
- 若文件不存在：不报错，仅使用进程里已有的环境变量（适合容器注入）。
- 若需指定任意路径：`DOTENV_PATH=/path/to/file.env`（优先级高于默认路径）。

## 启动命令

在 **`backend/`** 目录下：

| 环境 | 命令 |
|------|------|
| 开发 | `./scripts/run-dev.sh` |
| UAT | `./scripts/run-uat.sh` |
| 生产 | `./scripts/run-prod.sh` |

等价于设置 `APP_ENV` 后执行 `start.sh` / `uvicorn`。

手动示例：

```bash
export APP_ENV=uat
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 与旧 `.env` 的关系

若仍可访问历史 `backend/.env`，请将其中的 `DATABASE_URL`、`REDIS_*` 等迁入对应环境的 `*.env` 后删除 `.env`，避免两套配置不一致。

## 生产部署建议

- 模板文件只允许放占位符，真实账号、密码、AK/SK 只能通过 `*.env`、CI/CD 密钥或 K8s Secret 注入。
- 生产设置 `RELOAD=false`，并按机器规格设置 `UVICORN_WORKERS`。每个 worker 都会持有独立数据库连接池。
- 生产设置明确的 `CORS_ALLOWED_ORIGINS`，不要使用 `*`。若配置为 `*`，服务会自动关闭 CORS credentials。
- 通过 `APP_VERSION` 注入当前发布版本，`/health` 和 `/live` 会返回该版本，便于用户部署登记与排障。

## 新库初始化

部署到一套全新的 MySQL 时，先在目标环境文件里填写 `DATABASE_URL` 和首次管理员信息：

```bash
INIT_SUPER_ADMIN_USERNAME=admin
INIT_SUPER_ADMIN_PASSWORD=请改成客户专用强密码
INIT_SUPER_ADMIN_DISPLAY_NAME=超级管理员
INIT_SPACE_NAME=默认空间
INIT_SPACE_CODE=default
```

然后在 `backend/` 目录执行：

```bash
APP_ENV=prod python scripts/init_database.py
```

脚本会按 `DATABASE_URL` 自动创建数据库、创建 ORM 中登记的全部表，并写入这些必要默认值：

- 默认空间：`spaces.id=1`，编码默认 `default`。
- 预设超级管理员：默认用户名 `admin`，系统角色 `super_admin`，并加入默认空间为 `owner`。
- 默认文件夹：AutoBI、智能体应用、评测模块各一条系统默认文件夹。
- 系统配置：评测默认并发/超时/重试配置、评测对比系统模板、XLSX 洞察 PPT 内置模板。

如确认要重建空库，可追加 `--drop-existing`；该参数会删除 `DATABASE_URL` 指向的数据库后重新创建。

脚本重复执行是幂等的：默认不会覆盖已存在管理员的密码。若确实需要用环境变量中的 `INIT_SUPER_ADMIN_PASSWORD` 重置管理员密码，再追加 `--reset-admin-password`。
