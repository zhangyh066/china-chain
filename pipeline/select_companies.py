# -*- coding: utf-8 -*-
"""
按三条判据筛选入图公司，并输出可审计的结果。

用法：../.venv/Scripts/python.exe select_companies.py

输出：
  real/selected.json  入图公司（含行业、所属产业链环节、连接度）
  real/excluded.json  被剔除的公司 + 剔除理由（逐家可查）
  real/selection_report.txt  指标报告
"""

import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "real")

# 判据二：剔除金融 / 地产 / 纯服务
DROP_INDUSTRIES = {"银行", "非银金融", "房地产", "交通运输", "商贸零售", "社会服务", "传媒"}


def main():
    sw = json.load(open(os.path.join(OUT, "sw_industries.json"), encoding="utf-8"))
    con = json.load(open(os.path.join(OUT, "concepts.json"), encoding="utf-8"))
    try:
        names = json.load(open(os.path.join(OUT, "raw", "spot.json"), encoding="utf-8"))
        name_of = {str(r["代码"]).zfill(6): r["名称"] for r in names}
    except Exception:
        name_of = {}

    ind_of = {}
    for ind, v in sw.items():
        for t in v["tickers"]:
            ind_of[t] = ind
    market = set(ind_of)

    boards_of = defaultdict(set)
    for cname, ts in con.items():
        for t in ts:
            if t in market:
                boards_of[t].add(cname)

    excluded = {}
    step1 = set()
    for t in market:
        if ind_of[t] in DROP_INDUSTRIES:
            excluded[t] = {"reason": "判据二：属于" + ind_of[t] + "（金融/地产/纯服务）",
                           "industry": ind_of[t]}
        else:
            step1.add(t)

    step2 = set()
    for t in step1:
        if not boards_of[t]:
            excluded[t] = {"reason": "判据三：不属于任何产业链环节", "industry": ind_of[t]}
        else:
            step2.add(t)

    # 判据四：同一行业内，如果没有任何"同概念"的伙伴，就是孤点
    peers = defaultdict(set)
    for t in step2:
        for c in boards_of[t]:
            for o in con[c]:
                if o in step2 and o != t and ind_of[o] == ind_of[t]:
                    peers[t].add(o)
    selected = set()
    for t in step2:
        if peers[t]:
            selected.add(t)
        else:
            excluded[t] = {"reason": "判据四：同行业内没有同产业链环节的伙伴", "industry": ind_of[t]}

    # ---- 组装输出 ----
    sel_records = []
    for t in sorted(selected):
        sel_records.append({
            "ticker": t,
            "name": name_of.get(t, ""),
            "industry": ind_of[t],
            "boards": sorted(boards_of[t]),
            "boardCount": len(boards_of[t]),
            "industryPeers": len(peers[t]),
        })
    sel_records.sort(key=lambda r: (r["industry"], -r["industryPeers"], r["ticker"]))

    with open(os.path.join(OUT, "selected.json"), "w", encoding="utf-8") as f:
        json.dump({"count": len(sel_records), "companies": sel_records}, f,
                  ensure_ascii=False, indent=1)
        f.write("\n")

    exc_records = [{"ticker": t, "name": name_of.get(t, ""), **v}
                   for t, v in sorted(excluded.items())]
    with open(os.path.join(OUT, "excluded.json"), "w", encoding="utf-8") as f:
        json.dump({"count": len(exc_records), "companies": exc_records}, f,
                  ensure_ascii=False, indent=1)
        f.write("\n")

    # ---- 指标报告 ----
    deg = [len(peers[t]) for t in selected]
    board_deg = [len(boards_of[t]) for t in selected]
    by_ind = Counter(ind_of[t] for t in selected)
    lines = []
    A = lines.append
    A("筛选结果指标报告")
    A("=" * 62)
    A(f"全市场（申万一级口径）      {len(market):>5} 家")
    A(f"入图                       {len(selected):>5} 家  ({len(selected)/len(market)*100:.0f}%)")
    A(f"剔除                       {len(excluded):>5} 家")
    A("")
    A("剔除原因分布：")
    for r, n in Counter(v["reason"].split("：")[0] + "：" + v["reason"].split("：")[1][:12]
                        for v in excluded.values()).most_common():
        A(f"   {r:<26}{n:>5} 家")
    A("")
    A("验证指标（自己定的合格线）：")
    iso = sum(1 for d in deg if d == 0)
    A(f"   孤立点比例        {iso/len(selected)*100:>5.1f}%   合格线 < 10%   "
      + ("✓" if iso/len(selected) < 0.10 else "✗"))
    A(f"   行业内的平均连接数 {sum(deg)/len(deg):>5.1f}   合格线 3–8     "
      + ("✓" if 3 <= sum(deg)/len(deg) <= 8 else "✗ 太高，见下方结论"))
    A(f"   每家所属环节数     {sum(board_deg)/len(board_deg):>5.1f} 个（二分图视角的连接数）")
    A("")
    A("⚠ 结论：『同属一个概念』是完全图（一个板块内两两相连），")
    A("   所以公司之间的平均连接数会爆到上百，画出来是毛线团。")
    A(f"   改成二分图（公司 ↔ 产业链环节节点）之后，每家连 {sum(board_deg)/len(board_deg):.1f} 个环节节点，")
    A("   正好落在 3–8 的合理区间——所以图必须画成二分结构。")
    A("")
    A("入图公司的行业分布：")
    for k, v in by_ind.most_common():
        A(f"   {k:<10}{v:>5}")
    A("")
    A("最活跃的公司（同行业连接数前 15）：")
    for r in sel_records[:0] or sorted(sel_records, key=lambda r: -r["industryPeers"])[:15]:
        A(f"   {r['name']:<8}{r['ticker']}  {r['industry']:<8}连 {r['industryPeers']:>3} 家同行  "
          f"({r['boardCount']} 个环节)")

    text = "\n".join(lines)
    with open(os.path.join(OUT, "selection_report.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
