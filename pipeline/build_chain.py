# -*- coding: utf-8 -*-
"""
构建全市场产业链图谱的数据层（3889 家）。

取代原来的 build.py（那个只服务 159 家）。

产出：
  data/index.json        4071 家：身份 + 申万一级行业 + 所属产业链环节
                         + 价格/涨跌幅/市值三个轻量字段（首页卡片首帧用）
  data/f/{代码}.json     每家一份完整行情财务（约 2 KB，公司页按需加载）
  data/graph.json        二分图成员表：行业 → 公司、环节 → 公司
  data/{代码}.json       只给有手工供应链的 159 家（其余由前端从 graph.json 推导）

为什么拆成"index 轻量字段 + f/ 按需全量"：
  1.6 MB 的合并 fundamentals.json 里，首页/行业页/环图只用得到每家的
  价格、涨跌幅、市值三个数。把这三个字段并进 index.json（约 +130 KB），
  首屏 2.7 MB → 1.2 MB；完整财务拆成 f/ 下一 Company 页按需各拉一份。

为什么 graph.json 单列一份：
  全景区块要的是"每个行业有哪些公司、每家公司属于哪些环节"，
  这些从 index.json 里也能算，但前端为 3889 家算一遍没必要——
  构建期算好，运行期只读，跟整个项目的思路一致。

用法：python build_chain.py
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
REAL = os.path.join(HERE, "real")
GENERATED_AT = date.today().isoformat()
SCHEMA_VERSION = 2

sys.path.insert(0, HERE)


def board_of(code: str) -> str:
    if code.startswith("688"):
        return "科创板"
    if code.startswith("300"):
        return "创业板"
    if code.startswith(("600", "601", "603", "605")):
        return "沪市主板"
    if code.startswith(("000", "001", "002", "003")):
        return "深市主板"
    return "北交所"


def exchange_of(code: str) -> str:
    return "上交所" if code.startswith(("6", "9")) else "深交所"


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(name, obj, indent=None):
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False,
                  separators=(",", ":") if indent is None else None, indent=indent)
        f.write("\n")
    return os.path.getsize(path)


def main():
    os.makedirs(DATA, exist_ok=True)

    # ---- 读输入 ----
    sel = load_json(os.path.join(REAL, "selected.json"))
    if not sel:
        print("✗ 缺少 real/selected.json，先跑 select_companies.py")
        return 1
    companies = sel["companies"]

    from fetch_real import load_raw, quote_for          # noqa: E402
    from dataset import COMPANIES as CURATED, LINKS     # noqa: E402

    # ---- 行情 ----
    # 数据源暂时不可达、只想改筛选/推断口径重跑时，可设 QUOTES_FILE=<旧版合并文件>
    # 直接沿用其中行情（"某次抓取失败就保留上一版"）。日常管线不设置这个变量。
    global GENERATED_AT
    quotes_override = os.environ.get("QUOTES_FILE")
    if quotes_override:
        cached = load_json(quotes_override) or {}
        quotes = cached.get("quotes", {})
        # "截至日期"以行情缓存的日期为准——重建数据文件不等于数据变新了
        GENERATED_AT = cached.get("generatedAt") or date.today().isoformat()
        no_quote = [c["ticker"] for c in companies if c["ticker"] not in quotes]
        print(f"① 沿用行情缓存 {os.path.basename(quotes_override)}"
              f"（{len(quotes)} 家，截至 {GENERATED_AT}）")
        if no_quote:
            print(f"   缺行情 {len(no_quote)} 家：{no_quote[:5]}")
    else:
        spot, yjbb = load_raw()
        GENERATED_AT = (load_json(os.path.join(REAL, "fundamentals.json")) or {}).get(
            "generatedAt") or date.today().isoformat()
        print("① 组装行情（用缓存，不联网）")
        quotes, no_quote = {}, []
        for c in companies:
            q = quote_for(c["ticker"], spot, yjbb)
            if q:
                quotes[c["ticker"]] = q
            else:
                no_quote.append(c["ticker"])
        print(f"   取到行情 {len(quotes)} / {len(companies)} 家"
              + (f"（缺 {len(no_quote)}：{no_quote[:5]}）" if no_quote else ""))

    # ---- 行业与环节的成员表 ----
    industries, boards = {}, {}
    for c in companies:
        industries.setdefault(c["industry"], []).append(c["ticker"])
        for b in c["boards"]:
            boards.setdefault(b, []).append(c["ticker"])
    # 成员按市值降序，前端画图时默认取前面的，不用自己排
    mc = lambda t: (quotes.get(t) or {}).get("marketCap") or 0        # noqa: E731
    for d in (industries, boards):
        for k in d:
            d[k].sort(key=mc, reverse=True)

    industry_list = sorted(industries, key=lambda k: -len(industries[k]))
    board_list = sorted(boards, key=lambda k: -len(boards[k]))

    # ---- index.json ----
    print("② 写 index.json")
    idx_companies = []
    for c in companies:
        t = c["ticker"]
        q = quotes.get(t) or {}
        idx_companies.append({
            "ticker": t,
            "name": c["name"],
            "industry": c["industry"],
            "boardCount": c["boardCount"],   # 环节名不在这里存，见 graph.json 的 boardIdxOf
            "industryPeers": c["industryPeers"],
            "board": board_of(t),
            "exchange": exchange_of(t),
            "curated": t in {x[0] for x in CURATED},   # 有没有手工供应链
            # 首页/行业页卡片首帧只要这三个数；完整财务在 data/f/ 按需加载
            "price": q.get("price"),
            "changePercent": q.get("changePercent"),
            "marketCap": q.get("marketCap"),
        })

    totals = {
        "companies": len(idx_companies),
        "industries": len(industry_list),
        "boards": len(board_list),
        "edges": sum(c["boardCount"] for c in idx_companies),
        "curated": sum(1 for c in idx_companies if c["curated"]),
    }
    # 口径必须说清四层：哪部分真、哪部分推断、哪部分没有
    disclaimer = (
        f"行情与财务为<b>真实公开数据</b>（东方财富 · akshare，截至 {GENERATED_AT}）；"
        "公司介绍（主营业务、主营构成、工商信息）为<b>真实公开数据</b>"
        "（同花顺 · 巨潮资讯 · 东方财富）；"
        "申万一级行业与产业链环节归属为<b>真实公开归类</b>；"
        "<b>上下游连线为模型推断的模拟数据，未经核实</b>——"
        "「同属一条产业链」不等于「谁给谁供货」。不构成任何投资建议。"
    )
    disclaimer_text = (
        f"行情与财务为真实公开数据（东方财富 · akshare，截至 {GENERATED_AT}）；"
        "公司介绍（主营业务、主营构成、工商信息）为真实公开数据"
        "（同花顺 · 巨潮资讯 · 东方财富）；"
        "申万一级行业与产业链环节归属为真实公开归类；"
        "上下游连线为模型推断的模拟数据，未经核实——"
        "「同属一条产业链」不等于「谁给谁供货」。不构成任何投资建议。"
    )
    size_idx = write_json("index.json", {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": GENERATED_AT,
        "dataSource": "akshare",
        "industryList": industry_list,
        "boardList": board_list,
        "totals": totals,
        "disclaimer": disclaimer,
        "disclaimerText": disclaimer_text,
        "companies": idx_companies,
    })
    print(f"   {size_idx/1024:.0f} KB，{len(idx_companies)} 家，"
          f"{len(industry_list)} 个行业，{len(board_list)} 个环节")

    # ---- data/f/{代码}.json：完整行情财务，公司页按需加载 ----
    print("③ 写 f/ 行情明细")
    fdir = os.path.join(DATA, "f")
    os.makedirs(fdir, exist_ok=True)
    size_f = 0
    for t, q in quotes.items():
        path = os.path.join(fdir, f"{t}.json")
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(q, fp, ensure_ascii=False, separators=(",", ":"))
            fp.write("\n")
        size_f += os.path.getsize(path)
    print(f"   {len(quotes)} 个文件，共 {size_f/1024:.0f} KB")

    # ---- graph.json（二分图成员表）----
    print("④ 写 graph.json")
    # 公司 → 环节索引。名称只在 boardList 里存一份，
    # 否则同一串环节名要在 3889 家公司里各存一遍（index.json 会从 180KB 涨到 918KB）
    board_idx = {b: i for i, b in enumerate(board_list)}
    board_idx_of = {c["ticker"]: [board_idx[b] for b in c["boards"]] for c in companies}
    size_graph = write_json("graph.json", {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": GENERATED_AT,
        "note": "二分图：公司 ↔ 产业链环节。industries/boards 的值是公司代码，按市值降序；boardIdxOf 是公司 → 环节索引。",
        "industryList": industry_list,
        "boardList": board_list,
        "industries": industries,
        "boards": boards,
        "boardIdxOf": board_idx_of,
    })
    print(f"   {size_graph/1024:.0f} KB（行业 {len(industries)} / 环节 {len(boards)}）")

    # ---- 手工供应链的 159 家：每家公司一个文件 ----
    print("⑤ 写手工供应链卡片（159 家）")
    by_code = {c[0]: {"name": c[1]} for c in CURATED}
    sup_of, cus_of = {}, {}
    for sup, cus, role in LINKS:
        sup_of.setdefault(cus, []).append((sup, role))
        cus_of.setdefault(sup, []).append((cus, role))
    sel_of = {c["ticker"]: c for c in companies}
    written = 0
    for code in by_code:
        info = sel_of.get(code)
        if not info:
            continue
        nodes = []

        def push(other, direction, tier, role, extra=None):
            oi = sel_of.get(other)
            node = {
                "id": other, "ticker": other,
                "name": (oi or {}).get("name", other),
                "industry": (oi or {}).get("industry", ""),
                "boards": (oi or {}).get("boards", []),
                "relation": direction, "tier": tier,
                "role": role, "component": role,
            }
            if extra:
                node.update(extra)
            nodes.append(node)

        for other, role in sup_of.get(code, []):
            push(other, "upstream", 1, role)
        for other, role in cus_of.get(code, []):
            push(other, "downstream", 1, role)
        up1 = {s for s, _ in sup_of.get(code, [])}
        down1 = {c for c, _ in cus_of.get(code, [])}
        for s in sorted(up1):
            for other, role in sup_of.get(s, []):
                if other != code and other not in up1 and not any(
                        n["id"] == other and n["relation"] == "upstream" for n in nodes):
                    push(other, "upstream", 2, role, {"via": s})
        for c in sorted(down1):
            for other, role in cus_of.get(c, []):
                if other != code and other not in down1 and not any(
                        n["id"] == other and n["relation"] == "downstream" for n in nodes):
                    push(other, "downstream", 2, role, {"via": c})

        write_json(f"{code}.json", {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": GENERATED_AT,
            "anchor": {
                "ticker": code, "name": info["name"],
                "industry": info["industry"], "boards": info["boards"],
                "board": board_of(code), "exchange": exchange_of(code),
                "fundamentals": None,
            },
            "nodes": nodes,
        })
        written += 1
    print(f"   写了 {written} 个")

    print()
    print("=" * 58)
    print(f"公司            {totals['companies']}")
    print(f"申万一级行业      {totals['industries']}")
    print(f"产业链环节        {totals['boards']}")
    print(f"二分图边数        {totals['edges']}")
    print(f"有手工供应链的     {totals['curated']}")
    print(f"data/ 总大小      {(size_idx+size_f+size_graph)/1024:.0f} KB（不含 159 个卡片）")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
