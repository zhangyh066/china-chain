// 传导视图目检截图：li 桌面暗色（含 crosshair 悬停态）、EN、移动 390
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
const scrollToTm = async () => {
  await evaluate(`var el=document.querySelector('.transm'); el && window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 60);1`);
  await sleep(400);
};

// 1) li 桌面暗色：静态对齐 + 悬停 crosshair 态
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1250, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2800);
await scrollToTm();
await shot('tm-li-align');
await evaluate(`(() => {
  const el = document.querySelector('.transm .tm-rows');
  const rc = el.getBoundingClientRect();
  el.dispatchEvent(new PointerEvent('pointermove', { clientX: rc.left + rc.width * 0.72, clientY: rc.top + 60, bubbles: true }));
  return 1;
})()`);
await sleep(300);
await shot('tm-li-crosshair');
await evaluate(`document.querySelector('.transm .tm-rows').dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }))`);

// 2) EN
await evaluate(`localStorage.setItem('cnchain.locale','en');1`);
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2600);
await scrollToTm();
await shot('tm-li-en');
await evaluate(`localStorage.removeItem('cnchain.locale');1`);

// 3) 移动 390
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2800);
await scrollToTm();
await shot('tm-li-mobile');

// 4) pv 桌面（lag≠0 的链）
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1250, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/pv' });
await sleep(2800);
await scrollToTm();
await shot('tm-pv-align');

ws.close();
console.log('完成');
