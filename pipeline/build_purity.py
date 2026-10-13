# -*- coding: utf-8 -*-
"""概念纯度（照妖镜）管线：公司 i 在环节/阶段 j 的纯度 = 其主营构成（data/p
segments，分产品口径）中 item 命中该阶段关键词集合的 revenueRatio 之和。

全程离线，只读本地 data/，不做任何网络请求。

要点：
  - 关键词全部经过词汇调查定稿（扫描各阶段成员真实 segment item 后修正），
    定稿依据写在 PURITY 各阶段的注释里。未命中 = 0——这本身就是"蹭概念"
    信号，不粉饰成缺失。
  - 三档语义：p>0 为披露口径参与；p==0 时用同组关键词在 business+products
    （len≥2 关键词）与 scope（仅 len≥3 关键词）里做文本提及检测，命中
    记 m=1（"参与了但没单列披露"），否则 m=0（"没参与"）。scope 阈值更高的
    依据：全市场实测 2 字词在 scope 中噪音严重（回收 23→126、发电 96→506、
    软件 135→1228 家），3 字词相对干净（锂电池 38→30、碳酸锂 6→3）；
    单字别名（钒/酒/乳等）只做 segments 匹配，不进散文检测。
  - 边界冲突"更具体者优先"：同一公司同属一链多个阶段时（如格林美/华友同在前驱体
    与回收），一个 item 只归属列表中更靠前的阶段。PURITY 用有序 list，各链把
    更窄的阶段排前面（precursor 在 cathode 前、poly_silicon 在 cell_pv 前……）。
    当前数据下未出现真实冲突，此规则是兜底。
  - 199 个板块走通用回退：板块名归一化（去"概念"后缀、拆括号）作子串关键词，
    外加 BOARD_ALIAS 别名表（按实际命中情况手工补）。主营构成粒度粗，大量板块
    全零是真实结论，如实输出并在末尾汇报覆盖率。
  - 未命中成员也写入结果（p:0）。

产出：
  data/purity.json  {schemaVersion, generatedAt, period（众数报告期）,
                     chains:{链:{阶段:{code:{p, items, m}}}},
                     boards:{板块名:{code:p}},
                     boardsMentioned:{板块名:[code,…]}（仅 p==0 且 m==1）}
                     boards 只存数值控体积；若总大小超 SIZE_CAP 就只存非零。

用法：python build_purity.py
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

SIZE_CAP = 1024 * 1024   # boards 超 1 MB 时只存非零

# ---------------------------------------------------------------------------
# 链条阶段关键词（调查定稿）。每条链是有序 list：更具体的阶段在前，
# 一个 item 对同一公司只归第一个命中的阶段。
# ---------------------------------------------------------------------------
PURITY = {
    # 实际词汇：锂产品/锂系列产品/锂化合物及衍生品/锂矿/碳酸锂/锂矿采选及锂盐…。
    # 赣锋另有 34%「锂电池系列产品」——按语义归电芯口径，不计入上游（见汇报）。
    "lithium": [
        ("upstream_lithium", ["锂矿", "锂盐", "碳酸锂", "氢氧化锂", "锂化合物",
                              "锂精矿", "盐湖提锂", "锂产品", "锂系列", "锂业务"]),
        ("precursor", ["前驱体", "四氧化三钴"]),
        ("recycling", ["回收", "再生", "综合利用", "循环", "退役", "梯次"]),
        # 正极材料/磷酸盐系正极/多元材料/钴酸锂/磷酸铁锂/三元材料；成员自报的
        # 「前驱体」一项不计入（正极公司的前驱体多自用，边界归 precursor 阶段）
        ("cathode", ["正极", "磷酸铁锂", "磷酸盐", "三元材料", "钴酸锂", "锰酸锂",
                     "多元材料"]),
        # 璞泰来「新能源电池材料与服务」、杉杉「锂电池材料分部」均为负极口径
        ("anode", ["负极", "电池材料"]),
        ("separator", ["隔膜", "隔离膜"]),
        # 天赐「锂离子电池材料」、新宙邦「电池化学品」、石大胜华「锂离子电池相关材料」
        # 均为电解液口径；与负极「锂离子电池负极材料」无子串冲突
        ("electrolyte", ["电解液", "六氟磷酸锂", "电解质", "锂离子电池材料",
                         "电池化学品", "锂离子电池相关材料"]),
        ("equipment", ["锂电设备", "电池设备", "卷绕", "涂布", "化成分容",
                       "锂电池智能装备", "锂电池专用生产设备", "充放电设备"]),
        # 「电池材料及回收、矿产资源」等含回收字样的 item 已先被 recycling 拦截；
        # bare「锂电池」安全：含它的「锂电池隔膜/智能装备」成员都不在电芯阶段；
        # 「充电电池」专为比亚迪 business「二次充电电池」提及检测补的（segments 无此词）
        ("cell", ["动力电池", "储能电池", "电芯", "电池系统", "锂离子电池",
                  "消费电池", "消费类电池", "电动汽车类电池", "锂电池", "充电电池"]),
    ],
    "pv": [
        ("poly_silicon", ["多晶硅", "硅料"]),          # 实际：高纯多晶硅
        ("wafer", ["硅片", "硅棒", "单晶硅", "拉晶", "切片"]),  # 光伏硅片/硅片/硅棒
        ("cell_pv", ["电池片", "光伏电池", "太阳能电池"]),
        ("module", ["组件"]),
        ("glass", ["光伏玻璃", "太阳能玻璃"]),
        # 不写 bare「胶膜」：福斯特单列「非光伏胶膜」，命中会高估
        ("film", ["光伏胶膜", "光伏背板", "EVA", "POE", "光伏材料", "光伏运维材料"]),
        ("inverter", ["逆变器", "微逆"]),
        ("equipment_pv", ["光伏设备", "光伏装备", "太阳能电池", "单晶炉", "切片机",
                          "串焊机"]),
    ],
    "semi": [
        # 实际词汇高度分散：存储芯片/微控制器/模拟产品/信号链/电源管理/特种集成电路/
        # 智能安全芯片/互连类芯片/津逮/云端·边缘产品线（寒武纪）/高端处理器（海光）
        ("design", ["芯片", "集成电路", "半导体设计", "微控制器", "模拟产品", "射频",
                    "处理器", "传感器", "电源管理", "信号链", "津逮",
                    "云端产品线", "边缘产品线"]),
        ("foundry", ["晶圆", "代工", "集成电路"]),   # 集成电路晶圆代工；士兰微「集成电路」
        ("osat", ["封装", "封测"]),
        # 精测电子产品线只披露到「半导体」一词，该词在其口径下即半导体设备业务
        ("equipment_semi", ["半导体设备", "半导体装备", "半导体专用设备", "半导体",
                            "电子工艺装备", "刻蚀", "薄膜沉积", "清洗设备",
                            "测试机", "分选机"]),
        ("material", ["半导体硅片", "光刻胶", "特气", "靶材", "抛光", "湿电子化学品",
                      "前驱体材料", "半导体化学材料", "半导体材料", "电子材料"]),
        # 芯原的 IP 业务报为「设计服务收入/量产服务收入」，补「设计服务」
        ("eda", ["EDA", "IP授权", "IP特许", "设计服务", "技术开发"]),
    ],
    "robot": [
        # 双环的齿轮即减速器配套口径；中大「机电一体化产品」= 减速电机一体机
        ("reducer", ["减速器", "减速电机", "齿轮", "机电一体化"]),
        ("servo", ["伺服", "电机", "驱动系统", "控制系统", "控制电机", "工控",
                   "工业自动化"]),
        # 严格口径：三家公司报表均未单列丝杠收入（培育期），全零是真实结论
        ("screw", ["丝杠", "丝杆"]),
        ("sensor", ["传感器", "MEMS", "惯性"]),
        ("actuator", ["执行器"]),   # 拓普「机器人执行器」；三花未单列 → 0
        ("body", ["机器人", "自动化"]),
    ],
    "compute": [
        ("chip", ["芯片", "处理器", "云端产品线", "边缘产品线", "图形显控"]),
        ("optical", ["光通信", "光器件", "光互联", "光模块"]),
        ("pcb", ["PCB", "印制电路板", "线路板", "覆铜板"]),
        # 工业富联只披露到「3C电子产品」 lump → 0，披露粒度问题如实呈现
        ("server", ["服务器", "IT设备", "存储类"]),
        ("cooling", ["温控", "液冷", "恒温", "冷却", "换热"]),
        ("power", ["电源", "功率控制"]),
    ],
    "storage": [
        # 严格只算储能口径；鹏辉只披露「锂离子电池」→ 0
        ("battery", ["储能电池", "储能系统"]),
        ("pcs", ["变流器", "储能"]),
        ("tempctrl", ["温控", "液冷", "恒温", "冷却", "换热"]),
        # 盛弘的储能业务报为「新能源电能变换设备」
        ("integrate", ["储能", "系统集成", "综合能源", "电能变换"]),
    ],
    "pharma": [
        ("api", ["原料药", "中间体"]),
        # 百济神州按商品名单列（百悦泽/百泽安/安加维/倍利妥/凯洛斯/普贝希），
        # 关键词不含通用词根，按调查到的品名补齐
        ("innovative", ["药品", "许可", "授权", "百悦泽", "百泽安", "安加维",
                        "倍利妥", "凯洛斯", "普贝希"]),
        # 智飞只披露「自主产品/代理产品」——在疫苗阶段成员语境下即疫苗口径
        ("vaccine", ["疫苗", "生物制品", "基因工程", "合成生物", "自主产品",
                     "代理产品"]),
        # 片仔癀/云南白药/华润三九均按「医药行业…」口径披露，均为中药主业
        ("tcm", ["医药", "中药", "中成药"]),
        # 迈瑞「生命信息与支持类产品」无通用词根，单列
        ("device", ["器械", "影像", "诊断", "治疗", "解决方案", "生命信息与支持"]),
        # 药明康德按「化学业务/测试业务/生物学业务」披露，即其 CXO 分部口径
        ("cxo", ["CDMO", "CRO", "CMO", "外包", "临床试验", "临床研究", "实验室",
                 "化学业务", "测试业务", "生物学业务"]),
    ],
    "auto": [
        # 「汽车类」「汽车件」为旭升/鸿图压铸件口径
        ("lightweight", ["轻量化", "压铸", "铝铸件", "底盘", "减震", "内饰功能件",
                         "汽车类", "汽车件", "模具"]),
        # 三花的「汽车零部件」即车用热管理部件口径
        ("thermal", ["热管理", "热交换", "制冷", "汽车零部件"]),
        # 星宇（车灯）只披露「汽车零部件」
        ("trim", ["玻璃", "车灯", "轮胎", "汽车零部件"]),
        ("electronics", ["座舱", "智驾", "汽车电子", "电控", "制动", "转向",
                         "智云", "智芯", "智舱", "软件", "电子产品"]),
        # 长安只披露「销售商品」——在整车成员语境下即整车销售
        ("oem", ["整车", "汽车业务", "销售汽车", "汽车、汽车相关产品", "销售商品"]),
    ],
}

# 板块别名表：归一化名称之外按实际命中情况补的关键词。归一化 = 去「概念/板块」
# 后缀 + 拆括号（如 柔性屏(折叠屏) → [柔性屏, 折叠屏]）。补不到的概念关系型板块
# （华为/小米/苹果/中芯/英伟达概念等）注定全零——主营构成看不出供应链关系。
BOARD_ALIAS = {
    "锂电池概念": ["锂离子"], "电池技术": ["电池"],
    "国产芯片": ["芯片", "集成电路"], "军工": ["军工", "军品"],
    "医疗器械概念": ["器械"], "商业航天": ["航天", "卫星"],
    "人形机器人": ["机器人"], "氢能源": ["氢", "燃料电池"],
    "低空经济": ["低空", "无人机", "飞行器"], "充电桩": ["充电"],
    "风能": ["风电", "风能"], "国产软件": ["软件"],
    "固态电池": ["固态"], "消费电子概念": ["消费电子", "3C"],
    "核能核电": ["核电", "核能"], "PCB": ["PCB", "印制电路板", "线路板", "覆铜板"],
    "液冷服务器": ["液冷", "温控", "恒温"], "绿色电力": ["发电", "电力"],
    "油气资源": ["油气", "石油", "天然气"], "中药概念": ["中药", "中成药"],
    "存储芯片": ["存储芯片", "存储器"], "网络安全": ["网络安全", "信息安全"],
    "传感器": ["传感器", "MEMS"], "光通信模块": ["光模块", "光通信", "光器件"],
    "CPO概念": ["CPO", "光模块", "光器件", "光通信"],
    "汽车热管理": ["热管理", "热交换"], "工业母机": ["机床", "工业母机"],
    "无线耳机": ["耳机"], "3D打印": ["3D打印", "增材制造"],
    "装配建筑": ["装配式", "装配"], "先进封装": ["封装", "先进封装"],
    "创新医疗服务": ["医疗服务"], "飞行汽车(eVTOL)": ["eVTOL", "飞行汽车"],
    "汽车芯片": ["汽车芯片", "车规"], "卫星导航": ["卫星导航", "北斗"],
    "卫星互联网": ["卫星"], "钠离子电池": ["钠离"], "生物疫苗": ["疫苗"],
    "体外诊断概念": ["体外诊断", "IVD"], "降解塑料": ["降解"],
    "精准诊断": ["诊断"], "汽车一体化压铸": ["压铸", "一体化压铸"],
    "高压快充": ["快充", "充电"], "航天航空": ["航天", "航空"],
    "超超临界发电": ["超超临界"], "磷化工": ["磷化工", "磷酸"],
    "单抗概念": ["单抗", "抗体"], "CRO": ["CRO", "临床试验", "临床研究"],
    "免疫治疗": ["免疫治疗", "CAR-T", "细胞治疗"], "农药兽药": ["农药", "兽药"],
    "动力电池回收": ["回收", "梯次", "综合利用"], "激光雷达": ["激光雷达", "激光"],
    "油气设服": ["油服", "油田服务", "油气设服"], "基因测序": ["测序"],
    "无线充电": ["充电"], "抽水蓄能": ["抽水蓄能", "抽蓄"],
    "HJT电池": ["HJT", "异质结"], "稀土永磁": ["稀土", "永磁"],
    "减肥药": ["减肥药", "GLP-1", "多肽"], "超级电容": ["超级电容", "超容"],
    "铜缆高速连接": ["铜缆", "高速连接"],
    "锂矿概念": ["锂矿", "锂盐", "碳酸锂", "氢氧化锂", "锂产品", "锂系列",
                 "锂业务", "锂化合物"],
    "空气能热泵": ["热泵"], "猪肉概念": ["生猪", "猪肉"],
    "机器人执行器": ["执行器"], "AI芯片": ["芯片", "处理器"],
    "酿酒概念": ["酒"], "造纸印刷": ["造纸", "印刷"],
    "生物质能发电": ["生物质"], "工业气体": ["气体"],
    "调味品概念": ["调味", "酱油"], "乳业": ["乳"],
    "鸡肉概念": ["肉鸡", "鸡肉"], "航母概念": ["航母", "舰"],
    "AI手机": ["手机"], "CAR-T细胞疗法": ["CAR-T", "细胞治疗", "细胞疗法"],
    "粮食概念": ["粮食"], "被动元件概念": ["被动元件", "MLCC", "电感", "电容"],
    "高带宽内存": ["HBM", "存储芯片", "存储器"], "包装材料": ["包装"],
    "通用航空": ["通用航空", "通航"], "电子后视镜": ["后视镜"],
    "汽车整车": ["整车", "汽车业务", "汽车、汽车相关产品", "销售汽车"],
    "代糖概念": ["代糖", "甜味剂", "赤藓糖醇"], "碳基材料": ["碳基", "碳纤维"],
    "钒电池": ["钒"], "汽车拆解": ["拆解", "报废"], "熔盐储能": ["熔盐"],
    "地热能": ["地热"], "3D摄像头": ["3D摄像", "摄像头", "光学模组"],
    "低碳冶金": ["冶金"], "第四代半导体": ["第四代半导体", "氧化镓"],
    "虚拟机器人": ["机器人"], "工业机器人": ["机器人"],
}


def board_keywords(name):
    """板块名 → 关键词集合：归一化（去后缀/拆括号）+ 别名表。"""
    kws = set()
    parts = re.split(r"[（(]([^)）]*)[)）]", name)   # "柔性屏(折叠屏)" → [柔性屏, 折叠屏]
    for p in parts:
        p = re.sub(r"(概念|板块)$", "", p).strip()
        if len(p) >= 2:
            kws.add(p)
    kws.update(BOARD_ALIAS.get(name, []))
    return sorted(kws)


_profiles_cache = {}


def load_profile(code):
    """data/p/{code}.json → (segments, 提及检测文本)。文本 = business+products
    （主文本，len≥2 关键词）与 scope（样板法律条文，仅 len≥3 关键词）分开存。"""
    if code not in _profiles_cache:
        try:
            with open(os.path.join(DATA, "p", f"{code}.json"), encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        main = (d.get("business") or "") + "；" + (d.get("products") or "")
        _profiles_cache[code] = (d.get("segments") or [], main, d.get("scope") or "")
    return _profiles_cache[code]


def is_mentioned(keywords, main_text, scope_text):
    """文本提及检测：business+products 认 len≥2 关键词；scope 只认 len≥3。

    依据（全市场实测）：2 字词在 scope 里噪音严重——回收 23→126 家、
    发电 96→506、软件 135→1228；3 字词干净——锂电池 38→30、碳酸锂 6→3。
    单字符别名（钒/酒/乳等）在散文里一律不算命中（segments 结构化短标签里仍算）。
    """
    for kw in keywords:
        if len(kw) >= 2 and kw in main_text:
            return True
        if len(kw) >= 3 and kw in scope_text:
            return True
    return False


def main():
    generated = date.today().isoformat()
    periods = Counter()

    def scan(code, keywords):
        """返回 (purity, 命中 items, mentioned)。m=1：p>0 或文本提及命中。"""
        segs, main_text, scope_text = load_profile(code)
        hits = []
        total = 0.0
        for seg in segs:
            periods[seg.get("period")] += 1
            item = seg.get("item") or ""
            if any(kw in item for kw in keywords):
                r = seg.get("revenueRatio")
                if isinstance(r, (int, float)) and r > 0:
                    hits.append([item, r])
                    total += r
        p = round(min(total, 1.0), 4)
        m = 1 if (p > 0 or is_mentioned(keywords, main_text, scope_text)) else 0
        return p, hits, m

    # ---- 链条阶段（成员读 data/chain/{key}.json，已建成产物的实际口径）----
    chains_out = {}
    dist_rows = []
    for chain_key, stage_kws in PURITY.items():
        path = os.path.join(DATA, "chain", f"{chain_key}.json")
        if not os.path.exists(path):
            print(f"!! {path} 不存在，跳过 {chain_key} 链（先跑 build_chains.py）")
            continue
        with open(path, encoding="utf-8") as f:
            chain = json.load(f)
        stage_of = {}                       # code -> set(stage_key)
        for st in chain["stages"]:
            for c in st["companies"]:
                stage_of.setdefault(c["code"], set()).add(st["key"])
        kw_of = dict(stage_kws)
        order = [sk for sk, _ in stage_kws]  # 更具体者在前，first-match-wins
        acc = {sk: {} for sk in order}
        for code, my_stages in stage_of.items():
            attributed = {sk: [] for sk in my_stages}
            segs, main_text, scope_text = load_profile(code)
            for seg in segs:
                periods[seg.get("period")] += 1
                item = seg.get("item") or ""
                r = seg.get("revenueRatio")
                if not (isinstance(r, (int, float)) and r > 0):
                    continue
                for sk in order:
                    if sk in my_stages and any(kw in item for kw in kw_of[sk]):
                        attributed[sk].append([item, r])
                        break
            for sk in my_stages:
                p = round(min(sum(r for _, r in attributed[sk]), 1.0), 4)
                m = 1 if (p > 0 or
                          is_mentioned(kw_of[sk], main_text, scope_text)) else 0
                acc[sk][code] = {"p": p, "items": attributed[sk], "m": m}
        chains_out[chain_key] = acc
        for st in chain["stages"]:
            sk = st["key"]
            vals = [v["p"] for v in acc.get(sk, {}).values()]
            hi = sum(1 for v in vals if v > 0.5)
            zero = sum(1 for v in vals if v == 0)
            dist_rows.append((chain_key, sk, st["name"], len(vals), hi, zero))

    # ---- 199 板块通用回退 ----
    with open(os.path.join(DATA, "graph.json"), encoding="utf-8") as f:
        graph = json.load(f)
    boards_out = {}
    boards_mentioned = {}
    cov_rows = []
    for bname, codes in graph["boards"].items():
        kws = board_keywords(bname)
        entry = {}
        mentioned_codes = []
        nonzero = 0
        for code in codes:
            p, _, m = scan(code, kws)
            entry[code] = p
            nonzero += p > 0
            if p == 0 and m:
                mentioned_codes.append(code)
        boards_out[bname] = entry
        boards_mentioned[bname] = mentioned_codes
        cov_rows.append((bname, len(codes), nonzero, len(mentioned_codes)))

    period = periods.most_common(1)[0][0] if periods else None
    obj = {"schemaVersion": 1, "generatedAt": generated, "period": period,
           "chains": chains_out, "boards": boards_out,
           "boardsMentioned": boards_mentioned}
    out_path = os.path.join(DATA, "purity.json")
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > SIZE_CAP:
        # 超体积上限：boards 只留非零并明示
        obj["boards"] = {b: {c: p for c, p in e.items() if p > 0}
                         for b, e in boards_out.items()}
        obj["boardsNonZeroOnly"] = True
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        print("!! boards 超 1 MB，已只存非零（boardsNonZeroOnly=true）")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(payload)

    # ---- 汇总与抽查 ----
    print(f"\n各链条阶段纯度分布（成员数 / p>0.5 / p=0）：")
    for ck, sk, name, n, hi, zero in dist_rows:
        print(f"  {ck:<8} {sk:<18} {name:<12} {n:>2} 家 / >0.5: {hi:>2} / =0: {zero:>2}")

    n_cov = sum(1 for _, _, nz, _ in cov_rows if nz > 0)
    n_cov_m = sum(1 for _, _, nz, nm in cov_rows if nz > 0 or nm > 0)
    nonzero_counts = sorted(nz for _, _, nz, _ in cov_rows)
    median_nz = nonzero_counts[len(nonzero_counts) // 2]
    print(f"\nboards 覆盖率：{n_cov}/{len(cov_rows)} 个板块至少 1 家 p>0；"
          f"含提及口径 {n_cov_m}/{len(cov_rows)}；非零成员数中位 {median_nz}")
    zero_boards = [b for b, _, nz, nm in cov_rows if nz == 0 and nm == 0]
    print(f"p=0 且无人提及的全零板块 {len(zero_boards)} 个："
          f"{'、'.join(zero_boards[:20])}" + ("…" if len(zero_boards) > 20 else ""))

    # 全表统计：p==0 中 mentioned 占比
    all_zero, zero_m = 0, 0
    for acc in chains_out.values():
        for per in acc.values():
            for v in per.values():
                if v["p"] == 0:
                    all_zero += 1
                    zero_m += v["m"]
    b_zero = sum(1 for e in boards_out.values() for p in e.values() if p == 0)
    b_zero_m = sum(len(v) for v in boards_mentioned.values())
    print(f"\np==0 中 mentioned 占比：chains {zero_m}/{all_zero}"
          f"（{zero_m / all_zero * 100:.1f}%），boards {b_zero_m}/{b_zero}"
          f"（{b_zero_m / b_zero * 100:.1f}%）")

    def probe(chain, stage, code):
        v = chains_out.get(chain, {}).get(stage, {}).get(code, {})
        return v.get("p"), v.get("m")

    print("\n知名案例抽查：")
    p, m = probe('lithium', 'cell', '300750')
    print(f"  宁德时代 lithium.cell      = p {p}, m {m}（预期 p≈0.8861）")
    p, m = probe('lithium', 'cell', '002594')
    print(f"  比亚迪   lithium.cell      = p {p}, m {m}（预期 p=0, m=1："
          "scope 有「锂离子电池」、business 有「二次充电电池」）")
    p, m = probe('lithium', 'upstream_lithium', '002460')
    print(f"  赣锋锂业 upstream_lithium  = p {p}, m {m}")
    ssb = boards_out.get("固态电池", {})
    ssb_nz = sum(1 for p in ssb.values() if p > 0)
    ssb_m = len(boards_mentioned.get("固态电池", []))
    print(f"  固态电池板块 {len(ssb)} 家：p>0 有 {ssb_nz} 家，"
          f"p=0 但文本提及 {ssb_m} 家，全零 {len(ssb) - ssb_nz - ssb_m} 家")
    print("  机器人·丝杠三家提及情况：")
    for code, nm in (("601100", "恒立液压"), ("300580", "贝斯特"), ("603009", "北特科技")):
        v = chains_out["robot"]["screw"][code]
        print(f"    {code} {nm}: p={v['p']}, m={v['m']}")

    print(f"\ndata/purity.json {os.path.getsize(out_path)/1024:.1f} KB，"
          f"period={period}，chains={len(chains_out)}，boards={len(boards_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
