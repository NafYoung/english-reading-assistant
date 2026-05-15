#!/bin/zsh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="english-reading-assistant"
MAIN_FILE="$SCRIPT_DIR/main.py"

pause_and_exit() {
  local exit_code="${1:-1}"
  echo
  read -r "?按回车键关闭窗口..."
  exit "$exit_code"
}

if [[ ! -f "$MAIN_FILE" ]]; then
  echo "未找到项目入口：$MAIN_FILE"
  pause_and_exit 1
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
  echo "未找到 conda 初始化脚本，请先安装或修复 conda。"
  pause_and_exit 1
fi

source "$CONDA_SH"

if ! conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  echo "未找到 conda 环境：$ENV_NAME"
  echo "请先在项目目录运行：conda env create -f environment.yml"
  pause_and_exit 1
fi

if ! conda activate "$ENV_NAME"; then
  echo "激活 conda 环境失败：$ENV_NAME"
  pause_and_exit 1
fi

cd "$SCRIPT_DIR" || pause_and_exit 1

python main.py
status=$?

if [[ $status -ne 0 ]]; then
  echo
  echo "程序已退出，状态码：$status"
  pause_and_exit "$status"
fi
