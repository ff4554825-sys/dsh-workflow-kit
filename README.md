# dsh-workflow-kit

把「AI 助手的每轮任务」变成**可校验、可复盘、可外部判定**的流水线：一份 schema 化的任务日志 + 一个确定性校验器 + 一道交付门。

本仓库来自一台 Android 手机上跑 DSH（DeepSeek Harness）的真实工作流，2026-11-25 定稿为 v1.0。工具本身与具体模型、具体 App 无关，任何「模型会自己报告『我完成了』」的场景都能用。

## 它解决什么问题

模型自评不可信：它说「已完成」时，可能只是没验证。这套东西用三条硬约束把它顶回去：

1. **schema**：一条日志 17 个字段，缺一个就算没写完（`log-check` 判）。
2. **外部判定**：`acceptance[].verdict` 由用户点头/摇头或另一个模型复核后填，自评只写 `status`。
3. **交付门**：`gate` 先跑 schema，再跑解析/编译/测试，任一项红就不许说「完成」。

## 目录

```
bin/log-check      任务日志 schema 校验（S1–S10），退出码即判据
bin/gate           交付门：S（schema）→ F1（解析/编译）→ F2（测试）→ F3（质量指标）
bin/proc-stats     流程指标自动统计（轮次/步数/工具调用/被取消次数/gate 通过率）
bin/task-stats     日志快速统计（成功率、外部判定、返工次数）
bin/task-report    周期报告，输出 markdown 到 $DSH_HOME/reports/
verify/logcheck/   校验器自测（pytest，10 个用例：7 个坏样例 + 1 个好样例）
verify/cancel/     工具「分发前被取消」的取消判定回归测试（node）
docs/              schema 规范与「工具分发前被取消」的根因分析
examples/          一条脱敏示例日志
```

## 远程仓库

- 浏览：<https://github.com/ff4554825-sys/dsh-workflow-kit>
- SSH：`git@github.com:ff4554825-sys/dsh-workflow-kit.git`（走 `ssh.github.com:443`）
- 默认分支 `main`。建仓用手机上的狐猴浏览器，之后的改/删/推一律走这把 ed25519 key。

## 安装

```sh
git clone git@github.com:ff4554825-sys/dsh-workflow-kit.git
cd dsh-workflow-kit
install -m 755 bin/* ~/.dsh/bin/
mkdir -p ~/.dsh/verify/logcheck && cp -r verify/logcheck/* ~/.dsh/verify/logcheck/
```

默认数据目录是 `~/.dsh`，可用 `DSH_HOME` 覆盖；周报输出目录用 `TASK_REPORT_DIR` 覆盖。

## 用法

```sh
# 1) 校验日志（不加参数时读 $DSH_HOME/task-log.jsonl）
log-check --file task-log.jsonl          # SCHEMA: OK / SCHEMA: FAIL（退出码 0/1）

# 2) 交付前过门（task-log 文件会自动触发 S 系列前置校验）
gate task-log.jsonl src/foo.py tests/    # GATE: PASS / GATE: FAIL (S) / GATE: FAIL

# 3) 统计与周报
task-stats
task-report 30                           # 最近 30 天

# 4) 流程指标（aborted 数取自会话流，gate 通过率取自 gate 自己的记账）
proc-stats [SESSION_ID]
```

## 日志 schema（v1.0 摘要）

一条日志一行 JSON，17 个字段，值为空写 `null`：

```json
{"seq":26,"corrects":null,"ts":"2026-11-25T19:34:10+08:00","task":"一句话任务名",
 "tier":"full","tier_rule":"rule:T3(有外部裁决者)","degraded":false,
 "evidence":"这次靠什么定真假","kill_action":"一次就能判死的那一步","arbiter":"pytest",
 "gate":{"F1":"pass","F2":{"result":"pass","coverage":"tests/x.py::test_y"},
         "F3_task":"m=1","F3_proc":{"rounds":3,"red":0,"source":"auto"}},
 "red_attempts":[],"status":"done",
 "acceptance":[{"criterion":"判死条件","verdict":"PASS","pointer":"tests/x.py::test_y"}],
 "review":"回顾段",
 "improve":{"window":10,"finding":"no-new-pattern","action":null,"due":null,"restore":null},
 "carryover":[]}
```

规则要点（完整版见 `docs/task-log-v1.0.md`）：

- `seq` 严格 +1 无缺口，`ts` 单调不减，**只追加不改写**；写错就追加一条带 `corrects` 的更正记录指向原 seq。
- `status` 只允许 `done` / `partial` / `blocked`；`blocked` 必须 ≥3 条带失败签名的 `red_attempts`。
- `acceptance` 每条必须给 `verdict`(PASS/FAIL/UNKNOWN) 和**能打开的** `pointer`（`文件:行` / 命令 / URL）。
- `arbiter=none` 必须写 `arbiter_reason`；`degraded=true` 必须回答能否补回严格判据。
- `F3_proc.source` 必须是 `auto`（人工拍脑袋填指标算违规）。
- 历史记录可标 `legacy:true` 豁免其余规则，只受 seq/ts 约束——显式豁免，不是静默放过。

## 自测

```sh
python3 -m pytest verify/logcheck -q     # 10 passed
```

7 个坏样例分别触发 S1/S4/S5/S6/S7/S8/S9/S10，1 个好样例必须全绿。校验器改了不跑这个，等于没改。

## 为什么会有 `docs/aborted-before-dispatch.md`

调试时遇到「同一会话里所有工具调用都返回 `Error: tool call aborted before dispatch`」，看起来像限流。实际根因是规则文件热更新：编辑 `AGENTS.md` 会插入一条 `next-step` 消息，`splice` 把当前步骤的 abort 信号点掉并闩锁，之后每次工具分发都命中 `exec.signal.aborted`。时间线、源码行号、排除项都写在那份文档里——它也是本仓库「判死动作」方法的一个完整样例。

## License

MIT
