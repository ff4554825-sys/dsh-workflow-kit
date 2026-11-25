#!/bin/sh
# qcheck:allow-placeholders
# verify/gate/test_gate.sh — gate 行为测试：每个场景一次真实调用 + 输出断言
#
# 断的是行为，不是实现：串行短路、按内容识别 task-log、三关各自能红、
# 记账写进 gate-log、安装副本漂移能被 kit-doctor 抓到。
# 退出码 0 = 全绿。
#
# 本文件带着 allow 标记：E/F 两个场景故意在样例文件里写占位符，自己不能被判红。
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 2
W=$(mktemp -d) || exit 2
trap 'rm -rf "$W"' EXIT INT TERM

export DSH_HOME="$W/home"
mkdir -p "$DSH_HOME/bin" "$DSH_HOME/verify"
cp "$ROOT"/bin/* "$DSH_HOME/bin/" || exit 2
chmod +x "$DSH_HOME"/bin/* 2>/dev/null || true
# 安装副本还包含 verify 下的自测，kit-doctor 会比它们；不拷就会假报 MISSING
for d in logcheck gate; do
  cp -r "$ROOT/verify/$d" "$DSH_HOME/verify/$d" || exit 2
done
# schema-v12 依赖字段矩阵；不拷这份，kit-doctor 会一直报 MISSING
mkdir -p "$DSH_HOME/docs"
cp "$ROOT/docs/v12-field-matrix.json" "$DSH_HOME/docs/" || exit 2

GATE="$DSH_HOME/bin/gate"
GLOG="$DSH_HOME/verify/gate-log.jsonl"

pass=0
fail=0
ok()  { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; printf '%s\n' "${2:-}" | sed 's/^/     | /'; }

run() { OUT=$("$GATE" "$@" 2>&1); CODE=$?; }
has() { printf '%s' "$OUT" | grep -q -- "$1"; }

# ---- A 好文件必须 PASS ----
mkdir -p "$W/a"
printf '# 标题\n\n正文一行。\n' > "$W/a/doc.md"
run "$W/a/doc.md"
if [ "$CODE" -eq 0 ] && has 'GATE: PASS'; then ok "A 干净文件 → GATE: PASS"
else bad "A 干净文件 → GATE: PASS" "$OUT"; fi

# ---- B S 红立刻停：文件名不含 task-log 也要查；F1 不该跑 ----
mkdir -p "$W/b"
printf '%s\n' '{"seq":1,"corrects":null,"ts":"2026-11-25T10:00:00+08:00","task":"t","tier":"full","tier_rule":"rule:T3","degraded":false}' > "$W/b/log.jsonl"
run "$W/b/log.jsonl"
if has 'GATE: FAIL (S)' && ! has '✓ F1'; then
  ok "B S 红即停，且按内容识别（log.jsonl 不含 task-log 字样）"
else bad "B S 红即停 + 按内容识别" "$OUT"; fi

# ---- C F1 红：语法错的 .py，F2 不该跑 ----
mkdir -p "$W/c"
printf 'def broken(:\n' > "$W/c/bad.py"
printf 'def test_ok():\n    assert True\n' > "$W/c/test_ok.py"
run "$W/c"
if has 'GATE: FAIL (F1)' && ! has 'F2'; then ok "C F1 红短路，F2 未跑"
else bad "C F1 红短路" "$OUT"; fi

# ---- D F2 红：语法合法但断言失败，F3 不该跑 ----
mkdir -p "$W/d"
printf 'def test_bad():\n    assert 1 == 2\n' > "$W/d/test_bad.py"
run "$W/d"
if has 'GATE: FAIL (F2)' && ! has 'F3'; then ok "D F2 红短路，F3 未跑"
else bad "D F2 红短路" "$OUT"; fi

# ---- E F3 红：占位符残留 ----
mkdir -p "$W/e"
printf '# 文档\n\n这一步 TODO 待补。\n' > "$W/e/doc.md"
run "$W/e"
if has 'GATE: FAIL (F3)' && has '占位符'; then ok "E 占位符 → F3 红"
else bad "E 占位符 → F3 红" "$OUT"; fi

# ---- F 显式豁免：文件里写了 allow 标记就不扫占位符 ----
mkdir -p "$W/f"
printf '# qcheck:allow-placeholders\n\n这里写 TODO 说明规则本身，不判红。\n' > "$W/f/ok.md"
run "$W/f/ok.md"
if [ "$CODE" -eq 0 ] && has 'GATE: PASS'; then ok "F 显式豁免标记生效"
else bad "F 显式豁免标记生效" "$OUT"; fi

# ---- G 合法 task-log 改名 notes.jsonl 仍被 S 接管 ----
mkdir -p "$W/g"
cp "$ROOT/examples/task-log.sample.jsonl" "$W/g/notes.jsonl" || exit 2
run "$W/g/notes.jsonl"
if has 'S schema PASS' && has 'GATE: PASS'; then ok "G 按内容触发 S（notes.jsonl）"
else bad "G 按内容触发 S" "$OUT"; fi

# ---- H 普通 jsonl 不该被当 task-log ----
mkdir -p "$W/h"
printf '{"a":1}\n' > "$W/h/data.jsonl"
run "$W/h/data.jsonl"
if has 'S 跳过' && has 'GATE: PASS'; then ok "H 非 task-log 的 jsonl 明确跳过 S"
else bad "H 非 task-log 的 jsonl 明确跳过 S" "$OUT"; fi

# ---- L 数据文件里的占位符词不算质量问题（真实误报回归：日志 lesson 引用了这个词） ----
mkdir -p "$W/l"
python3 - "$ROOT/examples/task-log.sample.jsonl" "$W/l/log.jsonl" <<'PYEOF'
import json, sys
row = json.loads(open(sys.argv[1], encoding="utf-8").read().strip().split("\n")[0])
row["review"] = "这轮把待补项写进复盘文本，属于数据内容，不是交付占位符"
open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
PYEOF
run "$W/l/log.jsonl"
if has 'S schema PASS' && has 'ph=skip-json' && has 'GATE: PASS'; then
  ok "L 结构化数据文件不扫占位符（ph=skip-json）"
else bad "L 结构化数据文件不扫占位符" "$OUT"; fi

# ---- M 老日志（全是 legacy 行）也要被 S 接管 ----
mkdir -p "$W/m"
printf '%s\n' \
  '{"seq":1,"ts":"2026-11-25T10:00:00+08:00","legacy":true,"task":"老记录","result":"success"}' \
  '{"seq":2,"ts":"2026-11-25T10:01:00+08:00","legacy":true,"task":"老记录2","result":"success"}' \
  > "$W/m/old.jsonl"
run "$W/m/old.jsonl"
if has 'S schema PASS' && has 'GATE: PASS'; then ok "M legacy 老日志也被 S 接管"
else bad "M legacy 老日志也被 S 接管" "$OUT"; fi

# ---- N 缺解释器 = 不能判定 = 红（不是静默跳过） ----
mkdir -p "$W/n" "$W/fb"
printf 'export const a = 1;\n' > "$W/n/a.test.mjs"
for c in mkdir mktemp dirname date wc tr grep sed ls basename head jq python3 bash rm cat; do
  cp=$(command -v "$c" 2>/dev/null) && ln -sf "$cp" "$W/fb/$c"
done
NOUT=$(PATH="$W/fb" "$GATE" "$W/n/a.test.mjs" 2>&1); NCODE=$?
if [ "$NCODE" -eq 1 ] && printf '%s' "$NOUT" | grep -q '不能判定'; then
  ok "N 缺 node → F1 判红（不能判定≠通过）"
else bad "N 缺 node → F1 判红" "$NOUT"; fi

# ---- I 缺 log-check 时 fail-closed（不假装通过） ----
mkdir -p "$W/i"
printf '{"seq":1}\n' > "$W/i/x.jsonl"
mv "$DSH_HOME/bin/log-check" "$DSH_HOME/bin/log-check.bak"
run "$W/i/x.jsonl"
mv "$DSH_HOME/bin/log-check.bak" "$DSH_HOME/bin/log-check"
if has 'GATE: FAIL (S)' && has '缺工具=不通过'; then ok "I log-check 缺失 → fail-closed"
else bad "I log-check 缺失 → fail-closed" "$OUT"; fi

# ---- J gate-log 记账（proc-stats 依赖它） ----
missing=""
for r in PASS FAIL_S FAIL_F1 FAIL_F2 FAIL_F3; do
  grep -q "\"result\":\"$r\"" "$GLOG" 2>/dev/null || missing="$missing $r"
done
if [ -z "$missing" ]; then ok "J gate-log 记录 PASS/FAIL_S/FAIL_F1/FAIL_F2/FAIL_F3"
else bad "J gate-log 记账缺:$missing" "$(cat "$GLOG" 2>/dev/null)"; fi

# ---- K kit-doctor：一致 → 0；改一个字节 → 1；还原 → 0 ----
"$DSH_HOME/bin/kit-doctor" "$ROOT" >/dev/null 2>&1; c1=$?
printf '\n# drift\n' >> "$DSH_HOME/bin/qcheck"
"$DSH_HOME/bin/kit-doctor" "$ROOT" >/dev/null 2>&1; c2=$?
cp "$ROOT/bin/qcheck" "$DSH_HOME/bin/qcheck" && chmod +x "$DSH_HOME/bin/qcheck"
"$DSH_HOME/bin/kit-doctor" "$ROOT" >/dev/null 2>&1; c3=$?
if [ "$c1" -eq 0 ] && [ "$c2" -eq 1 ] && [ "$c3" -eq 0 ]; then
  ok "K kit-doctor: 一致=0 / 漂移=1 / 还原=0"
else bad "K kit-doctor 漂移检测 (c1=$c1 c2=$c2 c3=$c3)" ""; fi

# ---- O 只传一个失败测试文件：F2 必须真跑并判红（以前的静默跳测 = 假绿灯） ----
mkdir -p "$W/o"
printf 'def test_bad():\n    assert 1 == 2\n' > "$W/o/test_only.py"
run "$W/o/test_only.py"
if has 'GATE: FAIL (F2)' && ! has 'F3'; then
  ok "O 只传失败测试文件 → F2 红（不再静默跳测）"
else bad "O 只传失败测试文件 → F2 红" "$OUT"; fi

# ---- P 只传一个通过测试文件：F2 要真的跑过，不是跳过 ----
mkdir -p "$W/p"
printf 'def test_ok():\n    assert True\n' > "$W/p/test_only.py"
run "$W/p/test_only.py"
if [ "$CODE" -eq 0 ] && has '✓ F2 pytest PASS'; then
  ok "P 只传通过测试文件 → F2 真的跑了"
else bad "P 只传通过测试文件 → F2 真的跑了" "$OUT"; fi

# ---- 汇总 ----
echo "----------------------------------------"
echo "SCENARIOS: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
exit 0
