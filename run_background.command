#!/bin/zsh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="english-reading-assistant"
MAIN_FILE="$SCRIPT_DIR/main.py"
LOG_DIR="$HOME/Library/Logs/English Reading Assistant"
LOG_FILE="$LOG_DIR/app.log"

escape_for_applescript() {
  local value="${1//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '%s' "$value"
}

show_error() {
  local message
  message="$(escape_for_applescript "$1")"
  /usr/bin/osascript -e "display alert \"英语阅读助手启动失败\" message \"$message\" as critical" >/dev/null 2>&1 || true
}

append_log() {
  mkdir -p "$LOG_DIR"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

if [[ ! -f "$MAIN_FILE" ]]; then
  show_error "未找到项目入口：$MAIN_FILE"
  exit 1
fi

CONDA_SH=""
for candidate in \
  "/opt/anaconda3/etc/profile.d/conda.sh" \
  "$HOME/anaconda3/etc/profile.d/conda.sh" \
  "/opt/miniconda3/etc/profile.d/conda.sh" \
  "$HOME/miniconda3/etc/profile.d/conda.sh"
do
  if [[ -f "$candidate" ]]; then
    CONDA_SH="$candidate"
    break
  fi
done

if [[ -z "$CONDA_SH" ]]; then
  show_error "未找到 conda 初始化脚本，请先安装或修复 conda。"
  exit 1
fi

source "$CONDA_SH"

ENV_PREFIX="$(conda env list | awk -v env_name="$ENV_NAME" '$1 == env_name {print $NF; exit}')"
if [[ -z "$ENV_PREFIX" ]]; then
  show_error "未找到 conda 环境：$ENV_NAME\n请先在项目目录运行：conda env create -f environment.yml"
  exit 1
fi

PYTHON_BIN="$ENV_PREFIX/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  show_error "未找到 Python 解释器：$PYTHON_BIN"
  exit 1
fi

cd "$SCRIPT_DIR" || {
  show_error "无法切换到项目目录：$SCRIPT_DIR"
  exit 1
}

append_log "启动应用"
nohup "$PYTHON_BIN" "$MAIN_FILE" >> "$LOG_FILE" 2>&1 < /dev/null &
APP_PID=$!
sleep 1

if ! kill -0 "$APP_PID" 2>/dev/null; then
  append_log "应用启动失败"
  show_error "应用未能正常启动，请查看日志：$LOG_FILE"
  exit 1
fi

disown "$APP_PID" 2>/dev/null || true
append_log "应用已在后台启动，PID=$APP_PID"
