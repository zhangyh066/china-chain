// 锂电看板走查：结构断言 + 截图（深色/浅色/EN/移动端）+ 展开交互
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8123/';
const PORT = Number(process.argv[3] || 9223);
const OUT = join(dirname(fileURLToPath(import.meta.url)), 'shots') + '/';
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 预期从数据文件推导（补抓期间个别阶段序列可能为空 → 降级占位；补齐后全出图）
const liData = JSON.parse(readFileSync('data/chain/lithium.json', 'utf-8'));
const stageUsable = (s) => {
  const v = liData.trends?.stages?.[s.key];
  return Array.isArray(v) && v.length >= 20;
};
const expectSpark = liData.stages.filter(stageUsable).length;
const expectPending = liData.stages.length - expectSpark;

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

await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });

// 深色 + 结构断言（SPA 只改 hash 不重载，加 query 保证拿到新 app.js）
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2600);
const st = JSON.parse(await evaluate(`JSON.stringify({
  title: document.querySelector('.ind-title')?.textContent || null,
  cards: document.querySelectorAll('.li-card').length,
  sparks: document.querySelectorAll('.li-spark-svg path').length,
  pending: document.querySelectorAll('.li-pending').length,
  pendingKeys: [...document.querySelectorAll('.li-card.is-pending')].map((c) => c.dataset.stage),
  priceSec: [...document.querySelectorAll('.hist .sec-title')].map((e) => e.textContent),
  pricePath: document.querySelectorAll('.hist svg path').length >= 2,
  src: document.querySelector('.li-src')?.textContent || null,
  coLinks: document.querySelectorAll('.li-co').length,
  arrows: document.querySelectorAll('.li-arrow').length,
  moreBtns: document.querySelectorAll('[data-li-more]').length,
  noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth
})`));
check('页面标题 + 9 阶段卡片全部渲染', st.title === '锂电产业链' && st.cards === 9, `${st.title} / ${st.cards} 卡`);
check(`迷你图数 == 有非空序列的阶段数（${expectSpark}），占位卡数 == 空序列阶段数（${expectPending}）`,
  st.sparks === expectSpark && st.pending === expectPending
    && st.pendingKeys.sort().join(',') === liData.stages.filter((s) => !stageUsable(s)).map((s) => s.key).sort().join(','),
  `sparks=${st.sparks} pending=[${st.pendingKeys.join(',')}]`);
check('碳酸锂期货主力价格图（标题+折线+面积）',
  st.priceSec.includes('碳酸锂期货主力') && st.pricePath, st.priceSec.join('|'));
check('来源注记含「碳酸锂期货主力（广期所）」与更新日期',
  !!st.src && st.src.includes('碳酸锂期货主力（广期所）') && st.src.includes('2026-10-12'), st.src);
check('公司链接指向 #/c/ 路由（首批）', st.coLinks >= 9 * 2, `${st.coLinks} 个链接`);
check('主流线箭头 + 展开按钮存在', st.arrows === 3 && st.moreBtns >= 5, `箭头 ${st.arrows} / 展开 ${st.moreBtns}`);
check('桌面无横向溢出', st.noHScroll);

// 展开交互
await evaluate(`document.querySelector('[data-li-more]').click()`);
await sleep(200);
const exp = JSON.parse(await evaluate(`JSON.stringify({
  open: document.querySelector('[data-li-more]').getAttribute('aria-expanded'),
  restHidden: document.querySelector('.li-co-rest').hidden,
  btnText: document.querySelector('[data-li-more]').textContent
})`));
check('「全部 N 家」展开：rest 显示、按钮变「收起」', exp.open === 'true' && exp.restHidden === false && exp.btnText === '收起', JSON.stringify(exp));

let r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'li-dark.png', Buffer.from(r.data, 'base64'));
console.log('  li-dark.png');

// 浅色
await evaluate(`localStorage.setItem('cnchain.settings', JSON.stringify({theme:'light'}));1`);
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2400);
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'li-light.png', Buffer.from(r.data, 'base64'));
console.log('  li-light.png');

// EN
await evaluate(`localStorage.setItem('cnchain.locale','en');1`);
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2400);
const en = JSON.parse(await evaluate(`JSON.stringify({
  title: document.querySelector('.ind-title')?.textContent,
  stage1: document.querySelector('.li-card-title')?.textContent,
  pending: document.querySelector('.li-pending')?.textContent,
  price: [...document.querySelectorAll('.hist .sec-title')].map((e) => e.textContent).join('|'),
  cards: document.querySelectorAll('.li-card').length
})`));
check('EN：标题/阶段名/价格图标题全部翻译' + (expectPending ? '、降级文案' : ''),
  en.title === 'Lithium battery chain' && en.stage1 === 'Upstream · Lithium resources'
  && en.price.includes('Lithium carbonate futures')
  && (expectPending > 0 ? en.pending === 'History still being collected' : en.pending == null),
  JSON.stringify(en));
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'li-en.png', Buffer.from(r.data, 'base64'));
console.log('  li-en.png');

// 回中文 + 移动端 390
await evaluate(`localStorage.removeItem('cnchain.locale'); localStorage.removeItem('cnchain.settings');1`);
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/li' });
await sleep(2400);
const mob = JSON.parse(await evaluate(`JSON.stringify({
  cards: document.querySelectorAll('.li-card').length,
  noHScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  arrows: [...document.querySelectorAll('.li-arrow')].filter((a) => getComputedStyle(a).display !== 'none').length
})`));
check('移动端 390：9 卡、单列无箭头、无横向溢出', mob.cards === 9 && mob.noHScroll && mob.arrows === 0, JSON.stringify(mob));
r = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(OUT + 'li-mobile.png', Buffer.from(r.data, 'base64'));
console.log('  li-mobile.png');

// 首页入口
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '?fresh=' + Date.now() + '#/' });
await sleep(2600);
const entry = JSON.parse(await evaluate(`JSON.stringify({
  href: document.querySelector('.li-entry')?.getAttribute('href'),
  text: document.querySelector('.li-entry-title')?.textContent
})`));
check('首页入口卡片存在并指向 #/li', entry.href === '#/li' && !!entry.text, `${entry.text} → ${entry.href}`);

console.log('页面报错:', errors.length ? errors.join(' | ') : '无');
const failed = results.filter(([ok]) => !ok).length;
console.log(failed === 0 ? `\n锂电看板走查全部 ${results.length} 项通过` : `\n${failed}/${results.length} 项未通过`);
ws.close();
process.exit(failed === 0 && errors.length === 0 ? 0 : 1);
