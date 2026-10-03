import {
  initI18n, setLocale, getLocale, listLocales,
  t, fmtPrice, fmtCap, fmtPct, fmtNum, fmtInt,
} from "./i18n.js?v=__BUILD__";

const app = document.getElementById("app");
const searchEl = document.getElementById("search");
const langEl = document.getElementById("lang");
const footerEl = document.getElementById("footer-note");

/* ---- 全局状态 ------------------------------------------------------------ */
let indexData = null;              // { companies: [...], featured, totals }
let searchTerm = "";
let homeScrollY = 0;               // 记住首页滚动位置，返回时还原
let prevRouteName = "home";
/* 行业页的筛选状态。放在模块级是因为"加载更多"和芯片点击都要重绘列表，
   而列表重绘不该把整页（含滚动位置）推倒重来。 */
let indTerm = "";                  // 行业页内的关键词
let indSelChain = null;            // 选中的产业链环节
let indSelMarket = null;           // 选中的市场板块（沪市主板/深市主板/创业板/科创板）
let indLimit = 60;                 // 已显示多少家
let indCurrent = null;             // 当前行业，切行业时重置上面几个
const IND_STEP = 60;               // 每次"再看 N 家"补多少
const IND_CHAIN_CAP = 18;          // 环节芯片最多列几个（其余折进"其他"说明）

/* ---- 四份数据 ----
   index.json        4071 家：身份 + 行业 + 环节数 + 价格/涨跌幅/市值（首屏卡片用）
   f/{代码}.json     完整行情财务，公司页按需加载（一家约 2 KB）
   graph.json        二分图成员表：行业→公司、环节→公司、公司→环节索引
   chain_steps.json  行业级上下游步进表（人工整理的产业常识，53 条）：上游行业 → 下游行业 + 角色
   data/{代码}.json  151 家手工梳理的价值链档案（人工整理的真实档案）

   数据口径（折中方案）：有手工档案的公司显示真实价值链地图；其余公司只显示
   **行业级**位置图（步进表是真实的行业间原料流向，环节归属是真实公开归类）——
   界面不再出现虚构的公司间供货连线（chains.json 的推断数据已撤下，文件仅存档）。 */
let graphData = null;
let graphPromise = null;
let stepsData = null;
let stepsPromise = null;
function loadChainSteps() {
  if (!stepsPromise) {
    stepsPromise = getJSON("./data/chain_steps.json")
      .then((d) => (stepsData = d))
      .catch(() => null);
  }
  return stepsPromise;
}
// 某行业的上游 / 下游行业（chain_steps.json 的步进表，行业级；同一行业去重）
function stepsOf(ind) {
  const up = [], down = [];
  for (const [u, d, role] of (stepsData?.steps || [])) {
    if (d === ind && !up.some((x) => x.ind === u)) up.push({ ind: u, role });
    if (u === ind && !down.some((x) => x.ind === d)) down.push({ ind: d, role });
  }
  return { up, down };
}
function loadGraph() {
  if (!graphPromise) {
    graphPromise = getJSON("./data/graph.json")
      .then((d) => (graphData = d))
      .catch(() => null);
  }
  return graphPromise;
}
// 一家公司属于哪些产业链环节（名字）
function boardsOf(ticker) {
  if (!graphData || !graphData.boardIdxOf) return [];
  const idx = graphData.boardIdxOf[ticker] || [];
  return idx.map((i) => graphData.boardList[i]).filter(Boolean);
}

// 公司页
let mapZoom = null;                // null=未定；"fit"=适应宽度 | "full"=原始尺寸+横向平移
let mapRO = null;                  // 展开分组时重画连接线
let expandedClusters = new Set();

/* ---- 用户设置（持久化） -------------------------------------------------- */
const SETTINGS_KEY = "cnchain.settings";
const SETTINGS_DEFAULTS = {
  layout: "group",      // group | flat
  width: "narrow",      // narrow | wide
  animations: true,
  theme: "dark",        // dark（默认，终端风）| light（浅色研报风）
  accent: "navy",       // navy（默认）| forest | graphite —— 仅浅色主题生效
};
let settings = { ...SETTINGS_DEFAULTS };

function loadSettings() {
  try {
    settings = { ...SETTINGS_DEFAULTS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch { settings = { ...SETTINGS_DEFAULTS }; }
}
function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* ignore */ }
}
// 主色只有非默认值才写到 <html> 上；index.html 里有同样的一段内联脚本，
// 在首屏绘制前就打好属性，所以切换主色不会在重载时闪一下默认色。
function applyAccent() {
  const el = document.documentElement;
  if (settings.accent && settings.accent !== "navy") el.dataset.accent = settings.accent;
  else el.removeAttribute("data-accent");
}
// 主题只有浅色才需要打属性（:root 默认就是深色）；index.html 里有同款内联脚本防首屏闪烁。
function applyTheme() {
  const el = document.documentElement;
  if (settings.theme === "light") el.dataset.theme = "light";
  else el.removeAttribute("data-theme");
}
function applyMotion() {
  document.documentElement.classList.toggle("no-anim", !settings.animations);
}
function motionOff() {
  return !settings.animations ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

/* ---- 自选清单（持久化） -------------------------------------------------- */
const SAVED_KEY = "cnchain.saved";
let savedList = [];                // 加入顺序
let savedSet = new Set();

function loadSaved() {
  try {
    const arr = JSON.parse(localStorage.getItem(SAVED_KEY) || "[]");
    savedList = Array.isArray(arr) ? arr.map((x) => String(x).toUpperCase()) : [];
  } catch { savedList = []; }
  savedSet = new Set(savedList);
}
function persistSaved() {
  try { localStorage.setItem(SAVED_KEY, JSON.stringify(savedList)); } catch { /* ignore */ }
}
const isSaved = (ticker) => savedSet.has(String(ticker).toUpperCase());

function toggleSaved(ticker) {
  const tk = String(ticker).toUpperCase();
  if (savedSet.has(tk)) { savedSet.delete(tk); savedList = savedList.filter((x) => x !== tk); }
  else { savedSet.add(tk); savedList.push(tk); }
  persistSaved();
  syncStars(tk);
  renderTray();
}

// 把一个代码的自选状态同步到当前 DOM 里所有相关的星标按钮上
function syncStars(tk) {
  const on = savedSet.has(tk);
  const label = on ? t("save.remove", "移出自选") : t("save.toggle", "加入自选");
  document.querySelectorAll(`.card-star[data-save="${cssEscape(tk)}"]`).forEach((el) => {
    el.classList.toggle("on", on);
    el.setAttribute("aria-pressed", String(on));
    el.setAttribute("aria-label", label);
    el.title = label;
    const g = el.querySelector(".star-glyph");
    if (g) g.textContent = on ? "−" : "+";
    const txt = el.querySelector(".star-text");
    if (txt) txt.textContent = on ? t("save.onlist", "已在自选") : t("save.addlist", "加入自选");
  });
}

function starBtn(ticker, extra = "") {
  const on = isSaved(ticker);
  const label = on ? t("save.remove", "移出自选") : t("save.toggle", "加入自选");
  return `<button class="card-star ${extra} ${on ? "on" : ""}" type="button" data-save="${esc(ticker)}"`
    + ` aria-pressed="${on}" aria-label="${esc(label)}" title="${esc(label)}">`
    + `<span class="star-glyph" aria-hidden="true">${on ? "−" : "+"}</span></button>`;
}

// 公司页用的带文字药丸：沿用同一套 data-save / .star-glyph 钩子，
// 所以 syncStars 能一并把它更新掉。
function savePill(ticker) {
  const on = isSaved(ticker);
  return `<button class="card-star pr-save ${on ? "on" : ""}" type="button" data-save="${esc(ticker)}"`
    + ` aria-pressed="${on}">`
    + `<span class="star-glyph" aria-hidden="true">${on ? "−" : "+"}</span>`
    + `<span class="star-text">${esc(on ? t("save.onlist", "已在自选") : t("save.addlist", "加入自选"))}</span></button>`;
}

// 空状态的彩蛋：用字符网格 + 调色板定义一只小猫头鹰，
// 运行时生成 crispEdges 的内联 SVG（可缩放、体积极小、只有一个节点）。
const OWL_GRID = [
  "................",
  "....22....22....",
  "...2332..2332...",
  "..233332233332..",
  "..231112211132..",
  ".23311111111332.",
  ".23111111111132.",
  ".2311e1111e1132.",
  ".23111111111132.",
  "..231111111132..",
  "...2311111132...",
  "....23111132....",
  ".....233332.....",
  "................",
];
// 调色板从 CSS 变量取（--owl-*），深色/浅色主题各有一份——
// 浅色下是浅灰猫头鹰，深色下要反过来：深灰身体、亮色眼睛。
function owlSVG(px = 6) {
  const pal = {
    "1": cssVar("--owl-1", "#232C3A"), "2": cssVar("--owl-2", "#38445A"),
    "3": cssVar("--owl-3", "#5E6B7C"), "e": cssVar("--owl-e", "#D8DFE9"),
  };
  const cols = Math.max(...OWL_GRID.map((r) => r.length));
  const rows = OWL_GRID.length;
  let rects = "";
  OWL_GRID.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const c = pal[row[x]];
      if (c) rects += `<rect x="${x}" y="${y}" width="1" height="1" fill="${c}"/>`;
    }
  });
  return `<svg class="tray-fawn" viewBox="0 0 ${cols} ${rows}" width="${cols * px}" height="${rows * px}"`
    + ` shape-rendering="crispEdges" aria-hidden="true">${rects}</svg>`;
}

function renderTray() {
  const countEl = document.getElementById("tray-count");
  const drawerCountEl = document.getElementById("tray-drawer-count");
  const panel = document.getElementById("tray-panel");
  const foot = document.getElementById("tray-foot");
  if (countEl) countEl.textContent = String(savedList.length);
  if (drawerCountEl) drawerCountEl.textContent = String(savedList.length);
  if (foot) foot.style.display = savedList.length ? "" : "none";
  if (!panel) return;

  if (!savedList.length) {
    panel.innerHTML = `<div class="tray-empty">`
      + owlSVG(6)
      + `<span>${esc(t("saved.empty", "还没有自选"))}</span>`
      + `<span class="tray-empty-hint">${esc(t("saved.emptyHint", "点公司卡片右上角的加号收进来。"))}</span>`
      + `</div>`;
    return;
  }
  const byTicker = new Map((indexData?.companies || []).map((c) => [c.ticker.toUpperCase(), c]));
  // 最近加入的排最前（savedList 是追加顺序）
  const rows = savedList.slice().reverse().map((tk) => {
    const c = byTicker.get(tk);
    const name = c ? c.name : tk;
    return `<div class="tray-row">
        <a class="tray-row-link" href="#/c/${encodeURIComponent(tk)}">
          <span class="tray-row-ticker">${esc(tk)}</span>
          <span class="tray-row-name">${esc(name)}</span>
        </a>
        <button class="tray-row-x" type="button" data-save="${esc(tk)}" aria-label="${esc(t("save.remove", "移出自选"))}" title="${esc(t("save.remove", "移出自选"))}">✕</button>
      </div>`;
  }).join("");
  panel.innerHTML = `<div class="tray-rows">${rows}</div>`;
}

// 自选抽屉 + 委托式星标点击，只在启动时挂一次
function setupSaved() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-save]");
    if (!btn) return;
    e.preventDefault();        // 星标嵌在卡片的 <a> 里，别让它跳转
    e.stopPropagation();
    toggleSaved(btn.dataset.save);
  });

  const bar = document.getElementById("tray-toggle");
  const tray = document.getElementById("saved-tray");
  const setOpen = (open) => {
    if (!tray) return;
    tray.dataset.open = String(open);
    if (bar) bar.setAttribute("aria-expanded", String(open));
  };
  if (bar && tray) bar.addEventListener("click", () => setOpen(tray.dataset.open !== "true"));
  document.getElementById("tray-close")?.addEventListener("click", () => setOpen(false));
  document.getElementById("tray-clear")?.addEventListener("click", () => {
    const cleared = savedList.slice();
    const finish = () => {
      savedList = []; savedSet = new Set();
      persistSaved();
      cleared.forEach(syncStars);
      renderTray();
    };
    // 收据式折起：先把高度定死在当前值，再滚到 0，最后才真的清数据
    const rows = document.querySelector(".tray-rows");
    if (!rows) { finish(); return; }
    rows.style.maxHeight = `${rows.scrollHeight}px`;
    requestAnimationFrame(() => {
      rows.classList.add("folding");
      rows.style.maxHeight = "0px";
    });
    setTimeout(finish, motionOff() ? 0 : 500);
  });

  const drawer = document.getElementById("tray-drawer");
  drawer?.addEventListener("click", (e) => {
    const x = e.target.closest(".tray-row-x");
    if (x) {
      e.preventDefault(); e.stopPropagation();   // 别让全局星标处理器再 toggle 一次
      const row = x.closest(".tray-row");
      if (row && !motionOff()) {
        row.style.animation = "none";            // 清掉入场动画的填充，滑出才看得见
        row.classList.add("removing");
        setTimeout(() => toggleSaved(x.dataset.save), 280);
      } else {
        toggleSaved(x.dataset.save);
      }
      return;
    }
    if (e.target.closest(".tray-row-link")) setOpen(false);  // 跳转后自动收起
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && tray && tray.dataset.open === "true") setOpen(false);
  });
  renderTray();
}

/* ---- 工具 ---------------------------------------------------------------- */
// 数据里带的说明文案用 <b> 标重点。整段 esc() 会把标签转义成字面文本（页面上真的显示
// "<b>真实公开数据</b>"），所以这里先全转义、再只把 <b> / </b> 放回来 —— 白名单就这两个。
const richNote = (s) => esc(s).replace(/&lt;b&gt;/g, "<b>").replace(/&lt;\/b&gt;/g, "</b>");

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

// 只用于 querySelector 的文本，避免特殊字符把选择器语法打坏
function cssEscape(s) {
  return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^\w-]/g, "\\$&");
}

