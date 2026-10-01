// 首屏拆包（fundamentals.json → index 轻量字段 + data/f/ 按需全量）后的端到端验证。
// 覆盖：首屏数字渲染、footer 数据截至、公司页十项指标（f/ 按需加载）、
//       行业页/全景图谱/观点页回归、不再请求 fundamentals.json。
//
// 前置：python serve.py 8123 起服务；Edge 带 --remote-debugging-port=9223 启动。
// 用法: node _verify/slim-test.mjs [base] [port]

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9223);

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) { console.error('找不到 page target'); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let id = 0;
const pending = new Map();
const errors = [];
const reqs = { fundamentals: 0, fFiles: new Set(), dataUrls: [], cards404: 0 };
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
  if (m.method === 'Runtime.exceptionThrown') {
    errors.push((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text);
  }
  if (m.method === 'Network.requestWillBeSent') {
    const u = m.params.request.url;
    if (u.includes('/data/')) reqs.dataUrls.push(u.replace(/^https?:\/\/[^/]+/, ''));
    if (u.includes('fundamentals.json')) reqs.fundamentals++;
    const fm = u.match(/data\/f\/(\d+)\.json/);
    if (fm) reqs.fFiles.add(fm[1]);
  }
  if (m.method === 'Network.responseReceived') {
    if (m.params.response.status === 404) reqs.cards404++;
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
  return r.result.value;
};
async function navigate(url) {
  // hash 路由是同一文档内的跳转，不会触发 load 事件——只有跨文档跳转才等 load
  const sameDoc = url.includes('#') &&
    String(await evaluate('location.href')).startsWith(url.split('#')[0]);
  if (!sameDoc) {
    const loaded = new Promise((res) => {
      const h = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.method === 'Page.loadEventFired') { ws.removeEventListener('message', h); res(); }
      };
      ws.addEventListener('message', h);
    });
    await send('Page.navigate', { url });
    await Promise.race([loaded, sleep(8000)]);
  } else {
    await evaluate(`location.href = ${JSON.stringify(url)}`);
  }
}

// 等页面真的渲染出东西，而不是赌固定 sleep——慢网络（线上/CDN 冷启动）下尤其重要
async function waitFor(expr, ms = 15000) {
  const t0 = Date.now();
  for (;;) {
    const v = await evaluate(expr).catch(() => false);
    if (v) return v;
    if (Date.now() - t0 > ms) return false;
    await sleep(300);
  }
}

const results = [];
const check = (name, cond, detail = '') => {
  results.push([cond, name, detail]);
  console.log(`${cond ? '✓' : '✗'} ${name}${detail ? '  — ' + detail : ''}`);
};

await send('Runtime.enable');
await send('Page.enable');
await send('Network.enable');

console.log('— 首页 —');
await navigate(BASE + '#/');
const homeReady = await waitFor(`document.querySelectorAll('.hero-stat b').length === 4
  && (document.getElementById('market-ring')?._segs || []).length > 0`, 20000);
check('首页渲染完成', homeReady === true);
const asOf = await evaluate(`fetch('./data/index.json').then(r => r.json()).then(d => d.generatedAt || '')`);
await sleep(600);   // 等 canvas 画完（同步绘制，留一帧余量）
const home = JSON.parse(await evaluate(`JSON.stringify({
  heroStats: document.querySelectorAll('.hero-stat b').length,
  ring: (() => { const cv = document.getElementById('market-ring'); return cv ? {
    named: (cv._segs || []).filter(s => s.ind).length,
    folded: ((cv._segs || []).find(s => !s.ind)?.members || []).length,
    sumN: (cv._segs || []).reduce((t, s) => t + (s.n || 0), 0),
    drawn: cv.toDataURL().length
  } : null })(),
  footer: document.getElementById('footer-note')?.textContent || '',
  disclaimer: document.body.textContent.includes('上下游连线为模型推断')
})`));
check('四个总览数字', home.heroStats === 4, `实际 ${home.heroStats}`);
check('首页行业大环覆盖 24 个行业（20 个有名 + 小行业折叠）', home.ring && home.ring.named + home.ring.folded === 24,
  JSON.stringify(home.ring && { named: home.ring.named, folded: home.ring.folded }));
