// 新功能手动自测（CDP）：对比筐加/删/上限提示、CSV 导出内容、价值链地图 PNG、
// 无历史文件时走势图整块不渲染。
// 前置同 slim-test：python serve.py 8123 + 无头 Edge --remote-debugging-port=9223。
import fs from 'node:fs';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9223);

// 找一个 index.json 里有、但 data/h/ 没文件的公司（验证"无历史不渲染"）
const idx = JSON.parse(fs.readFileSync('data/index.json', 'utf-8'));
const noHist = idx.companies.find((c) => !fs.existsSync(`data/h/${c.ticker}.json`));
console.log(`无历史文件样本: ${noHist ? `${noHist.name} ${noHist.ticker}` : '（全部都有，跳过该用例）'}`);

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let id = 0;
const pending = new Map();
const errors = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
  if (m.method === 'Runtime.exceptionThrown') {
    errors.push((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 500));
  return r.result.value;
};
async function waitFor(expr, ms = 20000) {
  const t0 = Date.now();
  for (;;) {
    const v = await evaluate(expr).catch(() => false);
    if (v) return v;
    if (Date.now() - t0 > ms) return false;
    await sleep(250);
  }
}
const results = [];
const check = (name, cond, detail = '') => {
  results.push([cond, name]);
  console.log(`${cond ? '✓' : '✗'} ${name}${detail ? '  — ' + detail : ''}`);
};

await send('Runtime.enable');
await send('Page.enable');

// 从干净状态开始：清对比筐并整页重载（不刷新的话 app 内存里的对比清单是旧的）
// 注意顺序：about:blank 上 localStorage 是禁用的，必须先导航到站点再清、再重载
await send('Page.navigate', { url: BASE });
await waitFor(`document.readyState !== 'loading'`);
await evaluate(`localStorage.removeItem('cnchain.compare')`);
await send('Page.navigate', { url: BASE });
await waitFor(`document.querySelectorAll('.hero-stat b').length === 4`);

console.log('— 指数走势：首页全市场 —');
const mt = JSON.parse(await evaluate(`JSON.stringify({
  sec: !!document.querySelector('.trend'),
  main: !!document.querySelector('.trend-svg path[data-main]'),
  segs: document.querySelectorAll('.trend-svg path[data-seg]').length,
  base: !!document.querySelector('.trend-base'),
  legend: document.querySelectorAll('.trend-legend').length,
  ring: !!document.getElementById('market-ring')
})`));
check('首页全市场走势图（主线+虚线基线，单序列无图例），环图仍在',
  mt.sec && mt.main && mt.segs === 0 && mt.base && mt.legend === 0 && mt.ring, JSON.stringify(mt));

console.log('— 行业一年涨跌榜（首页市场趋势区块内）—');
const rankExpect = Object.keys(JSON.parse(fs.readFileSync('data/trends/index.json', 'utf-8')).industries || {}).length;
const rk = JSON.parse(await evaluate(`JSON.stringify({
  n: document.querySelectorAll('.irank-row').length,
  inTrendSec: !!document.querySelector('.trend .trank'),
  first: document.querySelector('.irank-row .trank-pct')?.textContent || null,
  last: [...document.querySelectorAll('.irank-row .trank-pct')].pop()?.textContent || null,
  href: document.querySelector('.irank-row')?.getAttribute('href') || null
})`));
check(`涨跌榜行数 == index.json industries 键数（${rankExpect}）且在市场趋势区块内`,
  rk.n === rankExpect && rk.inTrendSec, `${rk.n} 行`);
