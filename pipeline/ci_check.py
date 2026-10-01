# -*- coding: utf-8 -*-
"""CI 数据一致性自检：不联网、不重建，只校验已入库的 data/ 与 pages/ 互相吻合。

用法：python pipeline/ci_check.py  （退出码非 0 = 不通过）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
PAGES = os.path.join(ROOT, "pages")

failures = []


def check(name, cond, detail=""):
    print(f"{'ok ' if cond else 'XX '} {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


idx = load(os.path.join(DATA, "index.json")) or {}
graph = load(os.path.join(DATA, "graph.json")) or {}
chains = load(os.path.join(DATA, "chains.json")) or {}
comp = idx.get("companies", [])

check("index.json 公司数 ≥ 4000", len(comp) >= 4000, str(len(comp)))
check("graph.json 行业数 = 24", len(graph.get("industries", {})) == 24,
      str(len(graph.get("industries", {}))))

fdir = os.path.join(DATA, "f")
ffiles = os.listdir(fdir) if os.path.isdir(fdir) else []
check("data/f/ 行情文件数 = 公司数", len(ffiles) == len(comp),
      f"{len(ffiles)} vs {len(comp)}")

bad_json = 0
simulated = 0
for fn in ffiles:
    try:
        q = load(os.path.join(fdir, fn))
        if not isinstance(q, dict):
            bad_json += 1
        elif q.get("simulated"):
            simulated += 1
    except Exception:
        bad_json += 1
check("f/ 文件全部可解析为 JSON 对象", bad_json == 0, f"损坏 {bad_json}")
check("无模拟行情（入库数据应为真实抓取）", simulated == 0, f"模拟 {simulated}")

links = chains.get("links", {})
edges = sum(len(v.get("u", [])) + len(v.get("d", [])) for v in links.values())
check("chains 边数 > 20000", edges > 20000, str(edges))
conflicts = [t for t, v in links.items()
             if {x[1] for x in v.get("u", [])} & {x[1] for x in v.get("d", [])}]
check("方向冲突 0 例", not conflicts, str(len(conflicts)))

n_company_pages = len([f for f in os.listdir(os.path.join(PAGES, "c")) if f.endswith(".html")]) \
    if os.path.isdir(os.path.join(PAGES, "c")) else 0
n_industry_pages = len([f for f in os.listdir(os.path.join(PAGES, "i")) if f.endswith(".html")]) \
    if os.path.isdir(os.path.join(PAGES, "i")) else 0
check("pages/c 公司页数 = 公司数", n_company_pages == len(comp),
      f"{n_company_pages} vs {len(comp)}")
check("pages/i 行业页数 = 24", n_industry_pages == 24, str(n_industry_pages))

for tk, name in [("300750", "宁德时代"), ("002594", "比亚迪"), ("600519", "贵州茅台")]:
    p = os.path.join(PAGES, "c", f"{tk}.html")
    html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check(f"静态页 {tk} 含公司名", name in html, name)

sm = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(ROOT, "sitemap.xml")) else ""
check("sitemap 地址数 = 1 + 24 + 公司数", sm.count("<url>") == 25 + len(comp),
      str(sm.count("<url>")))

print()
if failures:
    print(f"不通过：{len(failures)} 项 — {failures}")
    sys.exit(1)
print("全部通过")
