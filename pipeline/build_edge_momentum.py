# -*- coding: utf-8 -*-
"""Cohen-Frazzini(2008) 周度迷你复刻：data/supply.json 披露边 × data/h/ 日线
→ data/edge_momentum.json。

全程离线，只读本地产物，不做任何网络请求。

设计（与 C&F 对应的迷你版）：
  - 边：supply.json 正向+反向合并去重，方向统一 供应商A → 客户B。
  - 假设：客户 B 的股价信息滞后传导到供应商 A（C&F 的 customer momentum）。
    对每条边算 B 的 5 日收益 与 A 在 lag 周后的 5 日收益 的 Pearson 相关：
    lag=0 同周对照，lag=1 传导主假设，lag=2 更慢传导。
  - 5 日收益重叠取样（r5[t]=close[t]/close[t-5]-1），lag 以 B 的交易日历
    按 5 交易日步进，A 侧要求同一日历日有观测（停牌缺日自然剔对）。
  - 重叠周观测 < 40 的边剔除。
  - 池化：所有边所有周观测合并算一个 r（不是各边 r 的均值），另按"两端
    同链"分组各算一份。lag1 r 显著 >0 才与 C&F 方向一致；lag1-lag0 差值
    即"传导增量"。
  - 每边在 lag∈[-2..+4] 取 |r| 最大的 lag 做直方图：正 lag = 客户领先。

诚实声明（也写入产物 method）：重叠样本自相关强、未做 Newey-West 调整，
r 的"显著性"只能粗看；披露边来自历史年报（含 2011 年老边），供应关系
可能已失效；样本仅约 1 年（250 交易日）。研究用途，非预测指标。

用法：python build_edge_momentum.py
"""

import glob
import json
import math
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
HIST = os.path.join(DATA, "h")

MIN_OBS = 40
LAGS = list(range(-2, 5))          # 直方图用全 lag
POOL_LAGS = (0, 1, 2)              # 池化只报 0/1/2


def pearson_sums():
    return [0.0, 0.0, 0.0, 0.0, 0.0, 0]   # Sx, Sy, Sxy, Sx2, Sy2, n


def add_pair(S, x, y):
    S[0] += x
    S[1] += y
    S[2] += x * y
    S[3] += x * x
    S[4] += y * y
    S[5] += 1


def pearson(S):
    Sx, Sy, Sxy, Sx2, Sy2, n = S
    if n < 3:
        return None
    num = n * Sxy - Sx * Sy
    den = (n * Sx2 - Sx * Sx) * (n * Sy2 - Sy * Sy)
    if den <= 0:
        return None
    return num / math.sqrt(den)


def load_edges(comps):
    edges = {}

    def add(a, b, ratio):
        if not a or not b or a == b:
            return
        k = (a, b)
        if k not in edges or (ratio or 0) > (edges[k] or 0):
            edges[k] = ratio

    for code, node in comps.items():
        for e in node.get("customers", []):
            add(code, e.get("code"), e.get("ratio"))
        for e in node.get("suppliers", []):
            add(e.get("code"), code, e.get("ratio"))
    return edges


