#!/usr/bin/env node
// 环图截图：在指定宽度下截 行业环图 与 环节清单
// 用法：node _verify/shot-ring.mjs [base] [port] [width] [height] [行业]
// 例：  node _verify/shot-ring.mjs http://127.0.0.1:8123/ 9261 720 704 机械设备

import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9222);
const W = Number(process.argv[4] || 720);
const H = Number(process.argv[5] || 704);
const IND = process.argv[6] || '机械设备';
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

await send('Runtime.enable');
await send('Page.enable');
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: W < 700 });

async function shot(name, fullPage = false) {
  const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: fullPage });
  writeFileSync(`${OUT}${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('  已保存', `${name}.png`, `(${W}×${H})`);
}

const url = `${BASE}?t=${Date.now()}#/m/${encodeURIComponent(IND)}`;
await send('Page.navigate', { url });
await sleep(3600);
await shot(`ring-${W}-${IND}`);

// 滚到环节清单
await send('Runtime.evaluate', { expression: `document.querySelector('.ring-chains').scrollIntoView({block:'start'});1` });
await sleep(700);
await shot(`ring-${W}-${IND}-list`);
ws.close();
