# -*- coding: utf-8 -*-
"""披露级供应链（前五大客户/供应商）管线：CNRDS 原始表 → data/supply.json。

许可红线：原始文件（新建文件夹/ 下的 CNRDS/DataSeed 数据）仅限本机使用，
绝不入库、绝不外传（新建文件夹/ 已加入 .gitignore）。本脚本只在内存里
解析原始表，输出聚合后的 data/supply.json（仅覆盖 data/index.json 的
4071 家上市公司：最新实名明细 + 历年集中度序列），原始明细行不落盘。
run_all.py 中本步骤仅在原始文件存在时执行（CI runner 上没有，静默跳过）。

原始表说明（SC_TopFiveSaleInfo.xlsx 客户 / SC_TopFivePurchaseInfo.xlsx 供应商）：
  - xlsx 的 dimension 元数据损坏（报 1 列），openpyxl 直接读会丢列，
    必须 XML iterparse 自行解析（本脚本 parse_sheet 即干这个）。
  - 行结构：第 1 行英文字段名、第 2 行中文、第 3 行单位、第 4 行起数据。
  - 金额单位为元（→ 本产物统一换算万元），占比单位为 %（→ 统一换算 0~1
    小数，保留 4 位）。Rank 1~5 为前五大明细，6 为「合计」行。
  - StateTypeCode：1=合并报表（只用这个），2=母公司报表（剔除——母公司
    口径下"客户"常是自家子公司，不是真实供应链）。

过滤规则：
  - 自环：对手方上市代码/关联上市代码含主体自身代码 → 剔；
  - 自家子公司：对手方名称含主体简称（去 ST 与 A/B/H 后缀，≥2 字）→ 剔。
    简称子串规则保守，抓不住无冠名子公司（如"广东邦普"之于宁德时代），
    宁可漏剔也不错杀真实对手方。

实名判定：名称命中 ANON_RE（"客户一/第一名/供应商1/客户A/合计/其他"式）
即匿名，不进出明细（但仍计入集中度——合计行不依赖实名）。

对手方代码匹配优先级：本身上市代码(BusinessSymbol) > 关联上市代码
(RelatedSymbol) > 名称规范化匹配 index.json 简称；多地上市分号串
（"00386;600028;SNP"）取落在 index.json 4071 家里的 A 股 6 位码。

产出 data/supply.json：
  {schemaVersion:1, generatedAt, sourceNote, companies:{code:{
    conc:{year, top5C, top5S, concHist:[[year, top5C],…]},
    customers:[{name, code, ratio, amount}],   // 最新有实名行年份，≤5 条
    suppliers:[…]}}}
  体量目标 < SIZE_CAP（2 MB）：先写全量 concHist，超了逐级砍到近 10/5/4/3 年。

用法：python build_supply.py
"""

import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(ROOT, "新建文件夹")

SIZE_CAP = 2 * 1024 * 1024   # 产物目标 < 2 MB

SALE_NAME = "SC_TopFiveSaleInfo.xlsx"
PUR_NAME = "SC_TopFivePurchaseInfo.xlsx"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 匿名占位名称：客户一/供应商1/第一名/客户A/甲/合计/其他/保密……
ANON_RE = re.compile(
    r"^(第[一二三四五六七八九十\d]+[名个]?|[一二三四五六七八九十\d]+|"
    r"(客户|供应商|单位|公司|企业|客商)?[A-Za-z]|"
    r"(客户|供应商|单位|公司|企业|客商)[一二三四五六七八九十\dA-Za-z]+[名个位]?|"
    r"(前五名|前5名|其他|合计|非关联|关联方|不适用|无|未知|保密|甲|乙|丙|丁).*)$")

# 原始表列序（两份表同构）
C_SYM, C_END, C_STATE, C_RANK, C_NAME = 0, 1, 2, 3, 5
C_BSYM, C_RSYM, C_AMT, C_PCT = 7, 9, 10, 11


def find_raw(name):
    """新建文件夹/ 下递归找原始表（CNRDS 下载目录层级不固定）。"""
    for dirpath, _dirnames, filenames in os.walk(RAW_DIR):
        if name in filenames:
            return os.path.join(dirpath, name)
    return None


