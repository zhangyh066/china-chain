# -*- coding: utf-8 -*-
"""链条级披露连线：把 supply.json 里的库内→库内披露边聚合到 27 条链上。

口径：只收"披露方与对手方都在同一条链成员名单里"的边——即链内成员互相
披露的真实客户/供应商关系（年报口径，非推断）。这与 chain_infer 的
validate（方向校验统计）/ suggest（链外候选成员）互补：本产物是链内
可点开看的具体连线，让分层带里的"同链 ≠ 供货"有一个披露级的例外清单。

方向语义：customers 里的对手方 B = A 的客户 → 边 A→B（下游）；
suppliers 里的 B = A 的供应商 → 边 B→A（上游）。rev 反向索引不单独
遍历——每条边都有披露方，披露方在链内即被覆盖。

用法：python build_chain_disclosure.py   （离线，读已提交的 data/ 文件）
产出：data/chain_disclosure.json
  {schemaVersion, generatedAt, sourceNote, chains: {key: {count, edges:[…]}}}
  edge = {from, to, fromName, toName, fromStage, toStage, kind, ratio, year}
  每链按 ratio 降序截断 ≤ CAP 条（count 记截断前的全量数）。
"""
import json
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

CAP = 40          # 每链最多保留的边数（前端只展示前若干条，这里是数据上限）


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    supply = load(os.path.join(DATA, "supply.json"))
    comps = supply.get("companies", {})
    idx = load(os.path.join(DATA, "index.json"))
    names = {c["ticker"]: c["name"] for c in idx["companies"]}

    chains = {}
    for fn in os.listdir(os.path.join(DATA, "chain")):
        if not fn.endswith(".json") or fn == "chain.json":
            continue
        d = load(os.path.join(DATA, "chain", fn))
        if not isinstance(d, dict) or not isinstance(d.get("stages"), list):
            continue
        stage_of = {}
        n_members = 0
        for st in d["stages"]:
            for c in st.get("companies", []):
                tk = c.get("code") if isinstance(c, dict) else c
                if tk and tk not in stage_of:
                    stage_of[tk] = st.get("key", "")
                    n_members += 1
        if n_members:
            chains[d.get("key", fn[:-5])] = stage_of

    out = {}
    n_total = 0
    for key, stage_of in chains.items():
        best = {}
        for a, a_stage in stage_of.items():
            rec = comps.get(a)
            if not rec:
                continue
            # side: 0 = A 自曝客户（对手方在下游）；1 = A 自曝供应商（对手方在上游）
            for side, book in ((0, "customers"), (1, "suppliers")):
                for e in rec.get(book) or []:
                    b = e.get("code")
                    if not b or b not in stage_of or b == a:
                        continue
                    frm, to = (a, b) if side == 0 else (b, a)
                    k = (frm, to)
                    prev = best.get(k)
                    if prev is None or (e.get("ratio") or 0) > (prev.get("ratio") or 0):
                        best[k] = {
                            "from": frm, "to": to,
                            "fromName": names.get(frm, frm), "toName": names.get(to, to),
                            "fromStage": stage_of[frm], "toStage": stage_of[to],
                            "kind": "customer" if side == 0 else "supplier",
                            "ratio": e.get("ratio"),
                            "year": None,
                        }
                # 披露年：明细行的年份在 build_supply 里没有单独存进条目（只进了
                # rev），这里用 rev 边的 year 补——rev 与正向边一一对应（同一笔）
        # 补 year：从被披露方的 rev 里查同一笔边的披露年
        for (frm, to), e in best.items():
            rev = (comps.get(to) or {}).get("rev") or {}
            bucket = rev.get("asSupplierOf" if e["kind"] == "customer" else "asCustomerOf") or []
            # customer 边：frm 把 to 列为客户 → to.rev.asSupplierOf 里有 from=frm
            for r in bucket:
                if r.get("from") == frm and (r.get("ratio") or 0) == (e["ratio"] or 0):
                    e["year"] = r.get("year")
                    break

        edges = sorted(best.values(), key=lambda x: (-(x["ratio"] or 0), x["from"], x["to"]))
        n_total += len(edges)
        out[key] = {"count": len(edges), "edges": edges[:CAP]}

    obj = {
        "schemaVersion": 1,
        "generatedAt": date.today().isoformat(),
        "sourceNote": "上市公司年报披露的前五大客户/供应商明细（学术数据集整理），"
                      "仅收披露方与对手方都在同一链条名单内的边",
        "chains": out,
    }
    path = os.path.join(DATA, "chain_disclosure.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    top = sorted(out.items(), key=lambda kv: -kv[1]["count"])[:8]
    print(f"data/chain_disclosure.json：{len(out)} 条链、链内披露边 {n_total} 条"
          f"（保留上限每链 {CAP}）", flush=True)
    for key, v in top:
        e = v["edges"][0] if v["edges"] else {}
        hint = f"，最重 {e.get('fromName')}→{e.get('toName')}" \
               f" 占营收 {(e.get('ratio') or 0) * 100:.0f}%" if e else ""
        print(f"  {key:<10} {v['count']:>3} 条{hint}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
