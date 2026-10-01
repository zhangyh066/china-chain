// 极简运行时多语言。加一门语言 = 往 /locales 丢一个文件 + 在 /locales/manifest.json
// 里加一行，不需要改任何代码。

const BUILD = "__BUILD__";   // 构建时由 build_dist.py 注入时间戳，发版即击穿浏览器缓存

let dict = {};
let current = "zh";
let locales = [{ code: "zh", label: "简体中文" }];

const STORAGE_KEY = "cnchain.locale";

export async function initI18n() {
  try {
    locales = await (await fetch("./locales/manifest.json?v=" + BUILD)).json();
  } catch {
    locales = [{ code: "zh", label: "简体中文" }];
  }
  let saved = null;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch { /* ignore */ }
  const wanted = saved && locales.some((l) => l.code === saved) ? saved : locales[0].code;
  await setLocale(wanted);
}

export async function setLocale(code) {
  try {
    dict = await (await fetch(`./locales/${code}.json?v=${BUILD}`)).json();
    current = code;
    try { localStorage.setItem(STORAGE_KEY, code); } catch { /* ignore */ }
    document.documentElement.lang = code === "zh" ? "zh-CN" : code;
  } catch {
    dict = {};
  }
}

export function t(key, fallback) {
  return dict[key] ?? fallback ?? key;
}

export function getLocale() {
  return current;
}

export function listLocales() {
  return locales;
}

/* ---- 格式化（全部走 Intl，按本币展示） ---------------------------------- */
// 金额一律以人民币（CNY）计价，与界面语言无关——这是证券的"本币"。

export function fmtPrice(v) {
  if (v == null) return "—";
  try {
    return new Intl.NumberFormat(current, {
      style: "currency", currency: "CNY",
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(v);
  } catch { return `¥${v}`; }
}

// 市值：value 单位是「亿元」
export function fmtCap(v) {
  if (v == null) return "—";
  if (current === "en") {
    const yuan = v * 1e8;
    const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"]];
    for (const [base, suffix] of units) {
      if (yuan >= base) {
        return `¥${(yuan / base).toFixed(2).replace(/\.?0+$/, "")}${suffix}`;
      }
    }
    return `¥${Math.round(yuan)}`;
  }
  if (v >= 10000) return `${(v / 10000).toFixed(2).replace(/\.?0+$/, "")}万亿`;
  return `${v.toFixed(1).replace(/\.0$/, "")}亿`;
}

export function fmtPct(v, withSign = true) {
  if (v == null) return "—";
  // signDisplay:"exceptZero" 已经负责加正负号，不要再自己补一个 "+"
  return new Intl.NumberFormat(current, {
    style: "percent", maximumFractionDigits: 2,
    signDisplay: withSign ? "exceptZero" : "auto",
  }).format(v / 100);
}

export function fmtNum(v, digits = 2) {
  if (v == null) return "—";
  return new Intl.NumberFormat(current, { maximumFractionDigits: digits }).format(v);
}

export function fmtInt(v) {
  if (v == null) return "—";
  return new Intl.NumberFormat(current).format(v);
}
