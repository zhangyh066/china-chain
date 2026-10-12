# -*- coding: utf-8 -*-
"""锂电池产业链深耕产物：手工链条档案 + 阶段等权指数 + 碳酸锂期货行情。

产出：
  data/chain/lithium.json   链条档案 + 阶段趋势：
                            {schemaVersion, generatedAt,
                             stages:[{key,name,desc,companies:[{code,name}]}],
                             trends:{dates:[...], stages:{key:[指数序列]}}}
                            阶段指数复用 build_trends 的等权逻辑（基期 100，
                            停牌前值填充，单日 |r|>30% 剔除）；成员日线缺文件
                            容错跳过，可随 data/h 补抓反复重跑。
  data/price/lithium.json   碳酸锂期货主力日线（akshare LC0，近 250 交易日），
                            与 data/h 同格式 {code 语义换为 name, points}。
                            网络失败时保留旧文件，只 warning 不覆盖。

链条定义为脚本顶部 LITHIUM_STAGES 常量（key/name/desc/代码）。公司名优先从
data/index.json 读（data/p 档案无 name 字段），常量里的手工名仅作兜底；
代码先用 data/p/{code}.json 是否存在校验，缺档案的打印 warning 并剔除。

用法：python build_lithium.py
"""

import json
import os
import sys
from datetime import date

import build_trends as bt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

PRICE_POINTS = 250       # 碳酸锂期货保留的交易日数

# 手工锂电链条定义。companies 为 (代码, 兜底名)；名称以 data/index.json 为准。
# 格林美/华友钴业同时出现在前驱体与回收两个环节，属预期内的重复。
LITHIUM_STAGES = [
    {"key": "upstream_lithium", "name": "上游·锂资源",
     "desc": "锂辉石/盐湖/锂云母采选，碳酸锂、氢氧化锂等锂盐冶炼",
     "companies": [("002460", "赣锋锂业"), ("002466", "天齐锂业"), ("000792", "盐湖股份"),
                   ("002756", "永兴材料"), ("002738", "中矿资源"), ("002176", "江特电机"),
                   ("002192", "融捷股份"), ("300390", "天华新能"), ("002240", "盛新锂能"),
                   ("002497", "雅化集团")]},
    {"key": "cathode", "name": "中游·正极材料",
     "desc": "磷酸铁锂、三元正极材料及前驱体配套",
     "companies": [("300073", "当升科技"), ("688005", "容百科技"), ("300769", "德方纳米"),
                   ("301358", "湖南裕能"), ("688779", "长远锂科"), ("688778", "厦钨新能"),
                   ("688707", "振华新材"), ("688275", "万润新能")]},
    {"key": "anode", "name": "中游·负极材料",
     "desc": "人造石墨、天然石墨负极及硅基负极",
     "companies": [("603659", "璞泰来"), ("600884", "杉杉股份"), ("300035", "中科电气"),
                   ("300890", "翔丰华"), ("001301", "尚太科技")]},
    {"key": "separator", "name": "中游·隔膜",
     "desc": "湿法/干法锂电隔膜及涂覆隔膜",
     "companies": [("002812", "恩捷股份"), ("300568", "星源材质"), ("002080", "中材科技"),
                   ("002108", "沧州明珠")]},
    {"key": "electrolyte", "name": "中游·电解液",
     "desc": "锂离子电池电解液、六氟磷酸锂及添加剂",
     "companies": [("002709", "天赐材料"), ("300037", "新宙邦"), ("002407", "多氟多"),
                   ("002759", "天际股份"), ("603026", "石大胜华")]},
    {"key": "cell", "name": "中游·电芯",
     "desc": "动力与储能电池电芯及 PACK 制造",
     "companies": [("300750", "宁德时代"), ("002594", "比亚迪"), ("300014", "亿纬锂能"),
                   ("002074", "国轩高科"), ("300207", "欣旺达"), ("688567", "孚能科技"),
                   ("300438", "鹏辉能源")]},
    {"key": "equipment", "name": "中游·锂电设备",
     "desc": "涂布机、卷绕机、化成分容等锂电池生产设备",
     "companies": [("300450", "先导智能"), ("688006", "杭可科技"), ("300457", "赢合科技")]},
    {"key": "precursor", "name": "中游·前驱体",
     "desc": "三元前驱体、钴镍资源冶炼与材料一体化",
     "companies": [("300919", "中伟股份"), ("603799", "华友钴业"), ("002340", "格林美")]},
    {"key": "recycling", "name": "回收",
     "desc": "退役动力电池梯次利用与再生回收",
     "companies": [("002340", "格林美"), ("002741", "光华科技"), ("002009", "天奇股份"),
                   ("603799", "华友钴业")]},
]