const pctOf = (s) => Number(String(s).replace(/[^\d.-]/g, ''));
check('涨跌榜按涨幅降序（首行 ≥ 末行）', pctOf(rk.first) >= pctOf(rk.last), `${rk.first} ≥ ${rk.last}`);
check('首行 href 指向行业路由', /^#\/i\/.+/.test(rk.href || ''), rk.href);

console.log('— 环节温度榜（首页市场趋势区块内，boards 键）—');
const boardsN = (JSON.parse(fs.readFileSync('data/trends/index.json', 'utf-8')).boards || []).length;
const bt = JSON.parse(await evaluate(`JSON.stringify({
  sec: !!document.querySelector('.btemp'),
  tabs: document.querySelectorAll('.btemp-tabs [data-btemp]').length,
  wRows: document.querySelectorAll('[data-btemp-body="w"] .btemp-row').length,
  mRows: document.querySelectorAll('[data-btemp-body="m"] .btemp-row').length,
  mHidden: document.querySelector('[data-btemp-body="m"]')?.hidden ?? null
})`));
if (boardsN > 0) {
  check(`温度榜：两 tab、各面板 10 行（最热5+最冷5）、近一月默认隐藏（boards=${boardsN}）`,
    bt.sec && bt.tabs === 2 && bt.wRows === 10 && bt.mRows === 10 && bt.mHidden === true, JSON.stringify(bt));
  await evaluate(`document.querySelector('[data-btemp="m"]').click()`);
  await sleep(150);
  const bt2 = JSON.parse(await evaluate(`JSON.stringify({
    wHidden: document.querySelector('[data-btemp-body="w"]').hidden,
    mHidden: document.querySelector('[data-btemp-body="m"]').hidden,
    pressed: document.querySelector('[data-btemp="m"]').getAttribute('aria-pressed')
  })`));
  check('温度榜 tab 切换：hidden/aria-pressed 翻转', bt2.wHidden === true && bt2.mHidden === false && bt2.pressed === 'true', JSON.stringify(bt2));
  const btHref = await evaluate(`document.querySelector('[data-btemp-body="m"] .btemp-row')?.getAttribute('href')`);
  check('温度榜行链接到行业页', /^#\/i\/.+/.test(btHref || ''), btHref);
} else {
  check('boards 键缺失 → 温度榜静默不渲染', bt.sec === false, `btemp=${bt.sec}`);
}

await evaluate(`document.querySelector('.irank-row').click()`);
await waitFor(`location.hash.startsWith('#/i/') && !!document.querySelector('.ind-title')`);
const rkRoute = JSON.parse(await evaluate(`JSON.stringify({hash: location.hash, title: document.querySelector('.ind-title')?.textContent || null})`));
check('点涨跌榜首行进入对应行业页', decodeURIComponent(rkRoute.hash) === decodeURIComponent(rk.href) && !!rkRoute.title,
  `${decodeURIComponent(rkRoute.hash)} → ${rkRoute.title}`);

console.log('— 历史走势图（有文件：002594）—');
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/002594')}`);
await waitFor(`!!document.querySelector('.pr-title')`);
const hist = JSON.parse(await evaluate(`JSON.stringify({
  sec: !!document.querySelector('.hist, #hist-sec .trend'),
  svg: !!document.querySelector('.hist svg path, #hist-sec .trend svg path'),
  chg: document.querySelector('.hist-chg, #hist-sec .sec-head .gain, #hist-sec .sec-head .loss')?.textContent || null,
  lbls: document.querySelectorAll('.hist-lbl, #hist-sec .trend-lbl').length
})`));
check('走势图区块渲染（折线+标注）', hist.sec && hist.svg, JSON.stringify(hist));

console.log('— 公司页走势对照细化（002594 汽车：segments 已补齐 → 三线全量）—');
// 注：汽车行业的 segments 原为空（两线用例），历史日线补齐后 002594 升级为三线+chips
const cmp2 = JSON.parse(await evaluate(`JSON.stringify({
  slot: !!document.getElementById('hist-sec'),
  paths: document.querySelectorAll('#hist-sec .trend-svg path').length,
  legend: document.querySelectorAll('#hist-sec .trend-legend span').length,
  legendPct: document.querySelectorAll('#hist-sec .trend-legend em').length,
  chips: document.querySelectorAll('#hist-sec [data-hseg]').length,
  pressed: document.querySelector('#hist-sec [data-hseg][aria-pressed="true"]')?.dataset.hseg || null,
  base: !!document.querySelector('#hist-sec .trend-base')
})`));
check('002594：公司+行业+环节 3 条路径、图例 3 项带涨跌幅、chips 存在且默认选中、基线在',
  cmp2.slot && cmp2.paths === 3 && cmp2.legend === 3 && cmp2.legendPct === 3 && cmp2.chips >= 1 && !!cmp2.pressed && cmp2.base,
  JSON.stringify(cmp2));

console.log('— 公司页走势对照（行业有序列、环节交集空 → 两线）—');
// 动态找样本：行业 segments 非空，但公司所属环节 ∩ segments 键为空（如 002479 富春环保∈公用事业）
const graph = JSON.parse(fs.readFileSync('data/graph.json', 'utf-8'));
const segCache = new Map();
const segInfoOf = (ind) => {
  if (!segCache.has(ind)) {
    const p = `data/trends/i/${ind}.json`;
    let info = null;
    if (fs.existsSync(p)) {
      const t = JSON.parse(fs.readFileSync(p, 'utf-8'));
      info = { ind: Array.isArray(t.industry) && t.industry.length > 0, segs: Object.keys(t.segments || {}) };
    }
    segCache.set(ind, info);
  }
  return segCache.get(ind);
};
const twoLine = idx.companies.find((c) => {
  if (!fs.existsSync(`data/h/${c.ticker}.json`)) return false;
  const si = segInfoOf(c.industry);
  if (!si || !si.ind || !si.segs.length) return false;
  const mine = (graph.boardIdxOf[c.ticker] || []).map((i) => graph.boardList[i]);
  return !mine.some((b) => si.segs.includes(b));
});
if (twoLine) {
  await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/${twoLine.ticker}'`);
  await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes(${JSON.stringify(twoLine.name)})`);
  await waitFor(`!!document.querySelector('#hist-sec .trend-svg')`);
  const cmp2b = JSON.parse(await evaluate(`JSON.stringify({
    paths: document.querySelectorAll('#hist-sec .trend-svg path').length,
    legend: document.querySelectorAll('#hist-sec .trend-legend span').length,
    chips: document.querySelectorAll('#hist-sec [data-hseg]').length
  })`));
  check(`${twoLine.name}（${twoLine.industry}）：环节交集空 → 公司+行业两线、无 chips`,
    cmp2b.paths === 2 && cmp2b.legend === 2 && cmp2b.chips === 0, JSON.stringify(cmp2b));
} else {
  check('两线样本（行业有序列但环节交集空）', true, '当前数据下无此样本，条件跳过');
}

console.log('— 公司页走势对照（600021 公用事业：三线 + 环节 chips 切换）—');
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/600021')}`);
await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes('上海电力')`);
await waitFor(`!!document.querySelector('#hist-sec .trend-svg')`);
const cmp3 = JSON.parse(await evaluate(`JSON.stringify({
  paths: document.querySelectorAll('#hist-sec .trend-svg path').length,
  legend: document.querySelectorAll('#hist-sec .trend-legend span').length,
  chips: document.querySelectorAll('#hist-sec [data-hseg]').length,
  pressed: document.querySelector('#hist-sec [data-hseg][aria-pressed="true"]')?.dataset.hseg || null
})`));
check('600021：3 条路径、图例 3 项、环节 chips ≥1 且有默认选中',
  cmp3.paths === 3 && cmp3.legend === 3 && cmp3.chips >= 1 && !!cmp3.pressed, JSON.stringify(cmp3));
if (cmp3.chips > 1) {
  await evaluate(`document.querySelectorAll('#hist-sec [data-hseg]')[1].click()`);
  await sleep(200);
  const cmp4 = JSON.parse(await evaluate(`JSON.stringify({
    paths: document.querySelectorAll('#hist-sec .trend-svg path').length,
    pressed: document.querySelector('#hist-sec [data-hseg][aria-pressed="true"]')?.dataset.hseg || null,
    title: (document.querySelector('.pr-title')?.textContent || '')
  })`));
  check('切环节 chip：区块内重绘仍 3 线、选中态跟随、页面其余不动',
    cmp4.paths === 3 && !!cmp4.pressed && cmp4.pressed !== cmp3.pressed && cmp4.title.includes('上海电力'),
    `${cmp3.pressed} → ${cmp4.pressed}`);
}

console.log('— 公司页走势对照（行业 trends 空 → 回退单线）—');
// 动态找一个「有 h 日线、但行业 trends 序列为空」的公司（随管线补齐自动迁移）
const elec = idx.companies.find((c) => {
  if (!fs.existsSync(`data/h/${c.ticker}.json`)) return false;
  const p = `data/trends/i/${c.industry}.json`;
  if (!fs.existsSync(p)) return true;
  const t = JSON.parse(fs.readFileSync(p, 'utf-8'));
  return !Array.isArray(t.industry) || !t.industry.length;
});
if (elec) {
  await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/${elec.ticker}'`);
  await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes(${JSON.stringify(elec.name)})`);
  await sleep(400);
  const cmp5 = JSON.parse(await evaluate(`JSON.stringify({
    single: !!document.querySelector('.hist svg path'),
    cmp: !!document.querySelector('#hist-sec .trend'),
    chips: document.querySelectorAll('[data-hseg]').length
  })`));
  check(`${elec.name}（${elec.industry}）：行业 trends 空 → 回退单线 histHTML、无对照区块`,
    cmp5.single && !cmp5.cmp && cmp5.chips === 0, JSON.stringify(cmp5));
} else {
  // 数据已全补齐：没有可测样本不算失败，条件跳过（记 pass + 说明）
  check('行业 trends 空的公司样本（数据已全补齐，条件跳过）', true, '24 行业 trends 均有序列，该降级路径暂无可测样本');
}

console.log('— 历史走势图（无文件：' + (noHist?.ticker || '无') + '）—');
if (noHist) {
  await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/' + noHist.ticker)}`);
  await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes(${JSON.stringify(noHist.name)})`);
  await sleep(300);   // 历史请求是并行的，等一个来回确认它 404 后仍无区块
  const h2 = JSON.parse(await evaluate(`JSON.stringify({
    sec: !!document.querySelector('.hist'),
    title: document.querySelector('.pr-title')?.textContent || ''
  })`));
  check('无历史文件时整块不渲染且不白屏', h2.sec === false && h2.title.length > 0, h2.title);
}

console.log('— 对比筐：加 / 删 / 上限 —');
const addVia = async (ticker) => {
  await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/${ticker}'`);
  // 等路由真的换到这家公司（hash 跳转不刷新文档，旧页面元素会先留着）
  const ok = await waitFor(`document.querySelector('.pr-actions [data-compare]')?.dataset.compare === '${ticker}'`);
  if (!ok) {
    console.log(`  [debug] addVia(${ticker}) 超时:`, await evaluate(`JSON.stringify({
      hash: location.hash,
      title: document.querySelector('.pr-title')?.textContent || null,
      pill: document.querySelector('.pr-actions [data-compare]')?.dataset.compare || null,
      appLen: document.getElementById('app').innerHTML.length
    })`));
  }
  await evaluate(`document.querySelector('.pr-actions [data-compare]').click()`);
  await sleep(120);
};
for (const tk of ['002594', '300750', '600519', '000063']) await addVia(tk);
let cmpState = JSON.parse(await evaluate(`localStorage.getItem('cnchain.compare')`));
check('连加 4 家', cmpState.length === 4, cmpState.join(','));
// 第 5 家：应被拒 + 提示
await addVia('000333');
cmpState = JSON.parse(await evaluate(`localStorage.getItem('cnchain.compare')`));
const toastOn = await evaluate(`!!document.getElementById('toast')`);
check('第 5 家被拒且出现提示', cmpState.length === 4 && !cmpState.includes('000333') && toastOn);
// 移除一家（再点一次已在筐里的公司按钮）
await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/300750'`);
await waitFor(`document.querySelector('.pr-actions [data-compare]')?.dataset.compare === '300750'`);
await evaluate(`document.querySelector('.pr-actions [data-compare]').click()`);
await sleep(120);
cmpState = JSON.parse(await evaluate(`localStorage.getItem('cnchain.compare')`));
check('再点一次移除', cmpState.length === 3 && !cmpState.includes('300750'), cmpState.join(','));
// 抽屉行内 ✕ 移除
await evaluate(`document.getElementById('cmp-toggle').click()`);
await sleep(150);
await evaluate(`document.querySelector('#cmp-panel [data-compare]')?.click()`);
await sleep(120);
cmpState = JSON.parse(await evaluate(`localStorage.getItem('cnchain.compare')`));
check('抽屉 ✕ 移除', cmpState.length === 2, cmpState.join(','));
const goBtn = JSON.parse(await evaluate(`JSON.stringify({
  text: document.getElementById('cmp-go')?.textContent, disabled: document.getElementById('cmp-go')?.disabled
})`));
check('"开始对比"按钮 2 家可点', goBtn.disabled === false && goBtn.text.includes('2/4'), goBtn.text);

