# -*- coding: utf-8 -*-
"""
抓产业链概念板块的成分股 → pipeline/real/concepts.json

只抓 chain_concepts.CORE（核心档，96 个），够覆盖所有主产业链的锚点环节。
不够就把 EXTRA 也加上——抓取是增量的、有缓存的，不会重复请求。

请求：96 次，间隔 0.9 秒，全部落盘。只跑一次。
用法：../.venv/Scripts/python.exe fetch_concepts.py [all]
     不加 all 只抓核心档；加 all 连补充档一起抓。
"""

import json
import os
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import akshare as ak  # noqa: E402

from chain_concepts import CORE, EXTRA  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "real")
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
SLEEP = 0.9


def safe(name):
    """概念名里有括号、斜杠之类，不能直接当文件名"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "_", name)


def cached_json(name, fn):
    path = os.path.join(RAW, name + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    last = None
    for attempt in (1, 2, 3):
        try:
            df = fn()
            rec = json.loads(df.to_json(orient="records", force_ascii=False))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
            time.sleep(SLEEP)
            return rec
        except Exception as e:
            last = e
            print(f"      ! 第 {attempt} 次失败（{type(e).__name__}: {str(e)[:60]}），4 秒后重试")
            time.sleep(4)
    print(f"      × 放弃 {name}：{last}")
    return []


def main():
    targets = CORE + (EXTRA if len(sys.argv) > 1 and sys.argv[1] == "all" else [])
    print(f"要抓 {len(targets)} 个概念板块"
          f"（核心 {len(CORE)}" + (f" + 补充 {len(EXTRA)}" if len(targets) > len(CORE) else "") + "）")

    concepts, failed = {}, []
    for i, name in enumerate(targets, 1):
        already = os.path.exists(os.path.join(RAW, "concept_" + safe(name) + ".json"))
        rows = cached_json("concept_" + safe(name),
                           lambda n=name: ak.stock_board_concept_cons_em(symbol=n))
        tickers = []
        for r in rows:
            t = str(r.get("代码") or "").strip().zfill(6)
            if t and t != "000000":
                tickers.append(t)
        if not tickers and not already:
            failed.append(name)
        concepts[name] = tickers
        if i % 10 == 0 or i == len(targets):
            print(f"  {i:3d}/{len(targets)}  累计 {sum(len(v) for v in concepts.values())} 条归属")

    with open(os.path.join(OUT, "concepts.json"), "w", encoding="utf-8") as f:
        json.dump(concepts, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # ---- 覆盖率：和申万一级口径的全市场比 ----
    sw = json.load(open(os.path.join(OUT, "sw_industries.json"), encoding="utf-8"))
    market = set()
    for v in sw.values():
        market.update(v["tickers"])

    covered = set()
    for ts in concepts.values():
        covered.update(ts)
    covered_in_market = covered & market

    multi = {}
    for name, ts in concepts.items():
        for t in ts:
            multi[t] = multi.get(t, 0) + 1

    print()
    print("=" * 60)
    print(f"概念板块       {len(concepts)} 个（有数据的 {sum(1 for v in concepts.values() if v)} 个）")
    print(f"归属条目       {sum(len(v) for v in concepts.values())} 条")
    print(f"覆盖公司       {len(covered_in_market)} 家 / 全市场 {len(market)} 家"
          f"（{len(covered_in_market)/len(market)*100:.0f}%）")
    dist = {}
    for t in covered_in_market:
        dist[multi[t]] = dist.get(multi[t], 0) + 1
    print("每家落在几个板块里：")
    for k in sorted(dist):
        print(f"   {k:>2} 个板块   {dist[k]:>5} 家")
    if failed:
        print(f"\n⚠ 抓不到数据的概念（{len(failed)} 个）：{failed}")


if __name__ == "__main__":
    main()
