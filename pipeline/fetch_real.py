# -*- coding: utf-8 -*-
"""
从 akshare 拉真实行情与财务 → pipeline/real/fundamentals.json

请求数量：整个市场只需要 4 次（不是每家公司一次）：
  - 实时行情快照        1 次 → 价格 / 昨收 / 涨跌幅 / 总市值 / 市盈率(动)
  - 业绩报表 × 3 个报告期 → 净利润 / 营收 / 毛利率 / 每股收益 / 营收同比
所有原始响应落盘缓存（raw/），改口径不用重新联网。

`make_quote()` 是核心的组装逻辑，被 build_chain.py 共用 ——
两份口径抄在两地，早晚会不一致。

用法：../.venv/Scripts/python.exe fetch_real.py
"""

import json
import math
import os
import random
import shutil
import subprocess
import urllib.parse
import sys
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")

import akshare as ak  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "real")
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)

def report_periods(today=None):
    """按今天的日期推算要拉的三个报告期（业绩报表都是**累计**口径）。

    披露截止：一季报 4/30 · 中报 8/31 · 三季报 10/31 · 年报次年 4/30。
    latest 取"披露截止日已过"的期止最近一期 —— 截止没到的不拉：
    东财业绩报表里只有已披露的公司，拿半截数据算 TTM 会错。

    返回 {latest, prev_same, prev_fy}：
      prev_same = 去年同期累计，prev_fy = 去年年报。
      TTM = prev_fy − prev_same + latest。latest 恰好是年报时
      prev_same 与 prev_fy 是同一份（都是上上年年报），公式自然退化成
      TTM = latest，不用特判；make_quote 里仍加了直接分支，省一次查表。
    """
    today = today or date.today()
    y = today.year
    # 枚举近两年的四个报告期（跨年之后今年还没有任何披露完的期，
    # 不把去年也算进来，1 月会取不到任何候选 —— 实测踩过）
    cand = []
    for yy in (y, y - 1, y - 2):
        cand += [
            (date(yy, 3, 31), date(yy, 4, 30)),        # 一季报
            (date(yy, 6, 30), date(yy, 8, 31)),        # 中报
            (date(yy, 9, 30), date(yy, 10, 31)),       # 三季报
            (date(yy, 12, 31), date(yy + 1, 4, 30)),   # 年报
        ]
    ok = [p for p, ddl in cand if ddl <= today]
    latest = max(ok)                             # 期止最近的可用报告期
    qend = {3: 31, 6: 30, 9: 30, 12: 31}[latest.month]
    return {
        "latest": latest.strftime("%Y%m%d"),
        "prev_same": date(latest.year - 1, latest.month, qend).strftime("%Y%m%d"),
        "prev_fy": date(latest.year - 1, 12, 31).strftime("%Y%m%d"),
    }


PERIODS = report_periods()   # 模块级缓存一份，import 方（build_chain）不用改