console.log('— CSV 导出 —');
await evaluate(`location.href = ${JSON.stringify(BASE + '#/i/%E7%94%B5%E5%AD%90')}`);
await waitFor(`document.querySelectorAll('#ind-list .card').length > 0`);
// 先切一个排序，验证导出跟随"当前筛选+排序"
await evaluate(`document.querySelector('#ind-toolbar [data-sort="chg"]').click()`);
await waitFor(`document.querySelector('#ind-toolbar [data-sort="chg"]')?.getAttribute('aria-pressed') === 'true'`);
const expected = Number((await evaluate(`document.getElementById('ind-count').textContent`)).replace(/[^\d]/g, ''));
await evaluate(`(() => {
  window.__csv = null; window.__csvName = null;
  const origCreate = URL.createObjectURL.bind(URL);
  URL.createObjectURL = (b) => { window.__csv = b; return origCreate(b); };
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () { window.__csvName = this.download || null; };
})()`);
await evaluate(`document.getElementById('ind-csv').click()`);
await sleep(300);
const csvInfo = JSON.parse(await evaluate(`(async () => {
  const buf = await window.__csv.arrayBuffer();
  const b = new Uint8Array(buf.slice(0, 8));
  const bom = b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF;   // .text() 会吞 BOM，必须看字节
  const txt = new TextDecoder().decode(buf);
  const lines = txt.trimEnd().split('\\r\\n');
  return JSON.stringify({
    name: window.__csvName, bom,
    header: lines[0].replace(/^\\uFEFF/, ''), rows: lines.length - 1,
    firstDataTicker: lines[1].split(',')[0]
  });
})()`));
check('CSV 行数 = 筛选结果全量（不受分页限制）', csvInfo.rows === expected, `${csvInfo.rows} 行 / 应有 ${expected}`);
check('CSV 带 BOM + 中文表头 + 文件名', csvInfo.bom && csvInfo.header.startsWith('代码,名称')
  && /电子-公司列表-\d{4}-\d{2}-\d{2}\.csv/.test(csvInfo.name || ''), csvInfo.name);