// Canvas 不认 CSS 变量，只能运行时从计算样式里取。
// 这么做是为了让画布和 CSS 共用同一份墨色——改主题时它自动跟着变，
// 而不是把色值在 JS 里再抄一份（抄了就一定有哪天两边不一致）。
function cssVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch { return fallback; }
}

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// 由字符串派生的确定性伪随机（mulberry32）。
// 用它而不是 Math.random()，是为了让图谱布局每次刷新都一样——
// 图表一旦每次换位置，就失去"地图"的意义了。
function seededRng(key) {
  let s = 0;
  for (const ch of String(key)) s = (s * 131 + ch.codePointAt(0)) >>> 0;
  let a = (s || 0x9E3779B9) >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let x = a;
    x = Math.imul(x ^ (x >>> 15), 1 | x);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---- 行情数据 ------------------------------------------------------------ */
// 首屏只需要每家的价格 / 涨跌幅 / 市值——这三个字段随 index.json 一起下来
// （pipeline/build_chain.py 并进去的），不再单独拉一份 1.6 MB 的全量合并文件。
// 公司页的完整财务指标（市盈率 / 毛利率 / 每股收益等十项）按需加载：
// data/f/{代码}.json 一家一份（约 2 KB），拉不到就按"没有数字"渲染，不白屏。
// ── 产业链档案数据（行业/公司/设备三级）──────────────────────
// 文件不存在或字段缺失都不算错——没有档案的对象不渲染档案块，
// 有档案但缺字段才显示「待接入具体数据接口」。
let chainPromise = null;
let chainDataCache = null;
const loadChainData = () => (chainPromise ||= getJSON("./data/chain/chain.json")
  .then((d) => { chainDataCache = d; return d; })
  .catch(() => { chainDataCache = { companies: {}, unlisted_companies: {}, industries: {}, devices: {} }; return chainDataCache; }));

const quoteCache = new Map();
function loadQuote(ticker) {
  if (!quoteCache.has(ticker)) {
    quoteCache.set(ticker, getJSON(`./data/f/${encodeURIComponent(ticker)}.json`)
      .then((q) => (q && typeof q === "object" ? q : null))
      .catch(() => null));   // 404 / 断网都按"无行情"处理
  }
  return quoteCache.get(ticker);
}
// 公司介绍（主营业务/经营范围/主营构成），同样一家一份、按需加载
const profileCache = new Map();
function loadProfile(ticker) {
  if (!profileCache.has(ticker)) {
    profileCache.set(ticker, getJSON(`./data/p/${encodeURIComponent(ticker)}.json`)
      .then((q) => (q && typeof q === "object" ? q : null))
      .catch(() => null));
  }
  return profileCache.get(ticker);
}
// 把完整行情挂到公司页数据上。只有锚点渲染行情指标，上下游卡片不显示数字，
// 所以它们不用拉。
function mergeFundamentals(data, quote) {
  if (data && data.anchor) {
    data.anchor.fundamentals = quote;
    // 卡片里的锚点字段叫 industry，地图的锚点节点要的是 sector。
    // 不补这一下，地图上会明晃晃地显示 "300750 · sector.undefined"。
    if (!data.anchor.sector) data.anchor.sector = data.anchor.industry;
  }
  if (data) data.generatedAt = (indexData && indexData.generatedAt) || "";
  return data;
}

/* ---- 路由 ---------------------------------------------------------------- */
function parseRoute() {
  const h = location.hash.replace(/^#\/?/, "");
  if (h.startsWith("c/")) return { name: "company", ticker: decodeURIComponent(h.slice(2)) };
  // 行业页：#/i/电子（公司列表）
  if (h.startsWith("i/")) return { name: "industry", industry: decodeURIComponent(h.slice(2)) };
  // 行业环图：#/m/电子（单个行业的大圆饼）
  if (h.startsWith("m/")) return { name: "industryMap", industry: decodeURIComponent(h.slice(2)) };
  // 设备档案：#/e/{id}（产业链档案的第三级）
  if (h.startsWith("e/")) return { name: "equipment", id: decodeURIComponent(h.slice(2)) };
  if (h === "vision") return { name: "vision" };
  // "atlas" 是"全景图谱"的旧名字，留着旧链接不失效
  if (h === "worldmap" || h === "atlas") return { name: "worldmap" };
  return { name: "home" };
}

async function route() {
  const r = parseRoute();
  // 离开首页时记下滚动位置；此刻 DOM 还没被替换，scrollY 仍是首页的值
  if (prevRouteName === "home" && r.name !== "home") homeScrollY = window.scrollY;
  const returningHome = r.name === "home" && prevRouteName !== "home";
  const cameFrom = prevRouteName;
  prevRouteName = r.name;

  closeSearchList();       // 换页时收起搜索候选
  document.body.classList.toggle("home", r.name === "home");
  markCurrentNav(r.name);

  // 进入一个不是首页的新页面时，把滚动位置归零。
  // 不归零的话，从很长的页面（行业页、公司页）跳到很短的页面（环图页）时，
  // 浏览器会保留原来的 scrollY，新页面一打开就停在半空中。
  // 回首页那条路不走这里 —— 它要还原离开时记住的位置。
  // 只有"换了一个页面"才归零；同一页面内重渲染（比如切筛选）不动位置
  if (!returningHome && r.name !== cameFrom) window.scrollTo(0, 0);

  if (r.name === "vision") {
    await renderVision();
  } else if (r.name === "worldmap") {
    await renderWorldMap();
  } else if (r.name === "industry") {
    await renderIndustryPage(r.industry);
  } else if (r.name === "industryMap") {
    await renderIndustryRingPage(r.industry);
  } else if (r.name === "equipment") {
    await renderEquipmentPage(r.id);
  } else if (r.name === "company") {
    app.innerHTML = "";
    startLoading();
    try {
      const ticker = r.ticker.toUpperCase();
      // 只加载这三个：4,071 家里只有 151 家有独立的价值链卡片，
      // 其余公司的信息全部从 index.json（身份/行业）+ graph.json（所属环节/同行）推导
      const info = (indexData?.companies || []).find((c) => c.ticker === ticker);
      const [, , quote, chain, profile] = await Promise.all([
        loadGraph(), loadChainSteps(),
        loadQuote(ticker),          // 完整财务指标，一家一份，按需
        loadChainData(),
        loadProfile(ticker),        // 公司介绍，一家一份，按需
      ]);
      let card = null;
      if (info && info.curated) {
        // 只有手工梳理过价值链的公司才有卡片文件，别的不用去问（省一次 404）
        try { card = await getJSON(`./data/${encodeURIComponent(ticker)}.json`); }
        catch { card = null; }
      }

      if (!card && !info) throw new Error("unknown company");
      // 有手工档案 = 真实价值链地图；没有就不再拼推断节点，位置图只用行业级真实数据画
      if (card) card.curated = true;
      const data = card || {
        curated: false,
        anchor: {
          ticker, name: info.name, industry: info.industry,
          board: info.board, exchange: info.exchange, fundamentals: null,
        },
        nodes: [],
      };
      mergeFundamentals(data, quote);
      data.profile = profile;   // 公司介绍（可能为 null，渲染层兜底）
      if (parseRoute().name !== "company") return;  // 加载途中用户跳走了，别再渲染
      renderCompany(data);
    } catch {
      app.innerHTML = `<p class="empty">${esc(t("err.company", "这家公司没加载出来。"))}`
        + ` <a href="#/">${esc(t("crumb.home", "全部公司"))}</a></p>`;
    } finally {
      stopLoading();
    }
  } else {
    renderHome(true);
    // 只在"从别的页面返回"时还原滚动位置，初次加载和原地搜索重绘都不动
    if (returningHome && homeScrollY > 0) {
      requestAnimationFrame(() => window.scrollTo(0, homeScrollY));
    }
  }
}

/* ---- 路由加载细线 --------------------------------------------------------
   驱动 header 下沿那条 2px 横线（见 styles.css 的 .load-rule）。
   调用会嵌套——boot() 为整个首屏持一个、route() 为它渲染的视图再持一个——
   所以用深度计数让它连续亮着，而不是在两者之间闪断。

   index.html 出厂时就带着 .boot 在跑，所以深度从 1 起步：
   在这个模块被解析之前，CSS 已经把首帧盖住了。 */
const LOAD_GATE_MS = 350;
let loadDepth = 1;
let loadGateTimer = 0;

function clearLoadRule(el, bar) {
  el.getAnimations().forEach((a) => a.cancel());
  bar.getAnimations().forEach((a) => a.cancel());
  el.classList.remove("boot", "on");
  el.style.opacity = "";
  bar.style.transform = "";
}

function startLoading() {
  const el = document.getElementById("load-rule");
  if (!el) return;
  if (++loadDepth > 1) return;      // 已经在亮着了，别重启动画
  const bar = el.firstElementChild;
  loadGateTimer = setTimeout(() => {
    clearLoadRule(el, bar);         // 取消上一次可能还在跑的淡出
    void bar.offsetWidth;           // 让绘制从零重新开始
    el.classList.add("on");
    const status = document.getElementById("load-status");
    if (status) status.textContent = t("loading", "加载中…");
  }, LOAD_GATE_MS);
}

function stopLoading() {
  const el = document.getElementById("load-rule");
  if (!el) return;
  if (--loadDepth > 0) return;
  loadDepth = 0;
  clearTimeout(loadGateTimer);
  const status = document.getElementById("load-status");
  if (status) status.textContent = "";
  const bar = el.firstElementChild;

  // 屏幕上什么都没出现：要么门闸还没到点，要么这次首屏加载跑赢了 boot 规则的
  // 350ms 延迟。直接清掉——下面的收尾动画会强行把它显出来闪一下，正是门闸要避免的事。
  if (parseFloat(getComputedStyle(el).opacity) === 0) { clearLoadRule(el, bar); return; }

  // 先把线冻结在它实际到达的宽度，补齐到 100%，再淡出。
  // 两段都用 WAAPI，这样复位可以挂在 `finished` 上——
  // 用定时器去追 CSS 过渡，在主线程忙的时候会把线卡在半透明。
  const full = el.getBoundingClientRect().width;
  const from = full ? bar.getBoundingClientRect().width / full : 1;
  el.classList.remove("boot", "on");
  el.style.opacity = "1";
  bar.style.transform = `scaleX(${from})`;
  bar.animate(
    [{ transform: `scaleX(${from})` }, { transform: "scaleX(1)" }],
    { duration: 180, easing: "ease", fill: "forwards" },
  );
  el.animate(
    [{ opacity: 1 }, { opacity: 0 }],
    { duration: 300, delay: 120, easing: "ease", fill: "forwards" },
  ).finished.then(() => clearLoadRule(el, bar)).catch(() => { /* 被新的加载取代了 */ });
}

/* ---- 打字机标题 ---------------------------------------------------------- */
function typeTitle(el, text, speed, onDone) {
  if (motionOff()) { el.textContent = text; onDone && onDone(); return; }
  el.textContent = "";
  const caret = document.createElement("span");
  caret.className = "hero-caret";
  caret.setAttribute("aria-hidden", "true");
  el.appendChild(caret);
  let i = 0;
  const tick = () => {
    if (i >= text.length) {
      caret.remove();
      el.textContent = text;
      onDone && onDone();
      return;
    }
    caret.insertAdjacentText("beforebegin", text[i++]);
    setTimeout(tick, speed);
  };
  setTimeout(tick, speed);
}

/* ---- 数字滚动（odometer）：终端/数据新闻的标配。
   元素带 data-count="终值" 才会滚；关动效时直接显示终值（HTML 里本来就写着终值）。 */
function countUp(el, dur = 850) {
  const target = Number(el.dataset.count);
  if (!target || motionOff()) { delete el.dataset.count; return; }
  const t0 = performance.now();
  const step = (now) => {
    if (!el.isConnected) return;
    const p = Math.min(1, (now - t0) / dur);
    const e = 1 - Math.pow(1 - p, 3);              // ease-out cubic
    el.textContent = fmtInt(Math.round(target * e));
    if (p < 1) requestAnimationFrame(step);
    else delete el.dataset.count;
  };
  requestAnimationFrame(step);
}
function countUpIn(root) {
  root.querySelectorAll("[data-count]").forEach((el) => countUp(el));
}

/* ---- 首页 ---------------------------------------------------------------- */
function changeClass(v) {
  if (v == null) return "flat";
  if (v > 0) return "gain";
  if (v < 0) return "loss";
  return "flat";
}

function cardHTML(c, wide = false) {
  const f = (indexData.quotes || {})[c.ticker];
  const chg = f ? f.changePercent : null;

  const nums = f ? `
      <div class="card-nums">
        <span class="card-price">${esc(fmtPrice(f.price))}</span>
        <span class="card-chg ${changeClass(chg)}">${esc(fmtPct(chg))}</span>
        <span class="card-cap">${esc(t("card.cap", "总市值"))}<br />${esc(fmtCap(f.marketCap))}</span>
      </div>` : "";

  // 同行业里有多少家与它共享产业链环节——这是"它在图上连了多少家"的直观指标
  const peers = c.industryPeers
    ? `<div class="chain-legend"><span class="k-peer">${esc(t("card.peers", "同行业 {n} 家共享产业链环节").replace("{n}", fmtInt(c.industryPeers)))}</span></div>`
    : "";

  return `
    <a class="card" href="#/c/${encodeURIComponent(c.ticker)}" data-card>
      ${starBtn(c.ticker)}
      <div class="card-head">
        <span class="card-name">${esc(c.name)}</span>
        <span class="card-ticker">${esc(c.ticker)}</span>
      </div>
      <div class="card-tags">
        <span class="tag tag-sector">${esc(t("sector." + c.industry, c.industry))}</span>
        <span class="tag">${esc(t("board." + c.board, c.board))}</span>
        ${c.boardCount ? `<span class="tag">${esc(fmtInt(c.boardCount))} ${esc(t("card.chains", "条产业链"))}</span>` : ""}
        ${c.curated ? `<span class="tag tag-chain">${esc(t("card.curated", "手工梳理"))}</span>` : ""}
      </div>
      ${nums}
      ${peers}
    </a>`;
}

// 口径文案：中文用数据里带的那份（跟具体抓取日期绑着），
// 别的语言用语言包里的（数据里的那份只有中文）
function noteHTML() {
  return richNote((getLocale() === "zh" && indexData?.disclaimer) || t("home.note", ""));
}

function heroHTML() {
  const tot = (indexData && indexData.totals) || { companies: 0, links: 0, sectors: 0, nodes: 0 };
  return `
    <section class="hero" id="home-hero">
      <p class="hero-kicker">${esc(t("home.kicker", "ChainAtlas · A 股产业链知识图谱"))}</p>
      <h1 id="home-hero-title"></h1>
      <p class="hero-slogan">${esc(t("home.slogan", ""))}</p>
      <p class="hero-sub">${esc(t("home.sub", ""))}</p>
      <div class="hero-stats">
        <span class="hero-stat"><b data-count="${tot.companies}">${esc(fmtInt(tot.companies))}</b><span>${esc(t("stat.companies", "家上市公司"))}</span></span>
        <span class="hero-stat"><b data-count="${tot.industries}">${esc(fmtInt(tot.industries))}</b><span>${esc(t("stat.sectors", "个申万一级行业"))}</span></span>
        <span class="hero-stat"><b data-count="${tot.boards}">${esc(fmtInt(tot.boards))}</b><span>${esc(t("stat.boards", "个产业链环节"))}</span></span>
        <span class="hero-stat"><b data-count="${tot.edges}">${esc(fmtInt(tot.edges))}</b><span>${esc(t("stat.edges", "条公司—环节关联"))}</span></span>
      </div>
      <p class="hero-note">${noteHTML()}</p>
    </section>
    <div class="hero-bar" id="home-hero-bar" hidden>
      <span class="hero-bar-title">${esc(t("home.title", ""))}</span>
      <span class="hero-bar-sub">${esc(fmtInt(tot.companies))} ${esc(t("stat.companies", ""))} · ${esc(fmtInt(tot.boards))} ${esc(t("stat.boards", ""))}</span>
      <button class="hero-bar-up" id="hero-bar-up" type="button">↑</button>
    </div>`;
}

/* ---- 首页：24 张行业概览卡 ------------------------------------------------
   首页不再一次铺开 4071 家公司（又长又慢），改成"按申万一级行业概览"：
   每张卡给出公司数、环节数、市值合计、平均涨跌、环节分布和头部公司，
   点进去才是该行业的完整公司列表。搜索仍然直接出公司卡片。 */

function industryStat(ind) {
  const q = indexData?.quotes || {};
  const members = graphData?.industries?.[ind] || [];
  let cap = 0, chgSum = 0, chgN = 0;
  for (const tk of members) {
    const f = q[tk] || {};
    if (typeof f.marketCap === "number") cap += f.marketCap;
    if (typeof f.changePercent === "number") { chgSum += f.changePercent; chgN++; }
  }
  // 这个行业里出现最多的几个产业链环节
  const freq = new Map();
  for (const tk of members) {
    for (const bi of (graphData?.boardIdxOf?.[tk] || [])) {
      freq.set(bi, (freq.get(bi) || 0) + 1);
    }
  }
  const ranked = [...freq.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const boards = ranked.slice(0, 4).map(([bi, n]) => ({ name: graphData.boardList[bi], n }));
  return {
    count: members.length,
    cap,
    avg: chgN ? chgSum / chgN : null,
    boardCount: ranked.length,
    boards,
    boardMax: boards.length ? boards[0].n : 1,
    top: members.slice(0, 3),
  };
}

/* ---- 首页：全市场大环 ----------------------------------------------------
   段的大小 = 该行业公司数占全市场的比例。它回答的是"哪个行业大、哪个小"，
   和全景图谱（24 个小圆饼，每个看这个行业由什么环节组成）回答的不是同一件事。

   弧长不足 6px 的行业并成「其他 N 个行业」—— 看不见也点不中的段没有意义。
   折叠不等于隐藏：段上带着数字、点一下展开，24 个行业一个不少。 */
const MARKET_MIN_ARC = 6;      // 一段至少这么长（px）才值得单独画

// 按家数把 24 个行业切成段；返回的 segs 里最后一段可能是"其他 N 个行业"
function marketSegments(R) {
  const tot = indexData?.totals?.companies || 1;
  const all = (indexData?.industryList || []).map((ind) => {
    const n = (graphData?.industries?.[ind] || []).length;
    return { ind, n, share: n / tot };
  }).sort((a, b) => b.n - a.n);
  const C = Math.PI * 2 * R;
  // 按家数降序，所以小行业必然排在最后 —— 直接把它们并成最后一段，角度仍然连续
  // 只折到 1 个就不折了 —— "其他 1 个行业"这种段落没意义，还不如把那一个直接画出来
  let small = all.filter((x) => x.share * C < MARKET_MIN_ARC);
  let big = all.filter((x) => x.share * C >= MARKET_MIN_ARC);
  if (small.length === 1) { big = all; small = []; }

  const segs = [];
  let a = -Math.PI / 2;
  const push = (o) => {
    const span = o.share * Math.PI * 2;
    const gap = Math.min(span * 0.08, 0.01);
    segs.push({ ...o, a0: a + gap / 2, a1: a + span - gap / 2, mid: a + span / 2, span });
    a += span;
  };
  for (const x of big) push(x);
  if (small.length) {
    push({
      ind: null, n: small.reduce((t, x) => t + x.n, 0),
      share: small.reduce((t, x) => t + x.share, 0), members: small,
    });
  }
  return { segs, small, tot };
}

function marketSide(cv) {
  const avail = cv.parentElement?.clientWidth || 900;
  // 环外不再需要留标签带（名字改成悬停弹方块了），但也不能真撑满一屏：
  // 要给下面的行业名那一排留位置，整块一屏看完才不会变成"每次都要滚"。
  return Math.round(clamp(Math.min(avail, 760, window.innerHeight - 250), 300, 820));
}

function drawMarketRing(cv, hover = -1, dragTo = -1) {
  const side = marketSide(cv);
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.floor(side * dpr);
  cv.height = Math.floor(side * dpr);
  cv.style.width = side + "px";
  cv.style.height = side + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, side, side);

  const cx = side / 2, cy = side / 2;
  const font = getComputedStyle(document.body).fontFamily;

  // 半径只留一圈按比例的外白边（给悬停描边 + 呼吸感），不再按"最长的标签有多宽"收。
  // 原先是两遍定半径：先量出"机械设备 496"这类环上标签的宽度，再据此把环往回收。
  // 标签已不画在环上（中文沿半径排字左半边必然是倒的），那 104px 就成了纯白扔，
  // 而且小屏上按固定像素扣会让环缩到很小 —— 改成按比例，两个尺寸都合理。
  const R = side / 2 - Math.round(side * 0.137);
  const market = marketSegments(R);
  const segs = market.segs;
  const small = market.small;
  // 图注跟着实际情况变：宽屏下 24 个都画得下，就不能说"并成了其他段"
  const noteEl = document.getElementById("market-note");
  if (noteEl) {
    noteEl.textContent = small.length
      ? t("market.noteFold", "弧长不足 6px 的 {n} 个行业并成了「其他 {n} 个行业」那一段（鼠标移上去会列出它们的名字）；全部 24 个行业的完整名单在全景图谱和每个行业页里，一个不少。").replace(/\{n\}/g, small.length)
      : t("market.noteAll", "每个行业一段，段的大小就是它占全市场的比例。点一段进那个行业；鼠标停在段上会在中心显示它的家数、占比、涨跌和市值。");
  }
  const band = Math.max(18, R * 0.3);         // 环的厚度
  const rOut = R, rIn = R - band;
  cv._segs = segs;
  cv._R = R;
  const INK = cssVar("--text", "#D8DFE9");
  const FAINT = cssVar("--text-faint", "#5E6B7C");
  const INK2 = cssVar("--text", "#D8DFE9");
  const RISEC = cssVar("--rise", "#F6465D");
  const FALLC = cssVar("--fall", "#2FB67C");
  const MUTED = cssVar("--border-strong", "#38445A");
  const CYCLE = partCycle();
  const OTHER = partOther();

  // 扫入动画：cv._introT ∈ [0,1]，只画 12 点顺时针到 cutoff 的部分（驱动器在 afterHomeBody）
  const intro = cv._introT == null ? 1 : cv._introT;
  const cutoff = -Math.PI / 2 + Math.PI * 2 * intro;

  // 环
  segs.forEach((sg, i) => {
    if (sg.a0 >= cutoff) return;               // 扫入还没走到这一段
    const a1 = Math.min(sg.a1, cutoff);
    const on = i === hover;
    ctx.beginPath();
    ctx.arc(cx, cy, rOut, sg.a0, a1);
    ctx.arc(cx, cy, rIn, a1, sg.a0, true);
    ctx.closePath();
    // 段色按序号取三色循环 —— 相邻必不同（金色已归数据色，所以高亮改成描边）
    ctx.fillStyle = sg.ind ? CYCLE[i % CYCLE.length] : OTHER;
    ctx.fill();
    if (on) {
      ctx.strokeStyle = INK2;
      ctx.lineWidth = 1.6;
      ctx.stroke();
    }
  });

  // 名字不画在环上（旋转文字会倒着），改成：悬停弹方块 + 环下面一排横排行业名 chips
  cv._labelInfo = { total: segs.length, shown: 0, all: false, hint: "hover" };

  // 中心读数（扫入结束后再出现，免得"4,071"比环先到）
  ctx.textAlign = "center";
  if (intro < 1) return;
  if (hover >= 0 && segs[hover]) {
    const sg = segs[hover];
    const q = indexData?.quotes || {};
    let sum = 0, cnt = 0, cap = 0;
    const members = sg.ind ? (graphData?.industries?.[sg.ind] || [])
      : sg.members.flatMap((x) => graphData?.industries?.[x.ind] || []);
    for (const tk of members) {
      const f = q[tk] || {};
      if (typeof f.changePercent === "number") { sum += f.changePercent; cnt++; }
      if (typeof f.marketCap === "number") cap += f.marketCap;
    }
    const avg = cnt ? sum / cnt : null;
    ctx.font = `500 20px ${font}`;
    ctx.fillStyle = INK;
    ctx.fillText(sg.ind ? t("sector." + sg.ind, sg.ind) : t("market.othersFmt", "其他 {n} 个行业").replace("{n}", sg.members.length), cx, cy - 26);
    ctx.font = `400 12px ${font}`;
    ctx.fillStyle = FAINT;
    ctx.fillText(`${fmtInt(sg.n)} ${t("stat.companies", "家上市公司")} · ${t("market.share", "占")} ${(sg.share * 100).toFixed(1)}%`, cx, cy - 4);
    ctx.fillStyle = avg == null ? FAINT : (avg < 0 ? FALLC : RISEC);
    ctx.fillText(`${fmtPct(avg)} · ${t("ind.capTotal", "市值")} ${fmtCap(cap)}`, cx, cy + 16);
    // 其他段：把被折叠的行业名列出来（折叠≠隐藏）
    if (!sg.ind) {
      ctx.font = `400 11px ${font}`;
      ctx.fillStyle = FAINT;
      const names = sg.members.map((x) => t("sector." + x.ind, x.ind));
      const rows = [];
      for (let k = 0; k < names.length && rows.length < 3; k += 4) rows.push(names.slice(k, k + 4).join("　"));
      rows.forEach((r, i) => ctx.fillText(r, cx, cy + 38 + i * 15));
    }
  } else {
    ctx.font = `500 26px ${font}`;
    ctx.fillStyle = INK;
    ctx.fillText(fmtInt(marketSegTotals().tot), cx, cy - 14);
    ctx.font = `400 12px ${font}`;
    ctx.fillStyle = FAINT;
    ctx.fillText(t("market.centerSub", "{n} 个申万一级行业").replace("{n}", fmtInt(marketSegTotals().inds)), cx, cy + 10);
    ctx.fillText(t("market.centerHint", "点一段进那个行业"), cx, cy + 32);
  }
}

// 用于中心读数的合计（放在函数外，避免在 draw 里反复算）
function marketSegTotals() {
  const tot = indexData?.totals || {};
  return { tot: tot.companies || 0, inds: tot.industries || 0 };
}

function setupMarketRing(cv) {
  if (!cv) return;
  const tipEl = () => document.getElementById("tile-tip");
  const pick = (e) => {
    const r = cv.getBoundingClientRect();
    const side = r.width;
    const mx = e.clientX - r.left - side / 2, my = e.clientY - r.top - side / 2;
    const dist = Math.hypot(mx, my);
    const R = cv._R || side / 2 - 96;
    const band = Math.max(18, R * 0.3);
    if (dist < R - band - 4 || dist > R + 6) return -1;
    let ang = Math.atan2(my, mx) + Math.PI / 2;
    while (ang < 0) ang += Math.PI * 2;
    while (ang >= Math.PI * 2) ang -= Math.PI * 2;
    const segs = cv._segs || [];
    for (let i = 0; i < segs.length; i++) {
      let a0 = segs[i].a0 + Math.PI / 2, a1 = segs[i].a1 + Math.PI / 2;
      if (ang >= a0 && ang <= a1) return i;
    }
    return -1;
  };
  cv.onmousemove = (e) => {
    const idx = pick(e);
    if (idx !== cv._hover) {
      cv._hover = idx;
      drawMarketRing(cv, idx);
      cv.style.cursor = idx >= 0 ? "pointer" : "default";
    }
    // 悬停弹一个小方块，上面写行业名（外加大数）—— 比把字转到环上强得多
    const tip = tipEl();
    const sg = (cv._segs || [])[idx];
    if (tip) {
      if (sg) {
        tip.hidden = false;
        tip.innerHTML = `<b>${esc(sg.ind ? t("sector." + sg.ind, sg.ind)
          : t("market.othersFmt", "其他 {n} 个行业").replace("{n}", sg.members.length))}</b>`
          + `<span>${esc(fmtInt(sg.n))} ${esc(t("stat.companies", "家"))} · `
          + `${esc(t("market.share", "占"))} ${(sg.share * 100).toFixed(1)}%</span>`;
        tip.style.left = `${e.clientX + 14}px`;
        tip.style.top = `${e.clientY + 14}px`;
      } else {
        tip.hidden = true;
      }
    }
  };
  cv.onmouseleave = () => {
    const tip = tipEl();
    if (tip) tip.hidden = true;
    if (cv._hover === -1) return;
    cv._hover = -1;
    drawMarketRing(cv, -1);
    cv.style.cursor = "default";
  };
  cv.onclick = (e) => {
    const idx = pick(e);
    const sg = (cv._segs || [])[idx];
    if (sg && sg.ind) location.hash = `#/i/${encodeURIComponent(sg.ind)}`;
    else if (sg) location.hash = "#/worldmap";     // "其他"那一段 → 去全景图谱看全部 24 个
  };

  // 名字那一排 ↔ 环：悬停 chip 就把环上对应段点亮（两边互相找得到）
  const chipsEl = document.getElementById("market-chips");
  if (chipsEl) {
    const light = (ind) => {
      const idx = (cv._segs || []).findIndex((sg) => sg.ind === ind);
      if (idx === cv._hover) return;
      cv._hover = idx;
      drawMarketRing(cv, idx);
    };
    chipsEl.addEventListener("mouseover", (e) => {
      const a = e.target.closest("[data-mind]");
      if (a) light(a.dataset.mind);
    });
    chipsEl.addEventListener("mouseleave", () => light(null));
  }
}

function marketRingHTML() {
  const tot = marketSegTotals();
  return `
    <section class="sec market-wrap">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("market.title", "全市场 {n} 个申万一级行业").replace("{n}", fmtInt(tot.inds)))}</h2>
        <span class="sec-sub">${esc(t("market.sub", "段的大小 = 该行业公司数占全市场 {c} 家的比例；点一段进那个行业").replace("{c}", fmtInt(tot.tot)))}</span>
        <span class="sec-rule"></span>
      </div>
      <figure class="market-figure">
        <canvas id="market-ring" class="market-canvas" role="img"
                aria-label="${esc(t("market.aria", "全市场行业构成环图，共 {n} 个申万一级行业").replace("{n}", fmtInt(tot.inds)))}"></canvas>
        <figcaption class="ring-note" id="market-note"></figcaption>
        <div class="market-chips" id="market-chips">
          ${(indexData?.industryList || [])
            .slice()
            .sort((a, b) => (graphData?.industries?.[b] || []).length - (graphData?.industries?.[a] || []).length)
            .map((ind) => `<a class="chip" href="#/i/${encodeURIComponent(ind)}" data-mind="${esc(ind)}">`
              + `${esc(t("sector." + ind, ind))}<span class="chip-n">${esc(fmtInt((graphData?.industries?.[ind] || []).length))}</span></a>`)
            .join("")}
        </div>
      </figure>
    </section>
    <div class="tile-tip" id="tile-tip" hidden></div>`;
}

let searchChain = null;            // 首页搜索结果里点中的环节（null = 不限）

function searchResultsHTML(term) {
  const low = term.toLowerCase();
  // 名字/代码/行业命中
  let hits = (indexData?.companies || []).filter((c) =>
    c.name.toLowerCase().includes(low) || c.ticker.toLowerCase().includes(low)
    || String(c.industry).toLowerCase().includes(low)
    || String(t("sector." + c.industry, c.industry)).toLowerCase().includes(low));
  // 环节名命中：搜"锂电池"要能搜出这个环节里的公司
  const hitBoards = (graphData?.boardList || []).filter((b) => b.toLowerCase().includes(low));
  if (hitBoards.length && !searchChain) {
    const seen = new Set(hits.map((c) => c.ticker));
    for (const b of hitBoards) {
      for (const tk of (graphData.boards[b] || [])) {
        if (seen.has(tk)) continue;
        const c = (indexData?.companies || []).find((x) => x.ticker === tk);
        if (c) { hits.push(c); seen.add(tk); }
      }
    }
  }
  // 点过环节芯片后，只留这个环节的公司
  if (searchChain) {
    const members = new Set(graphData?.boards?.[searchChain] || []);
    hits = hits.filter((c) => members.has(c.ticker));
  }
  const inds = (indexData?.industryList || []).filter((n) =>
    String(n).toLowerCase().includes(low)
    || String(t("sector." + n, n)).toLowerCase().includes(low));
  // 环节芯片最多列 6 个（"锂"能命中十几个概念，全列出来会盖掉结果）
  const chainChips = hitBoards.slice(0, 6).map((b) =>
    `<button class="chip" type="button" data-schain="${esc(b)}" aria-pressed="${searchChain === b}">`
    + `${esc(b)}<span class="chip-n">${esc(fmtInt((graphData?.boards?.[b] || []).length))}</span></button>`).join("");

  const cap = 120;
  return `
    ${(inds.length || chainChips) ? `<div class="search-inds">
      ${inds.length ? `<span class="sec-sub">${esc(t("search.inds", "匹配的行业"))}</span>`
        + inds.map((n) => `<a class="chip" href="#/i/${encodeURIComponent(n)}">${esc(t("sector." + n, n))}</a>`).join("") : ""}
      ${chainChips ? `<span class="sec-sub">${esc(t("search.chains", "匹配的产业链环节"))}</span>${chainChips}`
        + (hitBoards.length > 6 ? `<span class="sec-sub">${esc(t("search.moreChains", "还有 {n} 个").replace("{n}", hitBoards.length - 6))}</span>` : "")
        + `<button class="chip" type="button" data-schain="" aria-pressed="${searchChain === null}">${esc(t("search.chainAll", "不限环节"))}</button>` : ""}
    </div>` : ""}
    <section class="sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("search.results", "搜索结果"))}</h2>
        <span class="sec-sub">${esc(t("search.hint", "清空搜索框即回到行业总览"))}</span>
        <span class="sec-rule"></span>
        <span class="sec-sub">${esc(fmtInt(hits.length))} ${esc(t("ind.unitCompanies", "家"))}</span>
      </div>
      ${hits.length
        ? `<div class="card-grid ${settings.width === "wide" ? "wide" : ""}">`
          + hits.slice(0, cap).map((c) => cardHTML(c)).join("") + `</div>`
          + (hits.length > cap
            ? `<p class="sec-sub" style="margin-top:14px">${esc(t("list.capped", "只显示前 {n} 条，请输入更具体的关键词").replace("{n}", cap))}</p>`
            : "")
        : `<p class="empty">${esc(t("list.none", "没有匹配的公司，换个关键词试试。"))}</p>`}
    </section>`;
}

function homeBodyHTML() {
  const term = searchTerm.trim();
  return term ? searchResultsHTML(term) : marketRingHTML();
}

// 首页正文渲染完之后要画环（canvas 必须先插进 DOM 才能量尺寸）
function afterHomeBody() {
  const cv = document.getElementById("market-ring");
  if (!cv) return;
  // 大环扫入：从 12 点顺时针把各段依次"画"出来。悬停重画共享 cv._introT，
  // 所以动画中途鼠标划上来不会跳变，只会带着当前进度继续画。
  if (!motionOff() && cv._introT == null) {
    cv._introT = 0;
    const t0 = performance.now();
    const dur = 720;
    const step = (now) => {
      if (!cv.isConnected) return;
      const p = Math.min(1, (now - t0) / dur);
      cv._introT = 1 - Math.pow(1 - p, 3);
      drawMarketRing(cv, cv._hover ?? -1);
      if (p < 1) requestAnimationFrame(step);
      else cv._introT = 1;
    };
    requestAnimationFrame(step);
  } else {
    cv._introT = 1;
    drawMarketRing(cv, -1);
  }
  setupMarketRing(cv);
}

function renderHome(fresh) {
  const body = document.getElementById("home-body");
  // 原地重绘：搜索/清空时只换正文，hero 和滚动位置都不动
  if (!fresh && body) { body.innerHTML = homeBodyHTML(); afterHomeBody(); return; }

  app.innerHTML = `<div id="home-hero-slot">${heroHTML()}</div>`
    + `<div id="home-body">${homeBodyHTML()}</div>`;
  setupHomeChrome();
  afterHomeBody();
}

function setupHomeChrome() {
  const titleEl = document.getElementById("home-hero-title");
  if (titleEl) typeTitle(titleEl, t("home.title", "链谱（ChainAtlas）"), motionOff() ? 0 : 55);
  countUpIn(app);
  setupSpentHero();
}

/* ---- 行业页：#/i/{行业} --------------------------------------------------
   一个行业的完整视图：环节分布（可点筛选）+ 全部公司（可搜、可分页）。 */
function indMembers(ind) {
  return graphData?.industries?.[ind] || [];
}

function indChainDist(ind) {
  const freq = new Map();
  for (const tk of indMembers(ind)) {
    for (const bi of (graphData?.boardIdxOf?.[tk] || [])) {
      freq.set(bi, (freq.get(bi) || 0) + 1);
    }
  }
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1] || a[0] - b[0])
    .map(([bi, n]) => ({ name: graphData.boardList[bi], n }));
}

