# 根因：所有工具「分发前被取消」（`aborted before dispatch`）

一台 Android 手机上跑 DSH 的会话，出现这样的症状：用户连续发了几条消息，每条都得到「已处理」的回复，但**每一次工具调用都返回**：

```
Error: tool call aborted before dispatch
```

看起来像限流或长回合的调度问题。实际不是。

## 结论

**触发点是规则文件热更新。** 当时 `~/.dsh/AGENTS.md` 被编辑，系统在 0.14 秒后以 `next-step` 为目标注入「Updated instructions」消息；这次 `splice` 把当前步骤的 abort 信号点掉，随后又以 `outcome=canceled` 把消息撤掉。信号没有恢复，`AbortSignal` 保持已取消状态，于是**该 agent 之后每次工具分发都在 checkpoint 处被判为已取消**——工具体从未被调用。

## 一手证据

### 1. 这条报错只在「取消」分支产生

`@deepseek-ai/dsh-session-checkpoint-policy/lib/index.js:68-69`：

```js
ctx.on("tools/execute", async (exec, next) => {
  if (exec.agent === void 0 || exec.parent !== void 0) return next();
  await ctx.sessions.flush(exec.agent.session);
  if (exec.signal.aborted) return abortedBeforeDispatchResult();   // ← 就是这里
  return next();
});
```

语义：先落盘，再检查信号。信号已取消 → 直接返回规范化的取消结果，`next()` 不执行。所以「工具报错」是假象，**工具根本没跑**。

同一文本也出现在 `@deepseek-ai/dsh-tools/lib/pipeline.js:977` 与 `lib/types/batch.js:258`，都是「取消」语义，没有第二种来源。

### 2. 会话流时间线（绝对时间，逐事件比对）

| 时刻 | 事件 |
|---|---|
| 18:13:10 – 18:15:27 | 第 1 回合，27 次工具调用全部正常返回 |
| **18:15:27.574** | `AGENTS.md` 被改写（文件 mtime） |
| 18:15:27.716 | `agent/inbox/spliced`，`target=next-step`，注入「Updated instructions from: AGENTS.md」 |
| 18:15:27.724 | 同一次 splice 被撤销：`removedCount=1, outcome=canceled` |
| **18:15:34.442** | 首次 `ABORTED_BEFORE_DISPATCH` |
| 之后 7 个回合 | 每回合第一次工具调用都取消（8 次），`turn/end` 全部 `completed` |

取消率从 **0/27** 跳到 **8/8**，切换点就是那条 splice。

### 3. 排除项

- **不是回合没闭合**：该会话 289 个事件，`turn/start` 7 条 / `turn/end` 7 条平衡，末尾是 `turn=7 reason=completed`。
- **不是事件数限流**：同机另一个 934 事件、36 回合的会话一切正常；出事会话只有 289 事件。
- **不是工具故障**：35 次 `tool/call` 里 8 次取消，全部在切换点之后；同一批工具在前 27 次调用里都成功。
- **不是网络/凭据**：取消发生在 `flush` 之后、`next()` 之前，模型与网络层都没参与。

## 为什么信号会被闩锁

`agent/inbox/spliced` 的撤销路径（`@deepseek-ai/dsh-agent-loop/lib/index.js:215`）只有一种结果：

```js
const outcome = discardRemoved && actualDeleteCount > 0 ? "canceled" : void 0;
```

`outcome: "canceled"` 记录的是「这条排队消息被丢掉」，它不会回滚 `splice` 过程中为了插入消息而做的**步骤中断**。中断已经发生，信号已经是 aborted，消息虽被移除，信号不会复原。之后该 agent 的每次 `tools/execute` 都读到 `exec.signal.aborted === true`。

## 处置方式

1. **改完规则文件就开新会话。** 同一会话里继续发工具，只会把一次失败放大成 N 次。
2. 同一会话内必须继续时，先发**一个**单工具探针（例如只跑 `date`）。返回取消就立刻停手，改文本交付并写清状态。
3. 不要在同一轮里重试——取消是回合级的，重试得到的是同样的结果。
4. 会话事件数很多（近千）时的取消是另一类问题（通道降级），处置方式同样是停手转文本，但要标记 `degraded` 并在日志里回答能否补回严格判据。

## 这个案例的方法论

判断「为什么挂」时，只用三样东西就够：

1. **报错字符串的唯一来源**（源码里 grep 一次，确认它只在取消分支产生）；
2. **绝对时间戳对齐**（文件 mtime / 事件 time / 首次失败时刻，三个数一对就能锁死因果）；
3. **排除法**（把「限流」「回合没闭合」「工具坏了」逐条用数据否掉）。

缺了第 2 步，就只能停在「疑似限流，未确认」——那是猜测，不是结论。
