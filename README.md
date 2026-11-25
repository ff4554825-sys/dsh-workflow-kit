<!-- qcheck:allow-placeholders -->
# dsh-workflow-kit

把「AI 助手的每轮任务」变成**可校验、可复盘、可外部判定**的流水线：一份 schema 化的任务日志 + 一个确定性校验器 + 一道交付门。

本仓库来自一台 Android 手机上跑 DSH（DeepSeek Harness）的真实工作流，2026-11-25 定稿为 v1.0。工具本身与具体模型、具体 App 无关，任何「模型会自己报告『我完成了』」的场景都能用。

## 它解决什么问题

模型自评不可信：它说「已完成」时，可能只是没验证。这套东西用三条硬约束把它顶回去：

1. **schema**：一条日志 17 个字段，缺一个就算没写完（`log-check` 判）。
2. **外部判定**：`acceptance[].verdict` 由用户点头/摇头或另一个模型复核后填，自评只写 `status`。
3. **交付门**：`gate` 先跑 schema，再跑解析/编译、测试、质量指标，任一项红就不许说「完成」。

## 目录

```
bin/log-check      任务日志 schema 校验（S0–S11）+ 内容嗅探（--is-task-log）
bin/gate           交付门：S → F1 → F2 → F3，串行短路
bin/qcheck         F3 质量指标（占位符 / 空壳 / 编码 / 混行尾），阈值可核对
bin/kit-doctor     仓库副本 vs 安装副本一致性 + 能力探测
bin/proc-stats     流程指标自动统计（轮次/步数/工具调用/被取消次数/gate 通过率）
bin/task-stats     日志快速统计（成功率、外部判定、返工次数）
bin/task-report    周期报告，输出 markdown 到 $DSH_HOME/reports/
scripts/install.sh 安装到 $DSH_HOME/bin 并当场自检一致性
scripts/selftest.sh 全套自测（pytest + gate 行为场景）
verify/logcheck/   校验器判死测试（pytest：11 个坏样例 + 4 条嗅探 + legacy + 枚举正例）
verify/gate/       gate 行为场景测试（14 个场景，真实调用 + 输出断言）
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
sh scripts/install.sh          # 装到 $DSH_HOME/bin（默认 ~/.dsh/bin），装完当场跑 kit-doctor
```

装完最后一行必须是 `KIT: IN SYNC`。默认数据目录 `~/.dsh`，可用 `DSH_HOME` 覆盖。

**周报目录要固定在别处**（比如手机上的 `/sdcard/Download/...`）时，写一行配置，别改脚本——改脚本会让安装副本和仓库副本永久漂移：

```sh
mkdir -p ~/.dsh && echo /sdcard/Download/DSH-Go/任务总结 > ~/.dsh/reports-dir
```

优先级：`$TASK_REPORT_DIR` → `$DSH_HOME/reports-dir` 文件 → `$DSH_HOME/reports/`。

**为什么安装要自检**：`install` 是拷贝不是软链。拷贝会烂——旧 gate 配新 log-check，文档说的行为和你跑的行为就对不上了，而且不报错。`kit-doctor` 逐文件 `cmp` + 能力探测（装的那份认不认 `--is-task-log`），漂移就红。`gate --self-check` 是它的入口。

**工具查找顺序**：`gate` 找 `log-check` / `qcheck` / `kit-doctor` 时先看自己所在目录，再看 `$DSH_HOME/bin`。同目录优先，是为了让仓库副本自洽（改完就地能跑，不必先安装）；跨机部署才依赖安装副本。

## 用法

```sh
# 1) 校验日志（不加参数时读 $DSH_HOME/task-log.jsonl）
log-check --file task-log.jsonl          # SCHEMA: OK / SCHEMA: FAIL（退出码 0/1）
log-check --is-task-log notes.jsonl      # 内容嗅探：0 像 / 1 不像 / 2 文件不存在

# 2) 交付前过门（三关串行，任一关红即停）
gate task-log.jsonl src/foo.py tests/    # GATE: PASS / GATE: FAIL (S|F1|F2|F3)
gate --self-check                        # 仓库副本 vs 安装副本

# 3) 统计与周报
task-stats
task-report 30                           # 最近 30 天

# 4) 流程指标（aborted 数取自会话流，gate 通过率取自 gate 自己的记账）
proc-stats [SESSION_ID]

# 5) 全套自测
sh scripts/selftest.sh                   # SELFTEST: PASS
```

## 三道门各判什么（阈值写死在代码里，不靠感觉）

