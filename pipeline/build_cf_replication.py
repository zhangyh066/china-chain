# -*- coding: utf-8 -*-
"""Cohen & Frazzini (2008) 客户动量→供应商收益：月度迷你复刻。
data/supply.json 披露边 × real/hist_full/ 后复权月线 → data/cf_replication.json。

全程离线，只读本地产物与缓存；hist_full 抓取可能仍在进行，缓存缺失的公司
直接跳过并计入覆盖统计，随时可重跑。（周度版 build_edge_momentum.py 保持
不动，作对照。）

边模型（语义已核验，勿再改反）：
  - rev.asSupplierOf 条目 {from, ratio, year}：from 把我列为其客户
    → from 是我的供应商，边 = from(供应商)→我(客户)；
  - rev.asCustomerOf 条目：from 把我列为其供应商 → from 是我的客户，
    边 = 我(供应商)→from(客户)；
  - 正向 customers/suppliers 列表：code 可能为 null（丢弃），year 取披露
    公司的 conc.year（≈2025，全是近期）；
  - 同一对 (供应商,客户) 跨来源/多年重复披露去重：year 取**最早**（"关系
    公开已知"的起点），ratio 取最大（强弱分类用）。

方法（迷你但诚实）：
  1. 月收益：每月最后交易日收盘价，r_m=P_m/P_{m-1}-1；两端月任一缺失
     （停牌）该边-月丢弃。当前未完结月照常计入（迷你口径，见 method）。
  2. 池化 lead-lag：供应商 S 若对应多个客户，客户侧用等权组合月收益；
     收集 (客户组合 r_{m-k}, S 的 r_m) 对，k=0..3，池化所有供应商-月，
     报 Pearson r、n、简单 OLS t（=r·√((n-2)/(1-r²))，未做 Newey-West）。
  3. 两个变体并列：
     - naive 全历史朴素变体：所有可得月份——预期 lag0 高（共同 beta）、
       lag1≈0，作阴性对照 sanity check；
     - tradable 时间对齐变体：每条边只用 m ≥ year+1 年 7 月 的月份（年报
       披露截止 4 月底 + 2 个月缓冲，"可交易"保守口径；同一供应商的客户
       组合逐边各自对齐，未到可交易月份的客户不进当月组合）。
  4. Placebo：保持供应商不变，客户换成全宇宙（4071 ∩ 有价格缓存）随机
     一家（要求伪客户该月有价格数据），重算 tradable 变体 lag1 的 r，
     重复 200 次（seed=42），报真实 r 在 placebo 分布中的分位数。
  5. C&F 原始组合检验：每月末按"供应商的客户组合当月收益"分五档，等权
     做多最高档供应商、做空最低档，持有一个月，报多空月均收益差、t、
     月份数。样本太薄（可分组月份 <12 或每月供应商 <25）则跳过并注明。
  6. 强关系子样本：ratio≥0.2 的边重做 tradable 池化（ratio 语义混合：
     客户侧为占供应商销售比、供应商侧为占客户采购比，见 method）。

用法：python build_cf_replication.py
"""

import json
import math
import os
import random
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
HIST_FULL = os.path.join(HERE, "real", "hist_full")

LAGS = (0, 1, 2, 3)
MIN_OBS = 30            # 每个 lag 池化最少观测对数
PLACEBO_REPS = 200
PLACEBO_SEED = 42
STRONG_RATIO = 0.2
PF_MIN_SUPPLIERS = 25   # 组合检验：每月至少这么多供应商才分五档
PF_MIN_MONTHS = 12      # 至少这么多可分组月份才做组合检验


# ---------------------------------------------------------------- 基础工具

def month_idx(y, m):
    return y * 12 + (m - 1)


def idx_month(mi):
    return mi // 12, mi % 12 + 1


def load_monthly_returns(path):
    """points [[date,close],…] → {monthIdx: r}。相邻月连续才出收益。"""
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding="utf-8"))
    pts = d.get("points") or []
    mend = {}
    for ds, c in pts:
        try:
            y, m = int(ds[:4]), int(ds[5:7])
        except (TypeError, ValueError):
            continue
        mend[month_idx(y, m)] = c        # 同日被覆盖无碍，月末最后写入=最后交易日
    ret = {}
    for mi in sorted(mend):
        prev = mend.get(mi - 1)
        if prev:
            ret[mi] = mend[mi] / prev - 1.0
    return ret