function indFiltered(ind) {
  const low = indTerm.trim().toLowerCase();
  const byTicker = new Map((indexData?.companies || []).map((c) => [c.ticker, c]));
  return indMembers(ind)
    .map((tk) => byTicker.get(tk))
    .filter(Boolean)
    .filter((c) => {
      if (indSelMarket && c.board !== indSelMarket) return false;
      if (indSelChain && !boardsOf(c.ticker).includes(indSelChain)) return false;
      if (!low) return true;
      return c.name.toLowerCase().includes(low) || c.ticker.toLowerCase().includes(low);
    });
}

function indListHTML(ind) {
  const list = indFiltered(ind);
  if (!list.length) return `<p class="empty">${esc(t("ind.none", "这个条件下没有公司，换个环节或清掉筛选试试。"))}</p>`;
  const shown = list.slice(0, indLimit);
  const more = list.length - shown.length;
  return `<div class="card-grid ${settings.width === "wide" ? "wide" : ""}">`
    + shown.map((c) => cardHTML(c)).join("")
    + `</div>`
    + (more > 0
      ? `<div class="more-row">
          <button class="chip" id="ind-more" type="button">${esc(t("ind.more", "再看 {n} 家")
            .replace("{n}", Math.min(IND_STEP, more)))}</button>
          <span class="sec-sub">${esc(t("ind.showingFmt", "已显示 {a} / {b} 家")
            .replace("{a}", fmtInt(shown.length)).replace("{b}", fmtInt(list.length)))}</span>
        </div>`
      : `<p class="sec-sub" style="margin-top:14px">${esc(t("ind.showingAllFmt", "已显示全部 {b} 家")
          .replace("{b}", fmtInt(list.length)))}</p>`);
}

// 只重绘列表和计数，不动整页 —— 否则每次点筛选都会跳回页首
function refreshIndList() {
  const ind = indCurrent;
  if (!ind) return;
  const listEl = document.getElementById("ind-list");
  if (listEl) listEl.innerHTML = indListHTML(ind);
  const countEl = document.getElementById("ind-count");
  if (countEl) countEl.textContent = `${fmtInt(indFiltered(ind).length)} ${t("ind.unitCompanies", "家")}`;
  document.querySelectorAll("#ind-chains [data-chain]").forEach((b) => {
    b.setAttribute("aria-pressed", String(
      b.dataset.chain === "" ? indSelChain === null : b.dataset.chain === indSelChain));
  });
  document.querySelectorAll("#ind-toolbar [data-market]").forEach((b) => {
    b.setAttribute("aria-pressed", String(
      b.dataset.market === "" ? indSelMarket === null : b.dataset.market === indSelMarket));
  });
}

// ── 产业链档案（行业/公司/设备）共用渲染件 ─────────────────────────
// 数据原则（与《产业链网页修改方向》一致）：已有数据如实展示并标注口径；
// 有档案但缺字段 → 显示「待接入具体数据接口」；没有档案 → 整块不渲染，不刷屏。
function chainPending() {
  return `<span class="pending-note">${esc(t("chain.pending", "待接入具体数据接口"))}</span>`;
}

function chainField(label, valueHtml) {
  return `<div class="cf"><span class="cf-k">${esc(label)}</span><span class="cf-v">${valueHtml}</span></div>`;
}

function chainTextOrPending(text) {
  return text ? esc(text) : chainPending();
}

function chainOutputHTML(ov) {
  // 产值/市场规模：status=ready 且有值才显示数字（带年份与来源）；其余一律占位
  if (!ovReady(ov)) return chainPending();
  const num = `${esc(String(ov.value))}${ov.unit ? " " + esc(ov.unit) : ""}`;
  const yr = ov.year ? ` <span class="cf-meta">${esc(String(ov.year))} 年</span>` : "";
  const src = ov.source ? ` <span class="cf-meta">来源：${esc(String(ov.source))}</span>` : "";
  return `<b class="cf-num">${num}</b>${yr}${src}`;
}

// 产值是否已就绪（渲染层据此决定"显示数字"还是"整个字段不渲染"）
function ovReady(ov) {
  return !!ov && ov.status === "ready" && ov.value != null;
}

function chainDemoTag(entry) {
  return entry && entry.demo ? ` <span class="demo-tag">${esc(t("chain.demoTag", "示例数据"))}</span>` : "";
}

function chainSectionHTML(title, entry, fields) {
  return `
    <section class="sec chain-sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(title)}${chainDemoTag(entry)}</h2>
        <span class="sec-sub">${esc(t("chain.sub", "产业链档案 · 仅展示已接入的数据"))}</span>
        <span class="sec-rule"></span>
      </div>
      <div class="chain-fields">${fields}</div>
    </section>`;
}

// 设备引用统一渲染：有 ID 的设备变成可点的芯片，纯文本保持文本
function chainDeviceChips(refs) {
  const devs = chainDataCache && chainDataCache.devices ? chainDataCache.devices : {};
  return refs.map((r) => {
    // 引用有两种形态：设备 ID（在 devices 里有档案 → 渲染成可点芯片）和
    // 纯文本描述（设备库里没有 → 保持文本，不硬造链接）
    if (typeof r === "string" && !devs[r]) return `<span class="cf-text">${esc(r)}</span>`;
    const d = devs[r] || {};
    const label = d.name || r;
    return `<a class="chip" href="#/e/${encodeURIComponent(r)}">${esc(label)}<span class="chip-n">→</span></a>`;
  }).join("");
}

async function renderIndustryPage(ind) {
  app.innerHTML = "";
  startLoading();
  const [, g, chain] = await Promise.all([loadGraph(), loadChainData()]);
  if (parseRoute().name !== "industry") return;
  stopLoading();
  if (!g || !g.industries[ind]) {
    app.innerHTML = `<p class="empty">${esc(t("ind.unknown", "没有这个行业。"))}`
      + ` <a href="#/">${esc(t("crumb.home", "全部行业"))}</a></p>`;
    return;
  }

  // 换了一个行业就重置筛选，同一个行业返回时保留（用户刚筛过，别让他重筛）
  if (ind !== indCurrent) {
    indCurrent = ind;
    indTerm = "";
    indSelChain = null;
    indSelMarket = null;
    indLimit = IND_STEP;
  }

  const st = industryStat(ind);
  const dist = indChainDist(ind);
  const markets = ["沪市主板", "深市主板", "创业板", "科创板"];

  const chainChips = [`<button class="chip" type="button" data-chain="" aria-pressed="${indSelChain === null}">${esc(t("ind.chainAll", "全部环节"))}</button>`]
    .concat(dist.slice(0, IND_CHAIN_CAP).map((b) => `<button class="chip" type="button" data-chain="${esc(b.name)}" aria-pressed="${indSelChain === b.name}">`
      + `${esc(b.name)}<span class="chip-n">${esc(fmtInt(b.n))}</span></button>`))
    .join("");
  const marketChips = [`<button class="chip" type="button" data-market="" aria-pressed="${indSelMarket === null}">${esc(t("filter.boardAll", "全部板块"))}</button>`]
    .concat(markets.map((b) => `<button class="chip" type="button" data-market="${esc(b)}" aria-pressed="${indSelMarket === b}">${esc(t("board." + b, b))}</button>`))
    .join("");

  app.innerHTML = `
    <div class="crumb"><a href="#/"><span class="arr" aria-hidden="true">←</span> ${esc(t("crumb.home", "全部行业"))}</a></div>

    <header class="ind-head">
      <h1 class="ind-title">${esc(t("sector." + ind, ind))}</h1>
      <div class="ind-stats">
        <span class="ind-stat"><b data-count="${st.count}">${esc(fmtInt(st.count))}</b><span>${esc(t("stat.companies", "家上市公司"))}</span></span>
        <span class="ind-stat"><b data-count="${dist.length}">${esc(fmtInt(dist.length))}</b><span>${esc(t("stat.boards", "个产业链环节"))}</span></span>
        <span class="ind-stat"><b>${esc(fmtCap(st.cap))}</b><span>${esc(t("ind.capLabel", "市值合计"))}</span></span>
        <span class="ind-stat"><b class="${changeClass(st.avg)}">${st.avg == null ? "—" : esc(fmtPct(st.avg))}</b><span>${esc(t("ind.avgLabel", "今日平均涨跌"))}</span></span>
      </div>
      <p class="ind-map-link"><a class="chip" href="#/m/${encodeURIComponent(ind)}">${esc(t("ind.ringLink", "看这个行业的大环图 →"))}</a></p>
    </header>

    ${chain && chain.industries && chain.industries[ind] ? chainSectionHTML(
      t("chain.industryTitle", "行业档案"),
      chain.industries[ind],
      chainField(t("chain.fIntro", "行业简介"), chainTextOrPending(chain.industries[ind].intro))
      + chainField(t("chain.fPosition", "产业链位置"), chainTextOrPending(chain.industries[ind].chain_position))
      + chainField(t("chain.fOutput", "行业产值 / 市场规模"), chainOutputHTML(chain.industries[ind].output_value))
    ) : ""}

    <section class="sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("ind.distTitle", "产业链环节分布"))}</h2>
        <span class="sec-sub">${esc(t("ind.distSub", "这个行业里的公司都落在哪些环节上；点一个环节就只看那个环节的公司"))}</span>
        <span class="sec-rule"></span>
      </div>
      <div class="toolbar" id="ind-chains">${chainChips}
        ${dist.length > IND_CHAIN_CAP ? `<span class="sec-sub">${esc(t("ind.moreChains", "还有 {n} 个环节未列出").replace("{n}", dist.length - IND_CHAIN_CAP))}</span>` : ""}
      </div>
    </section>

    <section class="sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("ind.compTitle", "这个行业的公司"))}</h2>
        <span class="sec-rule"></span>
        <span class="sec-sub" id="ind-count">${esc(fmtInt(indFiltered(ind).length))} ${esc(t("ind.unitCompanies", "家"))}</span>
      </div>
      <div class="toolbar" id="ind-toolbar">
        <input class="ind-q" id="ind-q" type="search" autocomplete="off"
               placeholder="${esc(t("ind.searchPh", "在这个行业里搜公司"))}" value="${esc(indTerm)}" />
        <span class="toolbar-sep" aria-hidden="true"></span>
        <span class="sec-sub">${esc(t("filter.board", "板块"))}</span>${marketChips}
      </div>
      <div id="ind-list">${indListHTML(ind)}</div>
    </section>`;

  // 事件直接绑在新元素上（每次整页渲染都会重建，不会叠加）
  countUpIn(app);
  document.getElementById("ind-chains")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-chain]");
    if (!btn) return;
    indSelChain = btn.dataset.chain === "" ? null : btn.dataset.chain;
    indLimit = IND_STEP;
    refreshIndList();
  });
  document.getElementById("ind-toolbar")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-market]");
    if (!btn) return;
    indSelMarket = btn.dataset.market === "" ? null : btn.dataset.market;
    indLimit = IND_STEP;
    refreshIndList();
  });
  document.getElementById("ind-toolbar")?.addEventListener("input", (e) => {
    if (e.target.id !== "ind-q") return;
    indTerm = e.target.value;
    indLimit = IND_STEP;
    refreshIndList();
  });
  document.getElementById("ind-list")?.addEventListener("click", (e) => {
    if (!e.target.closest("#ind-more")) return;
    indLimit += IND_STEP;
    refreshIndList();
  });
}

/* ---- 已消耗的 hero -------------------------------------------------------
   往下滚的行为和平时一样。hero 完全滚出视口的那一刻，它被换成一条细 bar——
   这件事发生在屏幕外，并在同一帧里修正了滚动位置，所以视觉上什么都没动。
   因此往回滚时落在 bar 上，而不是又回到 hero。bar 上的箭头可以把 hero 叫回来。

   状态按会话记住，所以从公司页返回（它会还原记住的滚动位置）会直接渲染成 bar，
   不会在读者眼皮底下重跑一次替换。

   判据用 IntersectionObserver，不用 scroll 监听：scroll 监听必须自己算
   "滚过去了没有"，而 "把 hero 叫回来" 这个动作本身也会发出 scroll 事件，
   于是刚恢复的 hero 会在同一轮里又被判成"已滚过"、立刻消耗掉（自己吃掉自己）。
   观察者只在元素真的离开视口时才回调，不存在这个自触发回路。 */
const HERO_SPENT_KEY = "cnchain.heroSpent";
let heroIO = null;

function readHeroSpent() {
  try { return sessionStorage.getItem(HERO_SPENT_KEY) === "1"; } catch { return false; }
}
function writeHeroSpent(v) {
  try {
    if (v) sessionStorage.setItem(HERO_SPENT_KEY, "1");
    else sessionStorage.removeItem(HERO_SPENT_KEY);
  } catch { /* ignore */ }
}

function setupSpentHero() {
  const hero = document.getElementById("home-hero");
  const bar = document.getElementById("home-hero-bar");
  if (!hero || !bar) return;
  if (heroIO) { heroIO.disconnect(); heroIO = null; }

  const consume = () => {
    if (!hero.isConnected || hero.hidden) return;
    // Chrome 的滚动锚定也会在视口上方内容变高变矮时自行补偿，
    // 两套补偿会叠加，页面最后正好短掉一条 bar 的高度。
    // 替换期间先把它关掉，让只有我们的算术在移动视口。
    const root = document.documentElement;
    const prevAnchor = root.style.overflowAnchor;
    root.style.overflowAnchor = "none";

    bar.hidden = false;
    // 在两者都还在布局里的时候量，并在 hero 消失之前把目标位置定下来：
    // 移除 hero 会让文档变矮，浏览器会当场把 scrollY 夹到新的最大值——
    // 那时候再去读相对差值，读到的已经是夹过的值，会把读者甩到更上面去。
    const target = Math.max(0, window.scrollY - (hero.offsetHeight - bar.offsetHeight));
    hero.hidden = true;
    window.scrollTo(0, target);
    setTimeout(() => { root.style.overflowAnchor = prevAnchor; }, 0);
    writeHeroSpent(true);
    if (heroIO) { heroIO.disconnect(); heroIO = null; }
  };

  const observe = () => {
    if (heroIO) { heroIO.disconnect(); heroIO = null; }
    if (!window.IntersectionObserver) return;
    heroIO = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting || hero.hidden) continue;
        // bottom <= 0 才代表 hero 整体跑到了视口上方（真的"滚过去了"）；
        // 若它在视口下方，bottom 仍然为正，不该消耗。
        if (en.boundingClientRect.bottom > 0) continue;
        consume();
      }
    }, { threshold: 0 });
    heroIO.observe(hero);
  };

  // 把 hero 叫回来之后不能立刻布防：此时页面还停在下方，hero 一露出来就
  // 已经在视口外，观察者会当场把它又消耗掉。等滚动真的回到顶部再布防。
  const armWhenAtTop = () => {
    if (window.scrollY <= 4) { observe(); return; }
    const onScroll = () => {
      if (!hero.isConnected) { window.removeEventListener("scroll", onScroll); return; }
      if (window.scrollY <= 4) { window.removeEventListener("scroll", onScroll); observe(); }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    // 保险：4 秒内还没到顶部（例如用户中途又往下滚了），也照常布防
    setTimeout(() => {
      window.removeEventListener("scroll", onScroll);
      if (!heroIO && !hero.hidden && hero.isConnected) observe();
    }, 4000);
  };

  if (readHeroSpent()) {
    bar.hidden = false; hero.hidden = true;      // 不需要修正，直接呈现
  } else {
    hero.hidden = false; bar.hidden = true;
    observe();
  }

  document.getElementById("hero-bar-up")?.addEventListener("click", () => {
    writeHeroSpent(false);
    hero.hidden = false;
    bar.hidden = true;
    window.scrollTo({ top: 0, behavior: motionOff() ? "auto" : "smooth" });
    armWhenAtTop();
  });
}