def load_names():
    """data/index.json → {代码: 公司名}；读不到返回 {}（用手工兜底名）。"""
    try:
        with open(os.path.join(DATA, "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
        return {c["ticker"]: c["name"] for c in idx.get("companies", [])
                if c.get("ticker") and c.get("name")}
    except Exception as e:
        print(f"!! data/index.json 读取失败，公司名全部走手工兜底：{e}")
        return {}


def build_chain(names):
    """校验档案、组装 stages，返回 (stages, 有效代码集合, 剔除代码列表)。"""
    stages = []
    valid, dropped = set(), []
    for st in LITHIUM_STAGES:
        companies = []
        for code, fallback in st["companies"]:
            if not os.path.exists(os.path.join(DATA, "p", f"{code}.json")):
                print(f"!! {code}（{fallback}）缺 data/p 档案，从「{st['name']}」剔除")
                dropped.append(code)
                continue
            companies.append({"code": code, "name": names.get(code) or fallback})
            valid.add(code)
        stages.append({"key": st["key"], "name": st["name"],
                       "desc": st["desc"], "companies": companies})
    return stages, valid, dropped


def build_stage_trends(stages, valid):
    """对每阶段有日线的成员算等权指数；data/h 缺文件的成员容错跳过。

    返回 (trends, covered)：covered = 有日线数据的代码集合（供汇总打印）。
    """
    empty = {"dates": [], "stages": {st["key"]: [] for st in stages}}
    if not os.path.isdir(bt.H_DIR):
        print("!! data/h/ 不存在，trends 输出为空（先跑 fetch_history.py）")
        return empty, set()
    series = bt.load_history(valid)
    if not series:
        print("!! 链条成员暂无日线数据，trends 输出为空")
        return empty, set()
    axis, returns = bt.build_returns(series)
    n = len(axis)
    out = {}
    for st in stages:
        members = [c["code"] for c in st["companies"] if c["code"] in returns]
        out[st["key"]] = bt.index_series(members, returns, n) if members else []
    return {"dates": axis, "stages": out}, set(returns)


def write_price():
    """碳酸锂期货主力日线 → data/price/lithium.json。网络失败保留旧文件。"""
    out_path = os.path.join(DATA, "price", "lithium.json")
    try:
        import akshare as ak
        df = ak.futures_zh_daily_sina(symbol="LC0")
        if df is None or df.empty:
            raise RuntimeError("LC0 返回空数据")
        df = df.tail(PRICE_POINTS)
        points = [[str(d), float(c)] for d, c in zip(df["date"], df["close"])
                  if c == c and float(c) > 0]      # 拦 NaN
        if len(points) < 2:
            raise RuntimeError(f"有效数据点不足：{len(points)}")
    except Exception as e:
        if os.path.exists(out_path):
            print(f"!! 碳酸锂期货抓取失败（{e}），保留旧文件 {out_path}")
        else:
            print(f"!! 碳酸锂期货抓取失败（{e}），暂无旧文件可保留")
        return None
    obj = {"schemaVersion": 1, "generatedAt": date.today().isoformat(),
           "name": "碳酸锂期货主力", "points": points}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return obj


def main():
    generated = date.today().isoformat()
    names = load_names()
    stages, valid, dropped = build_chain(names)
    trends, covered = build_stage_trends(stages, valid)

    chain_obj = {"schemaVersion": 1, "generatedAt": generated,
                 "stages": stages, "trends": trends}
    chain_path = os.path.join(DATA, "chain", "lithium.json")
    os.makedirs(os.path.dirname(chain_path), exist_ok=True)
    with open(chain_path, "w", encoding="utf-8") as f:
        json.dump(chain_obj, f, ensure_ascii=False, separators=(",", ":"))

    price_obj = write_price()

    # 汇总
    print("\n各阶段成员（有效档案 / 其中有日线）：")
    for st in stages:
        n_hist = sum(1 for c in st["companies"] if c["code"] in covered)
        print(f"  {st['key']:<18} {st['name']:<10} "
              f"{len(st['companies']):>2} 家 / {n_hist:>2} 家有日线，"
              f"指数序列 {len(trends['stages'].get(st['key'], []))} 天")
    if dropped:
        print(f"被剔除代码（缺 data/p 档案）：{dropped}")
    print(f"trends 日期轴 {len(trends['dates'])} 天"
          + (f"（{trends['dates'][0]} ~ {trends['dates'][-1]}）" if trends["dates"] else ""))
    print(f"chain/lithium.json {os.path.getsize(chain_path)/1024:.1f} KB")
    price_path = os.path.join(DATA, "price", "lithium.json")
    if price_obj:
        print(f"price/lithium.json {os.path.getsize(price_path)/1024:.1f} KB，"
              f"{len(price_obj['points'])} 个点，最新 {price_obj['points'][-1][0]}")
    elif os.path.exists(price_path):
        print(f"price/lithium.json 沿用旧文件 {os.path.getsize(price_path)/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
