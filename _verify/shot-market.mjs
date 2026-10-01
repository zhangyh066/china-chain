// 截首页大环：node _verify/shot-market.mjs [base] [port] [width] [height]
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9222);
const W = Number(process.argv[4] || 1440);
const H = Number(process.argv[5] || 1100);
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

await send('Runtime.enable');
await send('Page.enable');
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: W < 700 });
await send('Page.navigate', { url: BASE + '?t=' + Date.now() });
await sleep(1200);
await send('Runtime.evaluate', { expression: 'try{sessionStorage.clear();localStorage.clear()}catch(e){}1' });
await send('Page.navigate', { url: BASE + '?t=' + Date.now() + '#/' });
await sleep(3000);

let r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'market-home-' + W + '.png', Buffer.from(r.data, 'base64'));
console.log('  已保存 market-home-' + W + '.png');

await send('Runtime.evaluate', { expression: "var el=document.getElementById('market-ring'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 80);1" });
await sleep(1000);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'market-ring-' + W + '.png', Buffer.from(r.data, 'base64'));
console.log('  已保存 market-ring-' + W + '.png');

await send('Page.navigate', { url: BASE + '#/worldmap' });
await sleep(3200);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'market-atlas-' + W + '.png', Buffer.from(r.data, 'base64'));
console.log('  已保存 market-atlas-' + W + '.png');

// 行业页的环节环图：会点——环节最多（124 个）的那个行业，最能看出"名字没转字"
await send('Runtime.evaluate', { expression: "location.hash='#/m/'+encodeURIComponent('机械设备');1" });
await sleep(3400);
await send('Runtime.evaluate', { expression: "var el=document.getElementById('ring-canvas'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 70);1" });
await sleep(900);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'market-ring-page-' + W + '.png', Buffer.from(r.data, 'base64'));
console.log('  已保存 market-ring-page-' + W + '.png');
ws.close();