/* ---- 公司页 -------------------------------------------------------------- */
function metric(label, value, big = false) {
  return `<span class="metric">
      <span class="metric-label">${esc(label)}</span>
      <span class="metric-val${big ? " big" : ""}">${esc(value)}</span>
    </span>`;
}

function linkColor(relation, tier) {
  if (relation === "upstream") return tier === 1 ? "var(--up1)" : "var(--up2)";
  return tier === 1 ? "var(--dn1)" : "var(--dn2)";
}
// 分组底色 / 列色带：都压到页面底色附近，只留一点冷暖方向，
// 免得色块比内容还抢眼——衬底从来是衬纸，不是主角。
// 颜色运行时从 CSS 变量取，深色/浅色两套主题各自有值。
function tintFor(relation, tier) {
  if (relation === "upstream") return cssVar(tier === 1 ? "--tint-up1" : "--tint-up2", "#16222E");
  return cssVar(tier === 1 ? "--tint-dn1" : "--tint-dn2", "#261E14");
}
function bandColor(dir, tier) {
  if (dir === "upstream") return cssVar(tier === 1 ? "--band-up1" : "--band-up2", "#1B2836");
  return cssVar(tier === 1 ? "--band-dn1" : "--band-dn2", "#2B2115");
}

function buildClusters(nodes) {
  const map = new Map();
  for (const n of nodes) {
    const key = `${n.relation}|${n.tier}|${n.role}`;
    let c = map.get(key);
    if (!c) { c = { key, dir: n.relation, tier: n.tier, group: n.role, members: [] }; map.set(key, c); }
    c.members.push(n);
  }
  return [...map.values()];
}
function orderedClusters(clusters, dir, tier) {
  return clusters
    .filter((c) => c.dir === dir && c.tier === tier)
    .sort((a, b) => b.members.length - a.members.length || a.group.localeCompare(b.group, "zh"));
}

function mapCard(n) {
  const color = linkColor(n.relation, n.tier);
  const dep = (n.depPct != null) ? `
        <span class="dep" title="${esc(n.name)} ${esc(fmtNum(n.depPct, 1))}% ${esc(t("company.depOn", ""))} (${esc(n.depAsOf || "")})">
          <span class="dep-bar"><span class="dep-fill" style="width:${clamp(n.depPct, 0, 100)}%;background:${color}"></span></span>
          <span class="dep-val" style="color:${color}">${esc(fmtNum(n.depPct, 1))}%</span>
        </span>` : "";
  return `
    <div class="vcm-card">
      <a class="map-node is-linked" href="#/c/${encodeURIComponent(n.ticker)}" style="border-left-color:${color}">
        <span class="map-node-text">
          <span class="map-node-name">${esc(n.name)}</span>
          <span class="map-node-role">${esc(n.role)}</span>
          <span class="seg">${esc(n.ticker)}</span>
          ${dep}
        </span>
        <span class="map-link-arrow" aria-hidden="true">↗</span>
      </a>
      <div class="vcm-tip" role="tooltip">
        <span class="vcm-tip-ticker">${esc(n.ticker)} · ${esc(t("sector." + n.sector, n.sector))}</span>
        <span class="vcm-tip-rel">${esc(n.name)} — ${esc(n.role)}</span>
      </div>
    </div>`;
}

function clusterHTML(c) {
  const open = expandedClusters.has(c.key);
  const accent = linkColor(c.dir, c.tier);
  const face = c.members[0];
  const rest = c.members.slice(1);
  return `
    <div class="vcm-cluster" data-key="${esc(c.key)}" data-dir="${esc(c.dir)}" data-tier="${esc(c.tier)}"
         data-via="${esc(face.via || "")}"
         style="background:${tintFor(c.dir, c.tier)};border-color:${accent}">
      <button class="vcm-cluster-head" type="button" aria-expanded="${open}">
        <span class="vcm-cluster-title">${esc(c.group)}</span>
        <span class="badge vcm-count">${c.members.length}</span>
        <span class="vcm-chev ${open ? "open" : ""}" aria-hidden="true"></span>
      </button>
      <div class="vcm-face">${face ? mapCard(face) : ""}</div>
      ${rest.length ? `<div class="vcm-rest" data-open="${open}"><div class="vcm-rest-inner">${rest.map(mapCard).join("")}</div></div>` : ""}
    </div>`;
}

function clusterCol(clusters, dir, tier) {
  const cs = orderedClusters(clusters, dir, tier);
  if (!cs.length) return "";
  const tierKey = dir === "upstream"
    ? (tier === 1 ? "company.tierUp1" : "company.tierUp2")
    : (tier === 1 ? "company.tierDown1" : "company.tierDown2");
  const label = t(tierKey, `${dir === "upstream" ? "上游" : "下游"} · Tier ${tier}`);
  return `<div class="vcm-col" data-dir="${dir}" data-tier="${tier}">
      <div class="tier-label">${esc(label)}</div>${cs.map(clusterHTML).join("")}</div>`;
}

function mapHTML(data) {
  const nodes = data.nodes || [];
  const a = data.anchor;
  const clusters = buildClusters(nodes);
  const hasDown = nodes.some((n) => n.relation === "downstream");
  // 下游为空时放一个"终端市场"占位，说明这条链的终点在覆盖范围之外
  const terminal = hasDown ? "" : `
      <div class="vcm-col" data-dir="downstream" data-tier="1">
        <div class="tier-label">${esc(t("company.tierDown1", "下游 · 一级"))}</div>
        <div class="vcm-cluster" style="background:${tintFor("downstream", 1)};border-color:var(--terminal)">
          <div class="vcm-face">
            <div class="vcm-card">
              <div class="map-node map-terminal">
                <span class="map-node-text">
                  <span class="map-node-name">${esc(t("company.terminalName", "终端市场"))}</span>
                  <span class="map-node-role">${esc(t("company.terminalRole", ""))}</span>
                </span>
              </div>
              <div class="vcm-tip" role="tooltip"><span class="vcm-tip-rel">${esc(t("company.terminalHint", ""))}</span></div>
            </div>
          </div>
        </div>
      </div>`;

  return `
    <div class="map" id="vcm-map">
      <div class="vcm-stage" id="vcm-stage">
        <div class="vcm-bands" id="vcm-bands" aria-hidden="true"></div>
        <div class="vcm-dividers" id="vcm-dividers" aria-hidden="true"></div>
        <svg class="vcm-links" id="vcm-links" aria-hidden="true"></svg>
        <div class="vcm-grid" id="vcm-grid">
          ${clusterCol(clusters, "upstream", 2)}
          ${clusterCol(clusters, "upstream", 1)}
          <div class="vcm-col vcm-anchor-col">
            <div class="tier-label">${esc(t("company.anchor", "锚点"))}</div>
            <div class="vcm-cluster vcm-anchor-cluster" data-key="__anchor__">
              <div class="vcm-face" style="padding:8px">
                <div class="map-node map-anchor" data-id="__anchor__">
                  <span class="map-node-text">
                    <span class="map-node-name">${esc(a.name)}</span>
                    <span class="map-node-role">${esc(a.ticker)} · ${esc(t("sector." + a.sector, a.sector))}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
          ${clusterCol(clusters, "downstream", 1)}
          ${terminal}
          ${clusterCol(clusters, "downstream", 2)}
        </div>
      </div>
    </div>`;
}

// 适应宽度（"fit"）或原始尺寸 + 横向平移（"full"）
function fitMap() {
  const mapEl = document.getElementById("vcm-map");
  const stage = document.getElementById("vcm-stage");
  const grid = document.getElementById("vcm-grid");
  if (!mapEl || !stage || !grid) return;
  stage.style.transform = "none";
  const naturalW = grid.scrollWidth;
  const naturalH = grid.scrollHeight;
  const viewW = mapEl.clientWidth;
  if (mapZoom === "fit") {
    const s = Math.min(1, viewW / naturalW);
    const offset = Math.max(0, (viewW - naturalW * s) / 2);
    // 缩放挂在 stage 上，origin 就必须设在 stage 上。
    // 设到外层 .map 上无效：stage 会退回默认的"以中心缩放"，
    // 结果顶部空出 (1-s)·H/2 的空白、底部还会溢出容器。
    stage.style.transformOrigin = "0 0";
    stage.style.transform = `translateX(${offset}px) scale(${s})`;
    mapEl.style.height = `${Math.ceil(naturalH * s)}px`;
    mapEl.classList.remove("pannable");
  } else {
    stage.style.transformOrigin = "";
    stage.style.transform = "none";
    mapEl.style.height = `${naturalH}px`;
    mapEl.classList.add("pannable");
  }
}

// 铺好无缝的层级色带、点状分隔线，以及各分组指向锚点的连接线
function drawMap() {
  const mapEl = document.getElementById("vcm-map");
  const stage = document.getElementById("vcm-stage");
  const grid = document.getElementById("vcm-grid");
  const bands = document.getElementById("vcm-bands");
  const dividers = document.getElementById("vcm-dividers");
  const svg = document.getElementById("vcm-links");
  if (!mapEl || !stage || !grid || !bands || !dividers || !svg) return;

  // 在未缩放的坐标系里量；量完由 fitMap 重新把缩放应用回去
  stage.style.transform = "none";
  const base = stage.getBoundingClientRect();
  const W = grid.scrollWidth;
  const H = grid.scrollHeight;
  if (!W || !H) return;

  const cols = [...grid.querySelectorAll(".vcm-col")];
  const lanes = cols.map((col) => {
    const r = col.getBoundingClientRect();
    return {
      col,
      cx: (r.left + r.right) / 2 - base.left,
      left: r.left - base.left,
      right: r.right - base.left,
      color: col.classList.contains("vcm-anchor-col")
        ? "var(--primary-soft)"
        : bandColor(col.dataset.dir, +col.dataset.tier),
    };
  }).sort((p, q) => p.cx - q.cx);

  if (lanes.length) {
    bands.style.width = `${W}px`;
    bands.style.height = `${H}px`;
    const stops = [`${lanes[0].color} 0%`]
      .concat(lanes.map((l) => `${l.color} ${((l.cx / W) * 100).toFixed(1)}%`))
      .concat([`${lanes[lanes.length - 1].color} 100%`]);
    bands.style.backgroundImage = `linear-gradient(90deg, ${stops.join(", ")})`;
  }

  // 列与列之间的点状分隔线（放在两列之间的空隙中点）
  dividers.style.height = `${H}px`;
  dividers.innerHTML = lanes.slice(1).map((l, i) => {
    const mid = (lanes[i].right + l.left) / 2;
    return `<span style="position:absolute;left:${mid.toFixed(1)}px;top:0;width:0;height:100%;`
      + `border-left:1px dotted var(--border-strong);opacity:.9"></span>`;
  }).join("");

  // 各分组 → 锚点的连接线
  const anchorNode = grid.querySelector(".map-anchor");
  const anchorCard = anchorNode ? anchorNode.closest(".vcm-card") || anchorNode : null;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  if (!anchorCard) { svg.innerHTML = ""; return; }

  const ar = anchorCard.getBoundingClientRect();
  const aL = ar.left - base.left;
  const aR = ar.right - base.left;
  const aCy = (ar.top + ar.bottom) / 2 - base.top;

  // 按代码找到某个列里装着它的那个分组
  const colFor = (dir, tier) => grid.querySelector(`.vcm-col[data-dir="${dir}"][data-tier="${tier}"]`);
  const clusterForTicker = (col, ticker) => {
    if (!col || !ticker) return null;
    const a = col.querySelector(`a.map-node[href="#/c/${cssEscape(ticker)}"]`);
    return a ? a.closest(".vcm-cluster") : null;
  };

  let paths = "";
  cols.forEach((col) => {
    if (col.classList.contains("vcm-anchor-col")) return;
    const dir = col.dataset.dir;
    const tier = +(col.dataset.tier || 1);
    const isUp = dir === "upstream";
    const accent = linkColor(dir, tier);

    [...col.querySelectorAll(".vcm-cluster")].forEach((cl) => {
      const cr = cl.getBoundingClientRect();
      let x1, y1, x2, y2;

      if (tier === 1) {
        // 一级分组 → 锚点
        y1 = (cr.top + cr.bottom) / 2 - base.top;
        y2 = aCy;
        x1 = isUp ? (cr.right - base.left) : (cr.left - base.left);
        x2 = isUp ? aL : aR;
      } else {
        // 二级分组 → 它所属的一级分组。
        // 二级直接连锚点会横穿整个一级列、被卡片盖住，等于白画一条线。
        const parent = clusterForTicker(colFor(dir, 1), cl.dataset.via);
        if (!parent) return;
        const pr = parent.getBoundingClientRect();
        y1 = (pr.top + pr.bottom) / 2 - base.top;
        y2 = (cr.top + cr.bottom) / 2 - base.top;
        x1 = isUp ? (pr.left - base.left) : (pr.right - base.left);
        x2 = isUp ? (cr.right - base.left) : (cr.left - base.left);
      }

      // 控制点要收在"列间空隙"里：外扩太多的话曲线会跑到卡片下面，
      // z-index 上 SVG 在卡片之下，等于白画。留 6~40px 的幅度。
      const dx = Math.max(6, Math.min(40, Math.abs(x2 - x1) * 0.4));
      const dirSign = x2 >= x1 ? 1 : -1;
      const c1 = x1 + dx * dirSign;
      const c2 = x2 - dx * dirSign;
      paths += `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} C${c1.toFixed(1)} ${y1.toFixed(1)}, ${c2.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}"`
        + ` pathLength="100" fill="none" stroke="${accent}" stroke-width="1.5" stroke-opacity="0.45" stroke-linecap="round"/>`;
    });
  });
  svg.innerHTML = paths;

  // 连接线首次绘制时从一端"长"到另一端（pathLength=100 把 dash 归一化，CSS 动画才有通用尺子）。
  // 只放一次：展开分组、切缩放、resize 都会重画，每次都重放就成抖了。
  // svg 元素随公司页整页重建，所以换一家公司仍然播得到。
  if (!svg._drew && paths && !motionOff()) {
    svg.classList.add("animate");
    const ps = [...svg.querySelectorAll("path")];
    ps.forEach((p, i) => { p.style.animationDelay = `${Math.min(i * 36, 380)}ms`; });
    // 延迟最大的是最后一条，它播完才摘类——早摘会把还没轮到的线切成瞬间到位
    ps[ps.length - 1].addEventListener("animationend", () => svg.classList.remove("animate"), { once: true });
  }
  svg._drew = true;

  fitMap();
}

// 公司介绍块：主营业务 + 主营构成（按产品/按地区双表）+ 工商信息 + 经营范围（折叠）。
// 数据来自 data/p/{代码}.json（同花顺主营业务 + 巨潮公司概况 + 东财主营构成），
// 抓取脚本 pipeline/fetch_profiles.py。没有数据就不渲染这个块。
function introHTML(pf) {
  if (!pf) return "";
  const facts = [];
  if (pf.listed) facts.push(`<span class="tag">${esc(t("intro.listed", "上市"))} ${esc(pf.listed)}</span>`);
  if (pf.csrcIndustry) facts.push(`<span class="tag">${esc(pf.csrcIndustry)}</span>`);
  if (pf.legal) facts.push(`<span class="tag">${esc(t("intro.legal", "法人代表"))} ${esc(pf.legal)}</span>`);
  if (pf.capital) facts.push(`<span class="tag">${esc(t("intro.capital", "注册资本"))} ${esc(pf.capital)}</span>`);
  if (pf.website) {
    const url = /^https?:/.test(pf.website) ? pf.website : `https://${pf.website}`;
    facts.push(`<a class="tag" href="${esc(url)}" target="_blank" rel="noopener">${esc(t("intro.website", "官网"))} ↗</a>`);
  }
  // 主营构成：优先用三分法数据，按产品 + 按地区并排（地区分布对很多公司信息量大得多，
  // 例：工业富联的境外收入占比）；老数据只有 segments 时退化为单表
  const segTable = (title, segs) => {
    if (!segs || !segs.length) return "";
    const rows = segs.slice(0, 5).map((s) => `<tr><td>${esc(s.item)}</td>`
      + `<td class="num">${esc(fmtPct(s.revenueRatio * 100, false))}</td>`
      + `<td class="num">${esc(fmtPct(s.grossMargin * 100, false))}</td></tr>`).join("");
    return `<div class="intro-seg-col">
      <div class="intro-seg-title">${esc(title)}<span class="cf-meta">${esc(segs[0].period || "")}</span></div>
      <table class="intro-segs">
        <tr><th>${esc(t("intro.segItem", "主营构成"))}</th>
            <th class="num">${esc(t("intro.revenueRatio", "收入占比"))}</th>
            <th class="num">${esc(t("intro.grossMargin", "毛利率"))}</th></tr>
        ${rows}
      </table></div>`;
  };
  const by = pf.segmentsBy || null;
  const prodTbl = segTable(t("intro.byProduct", "按产品"), by ? by.product : (pf.segments || []));
  const regionTbl = by ? segTable(t("intro.byRegion", "按地区"), by.region) : "";
  const segBlock = prodTbl || regionTbl
    ? `<div class="intro-seg-grid">${prodTbl}${regionTbl}</div>` : "";
  return `
    <section class="sec intro-sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("intro.title", "公司介绍"))}</h2>
        <span class="sec-sub">${esc(t("intro.source", "主营业务：同花顺 · 公司概况：巨潮资讯 · 主营构成：东方财富"))}</span>
        <span class="sec-rule"></span>
      </div>
      ${facts.length ? `<div class="tags">${facts.join("")}</div>` : ""}
      ${pf.business ? `<p class="intro-biz">${esc(pf.business)}</p>` : ""}
      ${pf.products ? `<p class="note">${esc(t("intro.products", "主要产品"))}：${esc(pf.products)}</p>` : ""}
      ${segBlock}
      ${pf.scope ? `<details class="intro-scope"><summary>${esc(t("intro.scope", "经营范围"))}</summary><p>${esc(pf.scope)}</p></details>` : ""}
    </section>`;
}

// 手工梳理公司的真实价值链地图（节点来自人工整理的档案）
function curatedMapSection(data) {
  return `
    <section class="map-wrap">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("company.chainTitle", "价值链地图"))}</h2>
        <span class="sec-sub">${esc(t("company.curatedSub", "手工梳理 · 节点关系经人工整理"))}</span>
        <span class="sec-rule"></span>
        <button class="chip" id="map-zoom" type="button" aria-pressed="${mapZoom === "fit"}">${esc(mapZoom === "fit" ? t("company.zoomFit", "适应宽度") : t("company.zoomFull", "原始尺寸"))}</button>
      </div>
      <p class="chain-caveat">${esc(t("company.curatedCaveat", "上下游节点与分工来自人工整理的公开资料档案；细节请以公司官方披露为准。"))}</p>
      ${mapHTML(data)}
    </section>`;
}

/* 行业级产业链位置图（没有手工档案的公司）：
   只用两类真实数据——步进表（行业间原料流向的产业常识）和环节归属（公开归类）。
   上游/下游列的是「行业」而不是具体公司，不出现虚构的供货连线。 */
function posMapHTML(a) {
  const { up, down } = stepsOf(a.industry);
  const indBoards = (ni) => (graphData && graphData.industries[ni] ? indChainDist(ni) : []).slice(0, 3);
  const indRows = (rows, dir) => rows.map(({ ind: ni, role }) => {
    const boards = indBoards(ni);
    return `<div class="pos-ind" style="background:${tintFor(dir, 1)}">
        <a class="pos-ind-head" href="#/i/${encodeURIComponent(ni)}">
          <span class="pos-ind-name">${esc(t("sector." + ni, ni))}</span>
          <span class="pos-ind-role">${esc(role)}</span>
          <span class="map-link-arrow" aria-hidden="true">↗</span>
        </a>
        ${boards.length ? `<div class="pos-boards">${boards.map((b) =>
          `<button class="chip" type="button" data-psearch="${esc(b.name)}">${esc(b.name)}<span class="chip-n">${esc(fmtInt(b.n))}</span></button>`).join("")}</div>`
        : ""}
      </div>`;
  }).join("");
  const myBoards = boardsOf(a.ticker);
  const selfBoards = myBoards.length
    ? myBoards.map((b) => `<button class="chip" type="button" data-psearch="${esc(b)}">${esc(b)}<span class="chip-n">${esc(fmtInt((graphData?.boards?.[b] || []).length))}</span></button>`).join("")
    : `<span class="sec-sub">${esc(t("company.noBoards", "这家公司没有落在已收录的产业链环节里。"))}</span>`;
  const empty = (key, fallback) => `<div class="pos-empty">${esc(t(key, fallback))}</div>`;
  return `
    <section class="sec map-wrap">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("company.posTitle", "产业链位置"))}</h2>
        <span class="sec-sub">${esc(t("company.posSub", "行业级公开关系示意：上游是供给来源行业，下游是需求去向行业"))}</span>
        <span class="sec-rule"></span>
      </div>
      <p class="chain-caveat">${esc(t("company.posCaveat", "⚠ 上下游为行业级公开关系示意（产业常识中的原料流向），环节归属为真实公开归类；不代表具体公司间的供货关系。"))}</p>
      <div class="posmap" id="posmap">
        <div class="pos-lane" data-dir="up">
          <div class="tier-label">${esc(t("company.posUp", "上游 · 供给来源"))}</div>
          ${up.length ? indRows(up, "upstream") : empty("company.posNoUp", "步进表暂无上游行业记录")}
        </div>
        <div class="pos-lane pos-self">
          <div class="tier-label">${esc(t("company.posSelf", "本公司"))}</div>
          <div class="map-node map-anchor pos-anchor">
            <span class="map-node-text">
              <span class="map-node-name">${esc(a.name)}</span>
              <span class="map-node-role">${esc(a.ticker)} · ${esc(t("sector." + a.industry, a.industry))}</span>
            </span>
          </div>
          <div class="pos-boards">${selfBoards}</div>
        </div>
        <div class="pos-lane" data-dir="down">
          <div class="tier-label">${esc(t("company.posDown", "下游 · 需求去向"))}</div>
          ${down.length ? indRows(down, "downstream") : `
            <div class="pos-ind" style="background:${tintFor("downstream", 1)}">
              <div class="pos-ind-head"><span class="pos-ind-name">${esc(t("company.terminalName", "终端市场"))}</span></div>
            </div>
            ${empty("company.posNoDown", "步进表暂无下游行业记录")}`}
        </div>
      </div>
    </section>`;
}

