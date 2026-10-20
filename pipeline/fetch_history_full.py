# -*- coding: utf-8 -*-
"""抓取公司全历史日线：后复权日 K → real/hist_full/{代码}.json，
Cohen-Frazzini 月度复刻（多年样本）专用。

与 fetch_history.py 的区别（ why 单开一个脚本）：
  - data/h/ 是公司页"近一年走势"发布文件（前复权、只留 ~250 点），本脚本
    **绝不触碰**；缓存文件直接采用与 data/h 相同的格式
    {"code", "generatedAt", "points": [[date, close], …]}，但保留全历史。
  - adjust="hfq"：多年跨度的收益计算必须后复权——前复权对长牛股的早期
    价格会出现负值（实测茅台 2001 年 qfq 收盘 = -314），hfq 恒正。
  - start_date 固定 20100101：2010 年前的披露边仅 46 条，舍弃以省抓取量。

数据源与断点机制同 fetch_history.py：
  - tx 腾讯 ak.stock_zh_a_hist_tx（默认；东财对本机 IP 有持续限流时的主力源，
    返回 date/close 英文列，全历史分页拉取，长历史单家约十几秒）
  - em 东财 ak.stock_zh_a_hist（备用，先打 fetch_real 的传输层 patch）
  - 缓存存在即跳过（断点续抓）；接口真异常（重试 3 次仍败）记入
    real/hist_full_failed.json，原命令重跑续抓。停牌/退市/新上市 points
    很少不算失败——正常落盘。
  - 自适应降速：基础间隔 SLEEP（env HIST_FULL_SLEEP，默认 0.5s）+ 随机抖动；
    每失败一次 +2s（上限 10s），连续 4 次失败冷却 30s，连续成功逐步恢复。

用法：
  python fetch_history_full.py                      # 增量抓全部缺失的
  python fetch_history_full.py --refresh            # 无视缓存全部重抓
  python fetch_history_full.py --limit 5            # 只抓前 5 家（调试用）
  python fetch_history_full.py --codes 300750,002594   # 只抓指定代码
  python fetch_history_full.py --batch 60           # 最多抓 60 家就退出（看门狗用）

全量 4071 家要几个小时——配合
`timeout 3600 python fetch_history_full.py --batch 400`，被杀后原命令重跑即续。
"""
import json
import os
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)          # 与 fetch_real.py 同目录，保证直接运行也能 import

REAL = os.path.join(HERE, "real")
CACHE = os.path.join(REAL, "hist_full")      # 全历史缓存（可断点），格式同 data/h
FAILED = os.path.join(REAL, "hist_full_failed.json")

START = "20100101"      # 2010 年前的披露边只有 46 条，舍弃
MIN_OK = 0              # points 再少（含 0）也算成功落盘；只有接口异常才进失败名单

SLEEP = float(os.environ.get("HIST_FULL_SLEEP", "0.5"))   # 公司之间的基础间隔
SLEEP_JITTER = 0.5    # 随机抖动：固定节奏更像机器，数据源不友好
RETRIES = 3
SLOW_STEP = 2.0       # 每失败一次间隔 +2s（上限 10s）
COOLDOWN_CONSEC = 4   # 连续失败 N 次后进入 30s 冷却


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=None, separators=(",", ":"))
        f.write("\n")


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
    """抓一家全历史：返回发布格式 dict。接口异常返回 None（由调用方记失败）。

    空 DataFrame（退市/长期停牌/新上市没数据）是正常结果，不是异常：
    points 为空照样落盘。
    """
    if source == "tx":
        sym = ("sh" if code.startswith("6") else "sz") + code
        df = fetch_with_retry(
            f"腾讯日K(全) {code}",
            lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start,
                                          end_date=end, adjust="hfq"))
        date_col, close_col = "date", "close"
    else:
        df = fetch_with_retry(
            f"东财日K(全) {code}",
            lambda: ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start, end_date=end,
                                       adjust="hfq"))
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
        if c != c or c == float("inf") or c == float("-inf"):   # 拦 NaN/Inf
            continue
        points.append([str(d), round(c, 2)])
    points.sort(key=lambda p: p[0])      # 接口返回本就升序，排序只是兜底

    return {"code": code, "generatedAt": date.today().isoformat(),
            "points": points}


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

    end = date.today().strftime("%Y%m%d")
    print(f"区间 {START} ~ {end}（后复权日线，全历史入 real/hist_full/，"
          f"不触碰 data/h/，源={source}）", flush=True)

    os.makedirs(CACHE, exist_ok=True)
    failed = set(load_json(FAILED, []))
    todo, skipped = [], 0
    for code in codes:
        if not refresh and os.path.exists(os.path.join(CACHE, f"{code}.json")):
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
            res = grab(ak, code, START, end, source)
        except Exception as e:      # 单家炸了整个进程太亏：记下、跳过、继续
            print(f"    XX 未捕获异常 {code}: {type(e).__name__} {str(e)[:80]}", flush=True)
            res = None
        done += 1
        if res is not None:
            save_json(os.path.join(CACHE, f"{code}.json"), res)
            failed.discard(code)
            ok += 1
            consec_fail = 0
            extra = max(0.0, extra - 0.5)   # 连续成功逐步恢复速度
            if len(res["points"]) < 20:
                print(f"    .. {code} 仅 {len(res['points'])} 个点（停牌/退市/新上市），照常落盘",
                      flush=True)
        else:
            failed.add(code)
            consec_fail += 1
            extra = min(10.0, extra + SLOW_STEP)
            if consec_fail >= COOLDOWN_CONSEC:
                print(f"  … 连续失败 {consec_fail} 次，冷却 30s（间隔已加到 {SLEEP + extra:.1f}s）",
                      flush=True)
                time.sleep(30)
        if done % 20 == 0 or done == len(todo):
            dt = time.time() - t0
            print(f"  {done}/{len(todo)}  成功 {ok}  失败累计 {len(failed)}"
                  f"  当前间隔 {SLEEP + extra:.1f}s  单家均耗 {dt/max(done,1):.1f}s"
                  f"  累计 {dt/60:.1f} 分钟",
                  flush=True)
        time.sleep(SLEEP + random.uniform(0, SLEEP_JITTER) + extra)

    save_json(FAILED, sorted(failed))
    dt = time.time() - t0
    print(f"[ok] 成功 {ok} / {len(todo)}，失败 {len(failed)} 家记入 {FAILED}；"
          f"单家均耗 {dt/max(done,1):.1f}s，总耗时 {dt/60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
