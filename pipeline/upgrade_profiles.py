# -*- coding: utf-8 -*-
"""给已抓好的公司介绍补抓「三分法主营构成」（按产品/按行业/按地区）。

fetch_profiles.py v1 只存了按产品分类；按地区分类对很多公司信息量大得多
（例：工业富联的境外收入占比）。本脚本只重抓东财主营构成这一源，
合并进现有缓存并重写 data/p/。增量断点：已有 segmentsBy 的跳过。

用法：
  python upgrade_profiles.py --batch 300   # 配合外层超时看门狗
  python upgrade_profiles.py               # 一口气跑完
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
REAL = os.path.join(HERE, "real")
CACHE = os.path.join(REAL, "profiles")
OUT = os.path.join(DATA, "p")

SLEEP = 0.4
RETRIES = 3


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def fetch_with_retry(fn):
    last = None
    for i in range(RETRIES):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    return None


def upgrade_one(ak, code):
    rec = load_json(os.path.join(CACHE, f"{code}.json")) or {"ticker": code}
    zygc = fetch_with_retry(lambda: ak.stock_zygc_em(
        symbol=("SH" if code.startswith("6") else "SZ") + code))
    if zygc is None or not len(zygc):
        return False
    latest = zygc[zygc["报告日期"] == zygc["报告日期"].max()]

    def pick(class_type):
        out = []
        for _, r in latest[latest["分类类型"] == class_type].iterrows():
            try:
                def num(v):        # NaN 是 truthy，"or 0" 拦不住，显式判
                    f = float(v)
                    return f if f == f and abs(f) != float("inf") else 0.0
                out.append({
                    "item": str(r.get("主营构成") or ""),
                    "revenueRatio": round(num(r.get("收入比例")), 4),
                    "grossMargin": round(num(r.get("毛利率")), 4),
                    "period": str(r.get("报告日期") or ""),
                })
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda x: -x["revenueRatio"])
        return out[:10]

    by = {k: v for k, v in
          (("product", pick("按产品分类")),
           ("industry", pick("按行业分类")),
           ("region", pick("按地区分类"))) if v}
    if not by:
        return False
    rec["segmentsBy"] = by
    rec["segments"] = by.get("product") or next(iter(by.values()))
    save_json(os.path.join(CACHE, f"{code}.json"), rec)
    save_json(os.path.join(OUT, f"{code}.json"), rec)
    return True


def main():
    batch = None
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])
    import akshare as ak          # noqa: E402
    sel = load_json(os.path.join(REAL, "selected.json")) or {}
    codes = [c["ticker"] for c in sel.get("companies", [])]
    todo = [c for c in codes
            if "segmentsBy" not in (load_json(os.path.join(CACHE, f"{c}.json")) or {})]
    if batch:
        todo = todo[:batch]
    print(f"待升级 {len(todo)} 家", flush=True)
    ok = 0
    for i, code in enumerate(todo, 1):
        try:
            ok += upgrade_one(ak, code)
        except Exception as e:
            print(f"  XX {code}: {type(e).__name__} {str(e)[:60]}", flush=True)
        if i % 200 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} 成功 {ok}", flush=True)
        time.sleep(SLEEP)
    print(f"[ok] 升级 {ok}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