function renderCompany(data) {
  // 首次进入按视口宽度选默认值：宽屏先看全貌，窄屏保持字号可读
  if (!mapZoom) mapZoom = window.innerWidth >= 900 ? "fit" : "full";
  const a = data.anchor;
  const f = a.fundamentals;
  const pf = data.profile || null;
  const nodes = data.nodes || [];
  const upN = nodes.filter((n) => n.relation === "upstream").length;
  const downN = nodes.length - upN;
  const total = upN + downN;
  const upPct = total ? (upN / total) * 100 : 0;

  const metrics = [];
  if (f) {
    metrics.push(metric(t("metric.price", "最新价"), fmtPrice(f.price), true));
    metrics.push(metric(t("metric.chg", "涨跌幅"), fmtPct(f.changePercent)));
    metrics.push(metric(t("company.preClose", "昨收"), fmtPrice(f.prevClose)));
    metrics.push(metric(t("metric.cap", "总市值"), fmtCap(f.marketCap)));
    metrics.push(metric(t("metric.pe", "市盈率TTM"),
      f.lossMaking ? t("company.loss", "亏损") : fmtNum(f.trailingPE, 1)));
    metrics.push(metric(t("metric.fpe", "市盈率(动)"), fmtNum(f.forwardPE, 1)));
    metrics.push(metric(t("metric.gm", "毛利率"), fmtPct(f.grossMargins, false)));
    metrics.push(metric(t("metric.pm", "净利率"), fmtPct(f.profitMargins, false)));
    metrics.push(metric(t("metric.rg", "营收增速"), fmtPct(f.revenueGrowth)));
    metrics.push(metric(t("metric.eps", "每股收益"), fmtNum(f.trailingEps)));
  }

  const boards = boardsOf(a.ticker);
  const peers = companyPeers(a.ticker);

  app.innerHTML = `
    <div class="crumb"><a href="#/"><span class="arr" aria-hidden="true">←</span> ${esc(t("crumb.home", "全部公司"))}</a></div>

    <header class="pr-head">
      <div class="pr-title-row">
        <h1 class="pr-title">${esc(a.name)}</h1>
        <span class="pr-ticker">${esc(a.ticker)}</span>
        ${f ? `<span class="card-chg ${changeClass(f.changePercent)}">${esc(fmtPct(f.changePercent))}</span>` : ""}
      </div>
      <div class="pr-tags">
        <span class="tag tag-sector">${esc(t("sector." + a.industry, a.industry))}</span>
        <span class="tag">${esc(t("board." + a.board, a.board))}</span>
        <span class="tag">${esc(t("exchange." + a.exchange, a.exchange))}</span>
        ${f ? `<span class="tag">${esc(f.simulated === false
          ? t("company.realTag", "真实行情")
          : t("company.simulated", "模拟数据"))}</span>` : ""}
        ${f && f.suspended ? `<span class="tag">${esc(t("company.suspended", "停牌"))}</span>` : ""}
      </div>
      <div class="pr-metrics">${metrics.join("")}</div>
      <div class="pr-actions">${savePill(a.ticker)}</div>
      ${total ? `<div class="pr-chain">
        <div class="pr-chain-label">
          <span>${esc(t("company.upCount", "上游 {n} 家").replace("{n}", upN))}</span>
          <span>${esc(t("company.downCount", "下游 {n} 家").replace("{n}", downN))}</span>
        </div>
        <div class="chain-bar"><span class="chain-seg up" style="width:${upPct.toFixed(1)}%"></span><span class="chain-seg down" style="width:${(100 - upPct).toFixed(1)}%"></span></div>
      </div>` : ""}
    </header>
    ${introHTML(pf)}

    <section class="sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("company.boardsTitle", "所属产业链环节"))}</h2>
        <span class="sec-sub">${esc(t("company.boardsSub", "来自公开的概念板块归类；同属一条产业链 ≠ 谁给谁供货"))}</span>
        <span class="sec-rule"></span>
        <span class="sec-sub">${esc(fmtInt(boards.length))} ${esc(t("company.boardUnit", "个"))}</span>
      </div>
      ${boards.length
        ? `<div class="board-chips">` + boards.map((b) => `<span class="board-chip">`
            + `<span class="board-chip-name">${esc(b)}</span>`
            + `<span class="board-chip-n">${esc(fmtInt((graphData?.boards?.[b] || []).length))}</span></span>`).join("") + `</div>`
        : `<p class="sec-sub">${esc(t("company.noBoards", "这家公司没有落在已收录的产业链环节里。"))}</p>`}
    </section>

    ${chainDataCache && chainDataCache.companies && chainDataCache.companies[data.anchor.ticker] ? (() => {
      const prof = chainDataCache.companies[data.anchor.ticker];
      // 有真实内容的字段才渲染：公司简介已由上方「公司介绍」承载（4,071 家全量），
      // 这里只留手工档案里独有的字段；设备/产值有了才显示——一屏「待接入」
      // 占位符比整块不渲染更显 unfinished
      const fields = [
        prof.intro ? chainField(t("chain.fIntro", "公司简介"), esc(prof.intro)) : "",
        prof.chain_position ? chainField(t("chain.fPosition", "产业链位置"), esc(prof.chain_position)) : "",
        (prof.representative_devices || []).length
          ? chainField(t("chain.fEquipment", "代表性设备设施"),
              `<div class="device-chips">${chainDeviceChips(prof.representative_devices)}</div>`) : "",
        !(prof.representative_devices || []).length && (prof.representative_equipment || []).length
          ? chainField(t("chain.fEquipment", "代表性设备设施"),
              `<div class="cf-text">${esc((prof.representative_equipment || []).join("、"))}</div>`) : "",
        ovReady(prof.output_value)
          ? chainField(t("chain.fOutput", "营收 / 产值"), chainOutputHTML(prof.output_value)) : "",
      ].filter(Boolean).join("");
      return fields ? chainSectionHTML(t("chain.companyTitle", "公司档案"), prof, fields) : "";
    })() : ""}

    ${peers.length ? `
    <section class="sec">
      <div class="sec-head">
        <h2 class="sec-title">${esc(t("company.peersTitle", "同行业里共享产业链环节的公司"))}</h2>
        <span class="sec-sub">${esc(t("company.peersSub", "按共同环节数排序"))}</span>
        <span class="sec-rule"></span>
      </div>
      <div class="peer-table">
        ${peers.map((p, i) => `
          <a class="peer-row" href="#/c/${encodeURIComponent(p.ticker)}">
            <span class="peer-idx">${i + 1}</span>
            <span class="peer-name">${esc(p.name)}</span>
            <span class="peer-ticker">${esc(p.ticker)}</span>
            <span class="peer-shared">${esc(t("company.sharedFmt", "共同 {n} 个环节").replace("{n}", p.shared))}：${esc(p.boards.slice(0, 3).join("、"))}${p.boards.length > 3 ? "…" : ""}</span>
          </a>`).join("")}
      </div>
    </section>` : ""}

    ${nodes.length ? curatedMapSection(data) : posMapHTML(a)}`;

  // 位置图里的环节芯片：跳到首页搜索这个词（环节的落地形态 = 首页搜索结果）
  document.getElementById("posmap")?.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-psearch]");
    if (chip) goToSearch(chip.dataset.psearch);
  });

  // 适应宽度 ⇄ 原始尺寸（原始尺寸下横向平移看完整链条）
  document.getElementById("map-zoom")?.addEventListener("click", (e) => {
    mapZoom = mapZoom === "fit" ? "full" : "fit";
    const b = e.currentTarget;
    b.textContent = mapZoom === "fit" ? t("company.zoomFit", "适应宽度") : t("company.zoomFull", "原始尺寸");
    b.setAttribute("aria-pressed", String(mapZoom === "fit"));
    requestAnimationFrame(drawMap);
  });

  // 展开 / 收起分组
  app.querySelectorAll(".vcm-cluster-head").forEach((head) => {
    head.addEventListener("click", () => {
      const cluster = head.closest(".vcm-cluster");
      const key = cluster?.dataset.key;
      const rest = cluster?.querySelector(".vcm-rest");
      if (!key || !rest) return;
      const open = !expandedClusters.has(key);
      if (open) expandedClusters.add(key); else expandedClusters.delete(key);
      rest.dataset.open = String(open);
      head.setAttribute("aria-expanded", String(open));
      head.querySelector(".vcm-chev")?.classList.toggle("open", open);
      requestAnimationFrame(drawMap);
    });
  });

  // 分组展开会改变高度，连接线要跟着重画
  if (mapRO) mapRO.disconnect();
  const grid = document.getElementById("vcm-grid");
  if (grid && window.ResizeObserver) {
    mapRO = new ResizeObserver(() => requestAnimationFrame(drawMap));
    mapRO.observe(grid);
  }

  requestAnimationFrame(() => {
    drawMap();
    // 等 web font / 图片稳定后再量一次，避免首帧量到的高度偏小
    setTimeout(drawMap, 220);
  });
}

// 设备档案页：产业链的第三级。面包屑「行业 > 公司 > 设备」里设备是终点，
// 所以所属公司做成可点的芯片——交叉关系从这里回到公司页。
async function renderEquipmentPage(id) {
  app.innerHTML = "";
  startLoading();
  const chain = await loadChainData();
  if (parseRoute().name !== "equipment") return;
  stopLoading();
  const d = chain && chain.devices ? chain.devices[id] : null;
  if (!d) {
    app.innerHTML = `<p class="empty">${esc(t("chain.errEquipment", "没有这个设备档案。"))}`
      + ` <a href="#/">${esc(t("chain.back", "回首页"))}</a></p>`;
    return;
  }
  const companies = (d.companies || []).map((c) =>
    c.ticker
      ? `<a class="chip" href="#/c/${encodeURIComponent(c.ticker)}">${esc(c.name)}<span class="chip-n">→</span></a>`
      : `<span class="cf-text">${esc(c.name)}</span>`).join("");
  const fields = chainField(t("chain.fOfficial", "官方口径名称"), chainTextOrPending(d.official_name))
    + chainField(t("chain.fIntro", "设备简介"), chainTextOrPending(d.intro))
    + chainField(t("chain.fSuppliers", "所属公司（供应商）"), companies || chainPending())
    + chainField(t("chain.fOutput", "市场规模"), chainOutputHTML(d.output_value));
  app.innerHTML = `
    <div class="crumb"><a href="#/"><span class="arr" aria-hidden="true">←</span> ${esc(t("chain.crumb", "产业链档案"))}</a></div>
    ${chainSectionHTML(t("chain.equipmentTitle", "设备档案"), d, fields)}`;
}

// 同行业里与它共享至少一个产业链环节的公司（图上"它连了谁"的直观呈现）
function companyPeers(ticker, limit = 24) {
  if (!graphData || !indexData) return [];
  const me = (indexData.companies || []).find((c) => c.ticker === ticker);
  if (!me) return [];
  const mine = new Set(graphData.boardIdxOf?.[ticker] || []);
  if (!mine.size) return [];
  const out = [];
  for (const t of (graphData.industries?.[me.industry] || [])) {
    if (t === ticker) continue;
    const shared = (graphData.boardIdxOf?.[t] || []).filter((b) => mine.has(b));
    if (!shared.length) continue;
    const info = (indexData.companies || []).find((c) => c.ticker === t);
    out.push({
      ticker: t,
      name: info ? info.name : t,
      shared: shared.length,
      boards: shared.map((i) => graphData.boardList[i]),
    });
  }
  out.sort((x, y) => y.shared - x.shared || x.ticker.localeCompare(y.ticker));
  return out.slice(0, limit);
}

/* ---- 成分归属：每家公司只归到一个"主环节" ---------------------------------
   一家公司通常同时属于 4~5 个环节（平均 4.6 个）。要在圆饼/圆环上给它排一个座位，
   就得先定"它主要属于哪个环节"。规则：取它所属环节里**成员最少**（最具体）的那个 ——
   "半导体概念"（几百家）和"第三代半导体"（几十家）相比，后者信息量更大。 */

function primaryPartOf(ticker, g) {
  const bs = g.boardIdxOf?.[ticker] || [];
  if (!bs.length) return null;
  let best = bs[0], bestN = Infinity;
  for (const bi of bs) {
    const n = (g.boards[g.boardList[bi]] || []).length;
    if (n < bestN) { bestN = n; best = bi; }
  }
  return best;
}

/* 一个行业的成分分析，小圆饼和大环图共用：
   ranked = 环节按公司数降序，每个环节带上自己的成员（成员顺序沿用 industries 里的市值降序） */
function industryParts(ind, g) {
  const members = g.industries[ind] || [];
  const byTicker = new Map();
  const freq = new Map();
  for (const tk of members) {
    const bi = primaryPartOf(tk, g);
    if (bi == null) continue;
    byTicker.set(tk, bi);
    if (!freq.has(bi)) freq.set(bi, { bi, n: 0, members: [] });
    const rec = freq.get(bi);
    rec.n++;
    rec.members.push(tk);
  }
  const ranked = [...freq.values()].sort((a, b) => b.n - a.n || a.bi - b.bi);
  for (const r of ranked) r.name = g.boardList[r.bi];
  return { ind, total: members.length, ranked, byTicker };
}

/* 环节切片：数据色明度阶（--data-*），"fewer hues, more shades"；
   红绿留给涨跌，故此处不含红绿。颜色运行时从 CSS 变量取——
   深色终端是亮蓝灰阶，浅色研报是藏青明度阶，切主题时自动跟随。 */
function partCycle() {
  return [cssVar("--data-1", "#5C7DA3"), cssVar("--data-2", "#A8BCD0"), cssVar("--data-3", "#33455E")];
}
function partOther() {
  return cssVar("--data-other", "#232C3A");
}

/* ---- 全景图谱：24 个小圆饼 ------------------------------------------------
   这个页面的任务只有一个：让人一眼看清 24 个行业各自由什么环节组成、规模多大。
   上一版在这里画的是"环节 — 公司"的归属连线，几百条线糊成一团，
   结论是**页面级的小图不能画线**。所以这里换成圆饼：没有任何线。

   想看某个行业里到底有哪些公司 → 点进去，那里有一张单独的大环图。 */

const TILE_PARTS = 5;        // 小圆饼最多切几片（其余归"其他"）

async function renderWorldMap() {
  app.innerHTML = "";
  startLoading();
  const g = await loadGraph();
  stopLoading();
  if (!g) {
    app.innerHTML = `<p class="empty">${esc(t("wm.error", "图谱数据没加载出来。"))}`
      + ` <a href="#/">${esc(t("crumb.home", "全部公司"))}</a></p>`;
    return;
  }
  if (parseRoute().name !== "worldmap") return;
  renderTilesPage(g);
}

function renderTilesPage(g) {
  const q = indexData?.quotes || {};
  const tiles = g.industryList.map((ind, tileIdx) => {
    const parts = industryParts(ind, g);
    const members = g.industries[ind] || [];
    let cap = 0, chgSum = 0, chgN = 0;
    for (const tk of members) {
      const f = q[tk] || {};
      if (typeof f.marketCap === "number") cap += f.marketCap;
      if (typeof f.changePercent === "number") { chgSum += f.changePercent; chgN++; }
    }
    const avg = chgN ? chgSum / chgN : null;
    const top = parts.ranked.slice(0, TILE_PARTS);
    const restN = parts.ranked.slice(TILE_PARTS).reduce((s, r) => s + r.n, 0);
    const cycle = partCycle();
    const rows = top.map((r, i) => `
          <li class="pie-row" data-i="${i}">
            <i style="background:${cycle[i % cycle.length]}"></i>
            <span class="pie-row-name">${esc(r.name)}</span>
            <span class="pie-row-n">${esc(fmtInt(r.n))}</span>
          </li>`).join("")
      + (restN ? `
          <li class="pie-row" data-i="${top.length}">
            <i style="background:${partOther()}"></i>
            <span class="pie-row-name">${esc(t("wm.others", "其他 {n} 个环节").replace("{n}", fmtInt(parts.ranked.length - top.length)))}</span>
            <span class="pie-row-n">${esc(fmtInt(restN))}</span>
          </li>` : "");

    return `
      <a class="pie-card" href="#/m/${encodeURIComponent(ind)}" data-ind="${esc(ind)}" style="--i:${tileIdx}">
        <div class="pie-head">
          <h3 class="pie-title">${esc(t("sector." + ind, ind))}</h3>
          <span class="pie-chg ${changeClass(avg)}">${avg == null ? "—" : esc(fmtPct(avg))}</span>
        </div>
        <div class="pie-body">
          <canvas class="pie-canvas" data-ind="${esc(ind)}" width="1" height="1"
                  role="img" aria-label="${esc(t("sector." + ind, ind))} ${esc(fmtInt(members.length))} ${esc(t("stat.companies", "家上市公司"))}"></canvas>
          <ul class="pie-legend" data-ind="${esc(ind)}">${rows}</ul>
        </div>
        <p class="pie-foot">${esc(fmtInt(members.length))} ${esc(t("ind.unitCompanies", "家"))} · ${esc(fmtInt(parts.ranked.length))} ${esc(t("ind.unitBoards", "个环节"))} · ${esc(t("ind.capTotal", "市值"))} ${esc(fmtCap(cap))}</p>
      </a>`;
  }).join("");

  const total = indexData?.totals || {};
  app.innerHTML = `
    <div class="crumb"><a href="#/"><span class="arr" aria-hidden="true">←</span> ${esc(t("crumb.home", "全部行业"))}</a></div>
    <section class="wm-page">
      <header class="wm-masthead">
        <div>
          <h1 class="wm-title">${esc(t("wm.title", "全景图谱"))}</h1>
          <p class="wm-colophon">${esc(t("wm.colophon2", "{c} 家公司 · {i} 个申万一级行业 · {b} 个产业链环节 · 数据 {d}")
            .replace("{c}", fmtInt(total.companies || 0))
            .replace("{i}", fmtInt(total.industries || 0))
            .replace("{b}", fmtInt(total.boards || 0))
            .replace("{d}", g.generatedAt || ""))}</p>
        </div>
        <p class="wm-tagline">${esc(t("wm.tilesNote2", "一个行业一个圆饼：扇形是产业链环节，扇形大小是落在这个环节上的公司数。点一个圆饼，进去看那个行业单独的大环图——到那里才有公司名字。"))}</p>
      </header>
      <div class="pies" id="wm-tiles">${tiles}</div>
    </section>`;

  const canvases = [...document.querySelectorAll(".pie-canvas")];
  canvases.forEach((cv) => { drawDonut(cv, cv.dataset.ind, g); donutHover(cv); });

  // 尺寸变化重画（圆饼按容器宽度现算）
  let pending = 0;
  window.addEventListener("resize", () => {
    clearTimeout(pending);
    pending = setTimeout(() => {
      if (parseRoute().name === "worldmap") {
        canvases.forEach((cv) => cv.isConnected && drawDonut(cv, cv.dataset.ind, g));
      }
    }, 160);
  });
}

/* 一个小圆饼：扇形 = 主环节（前 5 个 + 其他），中心是公司数。
   鼠标划到扇形上，中心改成显示这个环节的名字和家数，右边的图例同步高亮。 */
