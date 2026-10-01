// 补截图：普通公司（贵州茅台）的全量档案
import { writeFileSync } from 'node:fs';
const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = 9270;
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
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });

await send('Page.navigate', { url: BASE + '?t=' + Date.now() + '#/c/600519' });
await sleep(5500);
await send('Runtime.evaluate', { expression: "var el=document.querySelector('.chain-sec'); window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - 90));1" });
await sleep(700);
const r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync('_verify/shots/10-company-profile-regular.png', Buffer.from(r.data, 'base64'));
console.log('  ✓ 10-company-profile-regular');
ws.close();
