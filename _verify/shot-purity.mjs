// 纯度三档样式目检截图：锂电电芯卡展开态 + 行业页筛选列表（桌面/移动）+ 公司页 chips
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

// 1) 锂电看板：电芯卡展开（比亚迪「布局·未单列」在列）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2800);
await evaluate(`document.querySelector('.li-card[data-stage="cell"] [data-li-more]')?.click()`);
await sleep(400);
await evaluate(`document.querySelector('.li-card[data-stage="cell"]')?.scrollIntoView({block:'start'})`);
await sleep(400);
await shot('purity-li-cell');

// 2) 行业页：电力设备 × 光伏概念，默认序（三档徽章混排）
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/i/' + encodeURIComponent('电力设备') });
await sleep(2800);
await evaluate(`document.querySelector('#ind-chains [data-chain="光伏概念"]')?.click()`);
await sleep(600);
await evaluate(`window.scrollTo(0, 0)`);
await sleep(300);
await shot('purity-ind-default');

// 3) 行业页：按纯度排序（纯度档 → 提及档 → 未见披露档）
await evaluate(`document.querySelector('#ind-toolbar [data-sort="purity"]')?.click()`);
await sleep(600);
await evaluate(`window.scrollTo(0, 0)`);
await sleep(300);
await shot('purity-ind-sorted');

// 4) 移动端 390：行业页筛选列表
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/i/' + encodeURIComponent('电力设备') });
await sleep(2800);
await evaluate(`document.querySelector('#ind-chains [data-chain="光伏概念"]')?.click()`);
await sleep(600);
await evaluate(`window.scrollTo(0, 0)`);
await sleep(300);
await shot('purity-ind-mobile');

// 5) 公司页：比亚迪环节 chips（提及档徽章）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/c/002594' });
await sleep(3000);
await evaluate(`document.querySelector('.hist-segs')?.scrollIntoView({block:'center'})`);
await sleep(400);
await shot('purity-company-chips');

ws.close();
console.log('完成');
