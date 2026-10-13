// 产业链看板走查：锂 #/li、光伏 #/pv、半导体 #/semi
// 每条链：结构断言（标题/卡数/迷你图数 == 有非空序列阶段数/来源注记）+ EN 翻译
// + 移动端无溢出；价格图断言按 data/price/{key}.json 是否存在条件化。
// 预期全部从数据文件推导（补抓期间个别阶段序列可能为空 → 降级占位；补齐后全出图）。
import { writeFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9223);
const OUT = join(dirname(fileURLToPath(import.meta.url)), 'shots') + '/';
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CHAINS = [
  { hash: '#/li', key: 'lithium' },
  { hash: '#/pv', key: 'pv' },
  { hash: '#/semi', key: 'semi' },
  { hash: '#/robot', key: 'robot' },
  { hash: '#/compute', key: 'compute' },
  { hash: '#/storage', key: 'storage' },
  { hash: '#/pharma', key: 'pharma' },
  { hash: '#/auto', key: 'auto' },
];
const chainData = {};
const priceData = {};
for (const { key } of CHAINS) {
  chainData[key] = JSON.parse(readFileSync(`data/chain/${key}.json`, 'utf-8'));
  const p = `data/price/${key}.json`;
  const d = existsSync(p) ? JSON.parse(readFileSync(p, 'utf-8')) : null;
  priceData[key] = d && Array.isArray(d.points) && d.points.length >= 20 ? d : null;
}
// 传导视图数据：source.type=="price" 的链应渲染传导视图并替代独立价格图
const tmData = JSON.parse(readFileSync('data/transmission.json', 'utf-8'));
const stageUsable = (d, s) => {
  const v = d.trends?.stages?.[s.key];
  return Array.isArray(v) && v.length >= 20;
};

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
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
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 500));
  return r.result.value;
};
const results = [];
const check = (name, cond, detail = '') => {
  results.push([cond, name]);
  console.log(`${cond ? '✓' : '✗'} ${name}${detail ? '  — ' + detail : ''}`);
};
const shot = async (name) => {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(OUT + name, Buffer.from(r.data, 'base64'));
  console.log('  ' + name);
};

await send('Runtime.enable');
await send('Page.enable');

const STRUCT_EXPR = `JSON.stringify({
  title: document.querySelector('.ind-title')?.textContent || null,
  sub: document.querySelector('.ind-head .sec-sub')?.textContent || null,
  cards: document.querySelectorAll('.li-card').length,
  cardTitles: [...document.querySelectorAll('.li-card-title')].map((e) => e.textContent),
  sparks: document.querySelectorAll('.li-spark-svg path').length,
  pending: document.querySelectorAll('.li-pending').length,
  pendingKeys: [...document.querySelectorAll('.li-card.is-pending')].map((c) => c.dataset.stage),
  histTitles: [...document.querySelectorAll('.hist .sec-title')].map((e) => e.textContent),
  histSub: document.querySelector('.hist .sec-sub')?.textContent || null,
  pricePath: document.querySelectorAll('.hist svg path').length >= 2,
  src: document.querySelector('.li-src')?.textContent || null,
  coLinks: document.querySelectorAll('.li-co').length,
  arrows: document.querySelectorAll('.li-arrow').length,
  moreBtns: document.querySelectorAll('[data-li-more]').length,
  transm: !!document.querySelector('.transm'),
  tmRows: document.querySelectorAll('.transm .tm-row').length,
  tmSrc: document.querySelector('.transm .tm-row[data-tm-src] .tm-name')?.textContent || null,
  tmNames: [...document.querySelectorAll('.transm .tm-row:not([data-tm-src]) .tm-name')].map((e) => e.textContent),
  noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth
})`;