function drawDonut(cv, ind, g, hover = -1) {
  if (g) cv._g = g;
  if (!cv._parts) cv._parts = industryParts(ind, cv._g);
  const parts = cv._parts;
  const top = parts.ranked.slice(0, TILE_PARTS);
  const restN = parts.ranked.slice(TILE_PARTS).reduce((s, r) => s + r.n, 0);
  const cycle = partCycle();
  const slices = top.map((r, i) => ({ ...r, color: cycle[i % cycle.length] }));
  if (restN) slices.push({ name: t("wm.othersShort", "其他"), n: restN, color: partOther() });

  const dpr = window.devicePixelRatio || 1;
  const S = Math.max(104, Math.min(126, cv.parentElement?.clientWidth ? cv.parentElement.clientWidth * 0.42 : 112));
  cv.width = Math.floor(S * dpr);
  cv.height = Math.floor(S * dpr);
  cv.style.width = S + "px";
  cv.style.height = S + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, S, S);

  const cx = S / 2, cy = S / 2, R = S / 2 - 2;
  const hole = R * 0.62;
  const total = slices.reduce((s, x) => s + x.n, 0) || 1;
  let a = -Math.PI / 2;
  slices.forEach((s, i) => {
    const span = (s.n / total) * Math.PI * 2;
    const gap = Math.min(span * 0.06, 0.02);
    ctx.beginPath();
    ctx.arc(cx, cy, R, a + gap / 2, a + span - gap / 2);
    ctx.arc(cx, cy, hole, a + span - gap / 2, a + gap / 2, true);
    ctx.closePath();
    ctx.fillStyle = s.color;
    ctx.globalAlpha = hover === -1 || hover === i ? 1 : 0.32;
    ctx.fill();
    a += span;
  });

  // 中心：默认公司数，划到扇形上时改成"环节名 + 家数"
  ctx.globalAlpha = 1;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const ink = cssVar("--text", "#D8DFE9");
  const faint = cssVar("--text-faint", "#5E6B7C");
  if (hover >= 0 && slices[hover]) {
    const s = slices[hover];
    let name = s.name;
    ctx.font = `500 ${S < 116 ? 10 : 11}px ${getComputedStyle(document.body).fontFamily}`;
    while (name.length > 1 && ctx.measureText(name).width > hole * 1.8) name = name.slice(0, -1);
    ctx.fillStyle = ink;
    ctx.fillText(name, cx, cy - 7);
    ctx.font = `600 15px ${getComputedStyle(document.body).fontFamily}`;
    ctx.fillText(fmtInt(s.n), cx, cy + 9);
  } else {
    ctx.font = `600 ${S < 116 ? 18 : 21}px ${getComputedStyle(document.body).fontFamily}`;
    ctx.fillStyle = ink;
    ctx.fillText(fmtInt(parts.total), cx, cy - 4);
    ctx.font = `400 10px ${getComputedStyle(document.body).fontFamily}`;
    ctx.fillStyle = faint;
    ctx.fillText(t("ind.unitCompanies", "家"), cx, cy + 13);
  }
  cv._slices = slices;
}

// 扇形命中：由圆心和鼠标算角度，落进哪个扇区就是哪个
function donutHover(cv) {
  cv.onmousemove = (e) => {
    const slices = cv._slices;
    if (!slices) return;
    const r = cv.getBoundingClientRect();
    const S = r.width;
    const mx = e.clientX - r.left - S / 2, my = e.clientY - r.top - S / 2;
    const dist = Math.hypot(mx, my);
    const R = S / 2 - 2, hole = R * 0.62;
    let idx = -1;
    if (dist >= hole - 2 && dist <= R + 2) {
      let ang = Math.atan2(my, mx) + Math.PI / 2;
      while (ang < 0) ang += Math.PI * 2;
      const total = slices.reduce((s, x) => s + x.n, 0) || 1;
      let acc = 0;
      for (let i = 0; i < slices.length; i++) {
        const span = (slices[i].n / total) * Math.PI * 2;
        if (ang >= acc && ang < acc + span) { idx = i; break; }
        acc += span;
      }
    }
    if (idx === cv._hover) return;
    cv._hover = idx;
    drawDonut(cv, cv.dataset.ind, null, idx);
    const legend = document.querySelector(`.pie-legend[data-ind="${cssEscape(cv.dataset.ind)}"]`);
    if (legend) {
      legend.querySelectorAll(".pie-row").forEach((li) => {
        li.classList.toggle("on", Number(li.dataset.i) === idx);
      });
    }
  };
  cv.onmouseleave = () => {
    if (cv._hover === -1) return;
    cv._hover = -1;
    drawDonut(cv, cv.dataset.ind, null, -1);
    const legend = document.querySelector(`.pie-legend[data-ind="${cssEscape(cv.dataset.ind)}"]`);
    if (legend) legend.querySelectorAll(".pie-row").forEach((li) => li.classList.remove("on"));
  };
}

/* ---- 环形标签排布（当前没有调用点，留着备用） ------------------------------
   中文名字改成"悬停弹方块 + 横排清单"之后，两张环图都不在环上写字了，所以这个函数暂时没人调。
   留着是因为它本身不平凡：把角度轴展开成直线做链式推开，能保证相邻间距 ≥ need ——
   当初试过"反复互相推挤"，124 个标签推 320 轮都不收敛。以后若要给大环加水平标签，直接就能用。
   把角度轴展开成一条直线，做一次前向 + 一次后向的链式推开。
   比"反复互相推挤"稳：链式出来的相邻间距**一定** ≥ need，而且不需要迭代收敛
   （推挤那种写法 124 个标签推 320 轮都不收敛）。
   needOf(item) 返回"这个标签需要多少角宽"——字号不同、需求就不同。 */
function ringLabelLayout(cands, needOf) {
  const TAU = Math.PI * 2;
  const sorted = [...cands].sort((a, b) => a.mid - b.mid);
  const n = sorted.length;
  if (!n) return { sorted: [], u: [], ok: true };
  // 从"最大的那个空档"处切开 —— 切口选错的话展开后首尾会挤在一起，判定必然失败
  let cut = 0, best = -1;
  for (let i = 0; i < n; i++) {
    let d = sorted[(i + 1) % n].mid - sorted[i].mid;
    while (d < 0) d += TAU;
    if (d > best) { best = d; cut = (i + 1) % n; }
  }
  const rot = [...sorted.slice(cut), ...sorted.slice(0, cut)];
  const u = [rot[0].mid];
  for (let i = 1; i < n; i++) {
    let d = rot[i].mid - rot[i - 1].mid;
    while (d < 0) d += TAU;
    u.push(u[i - 1] + d);
  }
  for (let i = 1; i < n; i++) u[i] = Math.max(u[i], u[i - 1] + needOf(rot[i]));
  for (let i = n - 1; i > 0; i--) u[i - 1] = Math.min(u[i - 1], u[i] - needOf(rot[i]));
  // 首尾也是邻居，留出的缺口也得够一个标签
  return { sorted: rot, u, ok: (u[n - 1] - u[0]) <= TAU - needOf(rot[0]) };
}

/* ---- 行业大环图 #/m/{行业} ------------------------------------------------
   一个行业单独一张。做法沿用早期那版"大圆饼"：
   公司点排在一个圆周上、外侧用弧段标出它们属于哪个环节、中间留白放读数。

   跟上版的关键差别是**线只在鼠标落下时才出现** ——
   486 家公司的归属线全画出来就是一团毛线，这是上一版被否掉的原因。 */

const RING_MARGIN = 124;      // 环外留给标签的径向空间（环图命中判定的兜底也用这个）
// 实际画的时候环外留多宽：横排的名字比"沿半径排字"更占地方，实测 130 才够
// 放下"工程机械整机 32"这种最长的标签（6 个汉字 + 空格 + 两位数 ≈ 81px）。
const LABEL_BAND = 130;
const RING_SIDE_MAX = 940;    // 硬上限
const RING_CHROME = 232;      // 圆以外占掉的高度（顶栏+面包屑+标题+图注的下沿）

// 环图的边长：取"容器宽度"和"视口高度减去圆外元素"两者的小值，
// 让整个圆一屏能看全，不用滚动才能看完整张图。
function ringSide(cv) {
  const avail = cv.parentElement?.clientWidth || RING_SIDE_MAX;
  const byHeight = Math.max(window.innerHeight - RING_CHROME, RING_NARROW_MIN);
  // 注意这里是按"宽度"和"高度"分别取值再取小：
  // 高度不够时允许用户上下滚一点（名字需要径向空间），但宽度绝不能超，否则会横向溢出。
  return Math.round(clamp(Math.min(avail, RING_SIDE_MAX, byHeight), 320, 1060));
}
const RING_ROW_STEP = 20;     // 圈与圈之间的径向间距
// 一圈放不下就把点摊到内外几圈上：家数越多圈越多，每个点才站得开、也才画得大。
// 496 家挤在一圈上只会是一根细线，看不出"这里有多少公司"。
function ringRows(n) {
  return n > 340 ? 3 : n > 170 ? 2 : 1;
}
// 窄屏要把标签带压窄，否则 390px 宽下留给圆的半径只剩 55px，圆小得看不见
const RING_MIN_W = 520;       // 窄于这个宽度算窄屏：标签带压窄、字号取小的
const RING_NARROW_MIN = 720;  // 窄屏也至少给这么多边长，否则环外的名字没地方写

async function renderIndustryRingPage(ind) {
  app.innerHTML = "";
  startLoading();
  const [g] = await Promise.all([loadGraph()]);
  stopLoading();
  if (!g || !g.industries[ind]) {
    app.innerHTML = `<p class="empty">${esc(t("ind.unknown", "没有这个行业。"))}`
      + ` <a href="#/worldmap">${esc(t("wm.title", "全景图谱"))}</a></p>`;
    return;
  }
  if (parseRoute().name !== "industryMap") return;

  const parts = industryParts(ind, g);
  const q = indexData?.quotes || {};
  let cap = 0, chgSum = 0, chgN = 0;
  for (const tk of (g.industries[ind] || [])) {
    const f = q[tk] || {};
    if (typeof f.marketCap === "number") cap += f.marketCap;
    if (typeof f.changePercent === "number") { chgSum += f.changePercent; chgN++; }
  }
  const avg = chgN ? chgSum / chgN : null;

  app.innerHTML = `
    <div class="crumb"><a href="#/worldmap"><span class="arr" aria-hidden="true">←</span> ${esc(t("wm.title", "全景图谱"))}</a></div>
    <section class="ring-page">
      <header class="ring-head">
        <h1 class="ring-title">${esc(t("sector." + ind, ind))}</h1>
        <div class="ring-stats">
          <span class="ind-stat"><b data-count="${parts.total}">${esc(fmtInt(parts.total))}</b><span>${esc(t("stat.companies", "家上市公司"))}</span></span>
          <span class="ind-stat"><b data-count="${parts.ranked.length}">${esc(fmtInt(parts.ranked.length))}</b><span>${esc(t("stat.boards", "个产业链环节"))}</span></span>
          <span class="ind-stat"><b>${esc(fmtCap(cap))}</b><span>${esc(t("ind.capLabel", "市值合计"))}</span></span>
          <span class="ind-stat"><b class="${changeClass(avg)}">${avg == null ? "—" : esc(fmtPct(avg))}</b><span>${esc(t("ind.avgLabel", "今日平均涨跌"))}</span></span>
        </div>
      </header>

      <figure class="ring-figure">
        <canvas class="ring-canvas" id="ring-canvas" role="img"
                aria-label="${esc(t("sector." + ind, ind))} ${esc(t("ring.aria", "产业链环节环图"))}"></canvas>
        <figcaption class="ring-note" id="ring-note">${esc(t("ring.note", "点的大小 = 市值 · 颜色 = 涨跌（涨红跌绿）· 外圈弧段 = 这些公司所属的产业链环节。把鼠标移到点上：中间会显示公司名和它的环节，并画出它与其他环节的关联；点到弧段上则列出这个环节里的公司。"))}</figcaption>
      </figure>

      <section class="sec ring-chains">
        <div class="sec-head">
          <h2 class="sec-title">${esc(t("ring.legendTitle", "环节清单"))}</h2>
          <span class="sec-sub">${esc(t("ring.legendSub", "按环上的顺时针顺序排列，和弧段一一对应；鼠标移上去或在环上点它，两边会同时高亮"))}</span>
          <span class="sec-rule"></span>
          <span class="sec-sub">${esc(fmtInt(parts.ranked.length))} ${esc(t("ind.unitBoards", "个环节"))}</span>
        </div>
        <div class="chain-list" id="ring-chains">
          ${parts.ranked.map((r, i) => `
            <button class="chain-row" type="button" data-bi="${r.bi}">
              <span class="chain-row-i">${i + 1}</span>
              <span class="chain-row-name">${esc(r.name)}</span>
              <span class="chain-row-n">${esc(fmtInt(r.n))}</span>
            </button>`).join("")}
        </div>
      </section>

      <p class="ring-more">
        <a class="chip" href="#/i/${encodeURIComponent(ind)}">${esc(t("ring.toList", "看这个行业的公司列表 →"))}</a>
      </p>
    </section>
    <div class="tile-tip" id="tile-tip" hidden></div>`;

  countUpIn(app);
  const cv = document.getElementById("ring-canvas");
  let lastW = 0;
  const redraw = () => {
    if (!cv || !cv.isConnected) return;
    const w = ringSide(cv);
    if (Math.abs(w - lastW) > 8 || !cv._dots) {
      lastW = w;
      drawIndustryRing(cv, ind, g);
      const note = document.getElementById("ring-note");
      // 只剩一句图注了：环上不再写名字（中文沿半径排字，左半边必然是倒的），
      // 所以原来"屏幕只标得下 N 个名字"那条分支已作废 —— 它现在会渲染成
      // "124 个环节…只标得下 0 个名字"，是一句用户能看见的错话。
      if (note) note.textContent = t("ring.note", "");
    }
  };
  // 大环扫入：与首页同一节奏。悬停重画共享 cv._introT，中途鼠标上来不跳变。
  if (!motionOff()) {
    cv._introT = 0;
    const t0 = performance.now();
    const dur = 720;
    const step = (now) => {
      if (!cv.isConnected) return;
      const p = Math.min(1, (now - t0) / dur);
      cv._introT = 1 - Math.pow(1 - p, 3);
      drawIndustryRing(cv, ind, g, null, cv._hoverSector ?? -1);
      if (p < 1) requestAnimationFrame(step);
      else cv._introT = 1;
    };
    requestAnimationFrame(step);
  } else {
    cv._introT = 1;
  }
  redraw();
  setupRingHover(cv, ind, g);

  // 清单 ↔ 环图的联动：清单里 124 行不可能都记得住位置，所以让两边互相点亮
  const highlight = (bi) => {
    if (cv._hoverSector === bi) return;
    cv._sel = null;
    cv._hoverSector = bi;
    drawIndustryRing(cv, ind, g, null, bi);
  };
  const chainsEl = document.getElementById("ring-chains");
  chainsEl?.addEventListener("mouseover", (e) => {
    const row = e.target.closest("[data-bi]");
    if (row) highlight(Number(row.dataset.bi));
  });
  chainsEl?.addEventListener("mouseleave", () => highlight(-1));
  chainsEl?.addEventListener("click", (e) => {
    const row = e.target.closest("[data-bi]");
    if (!row) return;
    highlight(Number(row.dataset.bi));
    cv.scrollIntoView({ block: "center", behavior: motionOff() ? "auto" : "smooth" });
  });

  let pending = 0;
  window.addEventListener("resize", () => {
    clearTimeout(pending);
    pending = setTimeout(() => {
      if (parseRoute().name === "industryMap") redraw();
    }, 160);
  });
}

// 环上的一个点：位置、半径、所属环节
// 扇区的角度与大小：**只跟公司数有关，跟半径无关**。
// 单独拆出来是因为标签排布要在"定半径之前"就知道角度 —— 半径又反过来取决于标签带宽度，
// 否则就成了死循环。
function ringArcs(parts) {
  const groups = parts.ranked;
  const total = groups.reduce((s, x) => s + x.members.length, 0) || 1;
  const arcs = [];
  let a = -Math.PI / 2;
  for (const grp of groups) {
    const span = (grp.members.length / total) * Math.PI * 2;
    const gap = Math.min(span * 0.1, 0.012);
    const a0 = a + gap / 2, a1 = a + span - gap / 2;
    arcs.push({
      bi: grp.bi, name: grp.name, n: grp.n, a0, a1, mid: (a0 + a1) / 2, members: grp.members,
      // 命中判定用归一化角度（从 12 点方向顺时针 0→2π），避免在 -π/2 处跨越 2π 时误判
      n0: a0 + Math.PI / 2, n1: a1 + Math.PI / 2,
    });
    a += span;
  }
  return arcs;
}

// 公司点：这一步才需要半径
function ringDots(parts, arcs, R) {
  const total = arcs.reduce((s, x) => s + x.members.length, 0) || 1;
  const rows = ringRows(total);
  const dots = [];
  for (const s of arcs) {
    const n = s.members.length;
    for (let i = 0; i < n; i++) {
      const ang = n === 1 ? (s.a0 + s.a1) / 2 : s.a0 + ((i + 0.5) / n) * (s.a1 - s.a0);
      const tk = s.members[i];
      // 相邻两家分到不同圈上 —— 一圈 500 个点只会糊成一条实线
      const rr = R - (i % rows) * RING_ROW_STEP;
      dots.push({
        tk, ang, r: rr, bi: s.bi, name: s.name,
        x: Math.cos(ang) * rr, y: Math.sin(ang) * rr,
      });
    }
  }
  return { dots, arcs, parts, shown: total, all: parts.total, rows };
}

// 环外的环节名怎么摆：一律横排，每个标签配一根很短的径向引线指回它的弧段。
// 中文不能沿半径排字（左半边必然倒着），横排又比排字占地方 —— 124 个环节绝对放不下，
// 所以按"公司数从多到少"贪心占位：先放最值得标的（大环节弧段也长），
// 位置被占了就挪到外一圈，外一圈也被占或文字要出画布就不放这一条。
// 放不下的不硬挤（上一版 124 个名字挤成一圈，左上角糊成一片黑），
// 靠"悬停弧段弹方块 + 下方 124 行完整清单"兜底。
function ringSideLabels(ctx, arcs, cx, cy, R, side, fontPx) {
  ctx.font = `500 ${fontPx}px ${getComputedStyle(document.body).fontFamily}`;
  const H = 15;                    // 一行标签的占位高度（字号 + 一点上下留白）
  const M = 5;                     // 标签之间至少留这么多
  const bands = [R + 24, R + 50];
  const placed = [];
  const out = [];
  for (const s of arcs.slice().sort((a, b) => b.n - a.n)) {
    const nameW = ctx.measureText(s.name).width;
    const countW = ctx.measureText(String(s.n)).width;
    const w = nameW + 5 + countW;                  // 名字 + 间距 + 家数
    const cos = Math.cos(s.mid), sin = Math.sin(s.mid);
    const right = cos >= 0;
    for (let b = 0; b < bands.length; b++) {
      const rr = bands[b];
      const lx = cx + cos * rr, ly = cy + sin * rr;
      if (ly - H / 2 < 10 || ly + H / 2 > side - 10) continue;
      // 右侧标签从锚点往右排，左侧往左排 —— 文字永远不翻个儿
      const x0 = right ? lx + 6 : lx - 6 - w;
      if (x0 < 8 || x0 + w > side - 8) continue;
      // 用**精确的矩形相交**判断，不用"角度宽度"近似：
      // 顶部/底部的标签是"横向"铺开的，近似会把实际跨度算偏（实测会叠出 4px）
      const box = { x0: x0 - M, x1: x0 + w + M, y0: ly - H / 2 - M, y1: ly + H / 2 + M };
      const clash = placed.some((p) => box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0);
      if (clash) continue;
      placed.push(box);
      out.push({ s, lx, ly, cos, nameW, countW, w, x0, band: b });
      break;
    }
  }
  return out;
}

// 谁和它共享环节（同一行业里）
function ringCompanions(ticker, ind, g, selfDots) {
  const mine = g.boardIdxOf?.[ticker] || [];
  const inInd = new Set(g.industries[ind] || []);
  const shared = new Map();
  for (const bi of mine) {
    for (const other of (g.boards[g.boardList[bi]] || [])) {
      if (other === ticker || !inInd.has(other)) continue;
      shared.set(other, (shared.get(other) || 0) + 1);
    }
  }
  const sameSector = new Set();
  const across = [];
  for (const d of selfDots) {
    if (!shared.has(d.tk)) continue;
    if (mine.includes(d.bi)) sameSector.add(d.tk);
    else across.push({ tk: d.tk, n: shared.get(d.tk) });
  }
  across.sort((a, b) => b.n - a.n);
  return { total: shared.size, sameSector, across };
}