def pearson(pairs):
    n = len(pairs)
    if n < 3:
        return None, n, None
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    sx2 = sum(p[0] * p[0] for p in pairs)
    sy2 = sum(p[1] * p[1] for p in pairs)
    den = (n * sx2 - sx * sx) * (n * sy2 - sy * sy)
    if den <= 0:
        return None, n, None
    r = (n * sxy - sx * sy) / math.sqrt(den)
    t = None
    if abs(r) < 1:
        t = r * math.sqrt((n - 2) / (1 - r * r))
    return r, n, t


# ---------------------------------------------------------------- 边与组合

def build_edges(supply):
    """→ {(S,C): {"year": 最早披露年, "ratio": 最大占比}}"""
    edges = {}

    def add(s, c, ratio, year):
        if not s or not c or s == c:
            return
        k = (s, c)
        cur = edges.get(k)
        if cur is None:
            edges[k] = {"year": year, "ratio": ratio}
        else:
            if year and (cur["year"] is None or year < cur["year"]):
                cur["year"] = year
            if ratio and (cur["ratio"] is None or ratio > cur["ratio"]):
                cur["ratio"] = ratio

    for code, node in supply["companies"].items():
        conc_year = (node.get("conc") or {}).get("year")
        for e in node.get("customers", []):          # code 卖给 e.code
            add(code, e.get("code"), e.get("ratio"), conc_year)
        for e in node.get("suppliers", []):          # e.code 卖给 code
            add(e.get("code"), code, e.get("ratio"), conc_year)
        rev = node.get("rev") or {}
        for e in rev.get("asSupplierOf", []):        # from 卖给 code
            add(e["from"], code, e.get("ratio"), e.get("year"))
        for e in rev.get("asCustomerOf", []):        # code 卖给 from
            add(code, e["from"], e.get("ratio"), e.get("year"))
    return edges


def group_suppliers(edges, min_ratio=None):
    """(S,C) 边 → {S: [(C, year, ratio), …]}，可按 ratio 过滤。"""
    g = {}
    for (s, c), ev in edges.items():
        if min_ratio is not None and (ev["ratio"] is None
                                      or ev["ratio"] < min_ratio):
            continue
        g.setdefault(s, []).append((c, ev["year"], ev["ratio"]))
    return g


def port_return(custs, rets, mi, tradable):
    """客户组合在月 mi 的等权收益；tradable=True 时未到可交易月的客户不进组。"""
    vals = []
    for c, year, _r in custs:
        if tradable:
            if year is None or mi < month_idx(year + 1, 7):
                continue
        rc = rets.get(c)
        if rc is not None and mi in rc:
            vals.append(rc[mi])
    if not vals:
        return None
    return sum(vals) / len(vals)


def pooled_leadlag(groups, rets, tradable):
    """池化 (客户组合 r_{m-k}, 供应商 r_m)，k∈LAGS → {lag: {r,n,t}}。"""
    out = {}
    for k in LAGS:
        pairs = []
        for s, custs in groups.items():
            rs = rets.get(s)
            if rs is None:
                continue
            for mi, rv in rs.items():
                cp = port_return(custs, rets, mi - k, tradable)
                if cp is not None:
                    pairs.append((cp, rv))
        r, n, t = pearson(pairs)
        if n < MIN_OBS:
            out[f"lag{k}"] = {"r": None, "n": n, "t": None,
                              "note": f"观测<{MIN_OBS}，不足"}
        else:
            out[f"lag{k}"] = {"r": round(r, 4) if r is not None else None,
                              "n": n,
                              "t": round(t, 2) if t is not None else None}
    return out


# ---------------------------------------------------------------- placebo

