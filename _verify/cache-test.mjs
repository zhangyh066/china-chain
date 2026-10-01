// 用真实浏览器、并且【不禁用缓存】来验证——因为用户遇到的正是缓存问题。
// 刻意不走 cdp-browser-verify 的脚本（它默认关缓存，会把这个问题掩盖掉）。
//
// 用法: node _verify/cache-test.mjs [base] [port]

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9229);

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) { console.error('找不到 page target'); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let id = 0;
const pending = new Map();
const errors = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
  if (m.method === 'Runtime.exceptionThrown') {
    errors.push((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300));
  return r.result.value;
};
async function navigate(url) {
  const loaded = new Promise((res) => {
    const h = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.method === 'Page.loadEventFired') { ws.removeEventListener('message', h); res(); }
    };
    ws.addEventListener('message', h);
  });
  await send('Page.navigate', { url });
  await loaded;
  await sleep(1400);
}

await send('Runtime.enable');
await send('Page.enable');
// 关键：**不要**调 Network.setCacheDisabled —— 我们要的就是"浏览器按自己的规则缓存"。
// 只打开 Network 域以便读取响应头。
await send('Network.enable');

console.log('第 1 次加载（不带任何时间戳参数，走浏览器正常缓存策略）');
await navigate(BASE);
const first = await evaluate(`JSON.stringify({
  hasSearchWrap: !!document.querySelector('.search-wrap'),
  hasSearchList: !!document.getElementById('search-list'),
  hasGoToCompany: typeof goToCompany,
  // 新版才有这两个全局；旧版是 undefined
  markers: [typeof searchMatches, typeof closeSearchList, typeof setSearchActive]
})`);
console.log('  页面结构:', first);

console.log('第 2 次加载（普通刷新）');
await send('Page.reload', { ignoreCache: false });
await sleep(1800);
const second = await evaluate(`JSON.stringify({
  hasSearchList: !!document.getElementById('search-list'),
  searchFn: typeof searchMatches
})`);
console.log('  页面结构:', second);

console.log('第 3 次加载（硬刷新 Ctrl+Shift+R，ignoreCache=true）');
await send('Page.reload', { ignoreCache: true });
await sleep(1800);

console.log('走一遍真实交互：输入「比亚迪」→ 回车');
const flow = await evaluate(`(async () => {
  const s = document.getElementById('search');
  if (!s) return JSON.stringify({error: '没有搜索框'});
  s.value = '比亚迪';
  s.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 300));
  const rows = document.querySelectorAll('.search-row').length;
  s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await new Promise(r => setTimeout(r, 2600));
  return JSON.stringify({
    rowsInDropdown: rows,
    hash: location.hash,
    company: document.querySelector('.pr-title')?.textContent || null
  });
})()`);
console.log('  结果:', flow);

console.log('');
console.log('页面报错:', errors.length ? errors.join(' | ') : '无');
ws.close();
const ok = flow.includes('002594') && errors.length === 0;
console.log(ok ? '\n通过：缓存开着也能拿到新代码并正常搜索跳转' : '\n未通过');
process.exit(ok ? 0 : 1);
