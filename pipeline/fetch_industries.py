# -*- coding: utf-8 -*-
"""
抓申万一级行业的成分股，量出真实的市场结构。

为什么先做这一步：筛选规则（哪些行业留、哪些剔）不该拍脑袋定，
先用真实数字看清楚"每个行业多少家、剔除金融地产服务后还剩多少家"，再定阈值。

请求：31 次（31 个申万一级行业各一次）。全部落盘缓存，只跑一次。
用法：../.venv/Scripts/python.exe fetch_industries.py
输出：pipeline/real/sw_industries.json
"""

import json
import os
import time
import warnings
from collections import Counter

warnings.filterwarnings("ignore")

import akshare as ak  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "real")
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)

SLEEP = 0.9      # 请求间隔：别把数据源打疼（这个坑踩过）


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
            print(f"    ! 第 {attempt} 次失败（{type(e).__name__}），4 秒后重试")
            time.sleep(4)
    raise last


def main():
    print("① 申万一级行业清单")
    first = cached_json("sw_l1_list", ak.sw_index_first_info)
    cols = list(first[0].keys())
    print(f"  列名: {cols}")

    # 不同版本字段名可能不同，按实际列取
    code_key = next(k for k in cols if "代码" in k)
    name_key = next(k for k in cols if "名称" in k)
    industries = [(str(r[code_key]).split(".")[0], r[name_key]) for r in first]
    print(f"  共 {len(industries)} 个行业")

    print("② 逐个抓成分股（每个行业 1 次请求）")
    result, total_members = {}, 0
    for i, (code, name) in enumerate(industries, 1):
        rows = cached_json(f"sw_cons_{code}", lambda c=code: ak.index_component_sw(symbol=c))
        tickers = [str(r.get("证券代码") or r.get("股票代码") or "").strip().zfill(6) for r in rows]
        tickers = [t for t in tickers if t and t != "000000"]
        result[name] = {"swCode": code, "tickers": tickers}
        total_members += len(tickers)
        flag = "" if os.path.exists(os.path.join(RAW, f"sw_cons_{code}.json")) else " (新抓)"
        print(f"  {i:2d}/{len(industries)}  {name:<10}{len(tickers):>4} 家{flag}")

    with open(os.path.join(OUT, "sw_industries.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # ---- 统计 ----
    print(f"\n③ 汇总：31 个行业合计 {total_members} 家（含重复计入）")

    # 一家公司只应属于一个申万一级行业
    all_tickers = []
    for v in result.values():
        all_tickers.extend(v["tickers"])
    dup = [t for t, n in Counter(all_tickers).items() if n > 1]
    print(f"   去重后 {len(set(all_tickers))} 家；被重复归类的 {len(dup)} 家" + (f"（{dup[:5]}）" if dup else ""))

    print("\n④ 各行业规模（按家数排序）")
    for name, v in sorted(result.items(), key=lambda kv: -len(kv[1]["tickers"])):
        print(f"   {name:<10}{len(v['tickers']):>5} 家")


if __name__ == "__main__":
    main()
