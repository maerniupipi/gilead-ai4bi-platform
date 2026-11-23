# Workflow Script Imports Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让工作流脚本任务支持运行环境中可用模块的绝对导入，修复 `typing` 导入失败，并提供准确的脚本能力清单。

**Architecture:** 保留 RestrictedPython 的编译与受限内建环境，但将容易遗漏的静态 import 白名单替换为 Python 原生绝对导入。相对导入继续拒绝，因为工作流代码不是包模块；模块是否可用由 UAT 运行镜像中的 Python 3.11 标准库和 `requirements.txt` 决定。

**Tech Stack:** Python 3.11/3.13、RestrictedPython 8、unittest、FastAPI backend

---

### Task 1: Add import regression coverage

**Files:**
- Modify: `backend/tests/test_agent_workflow_engine.py`
- Test: `backend/tests/test_agent_workflow_engine.py`

**Step 1: Write the failing test**

添加与用户脚本一致的测试，覆盖 `import json`、`from typing import Any, Dict, List`、JSON 解析及四个输出字段。

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m unittest tests.test_agent_workflow_engine.TestScriptAndAgentConstInput.test_script_supports_json_and_typing_imports -v`

Expected: FAIL，错误包含 `不允许导入模块: typing`。

### Task 2: Open absolute imports to installed runtime modules

**Files:**
- Modify: `backend/app/services/agent_app/executors/script.py`
- Test: `backend/tests/test_agent_workflow_engine.py`

**Step 1: Replace the static allowlist importer**

允许所有绝对导入通过 Python 原生 `__import__` 解析；继续拒绝 `level != 0` 的相对导入，并为未安装模块提供面向脚本作者的错误信息。

**Step 2: Add behavior tests**

覆盖标准库顶层导入、`from ... import ...`、已安装第三方包、嵌套模块、相对导入拒绝和缺包提示。

**Step 3: Run focused tests**

Run: `backend/.venv/bin/python -m unittest tests.test_agent_workflow_engine.TestScriptAndAgentConstInput -v`

Expected: PASS。

### Task 3: Document the complete script task contract

**Files:**
- Create: `docs/工作流脚本任务模块清单.md`

**Step 1: Document execution contract**

说明入口函数、输入输出、变量类型、错误行为、兼容语法和示例。

**Step 2: Document imports**

列出 Python 3.11 标准库支持规则，以及 `requirements.txt` 中所有可直接使用的第三方 import 名称和版本。

**Step 3: Document runtime boundaries**

说明相对导入、未安装依赖、超时/资源隔离现状与可信作者约束，避免把 RestrictedPython 描述成进程级安全沙箱。

### Task 4: Verify and prepare UAT release

**Files:**
- Verify: `backend/app/services/agent_app/executors/script.py`
- Verify: `backend/tests/test_agent_workflow_engine.py`
- Verify: `docs/工作流脚本任务模块清单.md`

**Step 1: Run the complete workflow engine test module**

Run: `backend/.venv/bin/python -m unittest tests.test_agent_workflow_engine -v`

Expected: PASS。

**Step 2: Run backend compile checks**

Run: `backend/.venv/bin/python -m compileall -q app tests/test_agent_workflow_engine.py`

Expected: exit 0。

**Step 3: Verify the UAT runtime mode**

Run: `APP_ENV=uat backend/.venv/bin/python -c "from app.core.env_loader import load_app_environment; print(load_app_environment())"`

Expected: UAT 环境可加载，且不打印密钥。

**Step 4: Release through the repository's available UAT path**

只提交本任务文件，保留工作区中已有的用户改动；若远端或 CI 不可达，记录精确阻塞信息，不把本地 UAT 启动冒充远端发布。
