#!/usr/bin/env node
// 用 CDP 给四个路由各截一张图，存到 _verify/shots/
// 用法：node _verify/shots.mjs [base] [port]

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

await send('Runtime.enable');
await send('Page.enable');
await send('Network.enable');
await send('Network.setCacheDisabled', { cacheDisabled: true });

async function go(hash, wait, w, h) {
  await send('Emulation.setDeviceMetricsOverride', {
    width: w, height: h, deviceScaleFactor: 1, mobile: w < 700,
  });
  const url = `${BASE}?t=${Date.now()}${hash}`;
  const loaded = new Promise((res) => {
    const hh = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.method === 'Page.loadEventFired') { ws.removeEventListener('message', hh); res(); }
    };
    ws.addEventListener('message', hh);
  });
  await send('Page.navigate', { url });
  await loaded;
  await sleep(wait);
}

async function shot(name, fullPage = false) {
  const r = await send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: fullPage,
  });
  writeFileSync(`${OUT}${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('  已保存', `${name}.png`);
}

async function setHash(hash, wait) {
  await send('Runtime.evaluate', { expression: `location.hash='${hash}';1` });
  await sleep(wait);
}

async function scrollTo(y) {
  await send('Runtime.evaluate', { expression: `window.scrollTo(0,${y});1` });
  await sleep(600);
}

console.log('开始截图…');
// 清一遍会话状态，保证是首次访问的样子
await go('', 1600, 1440, 1000);
await send('Runtime.evaluate', { expression: 'try{sessionStorage.clear();localStorage.clear()}catch(e){};1' });

await go('', 1800, 1440, 1000);
await shot('01-home-hero');

await scrollTo(900);
await shot('02-home-grid');

await setHash('#/c/300750', 3200);
await shot('03-company-ningde');

await setHash('#/c/600519', 2600);
await shot('04-company-maotai-terminal');

await setHash('#/c/688836', 3000);
await scrollTo(1450);
await shot('05a-company-inferred-map');

await setHash('#/i/电子', 2800);
await shot('05b-industry-electronics');

await setHash('#/worldmap', 3400);
await shot('06-atlas-pies');

await scrollTo(780);
await shot('07-atlas-pies-scrolled');

// 大环图：单个行业
await setHash('#/m/机械设备', 3600);
await shot('08-ring-machinery');

// 大环图的悬停状态：把一个点选中，看金色高亮和跨环节的连线
await send('Runtime.evaluate', { expression: `(()=>{const cv=document.getElementById('ring-canvas');
  const r=cv.getBoundingClientRect();const S=r.width;const d=cv._dots[60];
  cv.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,clientX:r.left+S/2+d.x,clientY:r.top+S/2+d.y}));
  return d.tk})()` });
await sleep(700);
await send('Runtime.evaluate', { expression: `document.getElementById('tile-tip').hidden=true;1` });
await shot('09-ring-hover');

await setHash('#/vision', 2600);
await shot('10-vision');

await scrollTo(1250);
await shot('10b-vision-theses');

await go('', 1800, 1440, 1000);
const probe = await send('Runtime.evaluate', {
  expression: "(function(){var s=document.getElementById('search');if(!s)return 'no-input';"
    + "s.value='医药';s.dispatchEvent(new Event('input',{bubbles:true}));"
    + "var l=document.getElementById('search-list');"
    + "return 'value='+s.value+' list='+(l.hidden?'hidden':'shown')+' rows='+document.querySelectorAll('.search-row').length})()",
  returnByValue: true,
});
console.log('  搜索下拉状态:', probe.result && probe.result.value);
await sleep(700);
await shot('10-search-dropdown');

await go('', 1800, 390, 844);
await shot('09-mobile-home');

await setHash('#/c/300750', 3000);
await shot('10-mobile-company');

// 收尾把视口恢复成桌面，避免设备模拟残留到下一次测试
await go('', 1200, 1440, 1000);

ws.close();
console.log('完成。输出目录：_verify/shots/');