def placebo_lag1(groups, rets, universe):
    """客户换成全宇宙随机一家（按各供应商客户数同槽位抽），重算 lag1 r。"""
    rng = random.Random(PLACEBO_SEED)
    # 每个供应商预先生成 (rs_mi, mi-1) 月清单（tradable 对齐用不到伪客户，
    # 月份样本沿用真实变体的 rs 侧）
    sup_months = {}
    for s in groups:
        rs = rets.get(s)
        if rs is None:
            continue
        sup_months[s] = [(rv, mi - 1) for mi, rv in rs.items()]
    uni = [c for c in universe if c in rets]
    if not uni:
        return None
    dist = []
    for _rep in range(PLACEBO_REPS):
        pairs = []
        for s, obs in sup_months.items():
            nslots = len(groups[s])
            picks = [uni[rng.randrange(len(uni))] for _ in range(nslots)]
            prs = [rets[c] for c in picks]
            for rv, mprev in obs:
                vals = [pr[mprev] for pr in prs if mprev in pr]
                if vals:
                    pairs.append((sum(vals) / len(vals), rv))
        r, n, _t = pearson(pairs)
        if r is not None and n >= MIN_OBS:
            dist.append(r)
    if not dist:
        return None
    dist.sort()
    return dist


def quantile_of(dist, x):
    if x is None:
        return None
    le = sum(1 for v in dist if v <= x)
    return round(le / len(dist), 3)


# ---------------------------------------------------------------- 组合检验

def portfolio_test(groups, rets):
    """每月末按客户组合当月收益分五档，下月多最高档供应商/空最低档。"""
    # 供应商 → {mi: 客户组合收益（tradable 对齐）}
    sup_cp = {}
    for s, custs in groups.items():
        rs = rets.get(s)
        if rs is None:
            continue
        cp = {}
        for mi in rs:
            v = port_return(custs, rets, mi, True)
            if v is not None:
                cp[mi] = v
        if cp:
            sup_cp[s] = cp
    ls = []
    all_months = sorted({mi for cp in sup_cp.values() for mi in cp})
    for mi in all_months:
        row = [(cp[mi], s) for s, cp in sup_cp.items() if mi in cp]
        if len(row) < PF_MIN_SUPPLIERS:
            continue
        row.sort()
        q = len(row) // 5
        if q == 0:
            continue
        bottom = [s for _v, s in row[:q]]
        top = [s for _v, s in row[-q:]]
        nxt = mi + 1
        rt = [rets[s][nxt] for s in top if nxt in rets.get(s, {})]
        rb = [rets[s][nxt] for s in bottom if nxt in rets.get(s, {})]
        if rt and rb:
            ls.append(sum(rt) / len(rt) - sum(rb) / len(rb))
    if len(ls) < PF_MIN_MONTHS:
        return {"skipped": True,
                "reason": f"可分组月份 {len(ls)} < {PF_MIN_MONTHS}"
                          f"（或每月供应商 < {PF_MIN_SUPPLIERS}），样本太薄"}
    mean = sum(ls) / len(ls)
    var = sum((x - mean) ** 2 for x in ls) / (len(ls) - 1) if len(ls) > 1 else 0
    t = mean / math.sqrt(var / len(ls)) if var > 0 else None
    return {"skipped": False, "months": len(ls),
            "meanLS": round(mean, 4), "t": round(t, 2) if t is not None else None,
            "hitRate": round(sum(1 for x in ls if x > 0) / len(ls), 3),
            "note": "月频五档多空，等权，未计成本与做空限制"}


# ---------------------------------------------------------------- main

