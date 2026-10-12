# -*- coding: utf-8 -*-
"""把 data/h/ 逐股日线聚合为「行业指数 / 环节指数」，供前端画趋势图。

算法（与前端契约一致）：
  1. 公共日期轴 = 全部 data/h 文件日期的并集（升序）。每家公司建 date→close 映射，
     缺失日期（停牌）前值填充；上市日晚于轴线起点的新股，从其首个交易日起才参与，
     之前的日期不进均值。
  2. 日收益 r_t = close_t / close_{t-1} - 1，仅在当天有真实报价时计算，填充日记 0
     （复牌首日的分母是停牌前最后真实收盘，跳空幅度计入复牌日）。
  3. 指数 = 成员日收益等权平均逐日累计：index_t = index_{t-1} × (1 + mean(r_t))，
     基期 100，输出保留 2 位小数（累计用未舍入值，舍入仅发生在输出）。
  4. 单日 |r| > 30% 视为数据错误：该日该公司收益剔除后再平均（不计 0、也不计异常值）。

产出：
  data/trends/index.json     首页用：全市场指数 + 24 个申万一级行业指数
                             + 全市场环节榜摘要 boards（name/n/y/m/w，按近 20
                             交易日涨跌幅 m 降序；不足 3 家有数据成员的环节不输出）
  data/trends/i/{行业}.json  行业页用：该行业指数 + 行业内成员数前 12 的环节指数
                             （成员数按「有日线数据」计，不足 3 家的环节不输出）

用法：python build_trends.py
"""

import glob
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
H_DIR = os.path.join(DATA, "h")
OUT_DIR = os.path.join(DATA, "trends")

MIN_MEMBERS = 3          # 环节指数最少有数据成员数
MAX_SEGMENTS = 12        # 每个行业文件最多输出的环节数
OUTLIER = 0.30           # 单日 |r| 超过即剔除
BASE = 100.0


def load_history(codes):
    """读 data/h/{code}.json → {code: (date→close 映射, 升序日期列表)}。坏文件跳过。"""
    series = {}
    for path in glob.glob(os.path.join(H_DIR, "*.json")):
        code = os.path.splitext(os.path.basename(path))[0]
        if code not in codes:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                points = json.load(f).get("points") or []
        except Exception as e:
            print(f"!! {code}.json 解析失败，跳过：{e}")
            continue
        pts = [(d, c) for d, c in points
               if isinstance(c, (int, float)) and c > 0]
        if len(pts) < 2:
            continue
        pts.sort(key=lambda x: x[0])
        series[code] = (dict(pts), [d for d, _ in pts])
    return series


def build_returns(series):
    """对齐到公共日期轴，返回 (dates, {code: (first_idx, rets)})。

    rets 长度 = 轴长；first_idx 及之前为 None；填充日 0.0；异常日 None（剔除）。
    """
    axis = sorted({d for _, days in series.values() for d in days})
    n = len(axis)
    out = {}
    for code, (by_date, days) in series.items():
        first = axis.index(days[0])
        rets = [None] * n
        prev = by_date[days[0]]
        di = 1                      # days 的游标：days 是 axis 的子序列且同序
        for i in range(first + 1, n):
            d = axis[i]
            if di < len(days) and days[di] == d:
                close = by_date[d]
                r = close / prev - 1.0
                rets[i] = None if abs(r) > OUTLIER else r
                prev = close
                di += 1
            else:
                rets[i] = 0.0       # 填充日（停牌），前值填充 ⇒ 收益 0
        out[code] = (first, rets)
    return axis, out


def index_series(members, returns, n):
    """成员等权平均日收益逐日累计，基期 100，保留 2 位小数。"""
    out = [BASE]
    level = BASE
    for i in range(1, n):
        s = 0.0
        cnt = 0
        for code in members:
            first, rets = returns[code]
            if i > first:
                r = rets[i]
                if r is not None:
                    s += r
                    cnt += 1
        if cnt:
            level *= 1.0 + s / cnt
        out.append(round(level, 2))
    return out


def pct_change(series, window):
    """近 window 个交易日的涨跌幅 %：(末值 / 倒数第 window+1 个值 - 1) × 100。

    序列长度不足 window+1 时退化为能算的最长窗口；长度 < 6 时给 None。
    """
    if len(series) < 6:
        return None
    k = min(window, len(series) - 1)
    return round((series[-1] / series[-1 - k] - 1.0) * 100.0, 2)


