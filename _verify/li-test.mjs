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
  if (price) {
    check(`[${key}] 价格图（${price.name}）：标题取自 price JSON + 折线/面积 + 来源注记`,
      st.histTitles.includes(price.name) && st.pricePath
        && !!st.histSub && st.histSub.includes('广期所')
        && !!st.src && st.src.includes(`${price.name}（广期所）`) && st.src.includes(d.generatedAt),
      `${st.histTitles.join('|')} / ${st.src}`);
  } else {
    check(`[${key}] 无 price 文件 → 价格区块不出现，来源注记无价格措辞、含更新日期`,
      st.histTitles.length === 0
        && !!st.src && !st.src.includes('期货') && st.src.includes(d.generatedAt),
      `hist=${st.histTitles.length} / ${st.src}`);
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
  if (price) {
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

// ---- 概念纯度（照妖镜）：数据驱动断言
const purity = JSON.parse(readFileSync('data/purity.json', 'utf-8'));

// 1) 锂电看板 cell 阶段卡：公司按纯度降序（首屏前 4 同理），0 垫底带徽章，tooltip 有依据
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2600);
{
  const cellP = purity.chains?.lithium?.cell || {};
  const expectOrder = Object.entries(cellP).sort((a, b) => b[1].p - a[1].p).map(([code]) => code);
  const cellCard = JSON.parse(await evaluate(`JSON.stringify((() => {
    const card = document.querySelector('.li-card[data-stage="cell"]');
    if (!card) return null;
    return {
      cos: [...card.querySelectorAll('.li-co')].map((a) => a.getAttribute('href').split('/').pop()),
      pcts: [...card.querySelectorAll('.li-co .li-co-pct')].map((e) => e.textContent),
      firstTitle: card.querySelector('.li-co')?.getAttribute('title') || null,
      note: document.querySelector('.purity-note')?.textContent || null,
    };
  })())`));
  check('纯度：cell 阶段卡公司按纯度降序（含「全部 N 家」隐藏的）',
    !!cellCard && cellCard.cos.join(',') === expectOrder.join(','),
    cellCard ? cellCard.cos.join(',') : 'no card');
  const expectPcts = expectOrder.map((c) => (cellP[c].p * 100).toFixed(1) + '%');
  check('纯度：每家公司带百分比（0 也显示），宁德时代 88.6% 在首屏、比亚迪 0.0% 垫底',
    !!cellCard && cellCard.pcts.join(',') === expectPcts.join(',')
      && cellCard.cos.slice(0, 4).includes('300750')
      && cellCard.pcts[cellCard.pcts.length - 1] === '0.0%'
      && cellCard.cos[cellCard.cos.length - 1] === '002594',
    cellCard ? `first4=[${cellCard.cos.slice(0, 4)}] last=${cellCard.pcts[cellCard.pcts.length - 1]}` : '');
  check('纯度：首家公司 tooltip 是主营构成依据（业务名 + 占比拼接）',
    !!cellCard && !!cellCard.firstTitle && cellCard.firstTitle.includes('%')
      && (cellP[expectOrder[0]].items || []).every(([n]) => cellCard.firstTitle.includes(n)),
    cellCard?.firstTitle);
  check('纯度：链条页有口径说明（含报告期）',
    !!cellCard && !!cellCard.note && cellCard.note.includes(purity.period), cellCard?.note);
}

// 2) 行业页环节筛选：徽章 + 「纯度」排序 chip + 口径说明；取消筛选后全部消失
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
      note: document.querySelector('#ind-list .purity-note')?.textContent || null,
      cards: document.querySelectorAll('#ind-list .card').length,
    })`));
    // 首屏 60 家里 boards 有键的都该有徽章（0 也是有效值）
    const expectBadges = members.slice(0, 60).filter((tk) => typeof pOf(tk) === 'number').length;
    check(`纯度：行业页「${ind}」×「${BOARD}」——出现纯度排序 chip + 徽章数匹配 + 口径说明`,
      f.sortChips.includes('purity') && f.sortChips.length === 5
        && f.badges === expectBadges
        && !!f.note && f.note.includes(purity.period),
      `chips=${f.sortChips} badges=${f.badges}/${expectBadges} cards=${f.cards}`);

    await evaluate(`document.querySelector('#ind-toolbar [data-sort="purity"]')?.click()`);
    await sleep(400);
    const s2 = JSON.parse(await evaluate(`JSON.stringify({
      first: document.querySelector('#ind-list .card .card-ticker')?.textContent,
      pcts: [...document.querySelectorAll('#ind-list .purity-badge')]
        .map((b) => parseFloat(b.textContent.replace(/[^0-9.]/g, ''))),
    })`));
    const expectFirst = [...members].sort((a, b) => {
      const va = pOf(a), vb = pOf(b);
      return (vb ?? -1) - (va ?? -1);
    })[0];
    check('纯度：按纯度排序后第一张卡是纯度最高者，徽章序列降序',
      s2.first === expectFirst
        && s2.pcts.every((v, i, a) => i === 0 || a[i - 1] >= v),
      `first=${s2.first} expect=${expectFirst} top=${s2.pcts.slice(0, 3).join('/')}`);

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