def main():
    supply = json.load(open(os.path.join(DATA, "supply.json"), encoding="utf-8"))
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    universe = [c["ticker"] for c in idx["companies"]]

    edges = build_edges(supply)
    groups_all = group_suppliers(edges)
    groups_strong = group_suppliers(edges, STRONG_RATIO)

    # 价格：只载入边端用到的代码
    need = set()
    for s, c in edges:
        need.add(s)
        need.add(c)
    need |= set(universe)          # placebo 全宇宙也要
    rets = {}
    for code in sorted(need):
        r = load_monthly_returns(os.path.join(HIST_FULL, f"{code}.json"))
        if r:
            rets[code] = r

    priced_edges = sum(1 for s, c in edges if s in rets and c in rets)
    sup_priced = sum(1 for s in groups_all
                     if s in rets and any(c in rets for c, _y, _r in groups_all[s]))
    n_cache = len([f for f in os.listdir(HIST_FULL) if f.endswith(".json")]) \
        if os.path.isdir(HIST_FULL) else 0

    groups_priced = {s: cs for s, cs in groups_all.items()
                     if s in rets and any(c in rets for c, _y, _r in cs)}
    groups_strong_priced = {s: cs for s, cs in groups_strong.items()
                            if s in rets and any(c in rets for c, _y, _r in cs)}

    print(f"边 {len(edges)}（供应商 {len(groups_all)}），两端有价格 {priced_edges}；"
          f"价格缓存 {n_cache} 家", flush=True)

    print("naive 全历史朴素变体（阴性对照，预期 lag0 高 lag1≈0）…", flush=True)
    naive = pooled_leadlag(groups_priced, rets, tradable=False)
    print("tradable 时间对齐变体（m ≥ year+1 年 7 月）…", flush=True)
    trad = pooled_leadlag(groups_priced, rets, tradable=True)
    print(f"strong 强关系子样本（ratio≥{STRONG_RATIO}）…", flush=True)
    strong = pooled_leadlag(groups_strong_priced, rets, tradable=True)

    print(f"placebo（{PLACEBO_REPS} 次，seed={PLACEBO_SEED}）…", flush=True)
    dist = placebo_lag1(groups_priced, rets, universe)
    real_r1 = trad["lag1"]["r"]
    placebo = None
    if dist:
        mean = sum(dist) / len(dist)
        sd = math.sqrt(sum((x - mean) ** 2 for x in dist) / (len(dist) - 1)) \
            if len(dist) > 1 else 0
        placebo = {"reps": len(dist), "realR": real_r1,
                   "quantile": quantile_of(dist, real_r1),
                   "mean": round(mean, 4), "sd": round(sd, 4),
                   "p5": round(dist[int(0.05 * len(dist))], 4),
                   "p95": round(dist[min(int(0.95 * len(dist)), len(dist) - 1)], 4)}

    print("C&F 五档多空组合检验…", flush=True)
    pf = portfolio_test(groups_priced, rets)

    obj = {
        "schemaVersion": 1, "generatedAt": date.today().isoformat(),
        "priceCache": {"dir": "pipeline/real/hist_full", "codes": n_cache},
        "coverage": {"edges": len(edges), "edgesPriced": priced_edges,
                     "suppliers": len(groups_all),
                     "suppliersPriced": len(groups_priced)},
        "variants": {
            "naive": {**naive, "suppliers": len(groups_priced)},
            "tradable": {**trad, "suppliers": len(groups_priced)},
            "strong": {**strong, "edges": sum(len(v) for v in groups_strong.values()),
                       "suppliers": len(groups_strong_priced)},
        },
        "placebo": placebo,
        "portfolio": pf,
        "method": ("Cohen-Frazzini(2008) 月度迷你复刻，非严格学术口径。"
                   "月收益=月末最后交易日收盘价环比（hfq），边-月缺失即弃；"
                   "供应商对应多客户时客户侧等权组合；t 为简单 OLS 值，未做 "
                   "Newey-West/聚类调整；tradable 变体按 披露年+1 的 7 月起计"
                   "（年报 4 月底截止+2 月缓冲）；placebo 保持供应商、客户换"
                   "全宇宙随机同槽位；强关系子样本 ratio≥0.2 但 ratio 语义混合"
                   "（销售占比/采购占比）；幸存者偏差：仅现存 4071 家，退市"
                   "公司与失效关系不在样本；抓取进行中的版本覆盖率不全，"
                   "结果随时可重跑更新。研究用途，非投资建议。"),
    }
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    out = os.path.join(DATA, "cf_replication.json")
    with open(out, "w", encoding="utf-8") as f:
        f.write(payload)

    def fmt(v):
        return " ".join(f"{k}:r={v[k]['r']},n={v[k]['n']},t={v[k]['t']}"
                        for k in (f"lag{i}" for i in LAGS))

    print(f"\nnaive    ({len(groups_priced)} 供应商): {fmt(naive)}", flush=True)
    print(f"tradable ({len(groups_priced)} 供应商): {fmt(trad)}", flush=True)
    print(f"strong   ({len(groups_strong_priced)} 供应商): {fmt(strong)}", flush=True)
    if placebo:
        print(f"placebo lag1: 真实 r={placebo['realR']}，分位数 "
              f"{placebo['quantile']}（分布 {placebo['mean']}±{placebo['sd']}，"
              f"[{placebo['p5']},{placebo['p95']}]）", flush=True)
    print(f"portfolio: {pf}", flush=True)
    print(f"data/cf_replication.json：{os.path.getsize(out)/1024:.1f} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