check('CSV 首行跟随涨幅排序', csvInfo.firstDataTicker === await evaluate(`document.querySelector('#ind-list .card .card-ticker').textContent`),
  csvInfo.firstDataTicker);

console.log('— 指数走势：行业页降级/补齐（条件式）—');
// 动态查仍缺 segments 的行业；全补齐后（现状）改为断言曾缺数据的行业现在有走势图
const emptyInd = fs.readdirSync('data/trends/i').filter((f) => f.endsWith('.json'))
  .map((f) => f.replace(/\.json$/, ''))
  .find((ind) => {
    const t = JSON.parse(fs.readFileSync(`data/trends/i/${ind}.json`, 'utf-8'));
    return !Array.isArray(t.industry) || !t.industry.length || !Object.keys(t.segments || {}).length;
  });
if (emptyInd) {
  await evaluate(`location.href = ${JSON.stringify(BASE + '#/i/')} + encodeURIComponent(${JSON.stringify(emptyInd)})`);
  await waitFor(`document.querySelector('.ind-title')?.textContent === ${JSON.stringify(emptyInd)}`);
  await sleep(400);
  const et0 = JSON.parse(await evaluate(`JSON.stringify({
    sec: !!document.querySelector('.trend'),
    list: document.querySelectorAll('#ind-list .card').length
  })`));
  check(`环节指数缺失的行业（${emptyInd}）不渲染走势图、列表照常`, et0.sec === false && et0.list > 0, JSON.stringify(et0));
} else {
  // 此时页面就在 #/i/电子（CSV 用例留下的）：电子曾是没有 segments 的行业
  const et = JSON.parse(await evaluate(`JSON.stringify({
    sec: !!document.querySelector('.trend'),
    segs: document.querySelectorAll('.trend-svg path[data-seg]').length,
    list: document.querySelectorAll('#ind-list .card').length
  })`));
  check('24 行业 trends 已补齐：曾缺数据的行业（电子）现在渲染走势图（8 细分线）、列表照常',
    et.sec === true && et.segs === 8 && et.list > 0, JSON.stringify(et));
}

