# -*- coding: utf-8 -*-
"""
构建期管线：把 dataset.py 里的源数据 → data/*.json

设计要点（照搬原站思路）：
  构建期把所有推导工作做完（上下游一/二级展开、行业归属、财务数字），
  运行期前端只做"读 JSON + 画图"，不做任何计算。

用法：python pipeline/build.py
"""

import json
import os
import re
from datetime import date

from dataset import SECTORS, COMPANIES, LINKS, FEATURED, FEATURED_NAME

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HERE = os.path.dirname(os.path.abspath(__file__))
GENERATED_AT = date.today().isoformat()
SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# 模拟财务：固定种子，保证每次跑出来的数字一样（可复现）
# --------------------------------------------------------------------------
def rng_for(key: str):
    """由字符串派生的确定性伪随机（mulberry32），不用 random 模块以免受全局状态影响。"""
    s = 0
    for ch in key:
        s = (s * 131 + ord(ch)) & 0xFFFFFFFF
    state = [s or 0x9E3779B9]

    def nxt():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        x = state[0]
        x = (x ^ (x >> 15)) * (1 | x) & 0xFFFFFFFF
        x = (x + ((x ^ (x >> 7)) * (61 | x) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((x ^ (x >> 14)) & 0xFFFFFFFF) / 4294967296

    return nxt


# 各行业模拟区间：(股价下限, 股价上限, 市值下限亿, 市值上限亿, 毛利率区间%, 营收增速区间%)
# 后两项已被"市值 ÷ 股本"的算法取代，标记为未用；市值上限按各行业真实龙头量级收口，
# 避免随机抽到"一家调味品公司市值 1.8 万亿"这种一眼假的数字。
SECTOR_SIM = {
    0: (0, 0, 150, 4000, (18, 46), (-12, 75)),      # 电子
    1: (0, 0, 150, 6000, (16, 34), (-18, 55)),      # 电力设备
    2: (0, 0, 120, 3500, (28, 88), (-8, 40)),       # 医药生物
    3: (0, 0, 150, 4000, (12, 26), (-10, 90)),      # 汽车
    4: (0, 0, 80, 2000, (35, 72), (-15, 45)),       # 计算机
    5: (0, 0, 80, 2000, (18, 38), (-12, 50)),       # 通信
    6: (0, 0, 80, 1500, (22, 40), (-14, 42)),       # 机械设备
    7: (0, 0, 150, 3000, (10, 28), (-20, 60)),      # 有色金属
    8: (0, 0, 100, 2000, (12, 32), (-16, 48)),      # 基础化工
    9: (0, 0, 150, 5000, (26, 91), (-6, 26)),       # 食品饮料
    10: (0, 0, 120, 3000, (20, 34), (-10, 35)),     # 家用电器
}

# 少量知名公司的市值给一个贴近直觉的量级（其余按行业区间随机）
CAP_HINT = {
    "600519": 18600, "300750": 10500, "002594": 8200, "601899": 5600,
    "000333": 5200, "600309": 2400, "002475": 2600, "688981": 6300,
    "600276": 3100, "000858": 4600, "603259": 1800, "300760": 2900,
    "601138": 4200, "600887": 1700, "600690": 2500, "601012": 1200,
    "600031": 1500, "000651": 2400, "601633": 2100, "600104": 1700,
    "002371": 2400, "603501": 1500, "603986": 1000, "300308": 1600,
    "000063": 1600, "300059": 3600, "002230": 1200, "000568": 2000,
    "600809": 2100, "603288": 2000, "600660": 1400, "000338": 1300,
    "603993": 1800, "600111": 900, "300124": 1500, "002050": 1100,
    "002714": 2500, "300498": 1200, "601127": 2000, "601238": 900,
}


# 总股本（亿股）。给出市值后由它反推股价，保证"市值 ÷ 股本 = 股价"三个数字互相自洽，
# 不会出现"市值一万亿、股价五十块"这种一眼假的组合。
SHARES_HINT = {
    "600519": 12.56, "300750": 44.0, "002594": 29.1, "601899": 265.0,
    "000333": 76.6, "600309": 31.4, "002475": 72.5, "688981": 79.8,
    "600276": 63.8, "000858": 38.8, "603259": 29.0, "300760": 12.1,
    "601138": 198.6, "600887": 63.6, "600690": 94.5, "601012": 75.8,
    "600031": 84.8, "000651": 56.3, "601633": 85.6, "600104": 115.8,
    "002371": 5.31, "603501": 12.2, "603986": 6.66, "300308": 11.2,
    "000063": 47.8, "300059": 158.0, "002230": 23.1, "000568": 14.7,
    "600809": 12.2, "603288": 55.6, "600660": 26.1, "000338": 87.2,
    "603993": 216.0, "600111": 36.3, "300124": 26.8, "002050": 37.3,
    "002714": 54.6, "300498": 66.5, "601127": 15.1, "601238": 104.7,
}

# 少数公司的毛利率 / 净利率给一个贴近常识的量级。
# 为什么需要：随机生成虽然内部自洽，但"茅台毛利率 52%"这种数字
# 对金融读者来说一眼就假——演示的可信度会被这几家最知名的公司毁掉。
MARGIN_HINT = {
    "600519": (92.0, 52.0),   # 贵州茅台
    "000858": (75.5, 37.0),   # 五粮液
    "000568": (88.0, 43.0),   # 泸州老窖
    "600809": (75.0, 31.0),   # 山西汾酒
    "603288": (37.0, 25.0),   # 海天味业
    "600276": (85.0, 22.0),   # 恒瑞医药
    "600436": (48.0, 30.0),   # 片仔癀
    "300760": (64.0, 32.0),   # 迈瑞医疗
    "603259": (41.0, 22.0),   # 药明康德
    "000333": (26.0, 9.0),    # 美的集团
    "000651": (30.0, 12.0),   # 格力电器
    "600887": (33.0, 8.0),    # 伊利股份
    "601899": (15.0, 8.0),    # 紫金矿业
    "600309": (17.0, 10.0),   # 万华化学
    "002475": (12.0, 5.0),    # 立讯精密
    "002594": (20.0, 5.0),    # 比亚迪
    "300750": (22.0, 10.0),   # 宁德时代
    "688981": (23.0, 6.0),    # 中芯国际
    "601138": (8.0, 4.0),     # 工业富联
    "600690": (31.0, 7.0),    # 海尔智家
}

# 各行业总股本的模拟区间（亿股）
SHARES_SIM = {
    0: (5, 60), 1: (8, 50), 2: (3, 30), 3: (10, 100), 4: (5, 40), 5: (8, 60),
    6: (5, 40), 7: (20, 200), 8: (10, 80), 9: (3, 40), 10: (5, 60),
}


# 真实数据（由 fetch_real.py 从 akshare 拉取）。有就用真的，没有就退回模拟——
# 两条路径都要能跑，这样断网/接口挂了也不影响出页面。
REAL_FILE = os.path.join(HERE, "real", "fundamentals.json")


def load_real_quotes():
    if not os.path.exists(REAL_FILE):
        return None
    try:
        with open(REAL_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("quotes") or {}
    except Exception as e:
        print(f"  ! 真实数据读取失败（{e}），本次退回模拟值")
        return None


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


def simulate_fundamentals(code: str, name: str, sector: int) -> dict:
    r = rng_for(code)
    _p_lo, _p_hi, c_lo, c_hi, (gm_lo, gm_hi), (rg_lo, rg_hi) = SECTOR_SIM[sector]

    # 先定市值，再由市值反推股价：股价 = 市值 ÷ 股本
    # 市值用"对数均匀"抽样——真实的市值分布本来就是这样：绝大多数公司很小，
    # 少数很大。用线性抽样会让同一个行业里挤出一堆四千亿的"龙头"，一眼就假。
    cap = CAP_HINT.get(code)
    if cap is None:
        u = r() ** 1.6
        cap = round(c_lo * (c_hi / c_lo) ** u, 1)

    shares = SHARES_HINT.get(code)
    if shares is None:
        s_lo, s_hi = SHARES_SIM[sector]
        shares = round(s_lo + (s_hi - s_lo) * (r() ** 1.4), 2)

    price = cap / shares                       # 亿元 ÷ 亿股 = 元/股
    if not (2.0 <= price <= 1800.0):
        price = 2.0 + 1798.0 * (r() ** 3.2)    # 落到合理区间，再回推股本
    price = round(price, 2)
    shares = round(cap * 1e8 / price / 1e8, 4)  # 回推，保证三者自洽

    rg = round(rg_lo + (rg_hi - rg_lo) * r(), 1)

    hint = MARGIN_HINT.get(code)
    if hint:
        gm, pm = hint
        gm = round(gm + r() * 1.6, 1)          # 加一点抖动，避免和真实值一模一样
        pm = round(pm + r() * 0.8, 1)
    else:
        gm = round(gm_lo + (gm_hi - gm_lo) * r(), 1)
        # 净利率由毛利率派生，避免"毛利 90% 净利负数"这种不合常识的组合
        pm = round(max(-4.0, gm * (0.10 + 0.34 * r())), 1)

    pe = round(max(4.0, 8 + (r() ** 1.6) * 72), 1)
    fpe = round(max(3.5, pe * (0.62 + 0.34 * r())), 1)
    eps = round(price / pe, 2)
    feps = round(price / fpe, 2)

    # 模拟当日涨跌：A股 ±10% 为主，偏向微幅
    chg = round((r() ** 1.4) * 9.4 * (1 if r() < 0.54 else -1), 2)
    prev = round(price / (1 + chg / 100), 2)

    return {
        "currency": "CNY",
        "price": price,
        "shares": shares,
        "prevClose": prev,
        "changePercent": chg,
        "marketCap": cap,
        "marketCapUnit": "亿元",
        "trailingPE": pe,
        "forwardPE": fpe,
        "grossMargins": gm,
        "profitMargins": pm,
        "revenueGrowth": rg,
        "trailingEps": eps,
        "forwardEps": feps,
        "asOf": GENERATED_AT,
        "simulated": True,
    }


# --------------------------------------------------------------------------
def main():
    os.makedirs(DATA, exist_ok=True)

    # 真实数据在 index.json / fundamentals.json / 各公司卡片三处都要用，
    # 所以在最前面取一次
    real_quotes = load_real_quotes()
    data_source = "akshare" if real_quotes else "simulated"
    print(f"  数据来源: {'akshare 真实数据' if real_quotes else '模拟'}")

    by_code = {}
    for code, name, sec in COMPANIES:
        assert re.fullmatch(r"\d{6}", code), f"代码格式不对: {code}"
        assert code not in by_code, f"重复代码: {code}"
        by_code[code] = {"code": code, "name": name, "sector": sec,
                         "board": board_of(code), "exchange": exchange_of(code)}
    assert len(by_code) == len(COMPANIES)

    # 关系去重 + 校验
    seen, links = set(), []
    for sup, cus, role in LINKS:
        assert sup in by_code, f"供应商不存在: {sup}"
        assert cus in by_code, f"客户不存在: {cus}"
        assert sup != cus, f"自环: {sup}"
        k = (sup, cus)
        if k in seen:
            continue
        seen.add(k)
        links.append((sup, cus, role))

    # 邻接表
    sup_of = {c: [] for c in by_code}   # 谁供我
    cus_of = {c: [] for c in by_code}   # 我供谁
    for sup, cus, role in links:
        sup_of[cus].append((sup, role))
        cus_of[sup].append((cus, role))

    limit = lambda v: v[1]  # noqa: E731

    index_companies = []
    for code, info in by_code.items():
        up1 = sup_of[code]
        down1 = cus_of[code]
        up_set = {s for s, _ in up1}
        down_set = {c for c, _ in down1}
        up2 = {x for s in up_set for x, _ in sup_of[s]} - up_set - {code}
        down2 = {y for c in down_set for y, _ in cus_of[c]} - down_set - {code}
        index_companies.append({
            "ticker": code,
            "name": info["name"],
            "sector": SECTORS[info["sector"]],
            "sectorIndex": info["sector"],
            "board": info["board"],
            "exchange": info["exchange"],
            "nodeCount": len(up1) + len(down1) + len(up2) + len(down2),
            "up": len(up_set),
            "down": len(down_set),
        })

    sec_order = {s: i for i, s in enumerate(SECTORS)}
    index_companies.sort(key=lambda c: (sec_order[c["sector"]], c["ticker"]))

    # ---- data/index.json ----
    featured = []
    for code in FEATURED:
        info = by_code[code]
        ic = next(c for c in index_companies if c["ticker"] == code)
        featured.append({
            "ticker": code, "name": info["name"], "sector": SECTORS[info["sector"]],
            "board": info["board"], "up": ic["up"], "down": ic["down"],
        })

    totals = {
        "companies": len(by_code),
        "links": len(links),
        "sectors": len(SECTORS),
        "nodes": sum(c["nodeCount"] for c in index_companies),
    }

    # 两个版本：带 <b> 的给 hero-note（走 innerHTML），纯文本的给页脚（走 textContent，
    # 用 HTML 版会把 <b> 标签原样显示出来）
    if data_source == "akshare":
        disclaimer = (
            f"行情与财务数据为<b>真实公开数据</b>（东方财富 · akshare，截至 {GENERATED_AT}）；"
            "供应链关系基于公开信息推断、<b>未经逐条核实</b>，不构成任何投资建议。"
        )
        disclaimer_text = (
            f"行情与财务数据为真实公开数据（东方财富 · akshare，截至 {GENERATED_AT}）；"
            "供应链关系基于公开信息推断、未经逐条核实，不构成任何投资建议。"
        )
    else:
        disclaimer = (
            "演示用模拟数据：财务数字为随机生成，供应链关系基于公开信息推断且未经核实，"
            "不可用于任何投资决策。"
        )
        disclaimer_text = disclaimer

    with open(os.path.join(DATA, "index.json"), "w", encoding="utf-8") as f:
        json.dump({
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": GENERATED_AT,
            "sectors": SECTORS,
            "totals": totals,
            "dataSource": data_source,
            "disclaimer": disclaimer,
            "disclaimerText": disclaimer_text,
            "companies": index_companies,
            "featured": {"key": "core", "name": FEATURED_NAME, "companies": featured},
        }, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    # ---- data/fundamentals.json ----
    # 优先用 akshare 拉到的真实数据；取不到的那几家退回模拟，并逐条标注来源，
    # 让页面能如实区分"这是真行情"和"这是编的"。
    quotes = {}
    real_count = 0
    for code, info in by_code.items():
        rq = (real_quotes or {}).get(code)
        if rq:
            q = dict(rq)
            q["simulated"] = False
            real_count += 1
        else:
            q = simulate_fundamentals(code, info["name"], info["sector"])
            q["simulated"] = True
        quotes[code] = q
    sim_count = len(quotes) - real_count
    print(f"  其中真实 {real_count} 家 / 模拟 {sim_count} 家")
    with open(os.path.join(DATA, "fundamentals.json"), "w", encoding="utf-8") as f:
        json.dump({"generatedAt": GENERATED_AT, "count": len(quotes), "quotes": quotes},
                  f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    # ---- data/{TICKER}.json（每家公司一张价值链卡片）----
    total_nodes = 0
    for code, info in by_code.items():
        nodes = []

        def push(other, direction, tier, role, extra=None):
            oi = by_code[other]
            node = {
                "id": other,
                "ticker": other,
                "name": oi["name"],
                "sector": SECTORS[oi["sector"]],
                "relation": direction,
                "tier": tier,
                "role": role,
                "component": role,
                "summary": f"{oi['name']}向{info['name']}提供{role}" if direction == "upstream"
                           else f"{info['name']}向{oi['name']}供应{role}",
            }
            if extra:
                node.update(extra)
            nodes.append(node)

        # 上游一级
        for other, role in sup_of[code]:
            extra = None
            if other in CAP_HINT or rng_for(other + code)() < 0.45:
                dep = round(3 + rng_for(other + code)() * 42, 1)
                extra = {"depPct": dep, "depAsOf": GENERATED_AT}
            push(other, "upstream", 1, role, extra)

        # 下游一级
        for other, role in cus_of[code]:
            push(other, "downstream", 1, role)

        # 上游二级（经一级供应商）
        up_set = {s for s, _ in sup_of[code]}
        for s in sorted(up_set):
            for other, role in sup_of[s]:
                if other == code or other in up_set:
                    continue
                if any(n["id"] == other and n["relation"] == "upstream" for n in nodes):
                    continue
                push(other, "upstream", 2, role, {"via": s})

        # 下游二级（经一级客户）
        down_set = {c for c, _ in cus_of[code]}
        for c in sorted(down_set):
            for other, role in cus_of[c]:
                if other == code or other in down_set:
                    continue
                if any(n["id"] == other and n["relation"] == "downstream" for n in nodes):
                    continue
                push(other, "downstream", 2, role, {"via": c})

        total_nodes += len(nodes)
        with open(os.path.join(DATA, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump({
                "schemaVersion": SCHEMA_VERSION,
                "generatedAt": GENERATED_AT,
                "anchor": {
                    "ticker": code, "name": info["name"],
                    "sector": SECTORS[info["sector"]], "sectorIndex": info["sector"],
                    "board": info["board"], "exchange": info["exchange"],
                    "fundamentals": None,
                },
                "nodes": nodes,
            }, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")

    # ---- data/worldmap.json ----
    wm_codes = list(by_code.keys())
    wm_idx = {c: i for i, c in enumerate(wm_codes)}
    wm_companies = [{
        "t": c, "n": by_code[c]["name"], "s": by_code[c]["sector"],
        "b": by_code[c]["board"], "mc": quotes[c]["marketCap"],
    } for c in wm_codes]
    wm_links = [[wm_idx[s], wm_idx[c], 1, r] for s, c, r in links]

    with open(os.path.join(DATA, "worldmap.json"), "w", encoding="utf-8") as f:
        json.dump({
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": GENERATED_AT,
            "sectors": SECTORS,
            "companies": wm_companies,
            "links": wm_links,
        }, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    # ---- 控制台小结 ----
    print(f"公司数        {len(by_code)}")
    print(f"供应链关系边  {len(links)}")
    print(f"展开后节点数  {total_nodes}")
    print(f"行业数        {len(SECTORS)}")
    print(f"财务记录      {len(quotes)}")
    print(f"生成日期      {GENERATED_AT}")


if __name__ == "__main__":
    main()
