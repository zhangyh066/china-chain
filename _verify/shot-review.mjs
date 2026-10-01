// 审美走查截图：覆盖全部 6 个页面
// 用法：node _verify/shot-review.mjs [base] [port] [width] [height]
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9270);
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
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });

const shot = async (name) => {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(OUT + name + '.png', Buffer.from(r.data, 'base64'));
  console.log('  ✓ ' + name);
};
const go = async (hash, wait = 3000) => {
  await send('Page.navigate', { url: BASE + '?t=' + Date.now() + hash });
  await sleep(wait);
};

// ① 首页顶部（hero + 行业卡开头）
await go('#/', 3200);
await shot('01-home-hero');
// ② 首页大环（滚到图谱）
await send('Runtime.evaluate', { expression: "var el=document.getElementById('market-ring'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 60);1" });
await sleep(900);
await shot('02-home-ring');
// ③ 行业页
await send('Runtime.evaluate', { expression: "location.hash='#/i/'+encodeURIComponent('电子');1" });
await sleep(3000);
await shot('03-industry');
// ④ 公司页
await send('Runtime.evaluate', { expression: "location.hash='#/c/600519';1" });
await sleep(3200);
await shot('04-company');
// ⑤ 全景图谱
await send('Runtime.evaluate', { expression: "location.hash='#/worldmap';1" });
await sleep(3200);
await shot('05-atlas');
// ⑥ 行业环图
await send('Runtime.evaluate', { expression: "location.hash='#/m/'+encodeURIComponent('机械设备');1" });
await sleep(3400);
await shot('06-ring-machinery');
// ⑦ 观点页
await send('Runtime.evaluate', { expression: "location.hash='#/vision';1" });
await sleep(2600);
await shot('07-vision');

ws.close();
console.log('全部截图完成 → ' + OUT);
