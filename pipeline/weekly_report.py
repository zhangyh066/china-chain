# -*- coding: utf-8 -*-
"""每周数据周报：只读仓库里已有的 data/ 产物，生成一份 markdown 到
仓库根 weekly_report.md（CI 里随后用 gh issue create --body-file 发成 Issue）。

内容全部由数据自动生成，不含人工观点（口径与站点一致）：
  全市场等权指数周涨跌 → 行业指数涨跌前五/后五 → 环节指数最强/最弱 →
  产业链看板阶段异动 top → 数据健康度摘要。

"周"= 最近 5 个交易日（数据里 dates 轴的末 6 点），标题里如实写区间——
数据滞后时区间就是滞后的区间，不假装是本周。

用法：python pipeline/weekly_report.py   （离线；输出 weekly_report.md，stdout 打摘要）
"""
import json
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "weekly_report.md")

WEEK_POINTS = 6        # 末 6 点 = 5 个交易日的涨跌


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def week_pct(series):
    """末 5 个交易日涨跌（%）；点数不足或基数为 0 返回 None。"""
    if not isinstance(series, list) or len(series) < WEEK_POINTS:
        return None
    a, b = series[-WEEK_POINTS], series[-1]
    if not a or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    return (b / a - 1) * 100


def fmt(p):
    return f"{p:+.2f}%" if p is not None else "—"


def main():
    ti = load(os.path.join(DATA, "trends", "index.json"))
    dates = ti.get("dates") or []
    if len(dates) < WEEK_POINTS:
        print("XX 趋势数据不足一周，不出周报")
        return 1
    start, end = dates[-WEEK_POINTS], dates[-1]
    mkt = week_pct(ti.get("market"))

    ind_rows = []
    seg_rows = []
    idir = os.path.join(DATA, "trends", "i")
    for fn in os.listdir(idir):
        if not fn.endswith(".json"):
            continue
        d = load(os.path.join(idir, fn))
        p = week_pct(d.get("industry"))
        if p is not None:
            ind_rows.append((p, d.get("name") or fn[:-5]))
        for seg, series in (d.get("segments") or {}).items():
            q = week_pct(series)
            if q is not None:
                seg_rows.append((q, seg, d.get("name") or fn[:-5]))

    chain_rows = []
    cdir = os.path.join(DATA, "chain")
    for fn in os.listdir(cdir):
        if not fn.endswith(".json") or fn == "chain.json":
            continue
        d = load(os.path.join(cdir, fn))
        tr = d.get("trends") or {}
        stages = {s.get("key"): s for s in d.get("stages") or []}
        for sk, series in (tr.get("stages") or {}).items():
            q = week_pct(series)
            if q is not None:
                st = stages.get(sk) or {}
                chain_rows.append((q, d.get("title") or fn[:-5],
                                   st.get("name") or sk))

    ind_rows.sort(key=lambda x: -x[0])
    seg_rows.sort(key=lambda x: -x[0])
    chain_rows.sort(key=lambda x: -abs(x[0]))

    health = load(os.path.join(DATA, "health.json")) if os.path.exists(
        os.path.join(DATA, "health.json")) else {}
    hq = (health.get("sources") or {}).get("quotes") or {}
    stale_days = ((date.today() - date.fromisoformat(hq["asOf"])).days
                  if hq.get("asOf") else None)
    health_line = (f"行情数据截至 **{hq.get('asOf') or '—'}**"
                   + (f"，已停更 {stale_days} 天（超出日更预期，详见站点 #/health）"
                      if stale_days is not None and stale_days > 14
                      else "（日更口径）")) if hq else "健康度数据缺失"

    def table(rows, with_chain=False):
        head = "| 周涨跌 | " + ("产业链 | 阶段 |" if with_chain else "名称 |") + "\n|---|" + "---|" * (3 if with_chain else 2)
        body = "".join(
            f"\n| {fmt(r[0])} | " + (f"{r[1]} | {r[2]} |" if with_chain else f"{r[1]} |")
            for r in rows)
        return head + body

    md = []
    md.append(f"# 链谱周报 · {start} ~ {end}")
    md.append("")
    md.append(f"> 全部由仓库数据自动生成（等权指数，口径同站点），无人工观点。{health_line}。")
    md.append("")
    md.append(f"## 全市场")
    md.append("")
    md.append(f"等权全市场指数近 5 个交易日 **{fmt(mkt)}**。")
    md.append("")
    md.append("## 行业指数（申万一级 · 等权）")
    md.append("")
    md.append("**涨前五**")
    md.append("")
    md.append(table(ind_rows[:5]))
    md.append("")
    md.append("**跌前五**")
    md.append("")
    md.append(table(ind_rows[-5:][::-1]))
    md.append("")
    md.append("## 环节指数（各行业成员数前 12 · 等权）")
    md.append("")
    md.append("**最强五个**")
    md.append("")
    md.append(table(seg_rows[:5]))
    md.append("")
    md.append("**最弱五个**")
    md.append("")
    md.append(table(seg_rows[-5:][::-1]))
    md.append("")
    md.append("## 产业链看板 · 阶段异动（绝对幅前八）")
    md.append("")
    md.append(table(chain_rows[-8:][::-1], with_chain=True))
    md.append("")
    md.append(f"---")
    md.append(f"生成于 {date.today().isoformat()} · [站点](https://zhangyh066.github.io/china-chain/) · "
              f"[数据健康度](https://zhangyh066.github.io/china-chain/#/health)")

    text = "\n".join(md) + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"weekly_report.md：{start} ~ {end}，全市场 {fmt(mkt)}，"
          f"行业 {len(ind_rows)}、环节 {len(seg_rows)}、链阶段 {len(chain_rows)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
