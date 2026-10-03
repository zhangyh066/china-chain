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

# chains.json 的推断连线已从界面撤下（仅存档）；UI 依赖的是行业级 chain_steps.json
steps = (load(os.path.join(DATA, "chain_steps.json")) or {}).get("steps", [])
check("chain_steps 步进表条数 40~80", 40 <= len(steps) <= 80, str(len(steps)))
inds = set(idx.get("industryList", []))
bad = [(u, d) for u, d, _ in steps if u not in inds or d not in inds]
check("chain_steps 两端都是 24 个申万行业内", not bad, str(bad[:5]))

n_company_pages = len([f for f in os.listdir(os.path.join(PAGES, "c")) if f.endswith(".html")]) \
    if os.path.isdir(os.path.join(PAGES, "c")) else 0
n_industry_pages = len([f for f in os.listdir(os.path.join(PAGES, "i")) if f.endswith(".html")]) \
    if os.path.isdir(os.path.join(PAGES, "i")) else 0
check("pages/c 公司页数 = 公司数", n_company_pages == len(comp),
      f"{n_company_pages} vs {len(comp)}")
check("pages/i 行业页数 = 24", n_industry_pages == 24, str(n_industry_pages))

# 公司介绍（data/p/，pipeline/fetch_profiles.py 的产出）：应全量覆盖公司数
pdir = os.path.join(DATA, "p")
pfiles = os.listdir(pdir) if os.path.isdir(pdir) else []
check("data/p/ 公司介绍已生成", len(pfiles) == len(comp),
      f"{len(pfiles)} vs {len(comp)}")
if pfiles:
    sample = load(os.path.join(pdir, "300750.json")) or {}
    check("公司介绍含主营业务", bool(sample.get("business")), sample.get("ticker", "?"))
    # Python 的 json.dump 会把 NaN 写成字面量——浏览器 JSON.parse 直接炸，必须拦住
    nan_files = []
    for fn in pfiles[:]:
        with open(os.path.join(pdir, fn), encoding="utf-8") as fh:
            if "NaN" in fh.read() or "Infinity" in fh.read():
                nan_files.append(fn)
    check("data/p/ 无 NaN/Infinity 字面量", not nan_files,
          f"{len(nan_files)} 个文件污染：{nan_files[:3]}")

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
