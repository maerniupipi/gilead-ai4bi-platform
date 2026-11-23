#!/usr/bin/env bash
# 在 backend/ 目录下使用：开发环境启动（加载 config/environments/dev.env）
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV=dev
exec ./start.sh