function drawIndustryRing(cv, ind, g, sel = null, hoverSector = -1) {
  const dpr = window.devicePixelRatio || 1;
  const side = ringSide(cv);
  cv.width = Math.floor(side * dpr);
  cv.height = Math.floor(side * dpr);
  // 宽高必须都按 px 写：只写 width:100% 会被容器的实际宽度拉成椭圆
  cv.style.width = side + "px";
  cv.style.height = side + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, side, side);

  const narrow = side < RING_MIN_W;
  const TAU = Math.PI * 2;
  const cx = side / 2, cy = side / 2;

  const parts = industryParts(ind, g);
  // 角度先算（与半径无关）
  const arcs0 = ringArcs(parts);
  const allParts = arcs0;
  // 环外那圈留给环节名（横排 + 一根细引线）。名字不能用"沿半径排字"的写法：
  // 中文一旦顺着半径排，左半边必然倒着 —— 上一版这样画，用户直接指出"字体都是倒着的"。
  // 横排比排字占地方，所以 124 个环节不可能全标下，只能按公司数从多到少逐个试位（见 ①b）。
  const band = narrow ? 52 : LABEL_BAND;
  const R = side / 2 - band;
  const data = ringDots(parts, arcs0, R);

  cv._dots = data.dots;
  cv._arcs = data.arcs;
  cv._R = R;                          // 悬停命中判定要用同一个半径

  const font = getComputedStyle(document.body).fontFamily;
  const INK = cssVar("--text", "#D8DFE9");
  const FAINT = cssVar("--text-faint", "#5E6B7C");
  const RISE = cssVar("--rise", "#F6465D");
  const FALL = cssVar("--fall", "#2FB67C");
  const GOLD = cssVar("--gold", "#E8A33D");
  const LINE = cssVar("--border-strong", "#38445A");
  const q = indexData?.quotes || {};
  // 扫入动画：与首页大环同一套约定（cv._introT ∈ [0,1]，12 点顺时针展开）
  const intro = cv._introT == null ? 1 : cv._introT;
  const cutoff = intro * Math.PI * 2;          // 归一化角度（12 点起顺时针）

  // ① 外圈弧段 = 环节。**每一段都画** —— 之前只画"有 3 家以上"的，
  //    结果大量环节在图上完全不存在，看起来像数据缺失。
  // 124 段时节弧很密，2px 的线几乎看不见（用户就是因此说"只剩下点了"），加粗一档
  const arcW = data.arcs.length > 60 ? 2.6 : 3.2;
  for (const s of data.arcs) {
    if (s.n0 >= cutoff) continue;              // 扫入还没走到这段弧
    const a1 = Math.min(s.a1, s.a1 - Math.max(0, s.n1 - cutoff));
    const on = hoverSector === s.bi || (sel && sel.bi === s.bi);
    ctx.beginPath();
    ctx.arc(cx, cy, R + 14, s.a0, a1);
    ctx.strokeStyle = on ? GOLD : LINE;
    ctx.globalAlpha = on ? 1 : 0.85;
    ctx.lineWidth = on ? 4 : arcW;
    ctx.stroke();
  }
  // ①b 环外环节名：横排 + 细引线（绝不沿半径排字，那样左半边是倒的）。
  // 扫入期间不标名字——标签是静态信息，跟着弧段长出来反而乱。
  const labelPx = narrow ? 10 : 11;
  ctx.font = `500 ${labelPx}px ${font}`;
  const labels = intro >= 1 ? ringSideLabels(ctx, data.arcs, cx, cy, R, side, labelPx) : [];
  for (const L of labels) {
    const on = hoverSector === L.s.bi || (sel && sel.bi === L.s.bi);
    const ax = cx + Math.cos(L.s.mid) * (R + 15), ay = cy + Math.sin(L.s.mid) * (R + 15);
    const right = L.cos >= 0;
    ctx.strokeStyle = on ? GOLD : LINE;
    ctx.lineWidth = on ? 1.2 : 0.75;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(L.lx, L.ly);
    ctx.lineTo(L.lx + (right ? 5 : -5), L.ly);      // 末端一小横，像印刷品的引线
    ctx.stroke();
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = `500 ${labelPx}px ${font}`;
    ctx.fillStyle = on ? GOLD : INK;
    ctx.fillText(L.s.name, L.x0, L.ly);
    ctx.font = `400 ${labelPx}px ${font}`;
    ctx.fillStyle = on ? GOLD : FAINT;
    ctx.fillText(String(L.s.n), L.x0 + L.nameW + 5, L.ly);
  }
  cv._labels = labels.map((L) => ({ name: L.s.name, n: L.s.n, bi: L.s.bi, x: L.x0, y: L.ly, w: L.w }));
  // 这些量留给断言看：环上到底标了几个名字、是不是全标上了、用的是什么模式
  cv._labelInfo = {
    total: data.arcs.length,
    shown: labels.length,
    all: labels.length >= data.arcs.length,
    mode: "horizontal-outside",
  };

  ctx.globalAlpha = 1;
  ctx.textBaseline = "middle";

  // ② 公司点
  const comp = sel ? ringCompanions(sel.tk, ind, g, data.dots) : null;
  for (const d of data.dots) {
    if (d.ang + Math.PI / 2 > cutoff) continue;   // 扫入还没走到这个点
    const f = q[d.tk] || {};
    const v = f.changePercent;
    const isSelf = sel && d.tk === sel.tk;
    const isComp = comp && (comp.sameSector.has(d.tk) || comp.across.some((x) => x.tk === d.tk));
    ctx.beginPath();
    ctx.arc(cx + d.x, cy + d.y, dotRadius(f.marketCap, data.shown / data.rows), 0, Math.PI * 2);
    if (isSelf) {
      ctx.fillStyle = GOLD;
    } else if (isComp) {
      ctx.fillStyle = GOLD;
    } else {
      ctx.fillStyle = v == null ? FAINT : (v < 0 ? FALL : (v > 0 ? RISE : FAINT));
    }
    ctx.globalAlpha = sel && !isSelf && !isComp ? 0.3 : 1;
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // ③ 线：只画"跨环节的共同归属"，而且只在选中某家公司时。
  //    同一个环节里的同伴不画线 —— 它们本来就在同一段弧里，画线反而糊。
  if (comp && comp.across.length) {
    const pos = new Map(data.dots.map((d) => [d.tk, d]));
    const p0 = pos.get(sel.tk);
    ctx.strokeStyle = GOLD;
    ctx.lineWidth = 1.1;
    for (const { tk } of comp.across.slice(0, 10)) {
      const p1 = pos.get(tk);
      if (!p1) continue;
      const x1 = cx + p0.x, y1 = cy + p0.y, x2 = cx + p1.x, y2 = cy + p1.y;
      // 控制点取"两点中点在圆周上的投影"——线就会贴着圆周走。
      // 原来把控制点往圆心拉，几条线叠起来像一把扇子横在圆里，很乱。
      const mrx = (p0.x + p1.x) / 2, mry = (p0.y + p1.y) / 2;
      const mlen = Math.hypot(mrx, mry) || 1;
      const mx = cx + (mrx / mlen) * R * 0.94;
      const my = cy + (mry / mlen) * R * 0.94;
      ctx.globalAlpha = 0.42;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.quadraticCurveTo(mx, my, x2, y2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // ④ 中心读数（扫入期间留白，结束后再落内容）
  ctx.textAlign = "center";
  const y0 = cy - 18;
  if (intro < 1) return;
  if (sel) {
    const f = q[sel.tk] || {};
    const mine = (g.boardIdxOf?.[sel.tk] || []).map((bi) => g.boardList[bi]);
    const info = (indexData?.companies || []).find((c) => c.ticker === sel.tk);
    ctx.font = `600 20px ${font}`;
    ctx.fillStyle = INK;
    ctx.fillText(info ? info.name : sel.tk, cx, y0);
    ctx.font = `400 12px ${font}`;
    ctx.fillStyle = FAINT;
    ctx.fillText(`${sel.tk} · ${fmtCap(f.marketCap)} · ${fmtPct(f.changePercent)}`, cx, y0 + 22);
    ctx.font = `400 11.5px ${font}`;
    ctx.fillStyle = INK;
    const line = mine.slice(0, 2).join(" · ") + (mine.length > 2 ? ` 等 ${mine.length} 个环节` : "");
    ctx.fillText(line, cx, y0 + 44);
    ctx.fillStyle = GOLD;
    ctx.fillText(t("ring.compFmt", "同环节 {a} 家 · 跨环节 {b} 家")
      .replace("{a}", comp.sameSector.size).replace("{b}", comp.across.length), cx, y0 + 66);
  } else if (hoverSector >= 0) {
    const s = data.arcs.find((x) => x.bi === hoverSector);
    if (s) {
      ctx.font = `600 19px ${font}`;
      ctx.fillStyle = INK;
      ctx.fillText(s.name, cx, y0);
      ctx.font = `400 12px ${font}`;
      ctx.fillStyle = FAINT;
      ctx.fillText(t("ring.sectorFmt", "这个行业里有 {n} 家主环节落在这个环节").replace("{n}", fmtInt(s.n)), cx, y0 + 20);
      ctx.fillStyle = INK;
      ctx.font = `400 12px ${font}`;
      const names = s.members.map((tk) => ((indexData?.companies || []).find((c) => c.ticker === tk) || {}).name || tk);
      const rows = [];
      for (let i = 0; i < names.length && rows.length < 6; i += 3) {
        rows.push(names.slice(i, i + 3).join("　"));
      }
      rows.forEach((r, i) => ctx.fillText(r, cx, y0 + 42 + i * 17));
    }
  } else {
    const parts = data.parts;
    ctx.font = `600 30px ${cssVar("--font-d", "Georgia, serif")}`;
    ctx.fillStyle = INK;
    ctx.fillText(t("sector." + ind, ind), cx, y0 - 52);
    ctx.font = `400 13px ${font}`;
    ctx.fillStyle = FAINT;
    ctx.fillText(t("ring.center", "{c} 家公司 · {b} 个产业链环节")
      .replace("{c}", fmtInt(data.all)).replace("{b}", fmtInt(parts.ranked.length)), cx, y0 - 26);
    // 中心默认态放一个"前 5 大环节"迷你条：原来中间是一大片没有内容支撑的空白，
    // 有了这几条，留白才变成构图的一部分（环节名右对齐 · 细条 · 家数）
    const top5 = data.arcs.slice().sort((a, b) => b.n - a.n).slice(0, 5);
    const maxN = top5.length ? top5[0].n : 1;
    const barMax = Math.min(150, R * 0.5);
    ctx.textBaseline = "middle";
    top5.forEach((s, i) => {
      const y = y0 + 6 + i * 19;
      ctx.font = `400 11px ${font}`;
      ctx.fillStyle = INK;
      ctx.textAlign = "right";
      ctx.fillText(s.name.length > 8 ? s.name.slice(0, 7) + "…" : s.name, cx - 96, y);
      const w = Math.max(10, (s.n / maxN) * barMax);
      ctx.fillStyle = LINE;
      ctx.globalAlpha = 0.9;
      ctx.fillRect(cx - 88, y - 3, w, 6);
      ctx.globalAlpha = 1;
      ctx.textAlign = "left";
      ctx.fillStyle = FAINT;
      ctx.fillText(fmtInt(s.n), cx - 82 + w, y);
    });
    ctx.textAlign = "center";
    ctx.font = `400 12px ${font}`;
    ctx.fillStyle = FAINT;
    ctx.fillText(t("ring.hint", "把鼠标移到点上；或点下方清单里的环节"), cx, y0 + 108);
  }
}

// 点的大小 = 市值（对数），同时按行业规模压一压，免得大行业糊成实线
function dotRadius(mcap, perRow) {
  const base = 1.3 + Math.min(3.0, Math.log10(Math.max(1, mcap || 1)) * 0.6);
  const density = clamp(Math.sqrt(150 / Math.max(perRow, 1)), 0.55, 1.2);
  return clamp(base * density, 1.4, 6.2);
}

function setupRingHover(cv, ind, g) {
  if (!cv) return;
  const tip = document.getElementById("tile-tip");
  const pick = (e) => {
    const r = cv.getBoundingClientRect();
    const side = r.width;
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const cx = side / 2, cy = side / 2;
    let hit = null, best = 11;
    for (const d of (cv._dots || [])) {
      const dd = Math.hypot(cx + d.x - mx, cy + d.y - my);
      if (dd < best) { best = dd; hit = d; }
    }
    if (hit) return { dot: hit };
    // 不在点上：看看是不是落在某个弧段的角度范围内（弧段在 R+11 那一圈）
    const dist = Math.hypot(mx - cx, my - cy);
    // R 由 drawIndustryRing 算好后存在画布上
    const R = cv._R || (side / 2 - RING_MARGIN);
    // 外圈这一带只有弧段（环节名已挪到下方横排清单），没有公司点，所以整条都算命中区
    if (dist > R - 6 && dist < R + 150) {
      let ang = Math.atan2(my - cy, mx - cx) + Math.PI / 2;
      while (ang < 0) ang += Math.PI * 2;
      while (ang >= Math.PI * 2) ang -= Math.PI * 2;
      for (const s of (cv._arcs || [])) {
        if (ang >= s.n0 && ang <= s.n1) return { sector: s.bi };
      }
    }
    return {};
  };

  cv.onmousemove = (e) => {
    const { dot, sector } = pick(e);
    if (dot) {
      if (cv._sel && cv._sel.tk === dot.tk) return;
      cv._sel = dot; cv._hoverSector = -1;
      drawIndustryRing(cv, ind, g, dot, -1);
      if (tip) {
        const info = (indexData?.companies || []).find((c) => c.ticker === dot.tk);
        const f = (indexData?.quotes || {})[dot.tk] || {};
        tip.hidden = false;
        tip.innerHTML = `<b>${esc(info ? info.name : dot.tk)}</b>`
          + `<span>${esc(dot.tk)} · ${esc(fmtCap(f.marketCap))} · `
          + `<span class="${changeClass(f.changePercent)}">${esc(fmtPct(f.changePercent))}</span></span>`;
        tip.style.left = `${e.clientX + 12}px`;
        tip.style.top = `${e.clientY + 12}px`;
      }
      cv.style.cursor = "pointer";
    } else {
      const s = sector == null ? -1 : sector;
      const changed = (cv._sel ? -2 : -1) !== cv._hoverSector || cv._sel;
      cv._sel = null;
      if (cv._hoverSector === s && !changed) { return; }
      cv._hoverSector = s;
      drawIndustryRing(cv, ind, g, null, s);
      // 悬停在弧段上：弹一个小方块写环节名 + 家数
      if (tip) {
        const arc = (cv._arcs || []).find((x) => x.bi === s);
        if (arc) {
          tip.hidden = false;
          tip.innerHTML = `<b>${esc(arc.name)}</b><span>${esc(fmtInt(arc.n))} ${esc(t("stat.companies", "家"))}</span>`;
          tip.style.left = `${e.clientX + 14}px`;
          tip.style.top = `${e.clientY + 14}px`;
        } else {
          tip.hidden = true;
        }
      }
      cv.style.cursor = "default";
    }
  };
  cv.onmouseleave = () => {
    cv._sel = null; cv._hoverSector = -1;
    drawIndustryRing(cv, ind, g, null, -1);
    if (tip) tip.hidden = true;
  };
  cv.onclick = (e) => {
    const { dot } = pick(e);
    if (dot) location.hash = `#/c/${encodeURIComponent(dot.tk)}`;
  };
}
/* ---- 观点页 -------------------------------------------------------------- */
function renderMarkdown(md) {
  const escHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const inline = (s) => escHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let para = [];
  const flush = () => {
    if (!para.length) return;
    const text = para.join(" ");
    const whole = text.match(/^\*\*(.+)\*\*$/);
    if (whole) out.push(`<p class="prose-emph"><strong>${inline(whole[1])}</strong></p>`);
    else out.push(`<p>${inline(text)}</p>`);
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if (/^\s*$/.test(line)) { flush(); continue; }
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
      flush();
      const lvl = m[1].length;
      out.push(`<h${lvl}>${inline(m[2])}</h${lvl}>`);
      continue;
    }
    if (/^\s*-{3,}\s*$/.test(line)) { flush(); out.push("<hr />"); continue; }
    if (/^\s*[-*]\s+/.test(line)) {
      flush();
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*[-*]\s+/, ""))}</li>`);
        i++;
      }
      i--;
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      flush();
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        i++;
      }
      i--;
      out.push(`<ol>${items.join("")}</ol>`);
      continue;
    }
    para.push(line.trim());
  }
  flush();
  return out.join("\n");
}

async function renderVision() {
  app.innerHTML = "";
  startLoading();
  const file = getLocale() === "en" ? "./content/vision.en.md" : "./content/vision.md";
  let md = "";
  try { md = await (await fetch(file)).text(); } catch { md = ""; }
  stopLoading();
  if (parseRoute().name !== "vision") return;

  const body = md.trim()
    ? renderMarkdown(md)
    : `<p class="empty">${esc(t("wm.error", "内容没加载出来。"))}</p>`;
  app.innerHTML = `
    <div class="crumb"><a href="#/"><span class="arr" aria-hidden="true">←</span> ${esc(t("crumb.home", "全部公司"))}</a></div>
    <article class="prose vision">${body}</article>`;
  playVisionIntro();
}

// 观点页入场：先用和首屏一样的打字机打出标题，最后一字落定时正文逐段落淡入。
function playVisionIntro() {
  const article = app.querySelector(".prose.vision");
  if (!article) return;
  const h1 = article.querySelector("h1");
  const rest = Array.prototype.filter.call(article.children, (el) => el !== h1);
  if (!h1 || motionOff()) return;
  rest.forEach((el, i) => el.style.setProperty("--i", i));
  article.classList.add("vision-enter");
  typeTitle(h1, h1.textContent, 70, () => article.classList.add("in"));
}

/* ---- 顶栏搜索：输入给候选，回车/点击跳转 ---------------------------------
   之前的实现只有"过滤首页卡片"一种行为，而且过滤结果在首屏之下——
   用户在搜索框里打完整公司名，屏幕上什么都没发生，看起来就像坏了。
   现在补上主线：输入 → 下拉给候选（按精确度排序）→ 回车或点击直接进公司页。
   首页卡片过滤保留（浏览场景仍然好用），只是降级成次要行为。 */
let searchHits = [];       // 当前候选
let searchActive = -1;     // 键盘高亮到第几条

// 按"像不像"打分排序：代码全中 > 名称全中 > 前缀 > 包含 > 行业
function searchMatches(term, limit = 8) {
  const q = term.trim().toLowerCase();
  if (!q) return [];
  const hits = [];
  for (const c of (indexData?.companies || [])) {
    const name = c.name.toLowerCase();
    const ticker = c.ticker.toLowerCase();
    const sector = String(t("sector." + c.industry, c.industry)).toLowerCase();
    let score = 0;
    if (ticker === q) score = 100;
    else if (name === q) score = 95;
    else if (name.startsWith(q)) score = 80;
    else if (ticker.startsWith(q)) score = 70;
    else if (name.includes(q)) score = 50;
    else if (ticker.includes(q)) score = 40;
    else if (sector.includes(q)) score = 20;
    if (score) hits.push({ score, c });
  }
  hits.sort((a, b) => b.score - a.score || a.c.ticker.localeCompare(b.c.ticker));
  return hits.slice(0, limit).map((h) => h.c);
}

function closeSearchList() {
  const list = document.getElementById("search-list");
  if (list) { list.hidden = true; list.innerHTML = ""; }
  searchHits = [];
  searchActive = -1;
  searchEl?.setAttribute("aria-expanded", "false");
}

function renderSearchList(term) {
  const list = document.getElementById("search-list");
  if (!list) return;
  if (!term.trim()) { closeSearchList(); return; }
  searchHits = searchMatches(term);
  searchActive = searchHits.length ? 0 : -1;
  list.hidden = false;
  searchEl.setAttribute("aria-expanded", "true");
  list.innerHTML = searchHits.length
    ? searchHits.map((c, i) => `
        <button class="search-row${i === 0 ? " active" : ""}" type="button" role="option"
                data-ticker="${esc(c.ticker)}" aria-selected="${i === 0}">
          <span class="search-row-name">${esc(c.name)}</span>
          <span class="search-row-sector">${esc(t("sector." + c.industry, c.industry))}</span>
          <span class="search-row-ticker">${esc(c.ticker)}</span>
        </button>`).join("")
    : `<div class="search-empty">${esc(t("search.none", "没有匹配的公司"))}</div>`;
}

function setSearchActive(i) {
  if (!searchHits.length) return;
  searchActive = (i + searchHits.length) % searchHits.length;
  const rows = document.querySelectorAll("#search-list .search-row");
  rows.forEach((r, k) => {
    r.classList.toggle("active", k === searchActive);
    r.setAttribute("aria-selected", String(k === searchActive));
  });
  rows[searchActive]?.scrollIntoView({ block: "nearest" });
}

// 跳转：顺手清空搜索框，否则看起来还"筛着"
function goToCompany(ticker) {
  if (!ticker) return;
  closeSearchList();
  searchTerm = "";
  if (searchEl) searchEl.value = "";
  const m = document.getElementById("search-m");
  if (m) m.value = "";
  location.hash = `#/c/${encodeURIComponent(ticker)}`;
}

/* ---- 命令面板（⌘K / Ctrl-K / /） ------------------------------------------
   四组结果：页面（导航）/ 行业 / 产业链环节 / 公司。全键盘：↑↓ 移动、Enter 打开、
   Esc 关闭；另有 g h / g m / g v 的路由直达。DOM 首次打开时才建，语言切换后销毁
   重建（文案跟语言包走）。 */
let palEl = null, palBackdrop = null, palInput = null, palList = null;
let palItems = [];         // 当前面板里的可执行项，与 .pal-item 行一一对应
let palActive = -1;

// 环节不是页面，它的落地形态是"首页搜索结果里带上这个词"——环节芯片区会接住它
function goToSearch(name) {
  searchTerm = name;
  searchChain = null;
  if (searchEl) searchEl.value = name;
  const m = document.getElementById("search-m");
  if (m) m.value = name;
  if (parseRoute().name === "home") renderHome(false);
  else location.hash = "#/";
}

function paletteEnsure() {
  if (palEl) return;
  palBackdrop = document.createElement("div");
  palBackdrop.className = "palette-backdrop";
  palEl = document.createElement("div");
  palEl.className = "palette";
  palEl.setAttribute("role", "dialog");
  palEl.setAttribute("aria-modal", "true");
  palEl.setAttribute("aria-label", t("palette.placeholder", "搜索公司、行业、环节或页面…"));
  palEl.innerHTML = `
    <div class="palette-head">
      <span class="palette-prompt" aria-hidden="true">&gt;</span>
      <input class="palette-input" type="text" autocomplete="off" spellcheck="false"
             placeholder="${esc(t("palette.placeholder", "搜索公司、行业、环节或页面…"))}" />
    </div>
    <div class="palette-list" role="listbox"></div>
    <div class="palette-foot">${esc(t("palette.hint", "↑↓ 选择 · Enter 打开 · Esc 关闭"))}</div>`;
  document.body.append(palBackdrop, palEl);
  palInput = palEl.querySelector(".palette-input");
  palList = palEl.querySelector(".palette-list");

  palInput.addEventListener("input", () => renderPalette(palInput.value));
  palInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setPalActive(palActive + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setPalActive(palActive - 1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const item = palItems[palActive] || palItems[0];
      if (item) { closePalette(); item.run(); }
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();    // 别漏给 document 级处理器再关一次别的
      closePalette();
    }
  });
  palList.addEventListener("click", (e) => {
    const btn = e.target.closest(".pal-item");
    if (!btn) return;
    const item = palItems[Number(btn.dataset.i)];
    if (item) { closePalette(); item.run(); }
  });
  palList.addEventListener("mousemove", (e) => {
    const btn = e.target.closest(".pal-item");
    if (btn && Number(btn.dataset.i) !== palActive) setPalActive(Number(btn.dataset.i));
  });
  palBackdrop.addEventListener("click", closePalette);
}