console.log('— 指数走势：行业页（公用事业，8 条细分线 + 芯片联动）—');
await evaluate(`location.href = ${JSON.stringify(BASE + '#/i/' + encodeURIComponent('公用事业'))}`);
await waitFor(`!!document.querySelector('.trend-svg path[data-main]')`);
const it = JSON.parse(await evaluate(`JSON.stringify({
  segs: document.querySelectorAll('.trend-svg path[data-seg]').length,
  legend: document.querySelectorAll('.trend-legend [data-seg]').length,
  base: !!document.querySelector('.trend-base'),
  lbls: document.querySelectorAll('.trend-lbl').length
})`));
check('行业走势图：主线 + 8 条细分线 + 图例 + 基线 + 标注',
  it.segs === 8 && it.legend === 8 && it.base && it.lbls >= 5, JSON.stringify(it));
// 芯片联动：找一个既在图里又在芯片里的环节，点它
const chipName = await evaluate(`(() => {
  const chips = [...document.querySelectorAll('#ind-chains [data-chain]')].map((b) => b.dataset.chain).filter(Boolean);
  const segs = [...document.querySelectorAll('.trend-svg path[data-seg]')].map((p) => p.dataset.seg);
  return segs.find((s) => chips.includes(s)) || null;
})()`);
check('图里细分线与环节芯片有交集（联动前提）', !!chipName, chipName || '无交集');
if (chipName) {
  await evaluate(`[...document.querySelectorAll('#ind-chains [data-chain]')].find((b) => b.dataset.chain === ${JSON.stringify(chipName)}).click()`);
  await sleep(150);
  const hi = JSON.parse(await evaluate(`(() => {
    const paths = [...document.querySelectorAll('.trend-svg path[data-seg]')];
    const sel = paths.find((p) => p.dataset.seg === ${JSON.stringify(chipName)});
    const others = paths.filter((p) => p.dataset.seg !== ${JSON.stringify(chipName)});
    return JSON.stringify({
      w: sel && sel.style.strokeWidth, selOp: sel && sel.style.opacity,
      otherOps: [...new Set(others.map((p) => p.style.opacity))],
      listCount: document.querySelectorAll('#ind-list .card').length
    });
  })()`));
  check('点环节芯片：对应细分线加粗、其余压暗、列表照常过滤',
    hi.w === '2.4' && hi.selOp === '1' && hi.otherOps.length === 1 && hi.otherOps[0] === '0.15' && hi.listCount > 0,
    JSON.stringify(hi).slice(0, 120));
  await evaluate(`document.querySelector('#ind-chains [data-chain=""]').click()`);
  await sleep(150);
  const back = JSON.parse(await evaluate(`(() => {
    const paths = [...document.querySelectorAll('.trend-svg path[data-seg]')];
    return JSON.stringify({ ops: [...new Set(paths.map((p) => p.style.opacity || '1'))] });
  })()`));
  check('回「全部环节」：细分线全部复原', back.ops.length === 1 && back.ops[0] === '1', back.ops.join(','));
}

console.log('— 客户与供应商（年报披露）—');
const supply = JSON.parse(fs.readFileSync('data/supply.json', 'utf-8'));
// 与 i18n fmtPct 同口径：两位小数、去尾零
const pctTxt = (v) => (v * 100).toFixed(2).replace(/\.?0+$/, '') + '%';
// 样本 1：实名明细齐全（000559 万向钱潮，客户第一是比亚迪）
const sFull = '000559';
const sFullRec = supply.companies[sFull];
// 样本 2：有集中度但实名明细为空（降级文案）；样本 3：index 有但 supply 没有（整块不出现）
const sAnon = idx.companies.find((c) => {
  const r = supply.companies[c.ticker];
  return r && r.conc && !(r.customers || []).length && !(r.suppliers || []).length;
});
const sNone = idx.companies.find((c) => !supply.companies[c.ticker]);
console.log(`  样本：明细齐全=${sFull}；明细空=${sAnon ? `${sAnon.name} ${sAnon.ticker}` : '无'}；`
  + `无数据=${sNone ? `${sNone.name} ${sNone.ticker}` : '无'}`);

