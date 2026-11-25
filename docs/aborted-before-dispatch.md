# 根因：所有工具「分发前被取消」（`aborted before dispatch`）

一台 Android 手机上跑 DSH 的会话，出现这样的症状：用户连续发了几条消息，每条都得到「已处理」的回复，但**每一次工具调用都返回**：

```
Error: tool call aborted before dispatch
```

看起来像限流或长回合的调度问题。实际不是。

## 结论

**工具没有「失效」，是被取消闸门挡在分发之前。** `tools/execute` 在落盘之后检查 `exec.signal.aborted`，信号已取消就直接返回规范化的 `aborted before dispatch`，工具体一次都没执行——所以那是假象，不是工具、不是网络、不是限流。

问题因此只剩下一个：**谁取消了这次活动的信号**。

## 一手证据

### 1. 这条报错只在「取消」分支产生

`@deepseek-ai/dsh-session-checkpoint-policy/lib/index.js`：

```js
ctx.on("tools/execute", async (exec, next) => {
  if (exec.agent === void 0 || exec.parent !== void 0) return next();
  await ctx.sessions.flush(exec.agent.session);
  if (exec.signal.aborted) return abortedBeforeDispatchResult();   // ← 就是这里
  return next();
});
```

语义：先落盘，再检查信号。信号已取消 → 直接返回规范化的取消结果，`next()` 不执行。

同一文本也出现在 `@deepseek-ai/dsh-tools/lib/pipeline.js` 与 `lib/types/batch.js`（批次收尾时对剩余调用 `settlement.skip()`），都是「取消」语义，没有第二种来源。

### 2. 会话流时间线（绝对时间，逐事件比对）

| 时刻 | 事件 |
|---|---|
| 18:13:10 – 18:15:27 | 第 1 回合，27 次工具调用全部正常返回 |
| **18:15:27.487** | 模型发起 `edit` 调用，改写的正是 `AGENTS.md`（18:15:27.629 成功） |
| **18:15:27.574** | `AGENTS.md` 被改写（文件 mtime） |
| 18:15:27.716 | `agent/inbox/spliced`，`target=next-step`，注入「Updated instructions from: AGENTS.md」 |
| 18:15:27.724 | 同一次 splice 被撤销：`removedCount=1, outcome=canceled` |
| **18:15:34.442** | 首次 `ABORTED_BEFORE_DISPATCH` |
| 之后 7 个回合 | 每回合第一次工具调用都取消（8 次），`turn/end` 全部 `completed` |

取消率从 **0/27** 跳到 **8/8**。

### 3. 排除项

- **不是回合没闭合**：该会话 289 个事件，`turn/start` 7 条 / `turn/end` 7 条平衡，末尾是 `turn=7 reason=completed`。
- **不是事件数限流**：同机另一个 934 事件、36 回合的会话一切正常；出事会话只有 289 事件。
- **不是工具故障**：35 次 `tool/call` 里 8 次取消，全部在切换点之后；同一批工具在前 27 次调用里都成功。
- **不是网络/凭据**：取消发生在 `flush` 之后、`next()` 之前，模型与网络层都没参与。

## 2026-11-25 复核：splice 不是凶手

初版把根因写成「splice 把当前步骤的 abort 信号点掉、消息撤销后信号不复原」。逐行复核源码后，这条不成立：

1. `ReactLoopInbox.mutate()/splice()/remove()`（`dsh-agent-loop/lib/index.js:200-228`）只写 `session.append("agent/inbox/spliced", …)` 并派发事件，**全程不碰任何 AbortController**；`outcome: "canceled"` 只表示「这条排队消息被丢弃」，与信号无关。
2. 活动级信号只有两个写入点：`AgentLoop.cancel()` 里的 `this.phase.abort.abort(cause)`（`:618`）和 turn 边界处换新控制器（`:904`）。除此之外没有任何代码能把它置为已取消。

所以那条 splice 只是**同时发生的旁证**（改 `AGENTS.md` 同时触发了指令重算与 splice），不是原因。真凶必须从 `cancel()` 的调用方里找。

能调 `cancel()` 的调用方只有几类（`cause.kind`）：`user`（停止按钮 / 客户端取消）、`disposed`（生命周期回收）、`hook`（账号登出）、`parent`（父代理）、`user`（subagent 归档）。其中已经抓到一处**内部清理冒充用户停止**：

```js
// dsh-go companion recall，绑定过期/失效时的 retire 路径
agent.cancel({ kind: 'user' }, { keepInbox: true });   // 原本这样，和用户点停止无法区分
```

记忆绑定过期是定时器驱动的，正好能解释「相隔一分钟、间隔一小时的零散取消」。

**事故当时到底是谁取消的：未验证。** 旧代码不记录 cancel 调用点，事件流里也只有结果、没有来源，事后无法反推。

## 处置方式（已改）

1. **`[cancel-trace]` 日志**：`AgentLoop.cancel()` 取消活动信号前，记一条 `kind` + 调用栈（`agent-loop/lib/index.js`）。下次看后端日志一行就知道是谁。
2. **内部清理不再冒充 owner**：companion recall 的 retire 改用 `kind: 'recall'`；checkpoint 只豁免这一类内部清理，`user` / `disposed` / 未知原因继续 fail-closed（工具体不执行）。
3. **取消结果带原因**：`aborted before dispatch [cause=user]`，模型与日志都能直接读出原因，不用再靠时间线猜。
4. **回归测试**：`verify/cancel/checkpoint-policy.test.mjs`，六种信号状态逐一断言「工具体跑没跑」。
5. 补丁改的是运行中的 Node 进程加载的文件，**生效需要重启后端**；重启前行为不变。
6. 同一轮重试依然无意义（取消是活动级的）：拿到 `aborted before dispatch` 先看 `[cause=…]`，`user` 就停手，`recall` 说明已经被豁免、不该再出现。

## 这个案例的方法论

判断「为什么挂」时，只用三样东西就够：

1. **报错字符串的唯一来源**（源码里 grep 一次，确认它只在取消分支产生）；
2. **绝对时间戳对齐**（文件 mtime / 事件 time / 首次失败时刻，三个数一对就能锁死因果）；
3. **排除法**（把「限流」「回合没闭合」「工具坏了」逐条用数据否掉）。

再加一条：**别把同时发生当成因果。** 初版错在把 splice 与取消的时间贴近当成了因果链，而没有去找信号的唯一写入点——后者一次 grep 就能证伪前者。

缺了第 2 步，就只能停在「疑似限流，未确认」——那是猜测，不是结论。