def main():
    if not os.path.isdir(H_DIR):
        print(f"XX 未找到 {H_DIR}——先跑 fetch_history.py 抓日线")
        return 1

    with open(os.path.join(DATA, "graph.json"), encoding="utf-8") as f:
        graph = json.load(f)
    industries = graph["industries"]            # 行业名 → [代码]，按市值降序
    boards = graph["boards"]                    # 环节名 → [代码]
    industry_list = graph.get("industryList") or sorted(industries)

    all_codes = {c for codes in industries.values() for c in codes}
    series = load_history(all_codes)
    print(f"日线覆盖 {len(series)}/{len(all_codes)} 家公司")

    axis, returns = build_returns(series)
    n = len(axis)
    if n < 2:
        print("XX 公共日期轴不足 2 天，无法构建指数")
        return 1
    print(f"公共日期轴 {axis[0]} ~ {axis[-1]}，共 {n} 天")

    def with_data(codes):
        return [c for c in codes if c in returns]

    generated = date.today().isoformat()
    os.makedirs(os.path.join(OUT_DIR, "i"), exist_ok=True)

    # 全市场 + 24 行业
    market_members = with_data(sorted(all_codes))
    market = index_series(market_members, returns, n)
    ind_indexes = {}
    for name in industry_list:
        members = with_data(industries.get(name, []))
        ind_indexes[name] = index_series(members, returns, n) if members else None

    # 全市场环节榜：199 个环节各算一条全市场口径序列，只留摘要（n/y/m/w）
    board_summary = []
    for b, codes in boards.items():
        members = with_data(codes)
        if len(members) < MIN_MEMBERS:
            continue
        s = index_series(members, returns, n)
        board_summary.append({
            "name": b,
            "n": len(members),
            "y": round(s[-1] - BASE, 2),
            "m": pct_change(s, 20),
            "w": pct_change(s, 5),
        })
    board_summary.sort(key=lambda d: (d["m"] is None, -(d["m"] or 0.0), d["name"]))

    idx_obj = {
        "schemaVersion": 1,
        "generatedAt": generated,
        "dates": axis,
        "market": market,
        "industries": {k: v for k, v in ind_indexes.items() if v is not None},
        "boards": board_summary,
    }
    with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx_obj, f, ensure_ascii=False, separators=(",", ":"))

    # 24 个行业文件：行业指数 + 行业内成员数前 12 的环节
    n_seg_total = 0
    for name in industry_list:
        members = with_data(industries.get(name, []))
        ind_set = set(members)
        ranked = sorted(
            ((b, [c for c in codes if c in ind_set]) for b, codes in boards.items()),
            key=lambda t: (-len(t[1]), t[0]))
        segments = {}
        for b, codes in ranked:
            if len(codes) < MIN_MEMBERS:    # 已按成员数降序，此后只会更小
                break
            if len(segments) >= MAX_SEGMENTS:
                break
            segments[b] = index_series(codes, returns, n)
        n_seg_total += len(segments)
        # 注：契约示例里 "industry" 出现两次（名称与序列），JSON 对象键唯一，
        # 按 JS「后值覆盖前值」的解析结果，"industry" 放序列，名称用 "name"
        obj = {
            "schemaVersion": 1,
            "generatedAt": generated,
            "name": name,
            "dates": axis,
            "industry": index_series(members, returns, n) if members else [],
            "segments": segments,
        }
        with open(os.path.join(OUT_DIR, "i", f"{name}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

    # 汇总：全市场/各行业一年涨跌幅（末日值 - 100）
    print(f"\n已写出 data/trends/index.json（环节榜 {len(board_summary)} 条）"
          f" + 24 个行业文件（环节指数共 {n_seg_total} 条）")
    print("\n环节榜 top5（按近 20 交易日涨跌幅 m）：")
    for d in board_summary[:5]:
        print(f"  {d['name']:<12} m {d['m']:+7.2f}%  w {d['w']:+6.2f}%  "
              f"y {d['y']:+8.2f}%  n={d['n']}")
    print("环节榜 bottom5：")
    for d in board_summary[-5:]:
        print(f"  {d['name']:<12} m {d['m']:+7.2f}%  w {d['w']:+6.2f}%  "
              f"y {d['y']:+8.2f}%  n={d['n']}")
    print(f"\n一年涨跌幅（基期 100，{axis[0]} ~ {axis[-1]}）：")
    print(f"  {'全市场':<6} {market[-1] - BASE:+8.2f}%  （末日 {market[-1]}）")
    for name in sorted(ind_indexes, key=lambda k: -(ind_indexes[k][-1] if ind_indexes[k] else 0)):
        v = ind_indexes[name]
        if v:
            print(f"  {name:<6} {v[-1] - BASE:+8.2f}%  （末日 {v[-1]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
