// 披露校验/候选成员 + 首页研究卡目检截图：锂电页（桌面+移动）、首页研究卡（桌面+移动）
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

// 1) 锂电页：链条全景 + 校验小结（桌面暗色）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1150, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(3400);
await scrollTo('.li-validate', 320);
await shot('infer-validate-desktop');

// 2) 锂电页：候选成员区块（桌面暗色）
await scrollTo('.cand-sec', 60);
await shot('infer-cand-desktop');

// 3) 锂电页：候选成员区块（移动 390）
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(3400);
await scrollTo('.cand-sec', 60);
await shot('infer-cand-mobile');

// 4) 首页研究卡（桌面暗色）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1150, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/' });
await sleep(3400);
await scrollTo('.em-card', 200);
await shot('infer-em-desktop');

// 5) 首页研究卡（移动 390）
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/' });
await sleep(3400);
await scrollTo('.em-card', 120);
await shot('infer-em-mobile');

ws.close();
console.log('完成');