for (const { hash, key } of CHAINS) {
  const d = chainData[key];
  const price = priceData[key];
  const expectSpark = d.stages.filter((s) => stageUsable(d, s)).length;
  const expectPending = d.stages.length - expectSpark;
  const expectPendingKeys = d.stages.filter((s) => !stageUsable(d, s)).map((s) => s.key).sort();
  const totalCos = d.stages.reduce((n, s) => n + (s.companies || []).length, 0);
  const expectMore = d.stages.filter((s) => (s.companies || []).length > 4).length;

  // ---- 深色 + 中文结构断言（SPA 只改 hash 不重载，加 query 保证拿到新 app.js）
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + hash });
  await sleep(2600);
  const st = JSON.parse(await evaluate(STRUCT_EXPR));
  check(`[${key}] 标题/sub 来自 JSON meta，${d.stages.length} 阶段卡片全部渲染`,
    st.title === d.title && st.sub === d.sub && st.cards === d.stages.length,
    `${st.title} / ${st.cards} 卡`);
  check(`[${key}] 卡标题与 JSON name 一一对应`,
    st.cardTitles.sort().join('|') === d.stages.map((s) => s.name).sort().join('|'));
  check(`[${key}] 迷你图数 == 有序列阶段数（${expectSpark}），占位卡 == 空序列阶段数（${expectPending}）`,
    st.sparks === expectSpark && st.pending === expectPending
      && st.pendingKeys.sort().join(',') === expectPendingKeys.join(','),
    `sparks=${st.sparks} pending=[${st.pendingKeys.join(',')}]`);
  const tmChain = tmData.chains?.[key];
  const tmOn = !!(tmChain && tmChain.source?.type === 'price' && price);
  const tmStageN = tmOn ? d.stages.filter((s) => tmChain.stages[s.key] && stageUsable(d, s)).length : 0;
  if (tmOn) {
    check(`[${key}] 传导视图替代独立价格图：首行=价格源头「${price.name}」、环节行 ${tmStageN} 条、来源注记保留`,
      st.transm && st.tmSrc === price.name && st.tmRows === tmStageN + 1
        && st.histTitles.length === 0
        && !!st.src && st.src.includes(`${price.name}（广期所）`) && st.src.includes(d.generatedAt),
      `rows=${st.tmRows} hist=${st.histTitles.length} src=${st.src}`);
  } else if (price) {
    check(`[${key}] 价格图（${price.name}）：标题取自 price JSON + 折线/面积 + 来源注记`,
      st.histTitles.includes(price.name) && st.pricePath
        && !!st.histSub && st.histSub.includes('广期所')
        && !!st.src && st.src.includes(`${price.name}（广期所）`) && st.src.includes(d.generatedAt),
      `${st.histTitles.join('|')} / ${st.src}`);
  } else {
    check(`[${key}] 无 price 文件 → 价格区块与传导视图都不出现，来源注记无价格措辞、含更新日期`,
      st.histTitles.length === 0 && !st.transm
        && !!st.src && !st.src.includes('期货') && st.src.includes(d.generatedAt),
      `hist=${st.histTitles.length} transm=${st.transm} / ${st.src}`);
  }
  check(`[${key}] 公司链接 == 各阶段公司总数（${totalCos}），展开按钮 == 公司数>4 的卡数（${expectMore}）`,
    st.coLinks === totalCos && st.moreBtns === expectMore,
    `links=${st.coLinks} more=${st.moreBtns} 箭头 ${st.arrows}`);
  check(`[${key}] 桌面无横向溢出`, st.noHScroll);
  await shot(`${key}-dark.png`);

  // ---- 展开交互（每条链第一张可展开的卡）
  if (expectMore > 0) {
    await evaluate(`document.querySelector('[data-li-more]').click()`);
    await sleep(200);
    const exp = JSON.parse(await evaluate(`JSON.stringify({
      open: document.querySelector('[data-li-more]').getAttribute('aria-expanded'),
      restHidden: document.querySelector('.li-co-rest').hidden,
      btnText: document.querySelector('[data-li-more]').textContent
    })`));
    check(`[${key}]「全部 N 家」展开：rest 显示、按钮变「收起」`,
      exp.open === 'true' && exp.restHidden === false && exp.btnText === '收起', JSON.stringify(exp));
  }

  // ---- 浅色（只截锂，回归浅色配色）
  if (key === 'lithium') {
    await evaluate(`localStorage.setItem('cnchain.settings', JSON.stringify({theme:'light'}));1`);
    await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + hash });
    await sleep(2400);
    await shot('li-light.png');
    await evaluate(`localStorage.removeItem('cnchain.settings');1`);
  }

  // ---- EN：标题/阶段名/价格注记翻译（阶段名来自 JSON 的 nameEn）
  await evaluate(`localStorage.setItem('cnchain.locale','en');1`);
  await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + hash });
  await sleep(2400);
  const en = JSON.parse(await evaluate(STRUCT_EXPR));
  check(`[${key}] EN：标题/sub/阶段名全部走 *En 字段`,
    en.title === (d.titleEn || d.title) && en.sub === (d.subEn || d.sub)
      && en.cardTitles.sort().join('|') === d.stages.map((s) => s.nameEn || s.name).sort().join('|')
      && en.pending === expectPending,
    JSON.stringify({ title: en.title, first: en.cardTitles[0] }));
  if (expectPending > 0) {
    const pendTxt = await evaluate(`document.querySelector('.li-pending')?.textContent || null`);
    check(`[${key}] EN：「数据补齐中」降级文案已翻译`, pendTxt === 'History still being collected', pendTxt);
  }
  if (tmOn) {
    check(`[${key}] EN：传导视图在场（合约名仍中文），环节行名走 nameEn、按链条序`,
      en.transm && en.tmSrc === price.name
        && en.tmNames.join('|') === d.stages
          .filter((s) => tmChain.stages[s.key] && stageUsable(d, s))
          .map((s) => s.nameEn || s.name).join('|'),
      JSON.stringify({ src: en.tmSrc, first: en.tmNames[0] }));
  } else if (price) {
    check(`[${key}] EN：价格图标题为合约名，注记为英文（GFEX）`,
      en.histTitles.includes(price.name) && !!en.histSub && en.histSub.includes('GFEX'),
      en.histSub);
  }
  await shot(`${key}-en.png`);
  await evaluate(`localStorage.removeItem('cnchain.locale');1`);

  // ---- 移动端 390：单列、无箭头、无横向溢出
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + hash });
  await sleep(2400);
  const mob = JSON.parse(await evaluate(`JSON.stringify({
    cards: document.querySelectorAll('.li-card').length,
    noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    arrows: [...document.querySelectorAll('.li-arrow')].filter((a) => getComputedStyle(a).display !== 'none').length
  })`));
  check(`[${key}] 移动端 390：${d.stages.length} 卡、单列无箭头、无横向溢出`,
    mob.cards === d.stages.length && mob.noHScroll && mob.arrows === 0, JSON.stringify(mob));
  await shot(`${key}-mobile.png`);
}

