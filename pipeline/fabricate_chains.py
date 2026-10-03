# -*- coding: utf-8 -*-
"""
按显式产业链步进表**推断**公司的上下游 → data/chains.json

⚠️ 这是全站唯一"编"出来的关系数据，必须时刻标注。

编法：
  1. 人写一张「产业链步进表」——逐条写明"哪个行业是哪个行业的上游"
  2. 只在**共享同一个产业链环节**的公司之间，沿这些步进连上下游
  3. 取方向上**市值最大的几家**（不用随机抽样）
  4. 没有跨行业同环节候选的，退回"按步进表 + 同行业"取最大的几家

为什么不用"给行业排个总序"：试过——结果是迈瑞医疗的上游配到美的集团、
比亚迪的下游配到格力电器，方向性错误，给懂行的人一眼看穿。
根因是行业之间不是一条直线，而是一张网，必须逐条写。

输出刻意做小：只存 [环节索引, 公司代码, 角色]，名字由前端从 index.json 查。

用法：../.venv/Scripts/python.exe fabricate_chains.py
"""

import json
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

MAX_UP = 4
MAX_DOWN = 4
INF_SIZE = 10 ** 9   # 兜底路径没有共享环节，"环节有多具体"这一维不参与比较

# ⚠️ 这张表是**人写的假设**，不是数据。
# 收益是每一步单独看都站得住；代价是它仍然只是推断。
CHAIN_STEPS = [
    # 资源 → 材料
    ("农林牧渔", "食品饮料", "农产品原料"),
    ("农林牧渔", "基础化工", "农产品原料"),
    ("农林牧渔", "纺织服饰", "棉麻皮张原料"),
    ("煤炭", "公用事业", "动力煤"),
    ("煤炭", "钢铁", "焦煤"),
    ("煤炭", "基础化工", "煤化工原料"),
    ("石油石化", "基础化工", "石化原料"),
    ("有色金属", "钢铁", "合金原料"),
    ("有色金属", "电子", "金属材料"),
    ("有色金属", "电力设备", "锂钴镍材料"),
    ("有色金属", "汽车", "铝合金件"),
    ("有色金属", "建筑材料", "金属型材"),
    # 材料 → 器件 / 整机
    ("钢铁", "机械设备", "钢材"),
    ("钢铁", "汽车", "汽车板材"),
    ("钢铁", "建筑装饰", "建筑钢材"),
    ("基础化工", "电子", "电子化学品"),
    ("基础化工", "电力设备", "电池材料"),
    ("基础化工", "医药生物", "医药中间体"),
    ("基础化工", "纺织服饰", "化纤原料"),
    ("基础化工", "家用电器", "塑料与涂料件"),
    ("基础化工", "食品饮料", "食品添加剂"),
    ("基础化工", "汽车", "车用材料"),
    ("基础化工", "轻工制造", "化工原料"),
    ("建筑材料", "建筑装饰", "建材"),
    ("轻工制造", "食品饮料", "包装"),
    ("轻工制造", "家用电器", "结构件"),
    ("轻工制造", "电子", "结构件"),
    ("纺织服饰", "汽车", "内饰面料"),
    ("纺织服饰", "家用电器", "配套件"),
    # 器件 → 整机（注意方向：设备厂是制造厂的上游）
    ("机械设备", "电子", "半导体设备"),
    ("机械设备", "电力设备", "锂电光伏设备"),
    ("机械设备", "汽车", "产线装备"),
    ("机械设备", "国防军工", "军工装备"),
    ("机械设备", "医药生物", "医药装备"),
    ("电子", "通信", "芯片与元器件"),
    ("电子", "计算机", "芯片与部件"),
    ("电子", "汽车", "汽车电子"),
    ("电子", "家用电器", "控制芯片"),
    ("电子", "国防军工", "军用电子"),
    ("电子", "机械设备", "工控元件"),
    ("电力设备", "汽车", "动力电池"),
    ("电力设备", "公用事业", "发电输配电设备"),
    ("电力设备", "机械设备", "电控部件"),
    ("通信", "计算机", "网络设备"),
    ("计算机", "汽车", "智能驾驶软件"),
    ("计算机", "机械设备", "工业软件"),
    # 配套与终端
    ("公用事业", "基础化工", "电力"),
    ("公用事业", "有色金属", "电力"),
    ("环保", "基础化工", "环保处理"),
    ("环保", "公用事业", "环保工程"),
    # 美容护理的上游是化妆品原料 —— 走基础化工，而不是"食品饮料/医药"
    # （初版写成了 食品饮料→美容护理、医药→美容护理，语义牵强，实测抽出来很怪）
    ("基础化工", "美容护理", "化妆品原料"),
    # ("汽车", "交通运输", "整车") 已删除：现行 24 个申万一级行业里不含"交通运输"，
    # 汽车在该口径下没有行业级下游（终端市场在步进表之外），位置图会如实显示终端市场。
    ("家用电器", "建筑装饰", "家电配套"),
]

