# -*- coding: utf-8 -*-
"""
行业色与"已占用的语义色"必须拉开距离。

为什么：Atlas 那张画布上，行业图例的圆点和"选中公司的供应链高亮线"
同时存在。如果某个行业色和下游古铜几乎同色，读者会看到
「一个颜色表示两件事」——这正是本项目的配色原则里明令禁止的。

已占用的语义色：上游藏青 / 上游二级蓝 / 下游古铜 / 下游二级 / 主色藏青 / 金
"""

import itertools
import math

from palette_check import (check, delta_e, hex2rgb, rgb2lab,
                           sim_deuteranopia, sim_protanopia)

RESERVED = [
    ("上游藏青", "#1D4E7C"), ("上游二级", "#3E6E9C"),
    ("下游古铜", "#9C5A2C"), ("下游二级", "#7C4520"),
    ("主色藏青", "#13375E"),
]
CUR = ["#733f42", "#25545d", "#a09a54", "#464a79", "#4c8261",
       "#a46b94", "#9d643a", "#0083b1", "#b59089", "#544f2b", "#8a91d5"]
NAMES = ["电子", "电力设备", "医药生物", "汽车", "计算机", "通信",
         "机械设备", "有色金属", "基础化工", "食品饮料", "家用电器"]


def dist_to_reserved(c):
    return min((delta_e(hex2rgb(c), hex2rgb(v)), k) for k, v in RESERVED)


def trio_mins(pal):
    mn = [999.0, 999.0, 999.0]
    for c1, c2 in itertools.combinations(pal, 2):
        a, b = hex2rgb(c1), hex2rgb(c2)
        mn[0] = min(mn[0], delta_e(a, b))
        mn[1] = min(mn[1], delta_e(sim_protanopia(a), sim_protanopia(b)))
        mn[2] = min(mn[2], delta_e(sim_deuteranopia(a), sim_deuteranopia(b)))
    return mn


if __name__ == "__main__":
    print("当前 11 色与已占用语义色的最近距离：")
    for c in sorted(CUR, key=lambda x: dist_to_reserved(x)[0]):
        d, k = dist_to_reserved(c)
        flag = "   <- 冲突" if d < 12 else ""
        print(f"  {c}   最近 = {k:<8} dE {d:5.1f}{flag}")

    others = [c for c in CUR if c != "#9d643a"]
    base = trio_mins(others)
    print(f"\n剩下 10 色的三元最小色差：正常 {base[0]:.1f} / 红盲 {base[1]:.1f} / 绿盲 {base[2]:.1f}")
    print("给冲突色找替补（要求：与已占用色 dE >= 14，且不拉低其余色差）…")

    best = None
    for r in range(0x50, 0xC0, 6):
        for g in range(0x50, 0xC0, 6):
            for b in range(0x50, 0xC0, 6):
                cand = "#%02x%02x%02x" % (r, g, b)
                L, A, B = rgb2lab(hex2rgb(cand))
                if not (33 <= L <= 64 and 6 <= math.hypot(A, B) <= 40):
                    continue
                dres = dist_to_reserved(cand)[0]
                if dres < 14:
                    continue
                m = trio_mins(others + [cand])
                score = min(m[0] / 20.0, m[1] / 8.0, m[2] / 10.0) + dres / 200.0
                if best is None or score > best[0]:
                    best = (score, cand, m, dres)

    _, cand, m, dres = best
    print(f"\n  最佳替补 {cand}：三元最小色差 正常 {m[0]:.1f} / 红盲 {m[1]:.1f} / 绿盲 {m[2]:.1f}；"
          f"与已占用色最近 dE {dres:.1f}")

    final = ["#733f42", "#25545d", "#a09a54", "#464a79", "#4c8261",
             "#a46b94", cand, "#0083b1", "#b59089", "#544f2b", "#8a91d5"]
    check("修正后的行业配色", list(zip(NAMES, final)))
    print("\nWM_COLORS = [" + ", ".join(f'"{c}"' for c in final) + "]")

    print("\n全部 11 色与已占用色的距离：")
    for c in sorted(final, key=lambda x: dist_to_reserved(x)[0]):
        d, k = dist_to_reserved(c)
        print(f"  {c}   最近 = {k:<8} dE {d:5.1f}")
