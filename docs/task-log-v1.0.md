# 任务日志 schema v1.0

一条日志 = 一行 JSON。追加写入，绝不改写。校验器：`bin/log-check`（S 系列编号即本文档的规则号）。

## 17 个字段

| 字段 | 类型 | 含义 | 空值 |
|---|---|---|---|
| `seq` | int | 严格 +1 无缺口 | 不允许 |
| `corrects` | int/null | 本条目更正的是哪个 seq | `null` |
| `ts` | string | ISO 8601 带时区，单调不减 | 不允许 |
| `task` | string | 一句话任务名 | 不允许 |
| `tier` | string | 档位（`full` / `lite` 等） | `null` |
| `tier_rule` | string | 为什么归这一档，写成 `rule:...` | `null` |
| `degraded` | bool | 是否降级交付（通道失效等） | 不允许 |
| `evidence` | string | 这次靠什么定真假，写到可核对粒度 | 不允许 |
| `kill_action` | string | 一次就能判死的那一步 | 不允许 |
| `arbiter` | string | 谁裁决（`pytest` / `现场` / `none` …） | 不允许 |
| `gate` | object | 三道过滤器结果 + 流程指标 | 不允许 |
| `red_attempts` | array | 失败尝试，每条带 `sig` 失败签名 | `[]` |
| `status` | string | `done` / `partial` / `blocked` | 不允许 |
| `acceptance` | array | 验收行，每条 `criterion` + `verdict` + `pointer` | 不允许空 |
| `review` | string | 回顾段 | `null` |
| `improve` | object | 改进记账（窗口、发现、动作、到期、能否补回） | 不允许 |
| `carryover` | array | 留给下一轮的待办 | `[]` |

`gate` 结构：

```json
{"F1":"pass",
 "F2":{"result":"pass","coverage":"tests/test_x.py::test_y"},
 "F3_task":"m=1",
 "F3_proc":{"rounds":3,"red":0,"source":"auto"}}
```

## 校验规则 S1–S10

| 编号 | 规则 | 触发即红 |
|---|---|---|
| S0 | JSON 可解析、文件非空 | 一行坏 JSON |
| S1 | 17 字段齐全，`seq` 是整数 | 缺字段 |
| S2 | `seq` 连续（上一条 +1） | 跳号/重复 |
| S3 | `ts` 单调不减 | 时间倒退 |
| S4 | `corrects` 指向的 seq 真实存在 | 指向不存在 |
| S5 | `acceptance` 非空，每条有 `verdict` 和 `pointer` | 空验收 / 缺指针 |
| S6 | `gate.F2` 有 `coverage` 凭据 | 只说 pass 没凭据 |
| S7 | `arbiter=none` 必须带 `arbiter_reason` | 无裁决者又不说理由 |
| S8 | `status=blocked` 时 `red_attempts` ≥3 条且都带 `sig` | 挂起太随意 |
| S9 | `gate.F3_proc.source` 必须是 `auto` | 人工填流程指标 |
| S10 | `degraded=true` 时 `improve.restore` 必须回答 | 降级了不说能否补回 |

## legacy 豁免

历史记录加 `"legacy": true` 后只受 S2/S3 约束，其余规则跳过。这是**显式豁免**：校验器不会替历史记录补字段，也不会假装它合规。新条目一律不带 `legacy`。

## 更正链

写错不要改原行。追加一条新记录：

```json
{"seq":27,"corrects":26,"status":"partial", ...}
```

判定按链取**最新有效值**：`26` 的 `done` 被 `27` 的 `partial` 覆盖；S4 保证 `corrects` 不会指向空气。

已完成的条目也可以用同样的方式补证据（`evidence_note` 之类的补充字段不影响 S 系列）。

## 外部判定

`acceptance[].verdict` 不由写日志的人填：

- 用户当场点头/摇头 → 填 PASS/FAIL。
- 另一个模型复核 → 填 PASS/FAIL/UNKNOWN。
- 自己写的 `status` 只是自评。

用户当场指出错误时，必须追加一条 `corrects`：`status` 改成 `partial`，相关 `acceptance.verdict` 改 `FAIL`，即使后来修好了也一样——那条链记录的是「当时错了」。

## 判据诚实

- 交付物真能用且被验证 → `done`
- 交付但没验证，或只对了一部分 → `partial`
- 没做到、做错了、被纠正 → `blocked`（配合 ≥3 条 `red_attempts`）
- 不确定就写 `partial`，不要往 `done` 上凑

## 写入流程

1. 先跑验证动作，拿到退出码/测试报告/文件指针。
2. 写日志行（17 字段）。
3. `log-check`（gate 也会自动前置跑）。
4. 红就补，不红才算写完。
