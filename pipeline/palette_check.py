# -*- coding: utf-8 -*-
"""
配色校验：两两色差（CIE76 ΔE）+ 红绿色盲模拟下的色差。

为什么必须算：11 个行业色放在一张环形图上，如果两个颜色在色盲眼里
几乎一样，读者就分不出这是两家不同行业的公司——而"颜色"在图上承担的
是分类职责，不能靠"我觉得好看"。

色盲模拟用的是经典的 Viénot 型 LMS 线性变换（daltonize 那一套），
在 gamma 编码后的 RGB 上做，够用于"能不能区分"这个判断。
"""

import itertools
import math


# ---------- 基础色彩变换 ----------
def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def _srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb2lab(rgb):
    """sRGB(0-255) → CIE L*a*b*（D65）"""
    r, g, b = (_srgb_to_lin(v) for v in rgb)
    # sRGB → XYZ (D65)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    # 归一化到白点
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(c1, c2):
    """CIE76 色差"""
    l1, a1, b1 = rgb2lab(c1)
    l2, a2, b2 = rgb2lab(c2)
    return math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)


# ---------- 色盲模拟（Viénot 型） ----------
def _rgb2lms(rgb):
    r, g, b = rgb
    return (
        17.8824 * r + 43.5161 * g + 4.11935 * b,
        3.45565 * r + 27.1554 * g + 3.86714 * b,
        0.0299566 * r + 0.184309 * g + 1.46709 * b,
    )


def _lms2rgb(lms):
    l, m, s = lms
    return (
        0.080944 * l - 0.130504 * m + 0.116721 * s,
        -0.0102485 * l + 0.0540194 * m - 0.113615 * s,
        -0.000365294 * l - 0.00412163 * m + 0.693513 * s,
    )


def _clamp_rgb(rgb):
    return tuple(max(0.0, min(255.0, v)) for v in rgb)


def sim_protanopia(rgb):
    l, m, s = _rgb2lms(rgb)
    return _clamp_rgb(_lms2rgb((2.02344 * m - 2.52581 * s, m, s)))


def sim_deuteranopia(rgb):
    l, m, s = _rgb2lms(rgb)
    return _clamp_rgb(_lms2rgb((l, 0.494207 * l + 1.24827 * s, s)))


# ---------- 校验 ----------
def check(name, palette, min_normal=16.0, min_cvd=7.0):
    cols = [(n, hex2rgb(h)) for n, h in palette]
    worst = {"normal": (999, None), "protan": (999, None), "deutan": (999, None)}
    for (n1, c1), (n2, c2) in itertools.combinations(cols, 2):
        for key, f in (("normal", lambda x: x),
                       ("protan", sim_protanopia),
                       ("deutan", sim_deuteranopia)):
            d = delta_e(f(c1), f(c2))
            if d < worst[key][0]:
                worst[key] = (d, f"{n1} ↔ {n2}")

    ok = (worst["normal"][0] >= min_normal
          and worst["protan"][0] >= min_cvd
          and worst["deutan"][0] >= min_cvd)
    print(f"\n=== {name} ===  {'通过' if ok else '不通过'}")
    for key, label in (("normal", "正常视觉"), ("protan", "红色盲"), ("deutan", "绿色盲")):
        d, pair = worst[key]
        flag = "OK " if d >= (min_normal if key == "normal" else min_cvd) else "低 "
        print(f"  {flag}{label}最小色差 ΔE = {d:5.1f}   （最接近的一对：{pair}）")
    return ok


def report(palette):
    """把每对色差低于阈值的列出来，便于针对性调整"""
    cols = [(n, hex2rgb(h)) for n, h in palette]
    rows = []
    for (n1, c1), (n2, c2) in itertools.combinations(cols, 2):
        dn = delta_e(c1, c2)
        dp = delta_e(sim_protanopia(c1), sim_protanopia(c2))
        dd = delta_e(sim_deuteranopia(c1), sim_deuteranopia(c2))
        rows.append((min(dn, dp, dd), n1, n2, dn, dp, dd))
    rows.sort()
    print("\n  最接近的 8 对（按三者最小值排）:")
    for _, n1, n2, dn, dp, dd in rows[:8]:
        print(f"    {n1:<8} ↔ {n2:<8} 正常 {dn:5.1f}  红色盲 {dp:5.1f}  绿色盲 {dd:5.1f}")


if __name__ == "__main__":
    # 参考基准：原站公布过的 11 个 GICS 行业色（暖白底上的高饱和色系）
    original = [("IT", "#1a48bc"), ("Comm", "#4cbef7"), ("Fin", "#8a1586"),
                ("RE", "#a06aec"), ("HC", "#f983c3"), ("CS", "#cf3869"),
                ("CD", "#f99532"), ("Ind", "#0f86ad"), ("En", "#ad6800"),
                ("Mat", "#4e5d00"), ("Util", "#3fb785")]

    # 本项目最终采用（顺序 = Atlas 环上的行业顺序）
    final = [("电子", "#a29477"), ("电力设备", "#495870"), ("医药生物", "#37937d"),
             ("汽车", "#c18995"), ("计算机", "#7a5692"), ("通信", "#ac5e4e"),
             ("机械设备", "#759eb4"), ("有色金属", "#9296da"), ("基础化工", "#694b23"),
             ("食品饮料", "#0f7bb4"), ("家用电器", "#764a54")]

    # 已经被别的语义占用的颜色：画布上的上游藏青 / 下游古铜。
    # 行业色必须与它们拉开距离，否则同一张图上"一个颜色表示两件事"。
    RESERVED = [("上游藏青", "#1D4E7C"), ("下游古铜", "#9C5A2C")]

    check("参考站原配色（基准）", original)
    check("本项目最终配色", final)

    print("\n与已占用语义色（上游藏青/下游古铜）的距离，要求 >= 15:")
    worst = 999.0
    for n, h in final:
        d, who = min(((delta_e(hex2rgb(h), hex2rgb(r)), rn) for rn, r in RESERVED))
        worst = min(worst, d)
        print(f"  {n:<8}{h}   最近 {who}  dE {d:5.1f}")
    print(f"  最小 {worst:.1f}  {'OK' if worst >= 15 else '偏近'}")

    report(final)
