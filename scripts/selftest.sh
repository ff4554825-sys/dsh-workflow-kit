#!/bin/sh
# scripts/selftest.sh — 全套自测：log-check 判死测试（pytest）+ gate 行为场景
#
# 两头都要绿：S 系列判得准（pytest），三关的短路与判定行为对（test_gate.sh）。
set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
fail=0

echo "=== 1/2 log-check 判死测试（pytest） ==="
if PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider "$HERE/verify/logcheck"; then
  :
else
  fail=1
fi

echo "=== 2/2 gate 行为场景 ==="
if sh "$HERE/verify/gate/test_gate.sh"; then
  :
else
  fail=1
fi

echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
if [ "$fail" -eq 0 ]; then
  echo "SELFTEST: PASS"
  exit 0
fi
echo "SELFTEST: FAIL"
exit 1