UP_OF = defaultdict(list)      # 行业 → [(上游行业, 角色)]
DOWN_OF = defaultdict(list)    # 行业 → [(下游行业, 角色)]
for _up, _down, _role in CHAIN_STEPS:
    UP_OF[_down].append((_up, _role))
    DOWN_OF[_up].append((_down, _role))


def main():
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    graph = json.load(open(os.path.join(DATA, "graph.json"), encoding="utf-8"))
    # 市值排序用真实行情的 marketCap。data/ 下已无合并行情文件
    # （已拆成 index.json 轻量字段 + data/f/ 按需全量），marketCap 就在
    # index.json 的公司条目里，不用再开一份数据源
    mc_of = {c["ticker"]: c.get("marketCap") or 0 for c in idx["companies"]}

    board_members = graph["boards"]
    board_idx_of = graph["boardIdxOf"]
    industry_of = {c["ticker"]: c["industry"] for c in idx["companies"]}
    in_graph = set(industry_of)

    # 按行业分桶、桶内按市值降序 —— 兜底路径要取"这个行业最大的几家"
    by_industry = defaultdict(list)
    for c in idx["companies"]:
        by_industry[c["industry"]].append(c["ticker"])
    for k in by_industry:
        by_industry[k].sort(key=lambda t: -mc_of.get(t, 0))

    # 环节成员按行业分桶，避免每次都遍历全量成员
    board_by_industry = {}
    for bname, members in board_members.items():
        m = defaultdict(list)
        for t in members:
            m[industry_of.get(t, "")].append(t)
        board_by_industry[bname] = m

    links, no_link = {}, []

    for c in idx["companies"]:
        t, my_ind = c["ticker"], c["industry"]
        mine = board_idx_of.get(t) or []
        ups, downs = {}, {}

        def add(pool, other, role, shared, size):
            """累积证据，而不是"先到先得"。

            同一对公司可能从多个环节算到关系，而且方向可能相反 ——
            步进表里 `机械设备→电子（半导体设备）` 和 `电子→机械设备（工控元件）`
            两条都成立，于是当两家同时共享"机器人概念"和"半导体概念"时，
            会既被算成上游又被算成下游。实测宇树科技的上下游名单里
            曾经同时出现工业富联/立讯精密/兆易创新，一眼就是错的。

            所以这里把"支持这个方向的共享环节数"和"最具体的那个环节有多大"都攒下来，
            等两个方向都收齐之后一次性裁决（见下面的 resolve_direction）。
            """
            if other == t or other not in in_graph:
                return
            cur = pool.get(other)
            if cur is None:
                pool[other] = [role, 1 if shared else 0, size]
            else:
                if shared:
                    cur[0] = role                                   # 用最后一个环节的角色名
                    cur[1] += 1                                     # 支持这个方向的证据 +1
                    cur[2] = min(cur[2], size)                      # 记住最具体的那个环节

        # ① 主路径：共享环节 + 步进表
        for bi in mine:
            bname = graph["boardList"][bi]
            bucket = board_by_industry.get(bname, {})
            size = len(board_members.get(bname, []))     # 环节越小越具体，证据越硬
            for up_ind, role in UP_OF.get(my_ind, []):
                for other in bucket.get(up_ind, []):
                    add(ups, other, role, True, size)
            for down_ind, role in DOWN_OF.get(my_ind, []):
                for other in bucket.get(down_ind, []):
                    add(downs, other, role, True, size)

        # ② 兜底：没有跨行业同环节的候选时，按步进表 + 同行业取最大的两家
        if not ups:
            for up_ind, role in UP_OF.get(my_ind, []):
                for other in by_industry.get(up_ind, [])[:2]:
                    add(ups, other, role, False, INF_SIZE)
        if not downs:
            for down_ind, role in DOWN_OF.get(my_ind, []):
                for other in by_industry.get(down_ind, [])[:2]:
                    add(downs, other, role, False, INF_SIZE)

        # 裁决方向冲突：同一家公司只能出现在一边。
        # 先看谁的支持环节多，同样多看谁的环节更具体，再平就放弃这条边 ——
        # 宁可少一条边，也不要"既是上游又是下游"这种自相矛盾。
        for other in list(set(ups) & set(downs)):
            eu, ed = ups[other][1], downs[other][1]
            su, sd = ups[other][2], downs[other][2]
            if (eu, -su) > (ed, -sd):
                downs.pop(other)
            elif (ed, -sd) > (eu, -su):
                ups.pop(other)
            else:
                ups.pop(other)
                downs.pop(other)

        def pick(pool, limit):
            items = sorted(pool.items(), key=lambda kv: (not kv[1][1],
                                                         -mc_of.get(kv[0], 0)))
            out = []
            for other, (role, _evidence, _size) in items[:limit]:
                # 共同环节存在的话带上它的索引，前端可以显示环节名
                role_bi = next((bi for bi in (board_idx_of.get(other) or []) if bi in mine), None)
                if role_bi is None:
                    role_bi = mine[0] if mine else 0
                out.append([role_bi, other, role])
            return out

        u, d = pick(ups, MAX_UP), pick(downs, MAX_DOWN)
        if u or d:
            entry = {}
            if u:
                entry["u"] = u
            if d:
                entry["d"] = d
            links[t] = entry
        else:
            no_link.append(t)

    with open(os.path.join(DATA, "chains.json"), "w", encoding="utf-8") as f:
        json.dump({
            "schemaVersion": 2,
            # 连线的数据日期跟随 index.json（行情缓存是哪天抓的，推断就基于哪天），
            # 而不是生成脚本运行的当天
            "generatedAt": idx.get("generatedAt") or date.today().isoformat(),
            "source": "inferred",
            "note": "上下游关系为模型按产业链步进表 + 环节归属推断的模拟数据，未经任何核实，"
                    "仅用于示意产业链结构，不代表真实的供货关系。",
            "maxUp": MAX_UP,
            "maxDown": MAX_DOWN,
            "steps": [[a, b, r] for a, b, r in CHAIN_STEPS],
            "links": links,
        }, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    size = os.path.getsize(os.path.join(DATA, "chains.json"))
    nu = sum(len(v.get("u", [])) for v in links.values())
    nd = sum(len(v.get("d", [])) for v in links.values())
    print(f"[ok] {len(links)} 家有上下游 → data/chains.json（{size/1024:.0f} KB）")
    print(f"  边数 {nu + nd}（上游 {nu} / 下游 {nd}），平均每家 {(nu+nd)/max(1,len(links)):.1f} 条")
    print(f"  步进表 {len(CHAIN_STEPS)} 条")
    if no_link:
        print(f"⚠ {len(no_link)} 家编不出：{no_link[:6]}")


if __name__ == "__main__":
    main()
