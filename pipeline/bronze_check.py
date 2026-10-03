# -*- coding: utf-8 -*-
"""
WCAG 对比度检查器（换底色时用）。

背景：这个脚本原本是为一次「把页面底换成浅古铜」的尝试写的。那次尝试做法上没问题
（对比度全达标），但观感上被否了——大面积浅棕在屏幕上读起来是土黄，不是古铜。
**教训：判断一个颜色方向靠不靠谱，要先看大面积的实拍效果，再谈精修。**

脚本本身是通用的：改下面 BGS / TEXTS / DATA 里的色值就能复核任何一套底色。

换底色时最容易漏的不是正文（浅底深底都够），而是这些"看起来很安全"的中间色：
  - 弱化文字（原来的 #8A8A84 在米白上 3.1:1，看着还行；换到浅古铜上只有 2.4:1，直接糊）
  - 金色细线（浅金 #C3AE85 在深底上只有 1.5:1，等于消失）
所以换底后要逐项重算，不能只看正文。
"""

from palette_check import delta_e, hex2rgb, rgb2lab


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rel_lum(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = rel_lum(hex2rgb(a)), rel_lum(hex2rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def wcag(c):
    if c >= 7: return "AAA"
    if c >= 4.5: return "AA"
    if c >= 3: return "AA(大字/图形)"
    return "不达标"


BGS = {
    "旧米白 #F5F3EE": "#F5F3EE",
    "古铜纸 A #EAE1D0": "#EAE1D0",
    "古铜纸 B #E6DBC7": "#E6DBC7",
    "古铜纸 C #E2D5BE": "#E2D5BE",
}
SURFACES = {"暖白卡片 #FDFBF6": "#FDFBF6", "暖白卡片 #FCF9F3": "#FCF9F3"}

TEXTS = {
    "正文候选 #14181D": "#14181D",
    "正文候选 #171A1E": "#171A1E",
    "次级候选 #4A4A45": "#4A4A45",
    "次级候选 #514B41": "#514B41",
    "弱化候选 #8A8A84（沿用旧值）": "#8A8A84",
    "弱化候选 #7C7566": "#7C7566",
    "弱化候选 #736C5C": "#736C5C",
}

DATA = {
    "上游藏青 #1D4E7C": "#1D4E7C",
    "下游古铜 #9C5A2C": "#9C5A2C",
    "下游古铜(加深) #8A4A1E": "#8A4A1E",
    "涨红 #AE2A1E": "#AE2A1E",
    "跌绿 #0E6B4A": "#0E6B4A",
    "主色藏青 #13375E": "#13375E",
    "金(加深) #8A6A28": "#8A6A28",
}

if __name__ == "__main__":
    print("=== 文字 / 背景 对比度（WCAG，正文要 >= 4.5，理想 >= 7）===")
    for bn, bg in BGS.items():
        print(f"\n  底：{bn}")
        for tn, t in TEXTS.items():
            c = contrast(t, bg)
            print(f"    {tn:<26} {c:5.2f}  {wcag(c)}")

    print("\n\n=== 数据色 / 暖白卡片底 对比度（图形至少要 >= 3）===")
    for sn, s in SURFACES.items():
        print(f"\n  底：{sn}")
        for dn, d in DATA.items():
            c = contrast(d, s)
            print(f"    {dn:<26} {c:5.2f}  {wcag(c)}")

    print("\n\n=== 数据色 / 古铜纸底 对比度（判断古铜色还能不能用在古铜底上）===")
    for bn in ("古铜纸 A #EAE1D0", "古铜纸 C #E2D5BE"):
        bg = BGS[bn]
        print(f"\n  底：{bn}")
        for dn, d in DATA.items():
            c = contrast(d, bg)
            print(f"    {dn:<26} {c:5.2f}  {wcag(c)}")

    print("\n\n=== 与旧背景的色差（确认确实换了个调子）===")
    for bn, bg in BGS.items():
        if bn.startswith("旧"):
            continue
        print(f"  {bn}  vs 旧米白: dE {delta_e(hex2rgb(bg), hex2rgb('#F5F3EE')):.1f}")