await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/' + sFull)}`);
await waitFor(`!!document.querySelector('.pr-title')`);
await waitFor(`!!document.querySelector('.sup-sec')`);
const sup1 = JSON.parse(await evaluate(`JSON.stringify((() => {
  const sec = document.querySelector('.sup-sec');
  if (!sec) return null;
  const byd = sec.querySelector('a.sup-name[href="#/c/002594"]');
  const tds = byd ? [...byd.closest('tr').querySelectorAll('td')] : [];
  return {
    concText: sec.querySelector('.sup-conc')?.textContent || '',
    spark: !!sec.querySelector('.sup-conc-trend svg path'),
    cols: sec.querySelectorAll('.sup-grid .sup-col').length,
    yearTags: [...sec.querySelectorAll('.sup-grid .sup-col-title .cf-meta')].map((e) => e.textContent),
    bydName: byd?.textContent || null,
    bydPct: tds[1]?.textContent || null,
    bydAmt: tds[2]?.textContent || null,
    plainNames: sec.querySelectorAll('.sup-name.is-plain').length,
    note: sec.querySelector('.sup-note')?.textContent || null,
  };
})())`));
const conc = sFullRec.conc;
check('客户与供应商：000559 区块——集中度两项+披露年份+近4年趋势 sparkline+两列明细（表头注明年报）',
  !!sup1 && sup1.concText.includes(pctTxt(conc.top5C)) && sup1.concText.includes(pctTxt(conc.top5S))
    && sup1.concText.includes(String(conc.year))
    && sup1.spark && sup1.cols === 2
    && sup1.yearTags.length === 2 && sup1.yearTags.every((y) => y.includes(String(conc.year))),
  JSON.stringify({ conc: sup1?.concText, cols: sup1?.cols, spark: sup1?.spark }));
check('客户与供应商：比亚迪行链到 #/c/002594，占比 13.05% 与金额（亿）渲染',
  !!sup1 && !!sup1.bydName && sup1.bydName.includes('比亚迪')
    && sup1.bydPct === pctTxt(sFullRec.customers[0].ratio)
    && !!sup1.bydAmt && sup1.bydAmt.includes('亿'),
  JSON.stringify({ name: sup1?.bydName, pct: sup1?.bydPct, amt: sup1?.bydAmt }));
check('客户与供应商：code 为空的对手方是纯文本（无链接），口径说明在场',
  !!sup1 && sup1.plainNames >= 3 && !!sup1.note && sup1.note.includes('年报披露'),
  `plain=${sup1?.plainNames} note=${(sup1?.note || '').slice(0, 24)}`);

if (sAnon) {
  await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/${sAnon.ticker}'`);
  await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes(${JSON.stringify(sAnon.name)})`);
  const sup2 = JSON.parse(await evaluate(`JSON.stringify({
    sec: !!document.querySelector('.sup-sec'),
    anon: document.querySelector('.sup-anon')?.textContent || null,
    grid: !!document.querySelector('.sup-grid'),
    concRow: !!document.querySelector('.sup-conc')
  })`));
  check(`客户与供应商：${sAnon.name} 明细为空 → 降级文案 + 集中度行保留、无两列`,
    sup2.sec && sup2.anon === '该公司未披露实名客户/供应商' && !sup2.grid && sup2.concRow,
    JSON.stringify(sup2));
} else {
  check('客户与供应商：明细为空样本（找不到，条件跳过）', true, 'no sample');
}

if (sNone) {
  await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/c/${sNone.ticker}'`);
  await waitFor(`(document.querySelector('.pr-title')?.textContent || '').includes(${JSON.stringify(sNone.name)})`);
  const sup3 = await evaluate(`!!document.querySelector('.sup-sec')`);
  check(`客户与供应商：${sNone.name} 不在 supply.json → 区块整块不出现`, sup3 === false, `sec=${sup3}`);
} else {
  check('客户与供应商：无数据样本（找不到，条件跳过）', true, 'no sample');
}

console.log('— 反向披露（据对方披露）+ 披露真边 —');
// 300750 宁德：零自曝（customers/suppliers 皆空），rev.asSupplierOf 12 条（尚太科技 70.48% 居首）+ asCustomerOf 2 条
const sRev = supply.companies['300750'].rev;
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/300750')}`);
await waitFor(`!!document.querySelector('.sup-rev')`);
const rev1 = JSON.parse(await evaluate(`JSON.stringify((() => {
  const sec = document.querySelector('.sup-sec');
  const rev = sec ? sec.querySelector('.sup-rev') : null;
  if (!rev) return null;
  const first = rev.querySelector('.sup-col a.sup-name');
  const tds = first ? [...first.closest('tr').querySelectorAll('td')] : [];
  return {
    noSelf: sec.querySelector('.sup-no-self')?.textContent || null,
    anon: !!sec.querySelector('.sup-anon'),
    grids: sec.querySelectorAll('.sup-grid').length,
    cols: rev.querySelectorAll('.sup-col').length,
    upMeta: rev.querySelector('.sup-col-title .cf-meta')?.textContent || '',
    dnMeta: rev.querySelectorAll('.sup-col-title .cf-meta')[1]?.textContent || '',
    href: first?.getAttribute('href') || null,
    name: first?.textContent || null,
    pct: tds[1]?.textContent || null,
    amt: tds[2]?.textContent || null,
    yr: tds[3]?.textContent || null,
    revNote: sec.querySelector('.sup-rev-note')?.textContent || '',
  };
})())`));
check('反向披露：宁德零自曝 → 过渡句 + 反向两列（无正向两列、无匿名降级文案）',
  !!rev1 && !!rev1.noSelf && rev1.noSelf.includes('未自曝') && !rev1.anon
    && rev1.grids === 0 && rev1.cols === 2,
  JSON.stringify({ noSelf: rev1?.noSelf, grids: rev1?.grids, cols: rev1?.cols }));