def load_r5(code):
    p = os.path.join(HIST, f"{code}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    pts = d.get("points") or []
    if len(pts) < 6 + MIN_OBS:
        return None
    dates = [p_[0] for p_ in pts]
    closes = [p_[1] for p_ in pts]
    r5 = {}
    for i in range(5, len(pts)):
        if closes[i - 5]:
            r5[dates[i]] = closes[i] / closes[i - 5] - 1.0
    b_dates = [d_ for d_ in dates if d_ in r5]
    return b_dates, r5


def load_chains_mem():
    mem = {}
    for f in sorted(glob.glob(os.path.join(DATA, "chain", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        if not (isinstance(d, dict) and "stages" in d):
            continue
        for st in d["stages"]:
            for c in st["companies"]:
                mem.setdefault(c["code"], set()).add(d["key"])
    return mem


def main():
    supply = json.load(open(os.path.join(DATA, "supply.json"), encoding="utf-8"))
    edges = load_edges(supply["companies"])
    mem = load_chains_mem()

    series = {}

    def get(code):
        if code not in series:
            series[code] = load_r5(code)
        return series[code]

    pool = {k: pearson_sums() for k in POOL_LAGS}
    by_chain = {}
    chain_edges = {}
    hist = {k: 0 for k in LAGS}
    n_used = n_drop = 0

    for (a, b) in edges:
        sa, sb = get(a), get(b)
        if not sa or not sb:
            n_drop += 1
            continue
        b_dates, r5b = sb
        _a_dates, r5a = sa
        per_lag = {}
        for k in LAGS:
            S = pearson_sums()
            step = 5 * k
            for i, d in enumerate(b_dates):
                j = i + step
                if 0 <= j < len(b_dates):
                    ya = r5a.get(b_dates[j])
                    if ya is not None:
                        add_pair(S, r5b[d], ya)
            if S[5] >= MIN_OBS:
                r = pearson(S)
                if r is not None:
                    per_lag[k] = (r, S[5], S)
        if 1 not in per_lag:          # 主假设 lag 观测不足 → 剔边
            n_drop += 1
            continue
        n_used += 1
        for k in POOL_LAGS:
            if k in per_lag:
                S = per_lag[k][2]
                for i in range(6):
                    pool[k][i] += S[i]
        shared = mem.get(a, set()) & mem.get(b, set())
        for ch in shared:
            by_chain.setdefault(ch, {k: pearson_sums() for k in POOL_LAGS})
            chain_edges[ch] = chain_edges.get(ch, 0) + 1
            for k in POOL_LAGS:
                if k in per_lag:
                    S = per_lag[k][2]
                    T = by_chain[ch][k]
                    for i in range(6):
                        T[i] += S[i]
        best = max(per_lag.items(), key=lambda kv: abs(kv[1][0]))
        hist[best[0]] += 1

    def pack(S):
        r = pearson(S)
        return {"r": round(r, 4) if r is not None else None, "n": S[5]}

    pooled = {f"lag{k}": pack(pool[k]) for k in POOL_LAGS}
    r0, r1 = pooled["lag0"]["r"], pooled["lag1"]["r"]
    pooled["lag1MinusLag0"] = (round(r1 - r0, 4)
                               if r0 is not None and r1 is not None else None)
    chains_out = {}
    for ch, ks in sorted(by_chain.items()):
        chains_out[ch] = {"edges": chain_edges[ch]}
        for k in POOL_LAGS:
            chains_out[ch][f"lag{k}"] = pack(ks[k])

    obj = {
        "schemaVersion": 1, "generatedAt": date.today().isoformat(),
        "method": ("重叠5日收益 r5[t]=close[t]/close[t-5]-1；方向 B(客户)t周 "
                   "→ A(供应商)t+lag周，lag 按 B 交易日历 5 交易日步进、A 侧"
                   "要求同日历日有观测；Pearson 相关，lag0/1/2 为所有边全部"
                   "周观测池化（非各边 r 均值）；未做 Newey-West/重叠自相关"
                   "调整，显著性只能粗看；边来自历史年报披露（含 2011 年老边），"
                   "供应关系可能已失效；样本约 1 年（250 交易日）。"
                   "研究用途，非预测指标。"),
        "edgesTotal": len(edges), "edgesUsed": n_used, "edgesDropped": n_drop,
        "pooled": pooled,
        "byChain": chains_out,
        "bestLagHist": {str(k): v for k, v in hist.items()},
    }
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    out = os.path.join(DATA, "edge_momentum.json")
    with open(out, "w", encoding="utf-8") as f:
        f.write(payload)

    print(f"披露边 {len(edges)}，入样 {n_used}，剔除 {n_drop}"
          f"（缺日线或 lag1 重叠周观测 < {MIN_OBS}）", flush=True)
    print("池化结果：", flush=True)
    for k in POOL_LAGS:
        p = pooled[f"lag{k}"]
        print(f"  lag{k}: r={p['r']}  n={p['n']}", flush=True)
    print(f"  lag1-lag0 = {pooled['lag1MinusLag0']}（>0 才与 C&F 传导方向一致）",
          flush=True)
    for ch, co in chains_out.items():
        print(f"  [{ch}] 边{co['edges']} "
              + " ".join(f"lag{k} r={co[f'lag{k}']['r']}" for k in POOL_LAGS),
              flush=True)
    print("每边最佳 lag 分布（正 lag=客户领先）:",
          {k: hist[k] for k in LAGS}, flush=True)
    lead = sum(hist[k] for k in LAGS if k > 0)
    print(f"客户领先边占比：{lead}/{n_used}"
          f" = {lead/n_used:.1%}" if n_used else "", flush=True)
    print(f"data/edge_momentum.json：{os.path.getsize(out)/1024:.1f} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