check('环覆盖全部公司', home.ring && home.ring.sumN === 4071, `sumN ${home.ring?.sumN}`);
check('环已绘制', home.ring && home.ring.drawn > 1000, `${home.ring?.drawn}B`);
check('footer 显示数据截至', home.footer.includes(`数据截至 ${asOf}`), home.footer.slice(0, 40));
check('口径文案三层标注在', home.disclaimer === true);

console.log('— 搜索跳转：比亚迪 —');
await evaluate(`(() => {
  const s = document.getElementById('search');
  s.value = '比亚迪'; s.dispatchEvent(new Event('input', { bubbles: true }));
  s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
})()`);
const companyReady = await waitFor(`location.hash === '#/c/002594' && !!document.querySelector('.pr-title')`, 25000);
check('公司页渲染完成', companyReady === true);
const search = JSON.parse(await evaluate(`JSON.stringify({
  hash: location.hash,
  title: document.querySelector('.pr-title')?.textContent || null,
  metrics: document.querySelectorAll('.pr-metrics .metric').length,
  realTag: document.body.textContent.includes('真实行情')
})`));
check('跳到公司页', search.hash === '#/c/002594', search.hash);
check('公司名正确', search.title && search.title.includes('比亚迪'), search.title);
check('十项财务指标（f/ 按需加载）', search.metrics === 10, `实际 ${search.metrics}`);
check('标注真实行情', search.realTag === true);

console.log('— 行业页 —');
await navigate(BASE + '#/i/%E7%94%B5%E5%AD%90');
await waitFor(`document.querySelectorAll('.ind-stat b').length === 4`, 20000);
const ind = JSON.parse(await evaluate(`JSON.stringify({
  title: document.querySelector('.ind-title')?.textContent || '',
  stats: document.querySelectorAll('.ind-stat b').length,
  cards: document.querySelectorAll('#ind-list .card').length,
  cardNums: document.querySelectorAll('#ind-list .card-nums').length
})`));
check('行业页统计', ind.stats === 4, `实际 ${ind.stats}`);
check('行业页公司卡片', ind.cards > 0 && ind.cardNums > 0, `${ind.cards} 张卡 / ${ind.cardNums} 张带数字`);

console.log('— 全景图谱 —');
await navigate(BASE + '#/worldmap');
await waitFor(`document.querySelectorAll('canvas').length === 24`, 20000);
await sleep(800);
const wm = JSON.parse(await evaluate(`JSON.stringify({
  canvases: [...document.querySelectorAll('canvas')].map(cv => {
    try { return cv.toDataURL().length; } catch { return 0; }
  })
})`));
check('24 张画布且都有内容', wm.canvases.length === 24 && wm.canvases.every(n => n > 1000),
  `${wm.canvases.length} 张，最小 ${Math.min(...wm.canvases)}B`);

console.log('— 观点页 —');
await navigate(BASE + '#/vision');
await waitFor(`!!document.querySelector('#app h2, #app h1')`, 15000);
const vision = await evaluate(`document.querySelector('#app h2, #app h1')?.textContent?.length || 0`);
check('观点页 markdown 渲染', vision > 0);

console.log('— PWA manifest —');
const manifest = JSON.parse(await evaluate(`(async()=>{const r=await fetch('./manifest.webmanifest'); return r.ok?JSON.stringify(await r.json()):'null'})()`) || null);
check('manifest 可加载且含图标', manifest && manifest.icons && manifest.icons.length >= 3, manifest && manifest.name);
const manifestLink = await evaluate(`!!document.querySelector('link[rel=manifest]') && document.querySelector('meta[name=theme-color]')?.content || ''`);
check('index.html 接入 manifest + theme-color', !!manifestLink, String(manifestLink));

console.log('');
console.log(`网络：fundamentals.json 请求 ${reqs.fundamentals} 次（应为 0）；data/f/ 命中 ${[...reqs.fFiles].join(',') || '无'}`);
console.log('全部 /data/ 请求:', reqs.dataUrls.join(' | ') || '无');
check('不再请求 fundamentals.json', reqs.fundamentals === 0);
check('公司页请求了 f/002594.json', reqs.fFiles.has('002594'));
console.log('页面报错:', errors.length ? errors.join(' | ') : '无');

const failed = results.filter(([ok]) => !ok).length;
console.log(failed === 0 ? `\n全部 ${results.length} 项通过` : `\n${failed}/${results.length} 项未通过`);
ws.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
