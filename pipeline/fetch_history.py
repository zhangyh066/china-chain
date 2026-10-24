# -*- coding: utf-8 -*-
"""抓取公司日线历史：前复权日 K → data/h/{代码}.json，公司页"近一年走势"用。

每家一份紧凑 JSON（与 data/f/、data/p/ 同一发布模式）：
  {
    "code": "300750",
    "generatedAt": "2026-10-12",
    "points": [["2025-10-13", 305.12], …]   ← [日期, 收盘价(前复权)]，日期升序，
  }                                            只保留最近约 250 个交易日

两个数据源（--source 切换，默认 tx）：
- tx 腾讯：ak.stock_zh_a_hist_tx（代码带 sh/sz 前缀，返回 date/close 英文列）。
  东财对本机 IP 有持续限流时的主力源。
- em 东财：ak.stock_zh_a_hist（akshare 1.18.x 里 stock_zh_a_hist_em 已并入它，
  返回列：日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率）。
  传输层先调 fetch_real.patch_akshare_transport()（换 curl --ipv4 规避限流），
  再额外把 stock_hist_em 模块内的 requests 换成 curl 替身——它是模块级
  requests.get，不走 request_with_retry，patch 里的三个入口都盖不住它。

断点续抓：原始返回（400 天全量）存 real/hist/{code}.json，存在即跳过；
已入库的 data/h/{code}.json 也算抓过（CI runner 上没有 real/hist 缓存，
只认它会退化成每次全量重抓）。接口真异常（重试 3 次仍败）记入
real/hist_failed.json，原命令重跑续抓。
停牌/退市/新上市导致 points 少甚至为空不算失败——正常落盘，前端自己处理。

用法：
  python fetch_history.py                      # 增量抓全部缺失的
  python fetch_history.py --refresh            # 无视缓存全部重抓
  python fetch_history.py --limit 5            # 只抓前 5 家（调试用）
  python fetch_history.py --codes 300750,002594   # 只抓指定代码（补抓用）
  python fetch_history.py --batch 300          # 最多抓 300 家就退出（看门狗用）

与 fetch_profiles.py 同一节奏：--batch 让单轮有界，配合
`timeout 600 python fetch_history.py --batch 300`，被杀后原命令重跑即续。
"""
import json
import os
import sys
import time
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)          # 与 fetch_real.py 同目录，保证直接运行也能 import

DATA = os.path.join(ROOT, "data")
REAL = os.path.join(HERE, "real")
CACHE = os.path.join(REAL, "hist")           # 每家原始抓取的缓存（可断点）
OUT = os.path.join(DATA, "h")                # 发布文件
FAILED = os.path.join(REAL, "hist_failed.json")

DAYS_BACK = 400         # 拉 400 个自然日，够凑出最近 ~250 个交易日
KEEP_POINTS = 250       # 发布文件只留最近约一年的交易日
MIN_OK = 0              # points 再少（含 0）也算成功落盘；只有接口异常才进失败名单

SLEEP = float(os.environ.get("HIST_SLEEP", "0.5"))  # 公司之间的基础间隔（限流时用 HIST_SLEEP 放慢）
SLEEP_JITTER = 0.5    # 随机抖动：固定节奏更像机器，数据源不友好
RETRIES = 3
# 自适应降速：连续失败说明对方开始不耐烦了——冷却期拉长，恢复后逐步回到正常速度
SLOW_STEP = 2.0       # 每失败一次间隔 +2s（上限 10s）
COOLDOWN_CONSEC = 4   # 连续失败 N 次后进入 30s 冷却


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    # 先写临时文件再原子改名：配合 `timeout 600 --batch 300` 使用时进程可能被
    # 外层超时强杀，直写目标文件会留下半个 JSON，被断点逻辑当作"已抓完"永不重试
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=None, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, path)


def fetch_with_retry(label, fn):
    """单个接口抓取：网络间歇断连（本机实测），重试 RETRIES 次再放弃。"""
    last = None
    for i in range(RETRIES):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    print(f"    XX {label}: {type(last).__name__} {str(last)[:80]}")
    return None


def grab(ak, code, start, end, source="tx"):
    """抓一家：返回 (原始行, 发布记录)。接口异常返回 None（由调用方记失败）。

    空 DataFrame（退市/长期停牌/新上市没数据）是正常结果，不是异常：
    原始行存空表，发布记录 points 为空，照样落盘。

    source: "tx" 腾讯（默认；东财对本机 IP 有持续限流时的替代源）/ "em" 东财。
    """
    if source == "tx":
        sym = ("sh" if code.startswith("6") else "sz") + code
        df = fetch_with_retry(
            f"腾讯日K {code}",
            lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start,
                                          end_date=end, adjust="qfq"))
        date_col, close_col = "date", "close"
    else:
        df = fetch_with_retry(
            f"东财日K {code}",
            lambda: ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start, end_date=end, adjust="qfq"))
        date_col, close_col = "日期", "收盘"
    if df is None:
        return None

    points = []
    for _, r in df.iterrows():
        d, c = r.get(date_col), r.get(close_col)
        try:
            c = float(c)
        except (TypeError, ValueError):
            continue
        if c != c or c == float("inf") or c == float("-inf"):   # 拦 NaN/Inf：json.dump 会写字面量
            continue
        points.append([str(d), round(c, 2)])
    points.sort(key=lambda p: p[0])      # 接口返回本就升序，排序只是兜底

    raw = {"code": code, "start": start, "end": end, "adjust": "qfq",
           "fetchedAt": date.today().isoformat(), "points": points}
    pub = {"code": code, "generatedAt": date.today().isoformat(),
           "points": points[-KEEP_POINTS:]}
    return raw, pub


