# -*- coding: utf-8 -*-
"""披露边校验与推断链条位置：data/supply.json 披露边 × data/chain/ 八链 →
data/chain_infer.json。

全程离线，只读本地产物，不做任何网络请求。

边模型：supply.json 正向明细（customers/suppliers，code 非空）统一规范为
"供应商 → 客户"方向去重（同向重复披露取 ratio 最大）；year 从反向索引 rev
对碰取（正向条目本身无 year 字段——被 hub 截断未进 rev 的边 year=null，
如实标注）。反向边与正向同源，不重复计数。

三块产物：
  ① validate：两端同链的边，按链序判方向——from 阶段序 < to 阶段序 =
     consistent（与链序一致），相等 = sameStage，逆序 = conflict。矛盾案例
     单独全量列出（可能是我方手工归错阶段，也可能是真实但反直觉的披露，
     如实呈现不粉饰）。注意链序是机械应用（如 semi 的设备/材料排在制造
     之后、lithium 的前驱体排在电芯之后），由此产生的"矛盾"属口径产物。
  ② suggest：不在链中的公司，披露边指向链内成员且 ratio≥0.05 时推断其
     链条位置——我是对方供应商 → 对方上游相邻阶段（supplies_to）；我是
     对方客户 → 下游相邻阶段（buys_from）。越界（链首之上/链尾之下）归到
     链首/尾阶段并标 note="链外延伸"。每家公司每条链只留 ratio 最大的
     一条证据，每链按 ratio 降序截 ≤20。
  ③ links：两端分属不同链（无共同链）的边，逐对链组合输出，ratio 降序
     ≤30。

用法：python build_chain_infer.py
"""

import glob
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

SUGGEST_MIN_RATIO = 0.05
SUGGEST_CAP = 20
LINKS_CAP = 30
CONFLICTS_CAP = 50