| 关 | 判据 | 红了就 |
|---|---|---|
| **S** | 输入里**内容像 task-log** 的 JSON 文件 → 跑 `log-check`。形态判据：任意一条里 `seq`+`ts`，且（命中 ≥6 个必备字段 **或** 带 `legacy` 标记） | 停，`GATE: FAIL (S)` |
| **F1** | 可解析/可编译/结构合法：`.md` 代码围栏成对、`.json/.jsonl` 能被 `jq` 解析、`.py` 能 `compile`、`.sh` 过 `bash -n`、`.js/.mjs` 过 `node --check`、`.v` 过 `iverilog`、**无扩展名的脚本按 shebang 判**（`bin/gate` 这类自己也受检）。需要的解释器没装 → 判红（不能判定≠通过） | 停，`GATE: FAIL (F1)` |
| **F2** | 跑测试：`test_*.py` → `pytest`、`*.test.mjs` → `node --test`、`tb*.v` → `iverilog`+`vvp`。入口来自**目录**，也来自**显式点名的测试文件**（只传文件时同样会跑，否则就是假绿灯）。没有测试入口时打印「F2 未跑」（可见，不算红）；有测试入口但解释器没装 → 判红 | 停，`GATE: FAIL (F2)` |
| **F3** | `qcheck` 的确定性指标：占位符 0 处、非空、合法 UTF-8、CRLF/LF 不混用。全文可解析为 JSON 的**数据文件**不扫占位符（`ph=skip-json`） | 停，`GATE: FAIL (F3)` |

三条设计取舍：

- **短路的证据是「后面那关没跑」**，不是「后面那关跑了但没说话」。所以每条失败路径都早退，测试里断言的是「输出里不出现 F2/F3 的痕迹」。
- **缺工具 = 不通过**，不是「跳过」。没有 `log-check` 就没人能判 schema、没有 `node` 就没人能判 `.mjs` 语法、没有 `iverilog` 就没人能判 `.v`——这时说 PASS 等于放行。这与 `unknown 不算 pass` 是同一条原则。唯一的例外是「输入里根本没有这类测试入口」，那会明确打印「F2 未跑」。
- **S 关不看文件名**。日志改名成 `notes.jsonl` 照样被查；普通 `{"a":1}` 的 jsonl 会明确打印跳过原因，不是静默放过。

## F3 的占位符与显式豁免

`qcheck` 扫的占位符：`TODO`、`FIXME`、`待补`、`XXXX`、`— 略`、`PLACEHOLDER`。

**要写这些词做说明**（比如本文件）时，在文件前 5 行内放标记 `qcheck:allow-placeholders`，该文件就跳过占位符扫描。豁免必须写在文件里、`grep` 得到——是显式豁免，不是静默绕过。本文件第一行就是这个标记。

另一个例外不是豁免，是判据本身：**结构化数据文件不扫占位符**。全文能解析成 JSON/JSONL 的文件（日志、配置、报告数据）由 F1 判结构、S 判 schema；在数据里搜散文占位符只会误伤——真实案例是任务日志的 `review` 字段里写了「待补」，被 F3 判红，而这条日志本身 schema 完全合法。现在这类文件直接标 `ph=skip-json`。

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
- `status` **只允许 `done` / `partial` / `blocked`**，别的值由 S11 判红；`blocked` 必须 ≥3 条带失败签名的 `red_attempts`。
- `acceptance` 每条必须给 `verdict`(PASS/FAIL/UNKNOWN) 和**能打开的** `pointer`（`文件:行` / 命令 / URL）。
- `arbiter=none` 必须写 `arbiter_reason`；`degraded=true` 必须回答能否补回严格判据。
- `F3_proc.source` 必须是 `auto`（人工拍脑袋填指标算违规）。
- 历史记录可标 `legacy:true` 豁免其余规则，只受 seq/ts 约束——显式豁免，不是静默放过。

## 自测

```sh
sh scripts/selftest.sh
```

两头都要绿：

- `verify/logcheck`（pytest，**21 passed**）：11 个坏样例分别触发 S1–S11，四条嗅探用例证明 S 关按内容触发（含「全是 legacy 行的老日志」），`status` 三个合法值各一条正例，legacy 两条。
- `verify/gate`（sh，**16 passed**）：好文件 PASS、S 红即停、F1 红短路 F2、F2 红短路 F3、占位符判红、豁免标记生效、改名日志被 S 接管、普通 jsonl 明确跳过、数据文件不扫占位符、legacy 老日志被接管、缺 node 时判红、缺 `log-check` 时 fail-closed、`gate-log` 记账完整、`kit-doctor` 三态（一致/漂移/还原）、单文件测试入口跑与不跑各一条（失败判红 / 通过真跑）。

校验器或门改过不跑这两套，等于没改。

## 为什么会有 `docs/aborted-before-dispatch.md`

调试时遇到「同一会话里所有工具调用都返回 `Error: tool call aborted before dispatch`」，看起来像限流。实际根因是规则文件热更新：编辑 `AGENTS.md` 会插入一条 `next-step` 消息，`splice` 把当前步骤的 abort 信号点掉并闩锁，之后每次工具分发都命中 `exec.signal.aborted`。时间线、源码行号、排除项都写在那份文档里——它也是本仓库「判死动作」方法的一个完整样例。

## License

MIT
