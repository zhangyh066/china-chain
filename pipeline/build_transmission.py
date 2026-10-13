# -*- coding: utf-8 -*-
"""传导时滞（lead-lag）管线：每条产业链的"源头 → 各环节"滞后相关。

全程离线，只读本地 data/ 产物。

口径：
  - 源头：有价格线的链（lithium/pv）用期货主力日线（data/price/{key}.json），
    其余链用第一个阶段指数（stages 数组顺序即链条顺序，如 robot 的 reducer）。
  - 源头与阶段指数各自转日收益率，按共同交易日对齐（剔除非有限值）。
  - 每对（源头, 阶段）扫描滞后 -10~+20 个交易日：lag=k 表示源头领先 k 天
    （源头 t 日收益 vs 阶段 t+k 日收益），取 |r| 最大者记录 {lag, r, n}。
    源头阶段本身跳过；共同点 <60 的阶段不输出；|r|<0.1 标 weak:true。

日收益率的横截面相关性通常不高（0.1~0.3 即有意义），lag≈0 且 r 显著
表示同日消息同向传导；lag>0 表示源头先行。结果是相关性不是因果，
前端展示文案需注意。

产出：
  data/transmission.json  {schemaVersion, generatedAt, method,
                           chains:{链:{source:{type,name},
                                       stages:{阶段:{lag,r,n[,weak]}}}}}

用法：python build_transmission.py
"""

import json
import math
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

LAG_MIN, LAG_MAX = -10, 20     # 扫描窗口（交易日）
MIN_COMMON = 60                # 共同点下限，不足不输出
WEAK_R = 0.1                   # |r| 低于此值标 weak

CHAINS = ["lithium", "pv", "semi", "robot", "compute", "storage",
          "pharma", "auto"]
PRICE_CHAINS = {"lithium", "pv"}


def to_returns(series):
    """[(date, value)] 升序 → {date: 日收益}。剔除非有限/非正值。"""
    out = {}
    prev = None
    for d, v in series:
        if isinstance(v, (int, float)) and math.isfinite(v) and v > 0:
            if prev is not None:
                out[d] = v / prev - 1.0
            prev = v
        else:
            prev = None
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def best_lag(src_ret, stg_ret, dates):
    """在共同日期轴 dates（升序）上扫 lag ∈ [LAG_MIN, LAG_MAX]。

    lag=k：src_ret[dates[i]] vs stg_ret[dates[i+k]]（源头领先 k 天）。
    返回 (lag, r, n) 与 lag0 共同点数；轴太短返回 None。
    """
    n0 = sum(1 for d in dates if d in src_ret and d in stg_ret)
    if n0 < MIN_COMMON:
        return None
    best = None
    for k in range(LAG_MIN, LAG_MAX + 1):
        xs, ys = [], []
        for i, d in enumerate(dates):
            j = i + k
            if j < 0 or j >= len(dates):
                continue
            a, b = src_ret.get(d), stg_ret.get(dates[j])
            if a is not None and b is not None:
                xs.append(a)
                ys.append(b)
        if len(xs) < MIN_COMMON:
            continue
        r = pearson(xs, ys)
        if best is None or abs(r) > abs(best[1]):
            best = (k, r, len(xs))
    return best


def load_price(chain_key):
    path = os.path.join(DATA, "price", f"{chain_key}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("name", chain_key), d.get("points") or []


def main():
    generated = date.today().isoformat()
    chains_out = {}
    report = []
    for ck in CHAINS:
        cpath = os.path.join(DATA, "chain", f"{ck}.json")
        if not os.path.exists(cpath):
            print(f"!! {cpath} 不存在，跳过（先跑 build_chains.py）")
            continue
        with open(cpath, encoding="utf-8") as f:
            chain = json.load(f)
        dates = chain["trends"]["dates"]
        stage_series = chain["trends"]["stages"]
        stage_names = {st["key"]: st["name"] for st in chain["stages"]}

        price = load_price(ck) if ck in PRICE_CHAINS else None
        if price:
            src_name, points = price
            src_ret = to_returns(points)
            src_type = "price"
        else:
            first = chain["stages"][0]["key"] if chain["stages"] else None
            if not first or not stage_series.get(first):
                print(f"!! {ck} 无可用源头（无价格线且首阶段无序列），跳过")
                continue
            src_name = stage_names[first]
            src_ret = to_returns(list(zip(dates, stage_series[first])))
            src_type = "stage"

        stages_out = {}
        for st in chain["stages"]:
            sk = st["key"]
            vals = stage_series.get(sk)
            if not vals:
                continue
            stg_ret = to_returns(list(zip(dates, vals)))
            if src_type == "stage" and sk == chain["stages"][0]["key"]:
                continue                        # 源头阶段本身不算
            r = best_lag(src_ret, stg_ret, dates)
            if r is None:
                print(f"  -- {ck}/{sk} 共同点不足 {MIN_COMMON}，不输出")
                continue
            lag, corr, n = r
            entry = {"lag": lag, "r": round(corr, 3), "n": n}
            if abs(corr) < WEAK_R:
                entry["weak"] = True
            stages_out[sk] = entry
            report.append((ck, sk, st["name"], lag, corr, n, src_name))
        chains_out[ck] = {"source": {"type": src_type, "name": src_name},
                          "stages": stages_out}

    obj = {"schemaVersion": 1, "generatedAt": generated,
           "method": "daily-return cross-correlation, lag -10..+20",
           "chains": chains_out}
    out_path = os.path.join(DATA, "transmission.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

    print("\n各链源头 → 阶段 {lag, r, n}（lag>0 = 源头领先，|r|<0.1 为 weak）：")
    for ck, sk, name, lag, corr, n, src in report:
        weak = " weak" if abs(corr) < WEAK_R else ""
        print(f"  {ck:<8} [{src}] → {name:<12} lag={lag:+3d}  r={corr:+.3f}  n={n}{weak}")
    print(f"\ndata/transmission.json {os.path.getsize(out_path)/1024:.1f} KB，"
          f"chains={len(chains_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
