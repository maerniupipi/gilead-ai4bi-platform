#!/bin/bash
set -euo pipefail

# 与 config/environments/{dev|uat|prod}.env 对应；未设置时默认 dev
export APP_ENV="${APP_ENV:-dev}"

if [[ "${INSTALL_DEPS_ON_START:-false}" == "true" || "${INSTALL_DEPS_ON_START:-false}" == "1" ]]; then
  pip install -r requirements.txt
fi

# 启动服务
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"
WORKERS="${UVICORN_WORKERS:-1}"

if [[ "${KILL_PORT_ON_START:-true}" == "true" || "${KILL_PORT_ON_START:-true}" == "1" ]]; then
  # 开发机便捷开关：生产/用户部署不要默认强杀端口。
  _listeners_on_port() {
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true
  }
  _pids=$(_listeners_on_port | sort -u | tr '\n' ' ')
  if [[ -n "${_pids// /}" ]]; then
    echo "端口 $PORT 已被占用，正在终止进程: ${_pids}"
    for _pid in $(_listeners_on_port | sort -u); do
      [[ -z "$_pid" ]] && continue
      kill -9 "$_pid" 2>/dev/null || true
    done
    _n=0
    while [[ $_n -lt 25 ]]; do
      _left=$(_listeners_on_port | tr '\n' ' ')
      [[ -z "${_left// /}" ]] && break
      sleep 0.2 2>/dev/null || sleep 1
      _n=$((_n + 1))
    done
    _left=$(_listeners_on_port | tr '\n' ' ')
    if [[ -n "${_left// /}" ]]; then
      echo "警告: 端口 $PORT 仍被占用，请检查: lsof -nP -iTCP:$PORT -sTCP:LISTEN"
    fi
  fi
  unset -f _listeners_on_port 2>/dev/null || true
fi

if [[ "$RELOAD" == "true" || "$RELOAD" == "1" ]]; then
  exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
else
  exec uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
fi
