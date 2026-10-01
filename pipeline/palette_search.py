# -*- coding: utf-8 -*-
"""
行业配色搜索：在"低饱和 + 中间明度"的约束内，找一组两两色差最大的 11 色。

约束为什么这么定：
- 低饱和（色度上限）→ 避免霓虹感，做出"印刷油墨 / 潘通哑光"的高级质感
- 中间明度（L* 32~68）→ 作为圆点放在白底上要看得清，又不能压成黑块

但降饱和会牺牲色盲下的可区分性（明度是唯一能穿越所有色盲类型的通道），
所以不靠手挑：直接在这个约束空间里爬山，把"三元色差的最小值"最大化。

性能：每轮只改一个颜色，所以只重算涉及它的那 10 对色差（增量），
而不是全部 55 对——否则纯 Python 跑几万轮会直接超时。
"""

import itertools
import math
import random

from palette_check import (delta_e, hex2rgb, rgb2hex, rgb2lab,
                           sim_deuteranopia, sim_protanopia, check, report)

TARGET = (20.0, 8.0, 10.0)      # 目标：正常 20 / 红色盲 8 / 绿色盲 10

# 真正会和行业色同屏的，只有画布上那两条链条墨色。
# 其余语义色（上游二级 / 下游二级 / 主色 / 金）出现在别的页面或只在 UI 外壳上，
# 形态也不同（标签、细线、按钮），不构成混淆——一开始把它们全列进来，
# 约束过紧，反而把 11 色的互相色差从 29 压到了 20。
RESERVED = ["#1D4E7C", "#9C5A2C"]     # Atlas 画布上的上游藏青 / 下游古铜
RESERVED_MIN = 16.0                   # 与这两者的最小可接受色差
L_RANGE = (33.0, 64.0)
C_RANGE = (16.0, 38.0)
N = 11
NAMES = ["电子", "电力设备", "医药生物", "汽车", "计算机", "通信",
         "机械设备", "有色金属", "基础化工", "食品饮料", "家用电器"]


def lab2rgb(lab):
    L, a, b = lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def finv(t):
        t3 = t ** 3
        return t3 if t3 > 0.008856 else (116 * t - 16) / 903.3

    x, y, z = 0.95047 * finv(fx), finv(fy), 1.08883 * finv(fz)
    r = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
    g = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
    bb = x * 0.0556434 + y * -0.2040259 + z * 1.0572252

    def enc(c):
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

    out = []
    for c in (r, g, bb):
        if c < -0.002 or c > 1.002:
            return None
        out.append(round(max(0.0, min(1.0, enc(c))) * 255))
    return tuple(out)


def lch2rgb(L, C, H):
    return lab2rgb((L, C * math.cos(math.radians(H)), C * math.sin(math.radians(H))))


def dist(l1, l2):
    return math.sqrt((l1[0] - l2[0]) ** 2 + (l1[1] - l2[1]) ** 2 + (l1[2] - l2[2]) ** 2)


def trio(rgb):
    """一个颜色在三种视觉下的 Lab"""
    return rgb2lab(rgb), rgb2lab(sim_protanopia(rgb)), rgb2lab(sim_deuteranopia(rgb))


def pair_gaps(a, b):
    return dist(a[0], b[0]), dist(a[1], b[1]), dist(a[2], b[2])


class Problem:
    def __init__(self, rgbs, reserved=()):
        self.reserved_rgb = [hex2rgb(r) for r in reserved]
        self.rgbs = list(rgbs)
        self.trios = [trio(c) for c in rgbs]
        self.gaps = [[(999.0, 999.0, 999.0)] * N for _ in range(N)]
        for i, j in itertools.combinations(range(N), 2):
            self.gaps[i][j] = pair_gaps(self.trios[i], self.trios[j])

    def replace(self, i, rgb):
        self.rgbs[i] = rgb
        self.trios[i] = trio(rgb)
        for j in range(N):
            if j == i:
                continue
            a, b = (i, j) if i < j else (j, i)
            self.gaps[a][b] = pair_gaps(self.trios[a], self.trios[b])

    def mins(self):
        m = [999.0, 999.0, 999.0]
        for i, j in itertools.combinations(range(N), 2):
            g = self.gaps[i][j]
            for k in range(3):
                if g[k] < m[k]:
                    m[k] = g[k]
        return tuple(m)

    def reserved_penalty(self):
        pen = 0.0
        for c in self.rgbs:
            d = min(delta_e(c, res) for res in self.reserved_rgb)
            if d < RESERVED_MIN:
                pen += 0.05 * (RESERVED_MIN - d)
        return pen

    def score(self, mins):
        s = min(mins[0] / TARGET[0], mins[1] / TARGET[1], mins[2] / TARGET[2])
        # 轻微惩罚：过饱和（破坏哑光感）、过亮（圆点贴白底会发虚）
        chroma = sum(math.hypot(*rgb2lab(c)[1:]) for c in self.rgbs) / N
        s -= 0.006 * max(0.0, chroma - 30)
        s -= 0.006 * sum(max(0.0, rgb2lab(c)[0] - 63) for c in self.rgbs)
        s -= self.reserved_penalty()
        return s


