// 反向披露 + 披露真边目检截图：
//   300750 sup 反向两列（桌面暗色 + 移动 390）、300750 价值链地图叠边态（收起/展开）、000559 位置图实虚线对照
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
const scrollTo = async (sel, off = 60) => {
  await evaluate(`var el=document.querySelector(${JSON.stringify(sel)}); el && window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - ${off});1`);
  await sleep(400);
};

// 1) 300750 sup 反向两列：桌面暗色
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1150, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/c/300750' });
await sleep(3400);
await scrollTo('.sup-sec');
await shot('rev-sup-desktop');

// 2) 300750 价值链地图叠边态（默认收起）
await scrollTo('.map-wrap', 40);
await shot('rev-vcm-desktop');

// 3) 展开「披露 · 供应商」集群后再拍一张
await evaluate(`(() => {
  const h = document.querySelector('.vcm-col[data-dir="upstream"] .vcm-cluster[data-disclosed="1"] .vcm-cluster-head');
  if (h) h.click();
})()`);
await sleep(700);
await scrollTo('.map-wrap', 40);
await shot('rev-vcm-expanded');

// 4) 300750 sup 反向两列：移动 390
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/c/300750' });
await sleep(3400);
await scrollTo('.sup-sec');
await shot('rev-sup-mobile');

// 5) 000559 位置图：披露实线 vs 行业虚线（桌面暗色）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1150, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/c/000559' });
await sleep(3400);
await scrollTo('#posmap', 120);
await shot('rev-posmap-desktop');

// 6) 000559 位置图：移动 390（单列纵连）
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/c/000559' });
await sleep(3400);
await scrollTo('#posmap', 80);
await shot('rev-posmap-mobile');

ws.close();
console.log('完成');