def col_index(ref):
    v = 0
    for ch in re.match(r"([A-Z]+)", ref).group(1):
        v = v * 26 + ord(ch) - 64
    return v - 1


def parse_sheet(path):
    """iterparse 绕过损坏的 dimension，逐行 yield {列号: 文本}（跳过 3 行表头）。"""
    z = zipfile.ZipFile(path)
    f = z.open("xl/worksheets/sheet1.xml")
    cur = {}
    try:
        for _ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == NS + "row":
                vals, cur = cur, {}
                yield vals
                el.clear()
            elif el.tag == NS + "c":
                ci = col_index(el.get("r", "A1"))
                t = el.find(NS + "is/" + NS + "t")
                v = el.find(NS + "v")
                txt = t.text if t is not None else (v.text if v is not None else None)
                if txt is not None:
                    cur[ci] = txt
                el.clear()
    finally:
        f.close()
        z.close()


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def split_codes(s):
    return [t for t in re.split(r"[;,/\s]+", s or "") if re.fullmatch(r"\d{6}", t)]


def norm_name(s):
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"(股份有限公司|有限责任公司|有限公司|集团股份有限公司|集团|股份|公司)", "", s)
    return s.strip()


def short_key(name):
    """主体简称剔 ST/*ST 与尾部 A/B/H，用于自家子公司子串判定。"""
    s = re.sub(r"^\*?ST", "", name)
    s = re.sub(r"[ABH]$", "", s)
    return s


