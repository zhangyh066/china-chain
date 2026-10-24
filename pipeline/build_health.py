# -*- coding: utf-8 -*-
"""数据健康度快照：把 data/ 各数据源的"数据截至/覆盖/新鲜度预期"聚合成
一份 data/health.json，前端 #/health 页渲染。

为什么需要：站点的可信度建立在"口径诚实"上，而数据新旧此前只能靠页脚
一行"数据截至"。这里把每个数据源的最后更新时间、覆盖规模、更新预期
（日更/季更/年更）摊开给用户看——哪个源滞后了、滞后多少天，一眼可见，
而不是藏在免责声明里。

asOf 口径：优先取文件自带的 generatedAt；f/ 取全体 asOf 的最大值；
h/ 取全体末个交易日点的最大值，并统计"落后主线超过 14 天"的陈旧文件数
（fetch_history 无 TTL 增量缓存的已知问题，如实展示）。

expect 档位（前端按它给新鲜度徽章）：daily / weekly / monthly /
quarterly / annual / static。profiles（data/p）无独立时间戳，asOf 为空。

用法：python build_health.py   （离线，只读 data/，缺文件记 missing）
"""
import json
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

STALE_H_DAYS = 14     # data/h 末点落后全库主线超过该天数 → 计入陈旧数


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_or_none(path):
    return load(path) if os.path.exists(path) else None


def main():
    idx = load_or_none(os.path.join(DATA, "index.json")) or {}
    n_comp = len(idx.get("companies", []))

    src = {}

    # 行情快照 + 财务指标：index.json 的 generatedAt，f/ 的最新 asOf
    f_asof = None
    fdir = os.path.join(DATA, "f")
    n_f = len(os.listdir(fdir)) if os.path.isdir(fdir) else 0
    if n_f:
        for fn in os.listdir(fdir):
            try:
                a = json.load(open(os.path.join(fdir, fn), encoding="utf-8")).get("asOf")
            except Exception:
                continue
            if a and (f_asof is None or a > f_asof):
                f_asof = a
    src["quotes"] = {"asOf": f_asof or idx.get("generatedAt"), "n": n_f, "d": n_comp,
                     "expect": "daily"}

    # 日线历史：末点最大日期 + 陈旧文件数
    h_asof, n_h, h_stale = None, 0, 0
    hdir = os.path.join(DATA, "h")
    if os.path.isdir(hdir):
        for fn in os.listdir(hdir):
            try:
                pts = json.load(open(os.path.join(hdir, fn), encoding="utf-8")).get("points")
            except Exception:
                continue
            n_h += 1
            last = pts[-1][0] if pts else None
            if last and (h_asof is None or last > h_asof):
                h_asof = last
        if h_asof:
            from datetime import datetime, timedelta
            main_line = datetime.fromisoformat(h_asof)
            for fn in os.listdir(hdir):
                try:
                    pts = json.load(open(os.path.join(hdir, fn), encoding="utf-8")).get("points")
                except Exception:
                    continue
                last = pts[-1][0] if pts else None
                if not last or main_line - datetime.fromisoformat(last) > timedelta(days=STALE_H_DAYS):
                    h_stale += 1
    src["history"] = {"asOf": h_asof, "n": n_h, "d": n_comp, "stale": h_stale,
                      "expect": "daily"}

    # 公司介绍：无独立时间戳（随年报披露重抓），只报覆盖
    pdir = os.path.join(DATA, "p")
    n_p = len(os.listdir(pdir)) if os.path.isdir(pdir) else 0
    src["profiles"] = {"asOf": None, "n": n_p, "d": n_comp, "expect": "quarterly"}

    def gen(path, n, d, expect, **extra):
        o = load_or_none(path)
        if not o:
            return {"missing": True, "expect": expect}
        row = {"asOf": o.get("generatedAt"), "n": n, "d": d, "expect": expect}
        row.update(extra)
        return row

    tdir = os.path.join(DATA, "trends", "i")
    n_t = len(os.listdir(tdir)) if os.path.isdir(tdir) else 0
    src["trends"] = gen(os.path.join(DATA, "trends", "index.json"),
                        n_t, len(idx.get("industryList", [])), "daily")

    cdir = os.path.join(DATA, "chain")
    chain_files = [fn for fn in os.listdir(cdir) if fn.endswith(".json") and fn != "chain.json"] \
        if os.path.isdir(cdir) else []
    chain_gen = max((load(os.path.join(cdir, fn)).get("generatedAt") or "")
                    for fn in chain_files) if chain_files else None
    src["chains"] = {"asOf": chain_gen, "n": len(chain_files), "d": None, "expect": "monthly"}

    sup = load_or_none(os.path.join(DATA, "supply.json"))
    src["supply"] = {"asOf": sup.get("generatedAt") if sup else None,
                     "n": len(sup.get("companies", {})) if sup else 0, "d": n_comp,
                     "expect": "annual"}

    src["purity"] = gen(os.path.join(DATA, "purity.json"), None, None, "quarterly")
    src["transmission"] = gen(os.path.join(DATA, "transmission.json"), None, None, "monthly")

    disc = load_or_none(os.path.join(DATA, "chain_disclosure.json"))
    src["disclosure"] = {
        "asOf": disc.get("generatedAt") if disc else None,
        "n": sum(v.get("count", 0) for v in (disc.get("chains", {}) or {}).values()) if disc else 0,
        "d": len(chain_files), "expect": "annual"}

    steps = load_or_none(os.path.join(DATA, "chain_steps.json"))
    src["steps"] = {"asOf": steps.get("generatedAt") if steps else None,
                    "n": len(steps.get("steps", [])) if steps else 0, "d": None,
                    "expect": "static"}

    src["graph"] = gen(os.path.join(DATA, "graph.json"),
                       len((load_or_none(os.path.join(DATA, "graph.json")) or {})
                           .get("industries", {})), 24, "daily")

    obj = {
        "schemaVersion": 1,
        "generatedAt": date.today().isoformat(),
        "companyCount": n_comp,
        "staleHDays": STALE_H_DAYS,
        "sources": src,
    }
    path = os.path.join(DATA, "health.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    today = date.today().isoformat()
    print(f"data/health.json：{len(src)} 个数据源（{today}）", flush=True)
    for k, v in src.items():
        if v.get("missing"):
            age = "缺文件"
        else:
            days = ((date.fromisoformat(today) - date.fromisoformat(v["asOf"])).days
                    if v.get("asOf") else None)
            age = f"{v.get('asOf') or '无时间戳'}（{days if days is not None else '—'} 天前）"
        cov = f"{v.get('n')}/{v.get('d')}" if v.get("d") else (v.get("n") if v.get("n") is not None else "")
        extra = f"，陈旧 {v['stale']} 份" if v.get("stale") else ""
        print(f"  {k:<12} {v['expect']:<9} {age:<28} {cov}{extra}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
