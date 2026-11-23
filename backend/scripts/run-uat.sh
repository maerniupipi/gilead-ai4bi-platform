#!/usr/bin/env bash
# 在 backend/ 目录下使用：UAT（加载 config/environments/uat.env）
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV=uat
exec ./start.sh
