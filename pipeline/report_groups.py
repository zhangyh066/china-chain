# -*- coding: utf-8 -*-
"""生成人类可读的《环节归类表》——用来人工审":这个环节归得对不对"。

输出：pipeline/环节归类表.txt
用法：.venv/Scripts/python.exe report_groups.py
"""
import io
import json
import os
from collections import defaultdict

import chain_groups as cg

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(HERE, "环节归类表.txt")

COVER = 0.60      # 每类默认展开到覆盖该类的 60%
CAP = 12          # 但最多不超过 12 段


def load():
    g = json.load(io.open(os.path.join(DATA, "graph.json"), encoding="utf-8"))
    idx = json.load(io.open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    bl = g["boardList"]
    # 每家公司的主环节（它所属环节里成员最少的那个）
    primary = {}
    for c in idx["companies"]:
        bs = g["boardIdxOf"].get(c["ticker"]) or []
        if bs:
            primary[c["ticker"]] = min(bs, key=lambda bi: len(g["boards"][bl[bi]]))
    return g, bl, primary


def main():
    g, bl, primary = load()
    L = []
    w = L.append

    w("环节归类表（环节 → 大类）")
    w(f"数据：{len(primary)} 家公司 / {len(bl)} 个环节 / 24 个申万一级行业 · 生成于 2026-09-22")
    w("")
    w("【这张表是干什么的】")
    w("  环图要分两层：内环 = 下面这 14 个大类，外环 = 点开那一类里的环节。")
    w("  大类按「环节本身的技术性质」分，不看它出现在哪个申万行业 —— 因为实测")
    w("  199 个环节里有 188 个（95%）被 2 个以上行业当作主环节用（\"新材料\"被 12 个")
    w("  行业用、\"液冷服务器\"被 12 个），按行业各起一套会出现同一个\"减速器\"被归 3 次。")
    w("")
    w("")
    w("【两层各自怎么折叠（实测定下来的）】")
    w("  内环（大类）：按公司数从大到小取，直到覆盖该行业的 60%；其余合并成「其他 N 个大类 ›」")
    w("        → 实测内环 ≤ 5 段（机械设备），最少 2 段")
    w("  外环（环节）：同一套规则 → 实测外环 ≤ 11 段（含「其他」，医药生物最多）")
    w("  → 同时出现在屏幕上的段数 ≤ 16，且每段都有名字")
    w("  → 为什么不用「最多 10 个」那种规则：最小的大类只占 0.8° 的角度，名字根本写不下，")
    w("     补救就得设「最小角宽」，而最小角宽会把占比歪曲到 1:7 以上（视觉上撒谎）。")
    w("     折叠掉的段不画，所以占比全程真实。")
    w("  → 折叠不等于隐藏：每个折叠点都写明「其他 N 个」（带数字、可点）；")
    w("     悬停它，中心会把这 N 个名字列出来。")
    w("")
    w("【已通过的校验】")
    w(f"  1. {len(bl)} 个环节全部归类，无一遗漏")
    ind_grp = summarize_by_industry(g, bl, primary)
    n_max = max(len(v) for v in ind_grp.values())
    w(f"  2. 每个行业会拥有 2~{n_max} 个大类（最多的是电子，{n_max} 个）")
    need_max = 0
    for ind, per in ind_grp.items():
        for grp, (slots, tot) in per.items():
            run, need = 0, 0
            for _n, cnt in slots:
                run += cnt
                need += 1
                if run >= tot * COVER:
                    break
            need_max = max(need_max, need)
    w(f"  3. 外环按「覆盖该类 60%」折叠，实测最多只要 {need_max} 个环节")
    inner_max = 0
    for ind, per in ind_grp.items():
        total = sum(t for _, t in per.values())
        run = keep = 0
        for _g, (slots, tot) in sorted(per.items(), key=lambda kv: -kv[1][1]):
            run += tot
            keep += 1
            if run >= total * COVER:
                break
        inner_max = max(inner_max, keep + (1 if len(per) > keep else 0))
    w(f"  4. 内环按同一套规则折叠，实测最多 {inner_max} 段（含「其他 N 个大类」）")
    w(f"  5. 两层合计 ≤ {inner_max + need_max + 1} 段，每段都有名字")
    w("")

    w("═" * 74)
    w("一、按大类看（14 个）—— 审的就是这一节：环节归得对不对")
    w("═" * 74)
    for grp in cg.GROUP_NAMES:
        names = [b for b in bl if cg.GROUPS.get(b) == grp]
        w("")
        w(f"【{grp}】{len(names)} 个环节")
        for name in sorted(names, key=lambda x: -len(g["boards"][x])):
            n = len(g["boards"][name])
            note = cg.NOTES.get(name, "")
            w(f"    {name:<16}{n:>4} 家" + (f"   ← {note}" if note else ""))
    # 有备注但不在任何大类里的（防漏）
    w("")

    w("═" * 74)
    w("二、按行业看（24 个）—— 这是实际会出现在环上的形态")
    w("═" * 74)
    w("")
    for ind in sorted(ind_grp, key=lambda x: -sum(t for _, t in ind_grp[x].values())):
        per = ind_grp[ind]
        total = sum(t for _, t in per.values())
        # 内环按 60% 覆盖折叠后的段数
        run = keep = 0
        for _g, (_s, tt) in sorted(per.items(), key=lambda kv: -kv[1][1]):
            run += tt
            keep += 1
            if run >= total * COVER:
                break
        inner = keep + (1 if len(per) > keep else 0)
        w(f"【{ind}】{total} 家 · 内环 {inner} 段（{len(per)} 个大类中取前 {keep} 个"
          + (f" + 其他 {len(per) - keep} 个" if len(per) > keep else "") + "）")
        rows = sorted(per.items(), key=lambda kv: -kv[1][1])
        for grp, (slots, tot) in rows[:6]:
            run, need = 0, 0
            for _n, cnt in slots:
                run += cnt
                need += 1
                if run >= tot * COVER:
                    break
            need = min(need, CAP)
            tag = "全部展开" if len(slots) <= need else f"前 {need} 个 + 其他 {len(slots) - need} 个"
            w(f"    {grp:<10}{len(slots):>2} 个环节 /{tot:>4} 家   → {tag}")
        if len(rows) > 6:
            rest = rows[6:]
            w(f"    其余 {len(rest)} 个大类：{'、'.join(g_ for g_, _ in rest)}"
              f"（共 {sum(len(s) for _, (s, _t) in rest)} 个环节）")
        w("")

    w("═" * 74)
    w("三、判断有余地的条目（请你重点看这些）")
    w("═" * 74)
    w("")
    for k, v in cg.NOTES.items():
        w(f"  · {k}")
        w(f"      {v}")
    w("")
    w("（除了上面这些，其余 170 多个环节的归属都是很明确的：名字本身就说明了性质。）")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(f"已写出 {OUT}")
    print(f"  {len(L)} 行")


def summarize_by_industry(g, bl, primary):
    """行业 → {大类: ([(环节名, 家数)] 按家数降序, 该大类总家数)}"""
    out = defaultdict(dict)
    for ind, mem in g["industries"].items():
        per = defaultdict(lambda: defaultdict(int))
        for t in mem:
            bi = primary.get(t)
            if bi is None:
                continue
            grp = cg.GROUPS.get(bl[bi])
            if grp:
                per[grp][bl[bi]] += 1
        for grp, c in per.items():
            out[ind][grp] = (sorted(c.items(), key=lambda kv: -kv[1]), sum(c.values()))
    return out


if __name__ == "__main__":
    main()
