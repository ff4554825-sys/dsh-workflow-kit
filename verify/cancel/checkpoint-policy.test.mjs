/**
 * 回归测试：工具分发前的取消判定（工具「失效」的那条路径）。
 *
 * 判据：只有真正的 owner 停止（user / disposed / 未知原因）才拦下工具体；
 * 内部清理（recall）不得吞掉正在运行回合的下一个工具调用。
 *
 * 运行：node verify/cancel/checkpoint-policy.test.mjs
 * 依赖本机 DSH 安装；没有安装时打印 SKIP 并以 0 退出。
 */
import { existsSync } from 'node:fs';

const TARGET = '/opt/dsh/node_modules/@deepseek-ai/dsh-session-checkpoint-policy/lib/index.js';
if (!existsSync(TARGET)) {
  console.log('SKIP: DSH 安装不存在，跳过取消判定回归测试');
  process.exit(0);
}

const mod = await import(TARGET);
const handlers = {};
const logs = [];
const ctx = {
  on: (name, fn) => { handlers[name] = fn; },
  sessions: { flush: async () => {}, get: () => undefined },
  logger: { warn: (...args) => logs.push(args.join(' ')) },
};
mod.apply(ctx);

const handler = handlers['tools/execute'];
if (typeof handler !== 'function') {
  console.error('FAIL: tools/execute 监听未安装');
  process.exit(1);
}

const makeExec = (reason, aborted) => {
  const controller = new AbortController();
  if (aborted) controller.abort(reason);
  return { agent: { session: {} }, signal: controller.signal };
};

let bodyRuns = 0;
const next = async () => {
  bodyRuns += 1;
  return { content: [{ type: 'text', text: 'BODY-RAN' }], isError: false };
};

const cases = [];
const run = async (label, exec) => {
  const before = bodyRuns;
  const out = await handler(exec, next);
  cases.push({ label, bodyRan: bodyRuns > before, text: out?.content?.[0]?.text ?? '' });
};

await run('live signal', makeExec(undefined, false));
await run('user stop', makeExec({ kind: 'user' }, true));
await run('dispose', makeExec({ kind: 'disposed' }, true));
await run('recall housekeeping', makeExec({ kind: 'recall', reason: 'binding-retired' }, true));
await run('unknown reason', makeExec(undefined, true));
await run('bare Error reason', makeExec(new Error('boom'), true));

const expected = [
  ['live signal', true],
  ['user stop', false],
  ['dispose', false],
  ['recall housekeeping', true],
  ['unknown reason', false],
  ['bare Error reason', false],
];

let failed = 0;
for (const [label, want] of expected) {
  const got = cases.find((entry) => entry.label === label);
  const ok = got.bodyRan === want;
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}: bodyRan=${got.bodyRan} want=${want} text=${JSON.stringify(got.text)}`);
}

const causeShown = cases.find((entry) => entry.label === 'user stop').text.includes('[cause=user]');
if (!causeShown) failed += 1;
console.log(`${causeShown ? 'PASS' : 'FAIL'} 取消结果里带原因后缀`);

console.log(failed === 0 ? 'ALL GREEN' : `${failed} FAILED`);
process.exit(failed === 0 ? 0 : 1);