check('反向披露：列头口径「占对方营收比 / 占对方采购比」+ 口径说明含「占对方」',
  !!rev1 && rev1.upMeta.includes('占对方营收') && rev1.dnMeta.includes('占对方采购')
    && rev1.revNote.includes('占对方'),
  JSON.stringify({ up: rev1?.upMeta, dn: rev1?.dnMeta }));
check('反向披露：尚太科技行——链 #/c/001301、占比 70.48%、金额（亿）、2025 披露',
  !!rev1 && rev1.href === '#/c/001301' && rev1.name.includes('尚太科技')
    && rev1.pct === pctTxt(sRev.asSupplierOf[0].ratio)
    && !!rev1.amt && rev1.amt.includes('亿') && rev1.yr.includes(String(sRev.asSupplierOf[0].year)),
  JSON.stringify({ href: rev1?.href, pct: rev1?.pct, amt: rev1?.amt, yr: rev1?.yr }));

// 同一页（300750 手工档案）：价值链地图的披露真边 vs 推断虚线
await waitFor(`document.querySelectorAll('#vcm-links path').length > 0`);
const vcm = JSON.parse(await evaluate(`JSON.stringify((() => {
  const paths = [...document.querySelectorAll('#vcm-links path')].map((p) => ({
    w: +p.getAttribute('stroke-width'), dash: p.getAttribute('stroke-dasharray') || '' }));
  return {
    discClusters: document.querySelectorAll('.vcm-cluster[data-disclosed="1"]').length,
    discUp: !!document.querySelector('.vcm-col[data-dir="upstream"][data-tier="1"] .vcm-cluster[data-disclosed="1"]'),
    discDn: !!document.querySelector('.vcm-col[data-dir="downstream"][data-tier="1"] .vcm-cluster[data-disclosed="1"]'),
    tags: document.querySelectorAll('#vcm-grid .disc-tag').length,
    legend: document.querySelector('.map-wrap .map-legend')?.textContent || '',
    solid: paths.filter((p) => p.w >= 2.2 && !p.dash).length,
    dashed: paths.filter((p) => p.dash).length,
  };
})())`));
check('价值链地图披露层：宁德上游「披露·供应商」+ 下游「披露·客户」集群叠入一级列（披露徽记在场）',
  vcm.discUp && vcm.discDn && vcm.discClusters >= 2 && vcm.tags >= 2,
  JSON.stringify({ up: vcm.discUp, dn: vcm.discDn, n: vcm.discClusters, tags: vcm.tags }));
check('价值链地图披露层：披露边实线加粗 vs 推断边虚线 + 图例（实线=年报披露）',
  vcm.solid >= 2 && vcm.dashed >= 1
    && vcm.legend.includes('年报披露') && vcm.legend.includes('虚线'),
  JSON.stringify({ solid: vcm.solid, dashed: vcm.dashed, legend: vcm.legend }));

// 000019：conc 有但 customers/suppliers/rev 全空 → 反向区块不出现，正向降级文案保留
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/000019')}`);
await waitFor(`!!document.querySelector('.sup-sec')`);
const rev2 = JSON.parse(await evaluate(`JSON.stringify({
  rev: !!document.querySelector('.sup-rev'),
  revHead: !!document.querySelector('.sup-rev-head'),
  anon: !!document.querySelector('.sup-anon'),
})`));
check('反向披露：000019 无任何 rev → 反向区块不出现（自曝匿名降级文案保留）',
  rev2.rev === false && rev2.revHead === false && rev2.anon === true, JSON.stringify(rev2));

