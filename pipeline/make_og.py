# -*- coding: utf-8 -*-
"""生成 OG 分享卡片（assets/og/*.png，1200×630）。

做法：用 HTML + 内联 SVG 圆饼拼一张卡片，再用 Edge/Chromium 无头截图。
比纯 Python 光栅化好在：中文字体、字距、留白全部交给浏览器排版，
和站点本身是同一套设计语言（纸与墨 + 点睛金）。

用法：python make_og.py
  （需要本机装有 Edge 或 Chrome，自动探测）
"""
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "og")

PART_CYCLE = ["#1C3A5E", "#7A8CA3", "#3A3F45"]
PART_OTHER = "#CBC6BC"
PAPER, INK, FAINT, GOLD, NAVY = "#F5F3EE", "#14181D", "#8A8A84", "#13375E", "#13375E"

W, H = 1200, 630

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def donut_svg(segs, cx, cy, r, hole):
    """segs: [(label, n)] → 带小间隙的 SVG 圆环（外弧进、内弧回，两段弧的
    large 标志都按实际跨度算——近整圆的"其他"段才不会画成螺旋）。"""
    total = sum(n for _, n in segs) or 1
    parts = []
    a = -math.pi / 2
    for i, (label, n) in enumerate(segs):
        span = (n / total) * math.pi * 2
        gap = min(span * 0.05, 0.018)
        a0, a1 = a + gap / 2, a + span - gap / 2
        a += span
        color = PART_OTHER if label == "其他" else PART_CYCLE[i % len(PART_CYCLE)]
        large = 1 if (a1 - a0) > math.pi else 0
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        xi0, yi0 = cx + hole * math.cos(a0), cy + hole * math.sin(a0)
        parts.append(
            f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 {large} 1 {x1:.1f} {y1:.1f} '
            f'A{hole} {hole} 0 {large} 0 {xi0:.1f} {yi0:.1f} Z" fill="{color}"/>')
    return "".join(parts)


def card_html(title, subtitle, segs, center_top, center_bottom):
    legend = "".join(
        f'<div class="lg"><span class="dot" style="background:{PART_CYCLE[i % 3] if label != "其他" else PART_OTHER}"></span>'
        f'{label} <b>{n}</b></div>'
        for i, (label, n) in enumerate(segs[:5]))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{W}px; height:{H}px; background:{PAPER}; color:{INK};
         font-family:"Songti SC","Noto Serif CJK SC","SimSun",serif;
         border-top:10px solid {GOLD}; padding:56px 72px; position:relative; }}
  h1 {{ font-size:64px; letter-spacing:.04em; font-weight:700; margin-top:26px; }}
  .sub {{ font-size:28px; color:{FAINT}; margin-top:14px; letter-spacing:.08em; }}
  .donut {{ position:absolute; right:72px; top:80px; }}
  .lg {{ font-size:19px; color:{INK}; line-height:1.65; white-space:nowrap; }}
  .lg b {{ font-variant-numeric:tabular-nums; }}
  .dot {{ display:inline-block; width:16px; height:16px; border-radius:3px; margin-right:10px; }}
  .brand {{ position:absolute; bottom:40px; left:72px; font-size:26px; color:{NAVY};
           letter-spacing:.2em; font-weight:700; }}
  .brand small {{ color:{FAINT}; font-weight:400; letter-spacing:.06em; margin-left:14px; }}
  .note {{ position:absolute; bottom:44px; right:72px; font-size:20px; color:{FAINT}; }}
  </style></head><body>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="donut">
    <svg width="300" height="300" viewBox="0 0 400 400">
      {donut_svg(segs, 200, 200, 178, 106)}
      <text x="200" y="190" text-anchor="middle" font-size="44" fill="{INK}" font-weight="700">{center_top}</text>
      <text x="200" y="232" text-anchor="middle" font-size="22" fill="{FAINT}">{center_bottom}</text>
    </svg>
    <div style="margin-top:4px">{legend}</div>
  </div>
  <div class="brand">链谱 ChainAtlas<small>A 股产业链知识图谱</small></div>
  <div class="note">数据仅供结构示意 · 不构成投资建议</div>
  </body></html>"""


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    sys.exit("找不到 Edge/Chrome，无法截图生成 OG 图")


def shot(browser, html, out_path):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    r = subprocess.run(
        [browser, "--headless=new", f"--screenshot={out_path}",
         f"--window-size={W},{H}", "--hide-scrollbars", "--force-device-scale-factor=1",
         "--virtual-time-budget=2000", f"file:///{tmp.replace(os.sep, '/')}"],
        capture_output=True, timeout=60)
    os.unlink(tmp)
    if not os.path.exists(out_path):
        sys.exit(f"截图失败：{r.stderr.decode('utf-8', 'replace')[:300]}")


def main():
    idx = load("index.json")
    graph = load("graph.json")
    os.makedirs(OUT, exist_ok=True)
    browser = find_browser()

    # 行业卡片：环节分布
    industries = idx["industryList"]
    print(f"行业 OG 图 × {len(industries)}")
    for ind in industries:
        members = graph["industries"][ind]
        freq = {}
        for tk in members:
            for bi in graph["boardIdxOf"].get(tk, []):
                freq[bi] = freq.get(bi, 0) + 1
        dist = sorted(freq.items(), key=lambda kv: -kv[1])
        top = [(graph["boardList"][bi], n) for bi, n in dist[:5]]
        rest = sum(n for _, n in dist[5:])
        if rest:
            top.append(("其他", rest))
        html = card_html(f"{ind}行业", f"{len(members)} 家上市公司 · {len(dist)} 个产业链环节",
                         top, str(len(members)), "家上市公司")
        shot(browser, html, os.path.join(OUT, f"{ind}.png"))

    # 默认卡片：全行业规模
    segs = [(ind, len(graph["industries"][ind])) for ind in industries[:5]]
    segs.append(("其他", sum(len(graph["industries"][i]) for i in industries[5:])))
    html = card_html("A 股产业链图谱", f"{idx['totals']['companies']} 家上市公司 · "
                                       f"{idx['totals']['industries']} 个行业 · {idx['totals']['boards']} 个环节",
                     segs, str(idx['totals']['companies']), "家上市公司")
    shot(browser, html, os.path.join(OUT, "default.png"))
    print(f"[ok] 写入 {OUT}")


if __name__ == "__main__":
    main()
