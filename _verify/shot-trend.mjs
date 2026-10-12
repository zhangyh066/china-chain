// 截走势图：首页全市场（深/浅）+ 行业页行业与环节走势（深/浅，浅色带芯片选中态）
// 用法：node _verify/shot-trend.mjs [base] [port]
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9223);
const OUT = join(dirname(fileURLToPath(import.meta.url)), 'shots') + '/';
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const mid = ++id; pending.set(mid, { res, rej });
  ws.send(JSON.stringify({ id: mid, method, params }));
});
const evaluate = (expression) => send('Runtime.evaluate', { expression, awaitPromise: true });

await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });

const scrollToTrend = `
  var el=document.querySelector('.trend');
  if(el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 70);1`;

// —— 深色：首页 ——
await send('Page.navigate', { url: BASE + '?t=' + Date.now() });
await sleep(2600);
await evaluate(scrollToTrend);
await sleep(500);
let r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'trend-home-dark.png', Buffer.from(r.data, 'base64'));
console.log('  trend-home-dark.png');

// —— 深色：行业页（公用事业）——
await evaluate(`location.hash='#/i/'+encodeURIComponent('公用事业');1`);
await sleep(2200);
await evaluate(scrollToTrend);
await sleep(500);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'trend-industry-dark.png', Buffer.from(r.data, 'base64'));
console.log('  trend-industry-dark.png');

// —— 浅色：行业页 + 芯片选中「绿色电力」联动态 ——
await evaluate(`localStorage.setItem('cnchain.settings', JSON.stringify({theme:'light'}));1`);
await send('Page.navigate', { url: BASE + '?t=' + Date.now() + '#/i/' + encodeURIComponent('公用事业') });
await sleep(2600);
await evaluate(`var b=[...document.querySelectorAll('#ind-chains [data-chain]')].find(x=>x.dataset.chain==='绿色电力'); if(b) b.click();1`);
await evaluate(scrollToTrend);
await sleep(500);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'trend-industry-light-sel.png', Buffer.from(r.data, 'base64'));
console.log('  trend-industry-light-sel.png');

// —— 浅色：首页 ——
await evaluate(`location.hash='#/';1`);
await sleep(2200);
await evaluate(scrollToTrend);
await sleep(500);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'trend-home-light.png', Buffer.from(r.data, 'base64'));
console.log('  trend-home-light.png');

// 复位主题，别给后面跑测试的人留状态
await evaluate(`localStorage.removeItem('cnchain.settings');1`);
ws.close();
