// 补拍：行业页筛选列表（滚动到 #ind-list）
import { writeFileSync } from 'node:fs';
const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = process.argv[3] || 9223;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pend = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) {
    const p = pend.get(m.id); pend.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const mid = ++id; pend.set(mid, { res, rej });
  ws.send(JSON.stringify({ id: mid, method, params }));
});
await send('Page.enable'); await send('Runtime.enable');
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result?.value;
const shot = async (name) => {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('_verify/shots/' + name + '.png', Buffer.from(r.data, 'base64'));
  console.log('  ✓ ' + name);
};
const scrollToList = async () => {
  await evaluate(`var el=document.getElementById('ind-list'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 60);1`);
  await sleep(400);
};

// 桌面：默认序
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/i/' + encodeURIComponent('电力设备') });
await sleep(2800);
await evaluate(`document.querySelector('#ind-chains [data-chain="光伏概念"]')?.click()`);
await sleep(600);
await scrollToList();
await shot('purity-ind-default');

// 桌面：按纯度排序（顶部高纯度区）
await evaluate(`document.querySelector('#ind-toolbar [data-sort="purity"]')?.click()`);
await sleep(600);
await scrollToList();
await shot('purity-ind-sorted');

// 桌面：按纯度排序滚到 提及/未披露 过渡带
await evaluate(`window.scrollBy(0, 2400);1`);
await sleep(400);
await shot('purity-ind-sorted-tail');

// 移动 390：默认序
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/i/' + encodeURIComponent('电力设备') });
await sleep(2800);
await evaluate(`document.querySelector('#ind-chains [data-chain="光伏概念"]')?.click()`);
await sleep(600);
await scrollToList();
await shot('purity-ind-mobile');

ws.close();
console.log('完成');