// ---- 概念纯度（照妖镜）三档语义：数据驱动断言
const purity = JSON.parse(readFileSync('data/purity.json', 'utf-8'));
const purityRankOf = (v) => (v.p > 0 ? 2 + v.p : (v.m ? 1 : 0));
const purityTierText = (v) => (v.p > 0 ? (v.p * 100).toFixed(1) + '%' : (v.m ? '布局·未单列' : '未见披露'));

// 1) 锂电看板 cell 阶段卡：p 主序、m 次序；比亚迪 p==0 但文本提及 →「布局·未单列」，不再是 0.0%
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2600);
{
  const cellP = purity.chains?.lithium?.cell || {};
  const expectOrder = Object.entries(cellP)
    .sort((a, b) => purityRankOf(b[1]) - purityRankOf(a[1]))
    .map(([code]) => code);
  const cellCard = JSON.parse(await evaluate(`JSON.stringify((() => {
    const card = document.querySelector('.li-card[data-stage="cell"]');
    if (!card) return null;
    return {
      cos: [...card.querySelectorAll('.li-co')].map((a) => ({
        code: a.getAttribute('href').split('/').pop(),
        pct: a.querySelector('.li-co-pct')?.textContent || null,
        title: a.getAttribute('title') || null,
      })),
      note: document.querySelector('.purity-note')?.textContent || null,
    };
  })())`));
  check('纯度：cell 阶段卡公司按纯度降序（p 主序、m 次序，含「全部 N 家」隐藏的）',
    !!cellCard && cellCard.cos.map((c) => c.code).join(',') === expectOrder.join(','),
    cellCard ? cellCard.cos.map((c) => c.code).join(',') : 'no card');
  const byd = cellCard?.cos.find((c) => c.code === '002594');
  check('纯度：三档标记——p>0 显示百分比，比亚迪「布局·未单列」、全卡无 0.0%，宁德在首屏、比亚迪垫底',
    !!cellCard && cellCard.cos.every((c) => c.pct === purityTierText(cellP[c.code]))
      && byd?.pct === '布局·未单列'
      && !cellCard.cos.some((c) => c.pct === '0.0%')
      && cellCard.cos.slice(0, 4).some((c) => c.code === '300750')
      && cellCard.cos[cellCard.cos.length - 1].code === '002594',
    cellCard ? `first4=[${cellCard.cos.slice(0, 4).map((c) => c.code)}] byd=${byd?.pct}` : '');
  check('纯度：首家公司 tooltip 是主营构成依据（业务名 + 占比拼接）',
    !!cellCard && !!cellCard.cos[0].title && cellCard.cos[0].title.includes('%')
      && (cellP[expectOrder[0]].items || []).every(([n]) => cellCard.cos[0].title.includes(n)),
    cellCard?.cos[0]?.title);
  check('纯度：比亚迪 tooltip 是「提及」口径（公司介绍提及、收入未单列）',
    byd?.title === '公司介绍中提及该业务，收入未单列', byd?.title);
  check('纯度：链条页有口径说明（含报告期与三档释义）',
    !!cellCard && !!cellCard.note && cellCard.note.includes(purity.period)
      && cellCard.note.includes('布局·未单列') && cellCard.note.includes('未见披露'),
    cellCard?.note);
}