// 000559 万向钱潮（非手工）：位置图披露公司卡（自曝 2 客户+1 供应商，据对方 2 客户）vs 行业虚线
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/000559')}`);
await waitFor(`!!document.querySelector('#posmap .pos-disc')`);
await waitFor(`document.querySelectorAll('#pos-links path').length > 0`);
const pos = JSON.parse(await evaluate(`JSON.stringify((() => {
  const laneOf = (el) => el.closest('.pos-lane')?.dataset.dir;
  const discs = [...document.querySelectorAll('#posmap .pos-disc')].map((el) => ({
    lane: laneOf(el), href: el.getAttribute('href') }));
  const paths = [...document.querySelectorAll('#pos-links path')].map((p) => ({
    w: +p.getAttribute('stroke-width'), dash: p.getAttribute('stroke-dasharray') || '' }));
  return {
    upDisc: discs.filter((d) => d.lane === 'up').length,
    dnDisc: discs.filter((d) => d.lane === 'down').length,
    hrefs: discs.map((d) => d.href),
    tags: document.querySelectorAll('#posmap .disc-tag').length,
    legend: document.querySelector('.map-legend')?.textContent || '',
    solid: paths.filter((p) => p.w >= 2.2 && !p.dash).length,
    dashed: paths.filter((p) => p.dash).length,
  };
})())`));
check('位置图披露层：000559 上游 1 家 + 下游 4 家披露公司卡（自曝+据对方，按代码去重）',
  pos.upDisc === 1 && pos.dnDisc === 4 && pos.tags === 5
    && pos.hrefs.includes('#/c/002594') && pos.hrefs.includes('#/c/000708')
    && pos.hrefs.includes('#/c/002406') && pos.hrefs.includes('#/c/000572'),
  JSON.stringify({ up: pos.upDisc, dn: pos.dnDisc, hrefs: pos.hrefs }));
check('位置图披露层：披露卡实线加粗连锚点 vs 行业卡虚线 + 图例（实线=年报披露 · 虚线=行业推断）',
  pos.solid === 5 && pos.dashed >= 1
    && pos.legend.includes('年报披露') && pos.legend.includes('行业推断'),
  JSON.stringify({ solid: pos.solid, dashed: pos.dashed, legend: pos.legend }));

console.log('— 首页研究故事卡（判决书四段）—');
await evaluate(`location.href = ${JSON.stringify(BASE)} + '#/'`);
await waitFor(`!!document.querySelector('.em-card')`);
const story = JSON.parse(await evaluate(`JSON.stringify((() => {
  const card = document.querySelector('.em-card');
  return {
    title: card?.querySelector('.em-title')?.textContent || null,
    labels: [...(card?.querySelectorAll('.em-lbl') || [])].map((e) => e.textContent),
    text: card?.textContent || '',
    strongs: [...(card?.querySelectorAll('.em-sec-body strong') || [])].map((e) => e.textContent),
    takeGone: !document.querySelector('.em-take'),
    oldGone: !card?.querySelector('.em-body, .em-why, .em-foot'),
  };
})())`));
check('研究故事卡：标题逐字「沿供应链，没有晚到的钱」+ 四段标签（假设/验证/判决/意义）',
  story.title === '沿供应链，没有晚到的钱' && story.labels.join('|') === '假设|验证|判决|意义',
  JSON.stringify({ title: story.title, labels: story.labels }));
check('研究故事卡：判决段含 0.27 与 r≈0.00、嵌套 <strong> 正常渲染（未转义）',
  story.text.includes('0.27') && story.text.includes('r≈0.00')
    && story.strongs.length >= 2 && story.strongs.some((s) => s.includes('信息于当日沿链条定价完毕')),
  JSON.stringify({ strongs: story.strongs }));
check('研究故事卡：旧学术口径元素与 .em-take 专框已移除', story.takeGone && story.oldGone, '');

console.log('— 价值链地图导出 PNG（002594 手工档案）—');
await evaluate(`location.href = ${JSON.stringify(BASE + '#/c/002594')}`);
await waitFor(`!!document.getElementById('vcm-export')`);
await evaluate(`(() => {
  window.__png = null; window.__pngName = null;
  const orig = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function (cb, ...rest) {
    return orig.call(this, (b) => { window.__png = b; cb && cb(b); }, ...rest);
  };
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () { window.__pngName = this.download || null; };
})()`);
await evaluate(`document.getElementById('vcm-export').click()`);
await waitFor(`!!window.__png`, 10000);
const pngSize = await evaluate(`window.__png.size`);
const pngName = await evaluate(`window.__pngName`);
// 把字节捞回来存档 + 像素抽样在 node 侧做（直接看 PNG 文件）
const b64 = await evaluate(`(async () => {
  const buf = await window.__png.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(s);
})()`);
fs.mkdirSync('_verify/shots', { recursive: true });
fs.writeFileSync('_verify/shots/vcm-export.png', Buffer.from(b64, 'base64'));
// PNG 非纯色判断：文件尺寸足够大（纯色图压缩后极小，>50KB 即非空白）
check('PNG 非空白且 >50KB', pngSize > 51200 && /价值链地图\.png$/.test(pngName || ''),
  `${(pngSize / 1024).toFixed(0)}KB / ${pngName} → _verify/shots/vcm-export.png`);

// 复位：清掉对比筐，别给后面跑测试的人留状态
await evaluate(`localStorage.removeItem('cnchain.compare')`);

console.log('页面报错:', errors.length ? errors.join(' | ') : '无');
const failed = results.filter(([ok]) => !ok).length;
console.log(failed === 0 ? `\n自测全部 ${results.length} 项通过` : `\n${failed}/${results.length} 项未通过`);
ws.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
