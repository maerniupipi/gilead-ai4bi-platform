#!/usr/bin/env bash
# 在 backend/ 目录下使用：生产（加载 config/environments/prod.env）
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV=prod
export RELOAD="${RELOAD:-false}"
exec ./start.sh