const paletteOpen = () => !!(palEl && palEl.classList.contains("open"));

function openPalette() {
  paletteEnsure();
  palBackdrop.classList.add("open");
  palEl.classList.add("open");
  palInput.value = "";
  renderPalette("");
  palInput.focus();
}

function closePalette() {
  if (!palEl) return;
  palBackdrop.classList.remove("open");
  palEl.classList.remove("open");
  palInput.blur();   // 焦点不还回 body 的话，g h / / 这些全局键会被"输入框守卫"吞掉
}

function setPalActive(i) {
  const rows = palList ? [...palList.querySelectorAll(".pal-item")] : [];
  if (!rows.length) { palActive = -1; return; }
  palActive = ((i % rows.length) + rows.length) % rows.length;
  rows.forEach((el, k) => {
    el.classList.toggle("active", k === palActive);
    el.setAttribute("aria-selected", String(k === palActive));
  });
  rows[palActive].scrollIntoView({ block: "nearest" });
}

function renderPalette(qRaw) {
  const q = qRaw.trim().toLowerCase();
  const groups = [];

  // 页面：空查询也列——给"不知道搜什么、只想导航"一个出口
  const pages = [
    { name: t("nav.home", "首页"), hash: "#/", keys: "g h" },
    { name: t("nav.worldmap", "全景图谱"), hash: "#/worldmap", keys: "g m" },
    { name: t("nav.vision", "我们的观点"), hash: "#/vision", keys: "g v" },
  ].filter((p) => !q || p.name.toLowerCase().includes(q));
  if (pages.length) {
    groups.push({
      label: t("palette.pages", "页面"),
      items: pages.map((p) => ({ name: p.name, sub: p.keys, run: () => { location.hash = p.hash; } })),
    });
  }

  if (q) {
    const inds = (indexData?.industryList || [])
      .filter((ind) => ind.toLowerCase().includes(q)
        || String(t("sector." + ind, ind)).toLowerCase().includes(q))
      .slice(0, 4);
    if (inds.length) {
      groups.push({
        label: t("palette.industries", "行业"),
        items: inds.map((ind) => ({
          name: t("sector." + ind, ind),
          sub: `${fmtInt((graphData?.industries?.[ind] || []).length)} ${t("ind.unitCompanies", "家")}`,
          run: () => { location.hash = `#/i/${encodeURIComponent(ind)}`; },
        })),
      });
    }
    const boards = (graphData?.boardList || []).filter((b) => b.toLowerCase().includes(q)).slice(0, 4);
    if (boards.length) {
      groups.push({
        label: t("palette.boards", "产业链环节"),
        items: boards.map((b) => ({
          name: b,
          sub: `${fmtInt((graphData?.boards?.[b] || []).length)} ${t("ind.unitCompanies", "家")}`,
          run: () => goToSearch(b),
        })),
      });
    }
    const comps = searchMatches(qRaw, 6);
    if (comps.length) {
      groups.push({
        label: t("palette.companies", "公司"),
        items: comps.map((c) => ({
          name: c.name,
          sub: `${c.ticker} · ${t("sector." + c.industry, c.industry)}`,
          run: () => goToCompany(c.ticker),
        })),
      });
    }
  }

  palItems = [];
  let html = "";
  for (const g of groups) {
    html += `<div class="palette-group">${esc(g.label)}</div>`;
    for (const it of g.items) {
      it.name = typeof it.name === "string" ? it.name : String(it.name);
      palItems.push(it);
      html += `<button class="pal-item" type="button" role="option" data-i="${palItems.length - 1}" aria-selected="false">`
        + `<span class="pal-item-name">${esc(it.name)}</span>`
        + `<span class="pal-item-sub">${esc(it.sub)}</span></button>`;
    }
  }
  palList.innerHTML = html || `<div class="palette-empty">${esc(t("palette.empty", "没有匹配的结果"))}</div>`;
  setPalActive(palItems.length ? 0 : -1);
}

// 语言切换后面板文案要跟着换：直接销毁，下次打开时按新语言重建
function destroyPalette() {
  if (!palEl) return;
  palEl.remove();
  palBackdrop.remove();
  palEl = palBackdrop = palInput = palList = null;
  palItems = [];
  palActive = -1;
}

/* ---- 设置模态 ------------------------------------------------------------ */
function segRow(label, key, opts) {
  return `<div class="seg-row">
      <span class="seg-row-label">${esc(label)}</span>
      <span class="seg">
        ${opts.map((o) => `<button class="seg-btn" type="button" data-key="${esc(key)}" data-val="${esc(o.v)}" aria-pressed="${settings[key] === o.v}">${o.dot ? `<i class="swatch" style="background:${o.dot}"></i>` : ""}${esc(o.label)}</button>`).join("")}
      </span>
    </div>`;
}
function settingsBodyHTML() {
  return `
    ${segRow(t("settings.theme", "主题"), "theme", [
      { v: "dark", label: t("settings.theme.dark", "深色"), dot: "#0D1117" },
      { v: "light", label: t("settings.theme.light", "浅色"), dot: "#FFFFFF" },
    ])}
    ${segRow(t("settings.view", "首页大环"), "layout", [
      { v: "group", label: t("settings.view.detail", "标出每个行业") },
      { v: "flat", label: t("settings.view.compact", "只标最大的 8 个") },
    ])}
    ${segRow(t("settings.width", "卡片密度"), "width", [
      { v: "narrow", label: t("settings.width.narrow", "窄卡") },
      { v: "wide", label: t("settings.width.wide", "宽卡") },
    ])}
    ${segRow(t("settings.anim", "动效"), "animations", [
      { v: true, label: t("settings.anim.on", "开启") },
      { v: false, label: t("settings.anim.off", "关闭") },
    ])}
    ${segRow(t("settings.accent", "主色"), "accent", [
      { v: "navy", label: t("settings.accent.navy", "藏青"), dot: "#0A2540" },
      { v: "forest", label: t("settings.accent.forest", "松绿"), dot: "#1E4A3C" },
      { v: "graphite", label: t("settings.accent.graphite", "石墨"), dot: "#2A2E35" },
    ])}
    <p class="settings-note">${t("settings.note", "")}</p>`;
}
function openSettings() {
  document.getElementById("settings-backdrop")?.classList.add("open");
  const m = document.getElementById("settings-modal");
  if (m) { m.classList.add("open"); m.setAttribute("aria-hidden", "false"); }
}
function closeSettings() {
  document.getElementById("settings-backdrop")?.classList.remove("open");
  const m = document.getElementById("settings-modal");
  if (m) { m.classList.remove("open"); m.setAttribute("aria-hidden", "true"); }
}
const settingsOpen = () => !!document.getElementById("settings-modal")?.classList.contains("open");

function onSettingsClick(e) {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  const key = btn.dataset.key;
  let val = btn.dataset.val;
  if (key === "animations") val = val === "true";
  settings[key] = val;
  saveSettings();
  [...btn.parentElement.children].forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));

  if (key === "theme") {
    // 换肤本身成为一个动作：theme-anim 给全元素挂 220ms 颜色过渡，播完即摘，
    // 免得后续 hover 等状态色也被拖慢。画布色是绘制时读 cssVar 的，必须重渲染当前路由。
    if (!motionOff()) {
      document.documentElement.classList.add("theme-anim");
      setTimeout(() => document.documentElement.classList.remove("theme-anim"), 260);
    }
    applyTheme();
    route();
    return;
  }
  if (key === "accent") { applyAccent(); return; }
  if (key === "animations") { applyMotion(); return; }   // 下次渲染生效
  if (parseRoute().name === "home") {
    if (key === "layout") homeScrollY = 0;
    renderHome(false);
  }
}

// 事件只绑一次；文本和选项内容走 refreshSettings，语言切换时重刷即可
function setupSettings() {
  document.getElementById("settings-btn")?.addEventListener("click", openSettings);
  document.getElementById("settings-close")?.addEventListener("click", closeSettings);
  document.getElementById("settings-backdrop")?.addEventListener("click", closeSettings);
  document.getElementById("settings-body")?.addEventListener("click", onSettingsClick);
  refreshSettings();
}

function refreshSettings() {
  const title = document.getElementById("settings-title");
  if (title) title.textContent = t("settings.title", "设置");
  const body = document.getElementById("settings-body");
  if (body) body.innerHTML = settingsBodyHTML();
}

/* ---- 静态外壳 / 启动 ----------------------------------------------------- */
function markCurrentNav(name) {
  const home = document.getElementById("nav-home");
  const vision = document.getElementById("nav-vision");
  const worldmap = document.getElementById("nav-worldmap");
  // 公司页也算在"首页"这一栏下
  if (home) {
    const on = name === "home" || name === "company";
    if (on) home.setAttribute("aria-current", "page"); else home.removeAttribute("aria-current");
  }
  if (vision) {
    if (name === "vision") vision.setAttribute("aria-current", "page"); else vision.removeAttribute("aria-current");
  }
  if (worldmap) {
    if (name === "worldmap") worldmap.setAttribute("aria-current", "page"); else worldmap.removeAttribute("aria-current");
  }
}

function refreshChrome() {
  const ph = t("search.placeholder", "搜索名称或代码…");
  searchEl.placeholder = ph;
  const searchMEl = document.getElementById("search-m");
  if (searchMEl) searchMEl.placeholder = ph;
  // 页脚走 textContent，得用不带 <b> 的纯文本口径
  const asOf = indexData?.generatedAt
    ? t("footer.asOf", "数据截至 {d}").replace("{d}", indexData.generatedAt) + " · "
    : "";
  footerEl.textContent = asOf
    + ((getLocale() === "zh" && indexData?.disclaimerText) || t("footer", ""));
  const navHome = document.getElementById("nav-home");
  if (navHome) navHome.textContent = t("nav.home", "首页");
  const navVision = document.getElementById("nav-vision");
  if (navVision) navVision.textContent = t("nav.vision", "我们的观点");
  // 文字放在自己的 span 里，更新它不会把"新"角标一起抹掉
  const navMap = document.getElementById("nav-worldmap-text");
  if (navMap) navMap.textContent = t("nav.worldmap", "全景图谱");
  const chip = document.getElementById("nav-worldmap-chip");
  if (chip) chip.textContent = t("nav.newChip", "新");
  const trayLabel = document.getElementById("tray-label");
  if (trayLabel) trayLabel.textContent = t("saved.label", "自选");
  const trayTitle = document.getElementById("tray-title-text");
  if (trayTitle) trayTitle.textContent = t("saved.title", "自选清单");
  const trayClear = document.getElementById("tray-clear");
  if (trayClear) trayClear.textContent = t("saved.clear", "清空");
  renderTray();   // 刷新空状态文案和公司名
}

// 全景图谱入口上的"新"角标：前三次访问（一次会话算一次）弹出来，之后永久退休。
// 真正打开过这个页面，也会立刻退休。
const WM_CHIP_KEY = "cnchain.worldmapNewSeen";
function setupWorldMapChip() {
  const chip = document.getElementById("nav-worldmap-chip");
  if (!chip) return;
  let state = null;
  try { state = localStorage.getItem(WM_CHIP_KEY); } catch { state = "done"; }
  if (state === "done") { chip.remove(); return; }
  const dismiss = () => {
    try { localStorage.setItem(WM_CHIP_KEY, "done"); } catch { /* ignore */ }
    chip.remove();
  };
  let visits = parseInt(state, 10) || 0;
  try {
    if (!sessionStorage.getItem("cnchain.wmChipCounted")) {
      sessionStorage.setItem("cnchain.wmChipCounted", "1");
      visits += 1;
      localStorage.setItem(WM_CHIP_KEY, String(visits));
    }
  } catch { /* ignore */ }
  if (visits > 3 || parseRoute().name === "worldmap") { dismiss(); return; }
  chip.hidden = false;
  window.addEventListener("hashchange", () => {
    if (chip.isConnected && parseRoute().name === "worldmap") dismiss();
  });
}

function buildLangSwitcher() {
  langEl.innerHTML = listLocales().map((l) =>
    `<option value="${esc(l.code)}" ${l.code === getLocale() ? "selected" : ""}>${esc(l.label)}</option>`).join("");
}

/* ---- 终端启动序列：当天首次访问才播放 -------------------------------------
   data-boot="on" 由 index.html 的内联脚本在首帧前判定（当天没播过 + 允许动效），
   不播放的日子元素直接 display:none，连挂载都没有成本。
   这里是"真进度"：index/graph 两行等真实加载落定才打 OK——网络慢时它真的多停
   一会儿，这正是这台"终端"要说的事。CSS 里有 9s 兜底淡出，JS 异常也盖不死页面。 */
function startBootConsole() {
  const el = document.getElementById("boot-console");
  if (!el) return null;
  if (document.documentElement.dataset.boot !== "on" || motionOff()) {
    el.remove();
    delete document.documentElement.dataset.boot;
    return null;
  }
  const lines = [...el.querySelectorAll(".boot-line")];
  const show = (i) => lines[i] && lines[i].classList.add("on");
  const t0 = performance.now();
  show(0);                            // CHAINATLAS TERMINAL · BOOT SEQUENCE
  setTimeout(() => show(1), 120);     // AUTH OK
  const fill = (id, text) => {
    const v = document.getElementById(id);
    if (v) v.textContent = text;
  };
  return {
    indexDone() {
      fill("boot-index", `${fmtInt(indexData?.totals?.companies || 0)} COMPANIES OK`);
      show(2);
    },
    graphDone() {
      fill("boot-graph", `${fmtInt(graphData?.boardList?.length || 0)} BOARDS OK`);
      show(3);
      setTimeout(() => show(4), 90);  // RENDER + 光标
    },
    async done() {
      // 最短驻留 900ms：加载太快时也要让人读完这几行，不然仪式感白做
      const wait = Math.max(0, 900 - (performance.now() - t0));
      await new Promise((r) => setTimeout(r, wait));
      el.getAnimations().forEach((a) => a.cancel());   // 摘掉 9s 兜底，淡出改由 .out 控制
      el.classList.add("out");
      try {
        const now = new Date();
        localStorage.setItem("cnchain.bootDay", `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`);
      } catch { /* ignore */ }
      setTimeout(() => { el.remove(); delete document.documentElement.dataset.boot; }, 300);
    },
  };
}

async function boot() {
  // 滚动位置由我们自己管（返回首页时要还原），所以别让浏览器也来恢复一次
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  // 量一下吸顶 header 的实际高度，供加载线和 hero 条定位用
  // （窄屏下 header 会换行，所以量而不是写死）
  const syncHeaderHeight = () => {
    const h = document.querySelector(".site-header")?.offsetHeight || 52;
    document.documentElement.style.setProperty("--header-h", `${h}px`);
  };
  syncHeaderHeight();
  window.addEventListener("resize", syncHeaderHeight);

  loadSettings();
  applyTheme();       // index.html 已经在首帧前设过一遍（双保险）
  applyAccent();
  applyMotion();
  loadSaved();
  mapZoom = settings.zoom || mapZoom;
  const bootUI = startBootConsole();   // 启动序列开跑（今天播过/关动效则返回 null）

  await initI18n();
  if (loadDepth > 0) {
    const status = document.getElementById("load-status");
    if (status) status.textContent = t("loading", "加载中…");
  }
  buildLangSwitcher();
  refreshChrome();
  setupWorldMapChip();
  setupSettings();

  try {
    indexData = await getJSON("./data/index.json");
  } catch {
    indexData = { companies: [], totals: {} };
  }
  bootUI?.indexDone();

  // graph 给首页的行业概览卡提供环节分布（行情的三个数已随 index.json 下来）。
  await loadGraph();
  bootUI?.graphDone();
  // 把 index.json 里的轻量行情字段展开成 quotes 映射，下游渲染代码不用改。
  // 三个数全缺的公司不建条目——卡片本来就会按"没有数字"渲染。
  indexData.quotes = {};
  for (const c of indexData.companies || []) {
    if (c.price == null && c.changePercent == null && c.marketCap == null) continue;
    indexData.quotes[c.ticker] = {
      price: c.price, changePercent: c.changePercent, marketCap: c.marketCap,
    };
  }

  // index.json 里带着数据来源说明（disclaimer），要等它加载完再刷一次 chrome，
  // 否则页脚会一直停留在语言包里的兜底文案
  refreshChrome();
  setupSaved();

  // 桌面顶栏输入框和手机悬浮搜索条共用同一份状态
  const applySearch = (value) => {
    searchTerm = value;
    if (!value.trim()) searchChain = null;    // 清空搜索框 = 退出环节筛选
    // 输入时只过滤首页的卡片列表；不在首页就不动路由——
    // 现在是"输入给候选、回车才跳转"，把用户从公司页强行拽回首页是反效果。
    if (parseRoute().name === "home") renderHome(false);
    renderSearchList(value);
  };
  searchEl.addEventListener("input", (e) => {
    applySearch(e.target.value);
    const m = document.getElementById("search-m");
    if (m) m.value = e.target.value;
  });

  // 键盘：上下选候选、回车跳转、Esc 清空
  searchEl.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSearchActive(searchActive + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSearchActive(searchActive - 1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const pick = searchHits[searchActive] || searchHits[0];
      if (pick) goToCompany(pick.ticker);
    } else if (e.key === "Escape") {
      if (searchEl.value) {
        searchEl.value = ""; searchTerm = ""; closeSearchList();
        if (parseRoute().name === "home") renderHome(false);
        const m = document.getElementById("search-m");
        if (m) m.value = "";
      }
    }
  });

  // 首页搜索结果里的"匹配环节"芯片。
  // 挂在 document 上而不是 #home-body 上：#home-body 每次整页渲染都会重建，
  // 绑在它身上的监听会随着旧元素一起消失（踩过一次的坑）。
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-schain]");
    if (!btn) return;
    searchChain = btn.dataset.schain === "" ? null : btn.dataset.schain;
    renderHome(false);
  });

  // 点候选直接跳
  document.getElementById("search-list")?.addEventListener("click", (e) => {
    const row = e.target.closest("[data-ticker]");
    if (row) goToCompany(row.dataset.ticker);
  });

  // 点到搜索区外面就收起下拉
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrap")) closeSearchList();
  });

  const searchFab = document.getElementById("search-fab");
  const searchPill = document.getElementById("search-pill");
  const searchM = document.getElementById("search-m");
  if (searchFab && searchPill && searchM) {
    // 有些 iOS Safari 版本即便写了 maximum-scale=1 也会在聚焦时缩放页面。
    // 聚焦那一瞬间把 user-scalable 关掉是可靠的开关，过后立刻还原，
    // 双指缩放照常可用。
    const focusWithoutZoom = (input) => {
      const vp = document.querySelector('meta[name="viewport"]');
      if (!vp) { input.focus(); return; }
      const base = vp.getAttribute("content");
      vp.setAttribute("content", `${base}, user-scalable=no`);
      input.focus({ preventScroll: true });
      setTimeout(() => vp.setAttribute("content", base), 500);
    };
    searchFab.addEventListener("click", () => {
      const open = searchPill.hidden;
      searchPill.hidden = !open;
      searchFab.setAttribute("aria-expanded", String(open));
      if (open) { searchM.value = searchTerm; focusWithoutZoom(searchM); }
    });
    searchM.addEventListener("input", (e) => {
      searchEl.value = e.target.value;
      applySearch(e.target.value);
    });
    // 手机上没有下拉的位置（整个搜索区在窄屏是隐藏的），所以只保留回车跳转
    searchM.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const pick = searchMatches(searchM.value, 1)[0];
      if (pick) goToCompany(pick.ticker);
    });
  }

  langEl.addEventListener("change", async (e) => {
    await setLocale(e.target.value);
    refreshChrome();
    refreshSettings();
    destroyPalette();      // 面板文案跟语言包走，销毁后下次打开时按新语言重建
    route();
  });

  window.addEventListener("resize", () => {
    if (parseRoute().name === "company" && document.getElementById("vcm-map")) {
      requestAnimationFrame(drawMap);
    }
  });

  // Esc 的关闭顺序：命令面板 > 设置模态（搜索下拉的 Esc 由搜索框自己处理）
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (paletteOpen()) { closePalette(); return; }
    if (settingsOpen()) closeSettings();
  });

  // 全局快捷键：⌘K / Ctrl-K 开关命令面板；"/" 打开；g h / g m / g v 路由直达。
  // 输入框里一律不抢键（面板内的 ↑↓/Enter/Esc 由面板自己的监听器处理）。
  let gPending = 0;
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (paletteOpen()) closePalette(); else openPalette();
      return;
    }
    if (e.target.closest("input, textarea, select, [contenteditable]")) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;   // Shift 按下时 e.key 是大写
    if (k === "/") {
      e.preventDefault();
      openPalette();
      return;
    }
    if (k === "g") { gPending = Date.now(); return; }
    if (gPending && Date.now() - gPending < 1500) {
      const dest = { h: "#/", m: "#/worldmap", v: "#/vision" }[k];
      gPending = 0;
      if (dest) { location.hash = dest; return; }
    } else {
      gPending = 0;
    }
  });

  // 搜索框里的键帽：提示命令面板的存在，可点；非 Mac 平台显示真实键位
  const kbd = document.getElementById("search-kbd");
  if (kbd) {
    if (!/Mac|iPhone|iPad/.test(navigator.platform || "")) kbd.textContent = "Ctrl K";
    kbd.addEventListener("click", openPalette);
    kbd.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPalette(); }
    });
  }

  window.addEventListener("hashchange", () => { closePalette(); route(); });

  // 启动序列先谢幕，首个视图再亮相——hero 打字机、数字滚动、大环扫入
  // 都在幕布揭开后才开始，编排感才成立
  await bootUI?.done();

  // 首个视图真正渲染完之后，才释放进度线——
  // 在此之前它一直亮着，覆盖了 i18n + index.json 的加载
  await route();
  stopLoading();
}

boot();