def run_trial(rng, iters=24000):
    rgbs = []
    while len(rgbs) < N:
        rgb = lch2rgb(rng.uniform(*L_RANGE), rng.uniform(*C_RANGE), rng.uniform(0, 360))
        if rgb is None:
            continue
        L = rgb2lab(rgb)[0]
        if L_RANGE[0] - 1 <= L <= L_RANGE[1] + 1:
            rgbs.append(rgb)

    prob = Problem(rgbs, RESERVED)
    params = []
    for c in rgbs:
        L, a, b = rgb2lab(c)
        params.append([L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360])

    best = [list(p) for p in params]
    best_score = prob.score(prob.mins())
    step = [5.0, 7.0, 12.0]

    for it in range(iters):
        i = rng.randrange(N)
        j = rng.randrange(3)
        cand = list(params[i])
        cand[j] += rng.gauss(0, step[j])
        cand[0] = min(L_RANGE[1], max(L_RANGE[0], cand[0]))
        cand[1] = min(C_RANGE[1], max(C_RANGE[0], cand[1]))
        cand[2] %= 360
        rgb = lch2rgb(*cand)
        if rgb is None:
            continue

        old = prob.rgbs[i]
        prob.replace(i, rgb)
        s = prob.score(prob.mins())
        if s > best_score:
            best_score = s
            params[i] = cand
            best = [list(p) for p in params]
        else:
            prob.replace(i, old)      # 回退

        if it % 3000 == 0:
            step = [v * 0.8 for v in step]

    final = [lch2rgb(*p) or rgbs[k] for k, p in enumerate(best)]
    return final, Problem(final, RESERVED).mins()


if __name__ == "__main__":
    rng = random.Random(20260921)
    best = None
    for t in range(3):
        cols, gaps = run_trial(rng, iters=32000)
        print(f"  试次 {t + 1}: 正常 {gaps[0]:5.1f} / 红色盲 {gaps[1]:4.1f} / 绿色盲 {gaps[2]:5.1f}")
        if best is None or gaps > best[1]:
            best = (cols, gaps)

    cols, gaps = best
    # 环上相邻的行业如果颜色也相邻，边界就分不清了。
    # 所以按色相排序后交叉铺开，让"色相上挨着的"落在"环上离得远的"位置。
    order = sorted(range(N), key=lambda i: math.degrees(math.atan2(*rgb2lab(cols[i])[1:][::-1])) % 360)
    slot = [0, 6, 1, 7, 2, 8, 3, 9, 4, 10, 5]
    assigned = [None] * N
    for k, idx in enumerate(order):
        assigned[slot[k]] = cols[idx]
    cols = assigned
    palette = list(zip(NAMES, [rgb2hex(c) for c in cols]))

    print("\n最优解 最小色差  正常 %.1f / 红色盲 %.1f / 绿色盲 %.1f" % gaps)
    print()
    for n, h in palette:
        L, a, b = rgb2lab(hex2rgb(h))
        print(f"  {n:<8}{h}   L*{L:5.1f}   C*{math.hypot(a, b):4.1f}   H{math.degrees(math.atan2(b, a)) % 360:5.1f}")

    print("\n可直接粘贴：")
    print("WM_COLORS = [" + ", ".join(f'"{h}"' for _, h in palette) + "]")

    print("\n与已占用语义色的最近距离（要求 >= %.0f）:" % RESERVED_MIN)
    for n, h in palette:
        d = min((delta_e(hex2rgb(h), hex2rgb(r)), r) for r in RESERVED)
        mark = "   <- 偏近" if d[0] < RESERVED_MIN else ""
        print(f"  {n:<8}{h}   最近 {d[1]}  dE {d[0]:5.1f}{mark}")

    check("搜索得到的投行配色", palette)
    report(palette)