def main():
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    ours = {c["ticker"]: c["name"] for c in idx["companies"]}

    # 对手方名称 → 代码 的规范化索引（简称原样 + 去公司形态后缀两键）
    name2code = {}
    for code, nm in ours.items():
        name2code.setdefault(nm, code)
        name2code.setdefault(norm_name(nm), code)

    sale_path = find_raw(SALE_NAME)
    pur_path = find_raw(PUR_NAME)
    if not sale_path or not pur_path:
        print("XX 未找到原始表（新建文件夹/ 下应有 "
              f"{SALE_NAME} 与 {PUR_NAME}）", flush=True)
        return 1

    # sides: 0=customers(下游客户) 1=suppliers(上游供应商)
    # conc[code][side][year] = top5 合计占比(0~1)；det[code][side][year] = [行…]
    conc = {}
    det = {}
    n_rows = n_state = n_self = n_sub = n_ours = 0

    for side, path in ((0, sale_path), (1, pur_path)):
        for row in parse_sheet(path):
            sym = row.get(C_SYM)
            if not sym or not re.fullmatch(r"\d{6}", str(sym)):
                continue            # 表头三行（Symbol/股票代码/None）
            name = (row.get(C_NAME) or "").strip()
            if not name or name in ("元", "%"):
                continue
            n_rows += 1
            if sym not in ours:
                continue
            n_ours += 1
            if str(row.get(C_STATE)) != "1.0":
                n_state += 1
                continue            # 只要合并报表
            year = str(row.get(C_END) or "")[:4]
            if not re.fullmatch(r"\d{4}", year):
                continue
            b_codes = split_codes(row.get(C_BSYM))
            r_codes = split_codes(row.get(C_RSYM))
            if sym in b_codes or sym in r_codes:
                n_self += 1
                continue            # 自环（含对手方是自家子公司且关联码=自己）
            pct = to_float(row.get(C_PCT))
            ratio = round(pct / 100, 4) if pct is not None else None

            slot = conc.setdefault(sym, [{}, {}])
            if name == "合计":
                # 合计行优先：直接给 top5 合计占比；多次出现取最大（币种差异兜底）
                prev = slot[side].get(year)
                if ratio is not None and (prev is None or ratio > prev):
                    slot[side][year] = min(ratio, 1.0)
                continue

            key = short_key(ours[sym])
            if len(key) >= 2 and key in name:
                n_sub += 1
                continue            # 自家子公司（名称冠主体简称）

            # 明细行（含匿名）：先留作集中度兜底求和；实名与否在出产物时判
            amt = to_float(row.get(C_AMT))
            d = det.setdefault(sym, [{}, {}])[side].setdefault(year, [])
            d.append((name, b_codes, r_codes, ratio,
                      round(amt / 10000, 2) if amt is not None else None))

    # 出产物
    generated = date.today().isoformat()
    companies = {}
    st_conc = st_cust = st_supp = 0
    recent_codes = set()
    n_edges = 0

    def match_code(b_codes, r_codes, name):
        for t in b_codes + r_codes:
            if t in ours:
                return t
        return name2code.get(norm_name(name)) or name2code.get(name)

    for code, sides in conc.items():
        # 集中度：合计行优先；没有则同年明细占比求和（封顶 1.0）
        conc_c, conc_s = {}, {}
        for side, book in ((0, conc_c), (1, conc_s)):
            years = set(sides[side])
            d_years = det.get(code, [{}, {}])[side]
            years |= set(d_years)
            for y in years:
                v = sides[side].get(y)
                if v is None:
                    vals = [r[3] for r in d_years.get(y, []) if r[3] is not None]
                    v = round(min(sum(vals), 1.0), 4) if vals else None
                if v is not None:
                    book[y] = v
        if not conc_c and not conc_s:
            continue
        latest = max(set(conc_c) | set(conc_s))
        conc_obj = {
            "year": int(latest),
            "top5C": conc_c.get(latest),
            "top5S": conc_s.get(latest),
            "concHist": [[int(y), conc_c[y]] for y in sorted(conc_c)],
        }

        # 明细：每侧取"有实名行的最新年份"，按占比降序 ≤5 条
        out_sides = []
        for side in (0, 1):
            d_years = det.get(code, [{}, {}])[side]
            picked = []
            for y in sorted(d_years, reverse=True):
                real = [r for r in d_years[y] if not ANON_RE.match(r[0])]
                if real:
                    seen = {}
                    for r in real:
                        if r[0] not in seen or (r[3] or 0) > (seen[r[0]][3] or 0):
                            seen[r[0]] = r
                    real = sorted(seen.values(), key=lambda r: -(r[3] or 0))[:5]
                    picked = [{"name": r[0],
                               "code": match_code(r[1], r[2], r[0]),
                               "ratio": r[3], "amount": r[4]} for r in real]
                    det_year = int(y)
                    break
            if picked:
                n_edges += sum(1 for e in picked if e["code"])
                if side == 0:
                    st_cust += 1
                else:
                    st_supp += 1
                if det_year >= 2023:
                    recent_codes.add(code)
            out_sides.append(picked)
        st_conc += 1
        companies[code] = {"conc": conc_obj,
                           "customers": out_sides[0], "suppliers": out_sides[1]}

    obj = {"schemaVersion": 1, "generatedAt": generated,
           "sourceNote": "上市公司年报公开披露（学术数据集整理）",
           "companies": companies}
    # 体量控制：先全量 concHist，超 SIZE_CAP 逐级砍到近 10/5/4/3 年
    trimmed = None
    for keep in (None, 10, 5, 4, 3):
        if keep is not None:
            for c in companies.values():
                h = c["conc"]["concHist"]
                if len(h) > keep:
                    c["conc"]["concHist"] = h[-keep:]
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) <= SIZE_CAP:
            trimmed = keep
            break
    out_path = os.path.join(DATA, "supply.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(payload)
    size = os.path.getsize(out_path)

    print(f"原始行 {n_rows}，入库公司行 {n_ours}，剔母公司报表 {n_state}、"
          f"自环 {n_self}、自家子公司 {n_sub}", flush=True)
    print(f"data/supply.json：{size/1024:.0f} KB，公司 {len(companies)}/4071"
          f"{'' if trimmed is None else f'（concHist 砍至近 {trimmed} 年）'}", flush=True)
    print(f"有集中度数据 {st_conc}；有实名客户明细 {st_cust}、"
          f"实名供应商明细 {st_supp}；明细年份 2023+ 的公司 {len(recent_codes)}", flush=True)
    print(f"库内公司间连线（对手方命中代码）{n_edges} 条", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
