# -*- coding: utf-8 -*-
"""为全部 4,071 家公司生成产业链档案（写入 data/chain/chain.json）。

数据来源（全部是仓库里已有的真实数据，不联网、不编造）：
  - 行业：data/index.json 的 industry（申万一级行业）
  - 产业链位置：data/graph.json 的 boardIdxOf（该公司所属的产业链环节清单），
    按"环节在行业内的公司数"从大到小取前 4 个举例
  - 已建档的示例公司（demo=true）保持原样——它们有人工写的简介与设备，不被覆盖

缺失字段（公司简介 / 代表性设备 / 营收产值）一律不编造，
由前端统一显示「待接入具体数据接口」，等批量数据源接入后由本脚本重新生成。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CHAIN = os.path.join(DATA, "chain", "chain.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    idx = load(os.path.join(DATA, "index.json"))
    graph = load(os.path.join(DATA, "graph.json"))
    chain = load(CHAIN)

    companies = idx["companies"]
    board_names = graph["boardList"]
    board_idx_of = graph["boardIdxOf"]
    # 行业内环节规模：用于把公司"主要落在哪几个环节"举例得有依据
    board_size = {b: len(v) for b, v in graph["boards"].items()}

    kept_demo = 0
    generated = 0
    profiles = {}

    for c in companies:
        tk = c["ticker"]
        old = chain.get("companies", {}).get(tk)
        if old:
            # 已建档（示例或人工）的公司保持原样，不覆盖
            profiles[tk] = old
            kept_demo += 1
            continue

        boards = [board_names[i] for i in board_idx_of.get(tk, [])]
        if boards:
            # 举例的环节按"该环节在本行业的公司数"排序，取前 4 个
            in_ind = (graph.get("industries") or {}).get(c.get("industry", ""), [])
            sized = sorted(boards, key=lambda b: -(board_size.get(b, 0)))
            main = "、".join(sized[:4])
            pos = (f"申万一级行业「{c.get('industry', '')}」；"
                   f"主要落在 {len(boards)} 个产业链环节（{main} 等）")
        else:
            pos = f"申万一级行业「{c.get('industry', '')}」；暂未归入已收录的产业链环节"
            main = None
        profiles[tk] = {
            "name": c["name"],
            "chain_position": pos,
            "output_value": {"status": "pending_interface", "value": None,
                             "currency": "CNY", "unit": "亿元", "year": None, "source": None},
            "_main_boards": main,   # 内部字段：给后续"代表设备"批量补齐时参考
        }
        generated += 1

    # 行业档案：全部 24 个行业都生成（简介缺 → 前端占位；产业链位置用真实数据生成）
    industries = dict(chain.get("industries", {}))
    for ind in graph.get("industryList", []):
        if ind in industries:
            continue
        members = (graph.get("industries") or {}).get(ind, [])
        from collections import Counter
        cnt = Counter()
        for tk in members:
            for i in board_idx_of.get(tk, []):
                cnt[board_names[i]] += 1
        top = [name for name, _n in cnt.most_common(5)]
        industries[ind] = {
            "chain_position": ("公司主要落在：" + "、".join(top) + f" 等 {len(cnt)} 个产业链环节")
            if top else "暂未归入已收录的产业链环节",
            "output_value": {"status": "pending_interface", "value": None,
                             "currency": "CNY", "unit": "亿元", "year": None, "source": None},
        }

    # 未上市主体与设备实体原样保留
    out = dict(chain)
    out["companies"] = profiles
    out["industries"] = industries
    out["generatedAt"] = __import__("datetime").date.today().isoformat()
    out["note"] = ("产业链档案（行业/公司/设备三级）。公司档案已覆盖全部 "
                   f"{len(profiles)} 家（其中 {kept_demo} 家为人工/示例档案）。"
                   "缺失字段由前端统一显示「待接入具体数据接口」。")

    with open(CHAIN, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print(f"✓ 公司档案：保留人工/示例 {kept_demo} 家，新生成 {generated} 家，合计 {len(profiles)} 家")
    orphan = sum(1 for tk, p in profiles.items() if p.get("_main_boards") is None and not p.get("chain_position"))
    print(f"  其中未归入任何环节的公司：{orphan} 家（产业链位置会如实说明）")
    if len(profiles) != len(companies):
        print(f"  ✗ 数量与 index.json 不一致（{len(companies)}），请检查")
        sys.exit(2)


if __name__ == "__main__":
    main()
