#!/bin/sh
# scripts/install.sh — 把仓库副本装进 $DSH_HOME/bin 并立即自检一致性
#
# 装完不检查，等于把「文档写的行为」换成「旧副本的行为」还没人知道。所以最后一步固定
# 跑 kit-doctor：IN SYNC 才算装好。
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"

mkdir -p "$DSH_HOME/bin" "$DSH_HOME/verify"

# shellcheck disable=SC2086
install -m 755 "$HERE"/bin/* "$DSH_HOME/bin/"

mkdir -p "$DSH_HOME/docs"
install -m 644 "$HERE"/docs/v12-field-matrix.json "$DSH_HOME/docs/" 2>/dev/null || true

for d in logcheck gate cancel; do
  [ -d "$HERE/verify/$d" ] || continue
  rm -rf "$DSH_HOME/verify/$d"
  cp -r "$HERE/verify/$d" "$DSH_HOME/verify/$d"
done
find "$DSH_HOME/verify" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$DSH_HOME/verify" -name .pytest_cache -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "已安装: $DSH_HOME/bin"
exec "$DSH_HOME/bin/kit-doctor" "$HERE"