def num(v):
    """把 pandas 里的各种"缺失"统一成 None，数字统一成 float。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def make_quote(sp, cur, prev_same, prev_fy):
    """把「行情快照 + 三期业绩报表」组装成一家公司的行情记录。

    参数是三条原始记录（都是东财的字段名），返回统一口径的 dict。
    sp 为空说明这家公司没在行情快照里，返回 None。
    """
    if not sp:
        return None

    def rnd(v, d=2):
        return round(v, d) if v is not None else None

    price = num(sp.get("最新价"))
    mcap_yuan = num(sp.get("总市值"))
    pe_dyn = num(sp.get("市盈率-动态"))

    rec = {
        "currency": "CNY",
        "suspended": price is None,   # 停牌：最新价为空，但市值仍按停牌前算
        "price": price,
        "prevClose": num(sp.get("昨收")),
        "changePercent": num(sp.get("涨跌幅")),
        "marketCap": round(mcap_yuan / 1e8, 2) if mcap_yuan else None,  # 元 → 亿元
        "asOf": date.today().isoformat(),
        "source": "akshare",
        "simulated": False,
        "sourceNote": "东方财富 · akshare",
    }

    # 总股本（亿股）= 市值 / 价格，后面算 TTM 每股收益要用
    shares_yi = (mcap_yuan / price / 1e8) if (mcap_yuan and price) else None
    rec["shares"] = round(shares_yi, 4) if shares_yi else None

    rec["grossMargins"] = rnd(num(cur.get("销售毛利率")))
    rec["revenueGrowth"] = rnd(num(cur.get("营业总收入-同比增长")))
    rec["trailingEps"] = rnd(num(cur.get("每股收益")), 2)

    # 净利率 = 净利润 ÷ 营业总收入（两处都是累计口径，相除即净利率）
    nprofit, revenue = num(cur.get("净利润-净利润")), num(cur.get("营业总收入-营业总收入"))
    rec["profitMargins"] = rnd(nprofit / revenue * 100) if (nprofit and revenue) else None

    # TTM净利润 = 上年全年 + 本期累计 − 去年同期累计
    # （业绩报表给的是"累计"口径：一季报=Q1、中报=上半年、三季报=前三季、年报=全年，
    #   所以"去年全年 − 去年同期 + 今年本期"永远成立；本期就是年报时直接用它）
    np_fy = num(prev_fy.get("净利润-净利润"))
    np_cur = num(cur.get("净利润-净利润"))
    np_same = num(prev_same.get("净利润-净利润"))
    if PERIODS["latest"][4:6] == "12":
        ttm = np_cur                                   # latest 本身就是年报
    else:
        ttm = np_fy - np_same + np_cur if None not in (np_fy, np_cur, np_same) else None
    rec["lossMaking"] = bool(ttm is not None and ttm <= 0)

    if rec["lossMaking"]:
        # 亏损公司的市盈率是负数，没有含义 —— 宁可空着，也不展示 -5.81 这种数
        rec["trailingPE"] = None
        rec["forwardPE"] = None
        rec["peSource"] = "loss"
    elif ttm and mcap_yuan:
        rec["trailingPE"] = round(mcap_yuan / ttm, 2)
        rec["peSource"] = "ttm"
        if shares_yi:
            rec["trailingEps"] = rnd(ttm / 1e8 / shares_yi, 2)   # TTM 口径
        rec["forwardPE"] = pe_dyn
    else:
        rec["trailingPE"] = pe_dyn
        rec["forwardPE"] = pe_dyn
        rec["peSource"] = "dynamic"

    rec["reportPeriod"] = PERIODS["latest"]
    return rec


def fetch_cache(name, fn):
    """带磁盘缓存的请求：跑过一次就不重复联网。删掉 raw/ 下对应文件可强制重拉。"""
    path = os.path.join(RAW, name + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    df = None
    for attempt in (1, 2, 3):
        try:
            df = fn()
            break
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  ! {name} 第 {attempt} 次失败（{type(e).__name__}），5 秒后重试…")
            time.sleep(5)
    records = json.loads(df.to_json(orient="records", force_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"  ✓ {name}: {len(records)} 条")
    time.sleep(1)          # 请求之间留点间隔，别把数据源打疼
    return records


def index_by(rows, key):
    out = {}
    for r in rows:
        k = (r.get(key) or "").strip()
        if k:
            out[k] = r
    return out


def load_raw():
    """读出缓存的原始数据（不联网）。返回 (spot, yjbb) 两个索引。"""
    spot = index_by(json.load(open(os.path.join(RAW, "spot.json"), encoding="utf-8")), "代码")
    yjbb = {}
    for label, period in PERIODS.items():
        path = os.path.join(RAW, f"yjbb_{period}.json")
        yjbb[label] = index_by(json.load(open(path, encoding="utf-8")), "股票代码") \
            if os.path.exists(path) else {}
    return spot, yjbb


def quote_for(ticker, spot, yjbb):
    """给一个代码，返回它的行情记录（用缓存，不联网）。"""
    return make_quote(spot.get(ticker),
                      yjbb["latest"].get(ticker) or {},
                      yjbb["prev_same"].get(ticker) or {},
                      yjbb["prev_fy"].get(ticker) or {})


_CURL = shutil.which("curl") or "curl"   # 命令行 curl（Git 的和 Windows 自带的都行）


def curl_get(url, params=None, timeout=15):
    """用**命令行 curl（强制 IPv4）**发 GET 并返回一个只有 .json() 的响应对象。

    为什么（2026-09-26 排障结论）：push2.eastmoney.com 的 DNS 同时返回 IPv4 和
    IPv6，**IPv6 那条路（240e:e1:9600:…）连接一建立就被掐**，IPv4 正常。
    requests / curl_cffi 都优先走 IPv6，所以时好时坏 —— 全看系统这次让谁先连。
    --ipv4 直接绕开整类问题。之前怀疑的"TLS 指纹"是误判，实测 IPv4 上
    requests、curl、curl_cffi 都通。
    注意 --noproxy '*'：机器上有代理环境变量/系统代理时，请求会被代理截断。"""
    if params:
        qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus)
        url = f"{url}?{qs}"
    # akshare 写死的"82.push2"带序号镜像不稳定，统一走主站
    url = url.replace("82.push2.", "push2.")
    last_err = None
    for attempt in range(3):
        r = subprocess.run([_CURL, "-s", "--noproxy", "*", "--ipv4",
                            "--max-time", str(timeout), url],
                           capture_output=True, timeout=timeout + 10)
        if r.returncode == 0 and r.stdout.strip():
            return _CurlResponse(r.stdout)
        last_err = f"curl exit {r.returncode} {r.stderr.decode('utf-8', 'ignore')[:80]}"
        # 断连是间歇性的（同一条命令隔几分钟结果就不同），逐次加长间隔等好窗口
        time.sleep((2, 8, 20)[min(attempt, 2)])
    raise RuntimeError(f"curl 连续 3 次失败：{last_err}（{url[:80]}…）")


class _CurlResponse:
    """只实现 akshare 用到的部分：.json() / .status_code / .raise_for_status()。"""

    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return json.loads(self._body.decode("utf-8"))

    def raise_for_status(self):
        return None


class _CurlShim:
    """替身：给 stock_yjbb_em（模块内直接 requests.get(url, params=...)）用。"""

    @staticmethod
    def get(url, params=None, **kw):
        time.sleep(random.uniform(1.5, 3.0))   # yjbb 的翻页循环自己不带间隔，这里补上防限流
        return curl_get(url, params, kw.get("timeout", 15))


def _slow_fetch_paginated_data(url, base_params, timeout=15):
    """东财对**连续请求**限流：实测每页间隔 0.5-1.5 秒时，连续 4-5 页必被掐断
    连接（2026-09-28 实测两次都死在第 4-5 页）。akshare 自带的分页太密，
    这里整函数换成慢速版：每页间隔 3.5-5.5 秒。59 页约 4~5 分钟，日更可接受。"""
    import pandas as pd
    params = dict(base_params)
    data_json = curl_get(url, params, timeout).json()
    per_page = len(data_json["data"]["diff"])
    total_page = math.ceil(data_json["data"]["total"] / per_page)
    rows = list(data_json["data"]["diff"])
    print(f"    共 {data_json['data']['total']} 行 / {total_page} 页，慢速分页中…", flush=True)
    for page in range(2, total_page + 1):
        time.sleep(random.uniform(3.5, 5.5))
        params["pn"] = page
        rows.extend(curl_get(url, params, timeout).json()["data"]["diff"])
        if page % 10 == 0:
            print(f"    … 第 {page}/{total_page} 页", flush=True)
    return pd.DataFrame(rows)


def patch_akshare_transport():
    """把本项目用到的三个 akshare 请求入口整体换到 curl 子进程。
    只影响本进程的内存对象，不改 akshare 的文件。三个入口：
      1. akshare.utils.request.request_with_retry   —— 原始定义处
      2. akshare.utils.func.request_with_retry      —— func.py 是 from-import，
         必须改它模块里的名字，否则行情分页还是走旧通道
      3. akshare.stock_feature.stock_yjbb_em.requests —— 业绩报表是模块内直接
         requests.get，给它一个 curl 替身
    """
    import akshare.utils.request as _req
    import akshare.utils.func as _func
    import akshare.stock_feature.stock_yjbb_em as _yjbb
    import akshare.stock_feature.stock_hist_em as _hist

    def request_with_retry(url, params=None, timeout=15, max_retries=3,
                           base_delay=1.0, random_delay_range=(0.5, 1.5)):
        return curl_get(url, params, timeout)      # curl_get 内部自带 3 次重试

    _req.request_with_retry = request_with_retry
    _func.request_with_retry = request_with_retry
    _func.fetch_paginated_data = _slow_fetch_paginated_data      # 慢速分页（防限流）
    _hist.fetch_paginated_data = _slow_fetch_paginated_data      # 同上，stock_hist_em 是 from-import
    _yjbb.requests = _CurlShim
    print(f"  传输层已切换命令行 curl（{_CURL}）+ 慢速分页 —— 东财对连续请求限流")


def main():
    from dataset import COMPANIES   # 旧路径：只为这 159 家出数据

    patch_akshare_transport()

    # --refresh：日更用。删掉行情/业绩的原始缓存再拉，否则 fetch_cache
    # 看到 raw/ 里有文件就直接用旧的、根本不联网 —— 数据永远停在第一天。
    # ⚠️ 只删行情自己的 4 个文件。real/raw/ 是三个抓取脚本共用的目录，
    #    行业（31 请求）和概念（185 请求）的缓存也在里面，误删的话
    #    以后改筛选口径就得重新联网抓一遍。
    if "--refresh" in sys.argv:
        gone = []
        for name in ["spot.json"] + [f"yjbb_{p}.json" for p in PERIODS.values()]:
            f = os.path.join(RAW, name)
            if os.path.exists(f):
                os.remove(f)
                gone.append(name)
        print(f"① 清掉行情缓存 {len(gone)} 个：{', '.join(sorted(gone)) or '（原本就没有）'}")

    tickers = [c[0] for c in COMPANIES]

    print("① 实时行情快照（1 次请求，全市场）")
    fetch_cache("spot", lambda: ak.stock_zh_a_spot_em())

    print("② 业绩报表（3 个报告期，用于 TTM 与利润率）")
    for label, period in PERIODS.items():
        fetch_cache(f"yjbb_{period}", lambda p=period: ak.stock_yjbb_em(date=p))

    print("③ 组装")
    spot, yjbb = load_raw()
    out, missing = {}, []
    for t in tickers:
        rec = quote_for(t, spot, yjbb)
        if rec:
            out[t] = rec
        else:
            missing.append(t)

    with open(os.path.join(OUT, "fundamentals.json"), "w", encoding="utf-8") as f:
        json.dump({"generatedAt": date.today().isoformat(), "quotes": out},
                  f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n✓ 写出 {len(out)} 家真实数据 → real/fundamentals.json")
    if missing:
        print(f"⚠ {len(missing)} 家没取到：{missing[:8]}")


if __name__ == "__main__":
    sys.exit(main())
