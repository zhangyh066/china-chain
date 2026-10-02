# -*- coding: utf-8 -*-
"""抓取公司介绍：同花顺主营业务 + 巨潮公司概况 + 东财主营构成。

每家合并成一份 data/p/{代码}.json，公司页按需加载（与 data/f/ 同一模式）：
  {
    "ticker": "600519",
    "business": "茅台酒及系列酒的生产与销售。",        ← 同花顺 主营业务
    "products": "茅台酒、其他系列酒",                    ← 同花顺 产品名称
    "scope": "茅台酒及系列酒的生产与销售；……",          ← 同花顺 经营范围
    "listed": "2001-08-27", "website": "……",          ← 巨潮 公司概况（缺字段则无）
    "legal": "……", "capital": "……", "officeAddr": "……",
    "segments": [{"item": "茅台酒", "revenueRatio": 0.857,
                  "grossMargin": 0.923, "period": "2026-06-30"}, …]
                                                   ← 东财 主营构成（按产品，收入比例降序前 8）
  }

三家数据源都抓失败的记入 real/profiles_failed.json，可原命令重跑续抓
（已有缓存的自动跳过）。行情数据与介绍数据分文件、分节奏——行情天天变，
介绍季度变。

用法：
  python fetch_profiles.py             # 增量抓全部缺失的
  python fetch_profiles.py --refresh   # 无视缓存全部重抓
  python fetch_profiles.py --limit 50  # 只抓前 50 家（调试用）
  python fetch_profiles.py --batch 300 # 最多抓 300 家就退出（外层超时看门狗用）

说明：个别 HTTP 请求可能永久挂起（akshare 底层无读超时）。--batch 让单轮
有界，配合 `timeout 600 python fetch_profiles.py --batch 300` 使用：
批超时被杀后原命令重跑即续抓（已入库的自动跳过）。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
REAL = os.path.join(HERE, "real")
CACHE = os.path.join(REAL, "profiles")       # 每家原始抓取的缓存（可断点）
OUT = os.path.join(DATA, "p")                # 合并后的发布文件
FAILED = os.path.join(REAL, "profiles_failed.json")

SLEEP = 0.5           # 公司之间的基础间隔
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


def grab(ak, code):
    """抓一家：三源合并。任一源失败不拖垮其他源。源与源之间留小间隔。"""
    rec = {"ticker": code}

    ths = fetch_with_retry("同花顺主营业务",
                           lambda: ak.stock_zyjs_ths(symbol=code))
    time.sleep(0.2)
    if ths is not None and len(ths):
        r = ths.iloc[0]
        rec["business"] = str(r.get("主营业务") or "").strip() or None
        rec["products"] = str(r.get("产品名称") or "").strip() or None
        rec["scope"] = str(r.get("经营范围") or "").strip() or None

    prof = fetch_with_retry("巨潮公司概况",
                            lambda: ak.stock_profile_cninfo(symbol=code))
    time.sleep(0.2)
    if prof is not None and len(prof):
        r = prof.iloc[0]
        m = prof.columns
        pick = lambda *names: next((str(r[n]).strip() for n in names
                                    if n in m and str(r.get(n) or "").strip()), None)
        rec["listed"] = pick("A股上市日期", "上市日期")
        rec["website"] = pick("官网")
        rec["legal"] = pick("法人代表")
        rec["capital"] = pick("注册资本")
        rec["officeAddr"] = pick("办公地址")
        rec["csrcIndustry"] = pick("所属行业", "证监会行业")

    zygc = fetch_with_retry("东财主营构成",
                            lambda: ak.stock_zygc_em(
                                symbol=("SH" if code.startswith("6") else "SZ") + code))
    segs = []
    if zygc is not None and len(zygc):
        latest = zygc[zygc["报告日期"] == zygc["报告日期"].max()]
        prod = latest[latest["分类类型"] == "按产品分类"]
        for _, r in prod.iterrows():
            try:
                segs.append({
                    "item": str(r.get("主营构成") or ""),
                    "revenueRatio": round(float(r.get("收入比例") or 0), 4),
                    "grossMargin": round(float(r.get("毛利率") or 0), 4),
                    "period": str(r.get("报告日期") or ""),
                })
            except (TypeError, ValueError):
                continue
        segs.sort(key=lambda x: -x["revenueRatio"])
    if segs:
        rec["segments"] = segs[:8]

    return {k: v for k, v in rec.items() if v not in (None, "")}


def main():
    refresh = "--refresh" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    batch = None
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])

    sel = load_json(os.path.join(REAL, "selected.json"))
    if not sel:
        print("XX 缺少 real/selected.json，先跑 select_companies.py")
        return 1
    companies = sel["companies"]
    if limit:
        companies = companies[:limit]

    import akshare as ak          # noqa: E402  延迟导入：没网时报错信息更干净

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    failed = set(load_json(FAILED, []))
    todo, skipped = [], 0
    for c in companies:
        code = c["ticker"]
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
    for i, code in enumerate(todo):
        try:
            rec = grab(ak, code)
        except Exception as e:      # 单家炸了整个进程太亏：记下、跳过、继续
            print(f"    XX 未捕获异常 {code}: {type(e).__name__} {str(e)[:80]}", flush=True)
            rec = None
        done += 1
        if rec and len(rec) > 1:        # 至少有 ticker 之外的一个字段才算成
            save_json(os.path.join(CACHE, f"{code}.json"), rec)
            save_json(os.path.join(OUT, f"{code}.json"), rec)
            failed.discard(code)
            ok += 1
            consec_fail = 0
            extra = max(0.0, extra - 0.5)   # 连续成功逐步恢复速度
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