def load_chains():
    """八链 → {chainKey: [stage...]} 与成员映射 {code: {chainKey: (stageIdx, stageKey)}}。
    同一公司在同链多阶段出现时取第一次（链序更靠前）。"""
    chains = {}
    mem = {}
    for f in sorted(glob.glob(os.path.join(DATA, "chain", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        if not (isinstance(d, dict) and "stages" in d):
            continue
        key = d["key"]
        chains[key] = d["stages"]
        for i, st in enumerate(d["stages"]):
            for c in st["companies"]:
                mem.setdefault(c["code"], {}).setdefault(key, (i, st["key"]))
    return chains, mem


def load_edges(comps):
    """supply.json → {(A供应商, B客户): {ratio, amount, year}}，ratio 取最大。"""
    edges = {}

    def add(a, b, ratio, amount):
        if not a or not b or a == b:
            return
        key = (a, b)
        cur = edges.get(key)
        if cur is None or (ratio or 0) > (cur["ratio"] or 0):
            edges[key] = {"ratio": ratio, "amount": amount, "year": None}

    for code, node in comps.items():
        for e in node.get("customers", []):
            add(code, e.get("code"), e.get("ratio"), e.get("amount"))
        for e in node.get("suppliers", []):
            add(e.get("code"), code, e.get("ratio"), e.get("amount"))

    yeared = 0
    for code, node in comps.items():
        r = node.get("rev")
        if not r:
            continue
        for e in r.get("asSupplierOf", []):     # from 把 code 列为客户 → from 供应 code
            k = (e["from"], code)
            if k in edges:
                edges[k]["year"] = e.get("year")
                yeared += 1
        for e in r.get("asCustomerOf", []):     # from 把 code 列为供应商 → code 供应 from
            k = (code, e["from"])
            if k in edges:
                edges[k]["year"] = e.get("year")
                yeared += 1
    return edges, yeared


def main():
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    name_of = {c["ticker"]: c["name"] for c in idx["companies"]}
    supply = json.load(open(os.path.join(DATA, "supply.json"), encoding="utf-8"))
    comps = supply["companies"]
    chains, mem = load_chains()
    edges, yeared = load_edges(comps)

    # ---------------------------------------------------------------- ① validate
    per = {k: {"consistent": 0, "sameStage": 0, "conflict": 0,
               "examples": {"consistent": [], "sameStage": [], "conflict": []}}
           for k in chains}
    total = {"consistent": 0, "sameStage": 0, "conflict": 0}
    conflicts = []
    # ---------------------------------------------------------------- ③ links
    links = []
    # ---------------------------------------------------------------- ② suggest
    cand = {k: {} for k in chains}   # chainKey -> code -> evidence

    for (a, b), ev in sorted(edges.items()):
        ratio, year = ev["ratio"], ev["year"]
        ca, cb = mem.get(a, {}), mem.get(b, {})
        shared = set(ca) & set(cb)
        if shared:
            for ch in sorted(shared):
                ia, sa = ca[ch]
                ib, sb = cb[ch]
                cls = ("consistent" if ia < ib
                       else "sameStage" if ia == ib else "conflict")
                rec = {"from": a, "to": b, "fromStage": sa, "toStage": sb,
                       "ratio": ratio, "year": year}
                per[ch][cls] += 1
                total[cls] += 1
                if len(per[ch]["examples"][cls]) < 3:
                    per[ch]["examples"][cls].append(rec)
                if cls == "conflict":
                    conflicts.append({"chain": ch, **rec})
        else:
            for ka, (ia, sa) in ca.items():
                for kb, (ib, sb) in cb.items():
                    if ka != kb:
                        links.append({"fromChain": ka, "fromStage": sa,
                                      "toChain": kb, "toStage": sb,
                                      "code": a, "name": name_of.get(a),
                                      "ratio": ratio, "year": year})

        if ratio is not None and ratio >= SUGGEST_MIN_RATIO:
            for ch, stages in chains.items():
                if b in mem and ch in mem[b] and not (a in mem and ch in mem[a]):
                    # a 是 b 的供应商 → a 在 b 上游相邻阶段
                    ib, _sb = mem[b][ch]
                    ext = ib - 1 < 0
                    si = max(ib - 1, 0)
                    evd = {"stage": stages[si]["key"],
                           "via": {"to": b, "toName": name_of.get(b),
                                   "relation": "supplies_to",
                                   "ratio": ratio, "year": year}}
                    if ext:
                        evd["note"] = "链外延伸"
                    cur = cand[ch].get(a)
                    if cur is None or ratio > cur["via"]["ratio"]:
                        cand[ch][a] = evd
                if a in mem and ch in mem[a] and not (b in mem and ch in mem[b]):
                    # b 是 a 的客户 → b 在 a 下游相邻阶段
                    ia, _sa = mem[a][ch]
                    ext = ia + 1 >= len(stages)
                    si = min(ia + 1, len(stages) - 1)
                    evd = {"stage": stages[si]["key"],
                           "via": {"to": a, "toName": name_of.get(a),
                                   "relation": "buys_from",
                                   "ratio": ratio, "year": year}}
                    if ext:
                        evd["note"] = "链外延伸"
                    cur = cand[ch].get(b)
                    if cur is None or ratio > cur["via"]["ratio"]:
                        cand[ch][b] = evd

    suggest = {}
    n_suggest = 0
    for ch, m in cand.items():
        rows = sorted(({"code": c, "name": name_of.get(c), **ev}
                       for c, ev in m.items()),
                      key=lambda r: -r["via"]["ratio"])[:SUGGEST_CAP]
        suggest[ch] = rows
        n_suggest += len(rows)

    links.sort(key=lambda r: -(r["ratio"] or 0))
    n_links_raw = len(links)
    links = links[:LINKS_CAP]

    obj = {
        "schemaVersion": 1, "generatedAt": date.today().isoformat(),
        "edgeCount": len(edges), "yearedEdges": yeared,
        "validate": {"total": total, "chains": per},
        "conflicts": conflicts[:CONFLICTS_CAP],
        "conflictCount": len(conflicts),
        "suggest": suggest,
        "links": links,
        "linkCount": n_links_raw,
    }
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    out = os.path.join(DATA, "chain_infer.json")
    with open(out, "w", encoding="utf-8") as f:
        f.write(payload)

    print(f"披露边 {len(edges)} 条（带 year {yeared}）", flush=True)
    print(f"validate 全库：一致 {total['consistent']} / 同环 {total['sameStage']}"
          f" / 矛盾 {total['conflict']}", flush=True)
    for ch in chains:
        p = per[ch]
        n = p["consistent"] + p["sameStage"] + p["conflict"]
        if n:
            print(f"  {ch:9s} 边{n:3d}：一致{p['consistent']:3d} "
                  f"同环{p['sameStage']:3d} 矛盾{p['conflict']:3d}", flush=True)
    print(f"矛盾案例 {len(conflicts)} 条（产物存前 {CONFLICTS_CAP} 条）", flush=True)
    for c in conflicts[:5]:
        print(f"  ⚠ {c['chain']}: {c['from']}({name_of.get(c['from'])})"
              f"[{c['fromStage']}] → {c['to']}({name_of.get(c['to'])})"
              f"[{c['toStage']}] ratio={c['ratio']} year={c['year']}", flush=True)
    print(f"suggest 候选 {n_suggest} 条（"
          + ", ".join(f"{k}:{len(v)}" for k, v in suggest.items() if v) + "）",
          flush=True)
    print(f"links 跨链边 {n_links_raw} 条，存 top{len(links)}", flush=True)
    print(f"data/chain_infer.json：{os.path.getsize(out)/1024:.0f} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
