#!/usr/bin/env bash
# スキルを .skill ファイル（zip）にまとめる。node_modules は含めない。
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/japanese-proofreading.skill
(cd skills && zip -rq ../dist/japanese-proofreading.skill japanese-proofreading \
  -x '*/node_modules/*' '*/__pycache__/*' '*.pyc' '*/.DS_Store')
echo "dist/japanese-proofreading.skill を作成しました。"
