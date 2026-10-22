#!/usr/bin/env node
// 首页研究故事卡（.em-card）截图：zh/en × 桌面/移动 四张，存 _verify/shots/
// 用法：node _verify/shot-em.mjs [base] [port]

import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9222);
const OUT = join(dirname(fileURLToPath(import.meta.url)), 'shots') + '/';
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) { console.error('找不到可用的 page target'); process.exit(1); }

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
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result ? r.result.value : undefined;
};

await send('Runtime.enable');
await send('Page.enable');
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });

async function shot(name) {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(`${OUT}${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('  已保存', `${name}.png`);
}

async function capture(locale, mobile) {
  const w = mobile ? 390 : 1440;
  const h = mobile ? 844 : 1100;
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: mobile ? 2 : 1, mobile });
  await evaluate(locale === 'en'
    ? `localStorage.setItem('cnchain.locale','en');1`
    : `localStorage.removeItem('cnchain.locale');1`);
  const loaded = new Promise((res) => {
    const hh = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.method === 'Page.loadEventFired') { ws.removeEventListener('message', hh); res(); }
    };
    ws.addEventListener('message', hh);
  });
  await send('Page.navigate', { url: `${BASE}?t=${Date.now()}#/` });
  await loaded;
  for (let i = 0; i < 60; i++) {
    if (await evaluate(`!!document.querySelector('.em-card')`)) break;
    await sleep(300);
  }
  await evaluate(`document.querySelector('.em-card').scrollIntoView({block:'center'});1`);
  await sleep(900);
  await shot(`em-${locale}-${mobile ? 'mobile' : 'desktop'}`);
}

await capture('zh', false);
await capture('en', false);
await capture('zh', true);
await capture('en', true);

// 收尾恢复桌面视口与默认语言，避免残留到下一次测试
await evaluate(`localStorage.removeItem('cnchain.locale');1`);
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });

ws.close();
console.log('完成。输出目录：_verify/shots/');