def main():
    refresh = "--refresh" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    batch = None
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])
    codes_arg = None
    if "--codes" in sys.argv:
        codes_arg = [c.strip() for c in
                     sys.argv[sys.argv.index("--codes") + 1].split(",") if c.strip()]
    source = "tx"
    if "--source" in sys.argv:
        source = sys.argv[sys.argv.index("--source") + 1]

    sel = load_json(os.path.join(REAL, "selected.json"))
    if not sel:
        print("XX 缺少 real/selected.json，先跑 select_companies.py")
        return 1
    if codes_arg:
        known = {c["ticker"] for c in sel["companies"]}
        codes = codes_arg          # 允许抓清单外的代码（补抓临时入选的）
        unknown = [c for c in codes if c not in known]
        if unknown:
            print(f"  ! {len(unknown)} 个代码不在 selected.json：{unknown[:5]}（仍照抓）")
    else:
        codes = [c["ticker"] for c in sel["companies"]]
        if limit:
            codes = codes[:limit]

    import akshare as ak          # noqa: E402  延迟导入：没网时报错信息更干净
    from fetch_real import patch_akshare_transport, curl_get  # noqa: E402
    patch_akshare_transport()

    if source == "em":
        # stock_zh_a_hist 是模块级 requests.get，上面的三个 patch 入口都盖不住，
        # 单独把 stock_hist_em 模块里的 requests 换成 curl 替身
        import akshare.stock_feature.stock_hist_em as _hist  # noqa: E402

        class _HistShim:
            @staticmethod
            def get(url, params=None, **kw):
                return curl_get(url, params, kw.get("timeout") or 15)

        _hist.requests = _HistShim

    today = date.today()
    start = (today - timedelta(days=DAYS_BACK)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    print(f"区间 {start} ~ {end}（前复权日线，发布保留最近 {KEEP_POINTS} 个交易日，源={source}）",
          flush=True)

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    failed = set(load_json(FAILED, []))
    todo, skipped = [], 0
    for code in codes:
        if not refresh and (
                os.path.exists(os.path.join(CACHE, f"{code}.json"))
                or os.path.exists(os.path.join(OUT, f"{code}.json"))):
            # CACHE 是本机断点缓存（gitignore），OUT 是已入库的发布文件——
            # 两者任一存在都算"抓过"。只认 CACHE 的话，CI runner 上 CACHE
            # 永远为空，每次都退化成 4000+ 家全量重抓（几个小时，必超时）
            skipped += 1
            continue
        todo.append(code)
    if batch:
        todo = todo[:batch]
    print(f"待抓 {len(todo)} 家（缓存命中 {skipped} 家）", flush=True)

    t0 = time.time()
    done = ok = 0
    import random
    extra = 0.0          # 自适应惩罚间隔
    consec_fail = 0
    for code in todo:
        try:
            res = grab(ak, code, start, end, source)
        except Exception as e:      # 单家炸了整个进程太亏：记下、跳过、继续
            print(f"    XX 未捕获异常 {code}: {type(e).__name__} {str(e)[:80]}", flush=True)
            res = None
        done += 1
        if res is not None:
            raw, pub = res
            save_json(os.path.join(CACHE, f"{code}.json"), raw)
            save_json(os.path.join(OUT, f"{code}.json"), pub)
            failed.discard(code)
            ok += 1
            consec_fail = 0
            extra = max(0.0, extra - 0.5)   # 连续成功逐步恢复速度
            if len(pub["points"]) < 20:
                print(f"    .. {code} 仅 {len(pub['points'])} 个点（停牌/退市/新上市），照常落盘",
                      flush=True)
        else:
            failed.add(code)
            consec_fail += 1
            extra = min(10.0, extra + SLOW_STEP)
            if consec_fail >= COOLDOWN_CONSEC:
                print(f"  … 连续失败 {consec_fail} 次，冷却 30s（间隔已加到 {SLEEP + extra:.1f}s）",
                      flush=True)
                time.sleep(30)
        if done % 100 == 0 or done == len(todo):
            dt = time.time() - t0
            print(f"  {done}/{len(todo)}  成功 {ok}  失败累计 {len(failed)}"
                  f"  当前间隔 {SLEEP + extra:.1f}s  累计耗时 {dt/60:.1f} 分钟",
                  flush=True)
        time.sleep(SLEEP + random.uniform(0, SLEEP_JITTER) + extra)

    save_json(FAILED, sorted(failed))
    print(f"[ok] 成功 {ok} / {len(todo)}，失败 {len(failed)} 家记入 {FAILED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
