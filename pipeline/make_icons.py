# -*- coding: utf-8 -*-
"""生成 PWA 图标（纯标准库，不依赖 Pillow）。

设计同 index.html 的内联 favicon：藏青圆角底 + 白色圆环 + 中心圆点
（"环上一点" = 行业环图上的一个公司）。

用法：python make_icons.py   →  ../assets/icon-*.png
"""
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")

NAVY = (0x13, 0x37, 0x5E, 0xFF)
WHITE = (0xFF, 0xFF, 0xFF, 0xFF)
TRANSPARENT = (0, 0, 0, 0)

SS = 3  # 超采样倍数：先 3 倍分辨率画，再盒式降采样，边缘即抗锯齿


def inside_rounded_rect(x, y, size, radius):
    """(x, y) 是否落在边长 size、圆角 radius 的方形内（坐标已归一化 0..1）。"""
    if x < 0 or y < 0 or x > size or y > size:
        return False
    r = radius
    cx = min(max(x, r), size - r)
    cy = min(max(y, r), size - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def render(size, *, full_bleed=False, glyph_scale=1.0):
    """返回 RGBA 字节串。full_bleed 给 maskable 用（底色铺满整幅，
    图形缩进安全区）；glyph_scale 控制环/点相对整幅的大小。"""
    s = size * SS
    px = [[TRANSPARENT] * s for _ in range(s)]

    radius = s * 0.22 if not full_bleed else 0          # 圆角底 or 全出血
    pad = s * (0.10 if full_bleed else 0.0)             # 安全区留白
    span = s - 2 * pad
    cx = cy = s / 2
    ring_r = span * 0.22 * glyph_scale
    ring_w = span * 0.085 * glyph_scale
    dot_r = span * 0.075 * glyph_scale

    for y in range(s):
        for x in range(s):
            if full_bleed:
                bg = True
            else:
                bg = inside_rounded_rect(x, y, s, radius)
            if not bg:
                continue
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            ring = abs(d2 ** 0.5 - ring_r) <= ring_w / 2
            dot = d2 ** 0.5 <= dot_r
            px[y][x] = WHITE if (ring or dot) else NAVY

    # 盒式降采样回目标尺寸
    out = bytearray()
    for y in range(size):
        for x in range(size):
            acc = [0, 0, 0, 0]
            for dy in range(SS):
                for dx in range(SS):
                    p = px[y * SS + dy][x * SS + dx]
                    for i in range(4):
                        acc[i] += p[i]
            n = SS * SS
            out += bytes(acc[i] // n for i in range(4))
    return bytes(out)


def write_png(path, size, rgba):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgba[y * size * 4:(y + 1) * size * 4]
                   for y in range(size))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    print(f"  {os.path.basename(path)}  {size}x{size}  {os.path.getsize(path)//1024} KB")


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        # (文件名, 尺寸, 全出血, 图形缩放)
        ("icon-192.png", 192, False, 1.0),
        ("icon-512.png", 512, False, 1.0),
        ("icon-512-maskable.png", 512, True, 1.0),
        ("apple-touch-icon.png", 180, True, 0.92),   # iOS 会自己裁圆角，底给满
    ]
    for name, size, bleed, scale in jobs:
        write_png(os.path.join(OUT, name), size, render(size, full_bleed=bleed, glyph_scale=scale))
    print(f"[ok] 写入 {OUT}")


if __name__ == "__main__":
    main()