// 2) 行业页环节筛选：三档徽章 + 「纯度」排序 chip + 口径说明；取消筛选后全部消失
{
  // 选一个纯度覆盖高的环节：「光伏概念」成员的众数行业
  const graph = JSON.parse(readFileSync('data/graph.json', 'utf-8'));
  const idx = JSON.parse(readFileSync('data/index.json', 'utf-8'));
  const BOARD = '光伏概念';
  const bi = graph.boardList.indexOf(BOARD);
  const indOf = new Map(idx.companies.map((c) => [c.ticker, c.industry]));
  const freq = new Map();
  for (const [tk, bis] of Object.entries(graph.boardIdxOf)) {
    if (!bis.includes(bi)) continue;
    const v = indOf.get(tk);
    if (v) freq.set(v, (freq.get(v) || 0) + 1);
  }
  const ind = [...freq.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const members = (graph.industries[ind] || []).filter((tk) => (graph.boardIdxOf[tk] || []).includes(bi));
  const pOf = (tk) => purity.boards?.[BOARD]?.[tk];
  const mSet = new Set(purity.boardsMentioned?.[BOARD] || []);
  const rankOfTk = (tk) => {
    const p = pOf(tk);
    if (typeof p !== 'number') return null;
    return p > 0 ? 2 + p : (mSet.has(tk) ? 1 : 0);
  };

  if (!ind || !members.length || !purity.boards?.[BOARD]) {
    check('纯度：行业页环节筛选（找不到有覆盖的环节，条件跳过）', true, 'no sample');
  } else {
    await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/i/' + encodeURIComponent(ind) });
    await sleep(2600);
    await evaluate(`document.querySelector('#ind-chains [data-chain="${BOARD}"]')?.click()`);
    await sleep(400);
    const f = JSON.parse(await evaluate(`JSON.stringify({
      sortChips: [...document.querySelectorAll('#ind-toolbar [data-sort]')].map((b) => b.dataset.sort),
      badges: document.querySelectorAll('#ind-list .purity-badge').length,
      tierPct: document.querySelectorAll('#ind-list .purity-badge:not(.is-mentioned):not(.is-none)').length,
      tierMen: document.querySelectorAll('#ind-list .purity-badge.is-mentioned').length,
      tierNone: document.querySelectorAll('#ind-list .purity-badge.is-none').length,
      note: document.querySelector('#ind-list .purity-note')?.textContent || null,
      cards: document.querySelectorAll('#ind-list .card').length,
    })`));
    // 首屏 60 家里 boards 有键的都该有徽章；三档各自计数与 purity.json 一致
    const first60 = members.slice(0, 60).filter((tk) => typeof pOf(tk) === 'number');
    const expPct = first60.filter((tk) => pOf(tk) > 0).length;
    const expMen = first60.filter((tk) => pOf(tk) === 0 && mSet.has(tk)).length;
    const expNone = first60.filter((tk) => pOf(tk) === 0 && !mSet.has(tk)).length;
    check(`纯度：行业页「${ind}」×「${BOARD}」——排序 chip + 三档徽章计数与数据一致 + 口径说明`,
      f.sortChips.includes('purity') && f.sortChips.length === 5
        && f.badges === first60.length
        && f.tierPct === expPct && f.tierMen === expMen && f.tierNone === expNone
        && !!f.note && f.note.includes(purity.period) && f.note.includes('布局·未单列'),
      `chips=${f.sortChips} badges=${f.badges}(${f.tierPct}/${f.tierMen}/${f.tierNone})`
        + ` expect=${first60.length}(${expPct}/${expMen}/${expNone})`);

    await evaluate(`document.querySelector('#ind-toolbar [data-sort="purity"]')?.click()`);
    await sleep(400);
    const s2 = JSON.parse(await evaluate(`JSON.stringify({
      first: document.querySelector('#ind-list .card .card-ticker')?.textContent,
      ranks: [...document.querySelectorAll('#ind-list .purity-badge')].map((b) =>
        b.classList.contains('is-mentioned') ? 1
        : b.classList.contains('is-none') ? 0
        : 2 + parseFloat(b.textContent.replace(/[^0-9.]/g, '')) / 100),
    })`));
    const expectFirst = [...members].sort((a, b) => (rankOfTk(b) ?? -1) - (rankOfTk(a) ?? -1))[0];
    check('纯度：按纯度排序后第一张卡是纯度最高者，徽章按档降序（纯度档 > 提及 > 未披露）',
      s2.first === expectFirst
        && s2.ranks.every((v, i, a) => i === 0 || a[i - 1] >= v),
      `first=${s2.first} expect=${expectFirst} top=${s2.ranks.slice(0, 3).join('/')}`);

    await evaluate(`document.querySelector('#ind-chains [data-chain=""]')?.click()`);
    await sleep(400);
    const f2 = JSON.parse(await evaluate(`JSON.stringify({
      sortChips: [...document.querySelectorAll('#ind-toolbar [data-sort]')].map((b) => b.dataset.sort),
      badges: document.querySelectorAll('#ind-list .purity-badge').length,
    })`));
    check('纯度：取消环节筛选后纯度 chip 与徽章消失（回落 4 个排序 chip）',
      !f2.sortChips.includes('purity') && f2.sortChips.length === 4 && f2.badges === 0,
      JSON.stringify(f2));
  }
}

// ---- 传导视图：标注文案与 transmission.json 逐行一致 + crosshair 悬停联动
const TM_ROWS_EXPR = `JSON.stringify((() => {
  const sec = document.querySelector('.transm');
  if (!sec) return null;
  const rows = [...sec.querySelectorAll('.tm-row')];
  return {
    srcFirst: rows[0]?.hasAttribute('data-tm-src') || false,
    srcName: rows[0]?.querySelector('.tm-name')?.textContent || null,
    rows: rows.slice(1).map((r) => ({
      stage: r.dataset.stage || null,
      name: r.querySelector('.tm-name')?.textContent || '',
      stat: r.querySelector('.tm-stat')?.textContent || '',
      weak: !!r.querySelector('.tm-stat.is-weak'),
    })),
    note: sec.querySelector('.tm-note')?.textContent || null,
  };
})())`;
const tmLagTxt = (st) => (st.lag > 0 ? `领先 ${st.lag} 日` : st.lag < 0 ? `滞后 ${-st.lag} 日` : '同日');
{
  const tmLi = tmData.chains.lithium;
  const liChain = chainData.lithium;
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
  await sleep(2600);
  const tv = JSON.parse(await evaluate(TM_ROWS_EXPR));
  const expectStages = liChain.stages.filter((s) => tmLi.stages[s.key] && stageUsable(liChain, s));
  check('传导：lithium 首行是价格源头「碳酸锂期货主力」，环节行按链条 stages 序',
    !!tv && tv.srcFirst && tv.srcName === '碳酸锂期货主力'
      && tv.rows.map((r) => r.stage).join(',') === expectStages.map((s) => s.key).join(','),
    tv ? `src=${tv.srcName} rows=${tv.rows.map((r) => r.stage).join(',')}` : 'no transm');
  check('传导：每行标注与 transmission.json 一致（r 两位小数 + 同日/领先/滞后）',
    !!tv && tv.rows.every((r) => {
      const st = tmLi.stages[r.stage];
      return st && r.stat === `r=${st.r.toFixed(2)} · ${tmLagTxt(st)}`;
    }) && tv.rows[0]?.stat === 'r=0.63 · 同日',
    tv ? tv.rows.map((r) => r.stat).join(' | ') : '');
  check('传导：口径说明含样本数与弱信号阈值',
    !!tv && !!tv.note && tv.note.includes('n=249') && tv.note.includes('|r|<0.2'), tv?.note);

  // crosshair：悬停任一行 → 所有行参考线同 x 出现、源头行出日期；移出即隐藏
  await evaluate(`(() => {
    const el = document.querySelector('.transm .tm-rows');
    const rc = el.getBoundingClientRect();
    el.dispatchEvent(new PointerEvent('pointermove', { clientX: rc.left + rc.width * 0.6, clientY: rc.top + 40, bubbles: true }));
    return 1;
  })()`);
  const ch = JSON.parse(await evaluate(`JSON.stringify({
    total: document.querySelectorAll('.transm .tm-cursor').length,
    visible: document.querySelectorAll('.transm .tm-cursor:not([hidden])').length,
    lefts: [...document.querySelectorAll('.transm .tm-cursor')].map((c) => c.style.left),
    date: document.querySelector('.transm .tm-hover-date')?.textContent || null,
  })`));
  check('传导：悬停联动——全部行参考线同 x 出现，源头行日期标注出现',
    ch.total > 0 && ch.visible === ch.total && new Set(ch.lefts).size === 1
      && /^\d{4}-\d{2}-\d{2}$/.test(ch.date || ''),
    JSON.stringify(ch));
  await evaluate(`document.querySelector('.transm .tm-rows').dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }))`);
  const offN = await evaluate(`document.querySelectorAll('.transm .tm-cursor:not([hidden])').length`);
  check('传导：移出后参考线全部隐藏', offN === 0, String(offN));
  await shot('tm-li-dark.png');
}

// pv：lag≠0 的标注（领先/滞后）与弱信号灰化
{
  const tmPv = tmData.chains.pv;
  await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/pv' });
  await sleep(2600);
  const pv = JSON.parse(await evaluate(TM_ROWS_EXPR));
  const rowOf = (k) => pv?.rows.find((r) => r.stage === k);
  check('传导：pv 标注 lag——组件「r=0.23 · 领先 12 日」、光伏设备「r=-0.18 · 滞后 6 日」弱信号灰化',
    !!pv && rowOf('module')?.stat === 'r=0.23 · 领先 12 日'
      && rowOf('equipment_pv')?.stat === 'r=-0.18 · 滞后 6 日'
      && rowOf('equipment_pv')?.weak === true,
    JSON.stringify({ module: rowOf('module')?.stat, eq: rowOf('equipment_pv') }));
  await shot('tm-pv-dark.png');
}

// ---- 首页入口：三张卡，标题来自各链 JSON，指向 #/li、#/pv、#/semi
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/' });
await sleep(2600);
const entry = JSON.parse(await evaluate(`JSON.stringify({
  secTitle: document.querySelector('.li-entry-sec .sec-title')?.textContent || null,
  cards: [...document.querySelectorAll('.li-entry')].map((a) => ({
    href: a.getAttribute('href'), title: a.querySelector('.li-entry-title')?.textContent
  }))
})`));
check('首页「产业链看板」区块：全部入口卡，标题来自各链 JSON meta',
  entry.secTitle === '产业链看板' && entry.cards.length === CHAINS.length
    && entry.cards.every((c) => {
      const key = CHAINS.find((x) => x.hash === c.href)?.key;
      return key && c.title === chainData[key].title;
    }),
  JSON.stringify(entry.cards));

console.log('页面报错:', errors.length ? errors.join(' | ') : '无');
const failed = results.filter(([ok]) => !ok).length;
console.log(failed === 0 ? `\n产业链看板走查全部 ${results.length} 项通过` : `\n${failed}/${results.length} 项未通过`);
ws.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
