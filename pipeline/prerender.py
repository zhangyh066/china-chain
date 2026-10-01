# -*- coding: utf-8 -*-
"""构建期预渲染：为 24 个行业 + 全部公司生成爬虫可读的静态页。

为什么需要：SPA 是 hash 路由（#/c/300750），搜索引擎只能看到 index.html
一个地址，微信等分享也没有预览。这些静态页把同一份 data/ 渲染成文字版——
对爬虫友好，对"只想快速看个关系"的纯文字阅读者也更友好——
每页都有"在交互图谱中打开"跳回 SPA，二者数据口径完全一致。

产出：
  pages/i/{行业}.html    24 个行业页：统计、环节分布、龙头公司
  pages/c/{代码}.html    公司页：行情快照、所属环节、推断上下游（文字版）
  sitemap.xml / robots.txt

用法：
  python prerender.py            # SITE_BASE 用默认值（见下）
  SITE_BASE=https://example.com/ python prerender.py
"""
import json
import os
from datetime import date
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
PAGES = os.path.join(ROOT, "pages")
SITE_BASE = os.environ.get("SITE_BASE", "").rstrip("/")

# 托管地址未给定时，sitemap/og:url 用相对站点的绝对路径占位——
# 真正部署后应该用真实域名重新生成一遍（GitHub Actions 里已带这步）
if not SITE_BASE:
    SITE_BASE = "https://0ebad93a143e456cbd2e30cb01966249.app.workbuddy.host"

TOP_BOARDS = 15        # 行业页环节分布最多列几个
TOP_COMPANIES = 12     # 行业页龙头最多列几家


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt_cap(v):
    """市值：亿/万亿，与前端 fmtCap 同口径。"""
    if v is None:
        return "—"
    if v >= 10000:
        return f"{v / 10000:.2f} 万亿"
    return f"{v:.0f} 亿"


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def fmt_price(v):
    if v is None:
        return "—"
    return f"{v:.2f}"


# ---------------------------------------------------------------- CSS（文字版页面共用）
CSS = """
  :root { --paper:#F5F3EE; --ink:#14181D; --faint:#8A8A84; --gold:#A8863F;
          --gold-line:#E0D3B4; --navy:#13375E; --rise:#AE2A1E; --fall:#0E6B4A; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--paper); color:var(--ink);
         font:16px/1.75 "Songti SC","Noto Serif CJK SC","SimSun",serif; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 40px 24px 64px; }
  header.site { border-top: 3px solid var(--gold); padding-top: 18px;
                display:flex; justify-content:space-between; align-items:baseline; }
  header.site a { color: var(--navy); text-decoration: none; }
  header.site .name { font-weight: 700; letter-spacing: .12em; }
  header.site .back { font-size: 14px; color: var(--faint); }
  h1 { font-size: 30px; margin: 28px 0 6px; letter-spacing: .02em; }
  h1 .tk { font-size: 18px; color: var(--faint); font-weight: 400; margin-left: 10px; }
  h2 { font-size: 19px; margin: 40px 0 12px; padding-top: 14px;
       border-top: 1px solid var(--gold-line); letter-spacing: .06em; }
  h2 .sub { float:right; font-size: 13px; color: var(--faint); font-weight: 400; }
  .tags { margin: 10px 0 0; }
  .tag { display:inline-block; border:1px solid var(--gold-line); border-radius:4px;
         padding: 1px 10px; font-size: 13px; color: var(--ink); margin: 0 6px 6px 0; }
  .tag.sector { background: var(--navy); border-color: var(--navy); color: #fff; }
  .stats { display:flex; flex-wrap:wrap; gap: 28px; margin: 22px 0 4px; }
  .stat b { display:block; font-size: 26px; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 13px; color: var(--faint); }
  table { width:100%; border-collapse: collapse; font-size: 15px;
          font-variant-numeric: tabular-nums; }
  th, td { text-align:left; padding: 7px 10px; border-bottom: 1px solid var(--gold-line); }
  th { font-size: 13px; color: var(--faint); font-weight: 400; }
  td.num, th.num { text-align: right; }
  tr.lead td { border-bottom: 1px solid var(--gold-line); }
  a { color: var(--navy); }
  .rise { color: var(--rise); } .fall { color: var(--fall); } .flat { color: var(--faint); }
  .chips { line-height: 2.2; }
  .chip { display:inline-block; border:1px solid var(--gold-line); border-radius: 4px;
          padding: 0 10px; margin: 0 6px 6px 0; font-size: 14px;
          color: var(--ink); text-decoration: none; background: #fff; }
  .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  @media (max-width: 720px) { .grid2 { grid-template-columns: 1fr; } }
  .rel-list { margin: 0; padding: 0; list-style: none; }
  .rel-list li { padding: 7px 0; border-bottom: 1px dashed var(--gold-line); font-size: 15px; }
  .rel-list .role { color: var(--faint); font-size: 13px; margin-left: 8px; }
  .rel-list .dir { font-size: 12px; color: #fff; background: var(--navy); border-radius: 3px;
                   padding: 0 6px; margin-right: 8px; }
  .rel-list .dir.down { background: #9C5A2C; }
  .note { font-size: 14px; color: var(--faint); }
  .warn { border-left: 3px solid var(--gold); background: #fff; padding: 10px 16px;
          font-size: 14px; margin: 18px 0; }
  .open-app { display:block; text-align:center; margin: 40px 0 8px; }
  .open-app a { display:inline-block; background: var(--navy); color:#fff; padding: 12px 34px;
                border-radius: 4px; text-decoration: none; letter-spacing: .1em; }
  footer { margin-top: 56px; padding-top: 14px; border-top: 1px solid var(--gold-line);
           font-size: 13px; color: var(--faint); line-height: 1.9; }
"""


def page_shell(title, desc, canonical_path, body, extra_head=""):
    url = f"{SITE_BASE}/{quote(canonical_path.lstrip('/'), safe='/')}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}" />
<link rel="canonical" href="{esc(url)}" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(desc)}" />
<meta property="og:url" content="{esc(url)}" />
<meta property="og:image" content="{esc(SITE_BASE)}/assets/og/default.png" />
<link rel="stylesheet" href="../style.css" />
{extra_head}
</head>
<body>
<div class="wrap">
<header class="site"><a class="name" href="{SITE_BASE}/">链谱 ChainAtlas</a>
<a class="back" href="{SITE_BASE}/">← 交互图谱首页</a></header>
{body}
<footer>
数据截至 {esc(GENERATED_AT)}（行情与财务：东方财富 · akshare）<br />
申万一级行业与产业链环节归属为真实公开归类；<b>上下游连线为模型推断的模拟数据，未经核实</b>——「同属一条产业链」不等于「谁给谁供货」。不构成任何投资建议。
</footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------- 载入数据
idx = load("index.json")
graph = load("graph.json")
chains = load("chains.json") or {}
GENERATED_AT = idx.get("generatedAt", date.today().isoformat())

companies = idx["companies"]
by_ticker = {c["ticker"]: c for c in companies}
board_list = graph["boardList"]
board_names_of = {t: [board_list[i] for i in bis] for t, bis in graph["boardIdxOf"].items()}

og_slugs = {}   # 行业 → og 图文件名（make_og.py 用同名产出）


def quote1(code):
    return load(f"f/{code}.json") or {}


def company_url(code):
    return f"c/{code}.html"


def industry_url(ind):
    # 磁盘文件名用中文原文（电子.html），URL 出现在 sitemap/canonical 时才百分号编码
    return f"i/{ind}.html"


# ---------------------------------------------------------------- 公司页
def company_page(c):
    t = c["ticker"]
    q = quote1(t)
    boards = board_names_of.get(t, [])
    link = (chains.get("links") or {}).get(t)

    # 行情快照
    rows = []
    if q:
        pe = "亏损" if q.get("lossMaking") else (f"{q['trailingPE']:.1f}" if q.get("trailingPE") is not None else "—")
        rows = [
            ("最新价", fmt_price(q.get("price"))),
            ("涨跌幅", f'<b class="{chg_class(q.get("changePercent"))}">{fmt_pct(q.get("changePercent"))}</b>'),
            ("总市值", fmt_cap(q.get("marketCap"))),
            ("市盈率 TTM", pe),
            ("市盈率(动)", f"{q['forwardPE']:.1f}" if q.get("forwardPE") is not None else "—"),
            ("毛利率", "—" if q.get("grossMargins") is None else f"{q['grossMargins']:.2f}%"),
            ("净利率", "—" if q.get("profitMargins") is None else f"{q['profitMargins']:.2f}%"),
            ("营收增速", "—" if q.get("revenueGrowth") is None else f"{q['revenueGrowth']:.2f}%"),
            ("每股收益", "—" if q.get("trailingEps") is None else f"{q['trailingEps']:.2f}"),
            ("数据日期", q.get("asOf", "—")),
        ]
    metrics_html = ("<table class='stats'><tr>" + "".join(
        f"<td class='stat'><b>{v}</b><span>{esc(k)}</span></td>" for k, v in rows[:5]
    ) + "</tr><tr>" + "".join(
        f"<td class='stat'><b>{v}</b><span>{esc(k)}</span></td>" for k, v in rows[5:]
    ) + "</tr></table>") if rows else "<p class='note'>行情数据暂缺。</p>"

    # 上下游（推断）：手工卡片优先（有 tier/via），否则 chains.json
    up, down = [], []
    card = load(f"{t}.json") if c.get("curated") else None
    if card:
        for n in card.get("nodes", []):
            item = (n.get("name") or by_ticker.get(n.get("ticker"), {}).get("name", n.get("ticker")),
                    n.get("ticker"), n.get("role") or "", n.get("relation"))
            (up if n.get("relation") == "upstream" else down).append(item)
    elif link:
        def names(entries):
            out = []
            for bi, tk, role in entries:
                nm = by_ticker.get(tk, {}).get("name", tk)
                bname = board_list[bi] if isinstance(bi, int) and bi < len(board_list) else ""
                out.append((nm, tk, f"{role} · {bname}" if role and bname else role or bname, None))
            return out
        up, down = names(link.get("u", [])), names(link.get("d", []))

    def rel_html(direction, items):
        if not items:
            return f"<p class='note'>{'上游' if direction == 'up' else '下游'}：现有步进表下推不出关系。</p>"
        lis = "".join(
            f"<li><span class='dir {'down' if direction == 'down' else ''}'>"
            f"{'下游' if direction == 'down' else '上游'}</span>"
            f"<a href='../c/{esc(tk)}.html'>{esc(nm)}</a>"
            f"<span class='tk' style='color:var(--faint);font-size:13px'>{esc(tk)}</span>"
            f"<span class='role'>{esc(role)}</span></li>"
            for nm, tk, role, _ in items)
        return f"<ul class='rel-list'>{lis}</ul>"

    ind = c["industry"]
    peers = c.get("industryPeers")
    body = f"""
<h1>{esc(c['name'])}<span class="tk">{esc(t)} · {esc(c.get('exchange', ''))}{esc(c.get('board', ''))}</span></h1>
<div class="tags"><a class="tag sector" href="../i/{esc(ind)}.html">{esc(ind)}</a>
<span class="tag">{esc(c.get('board', ''))}</span>
{'<span class="tag">手工梳理价值链</span>' if c.get('curated') else ''}</div>
{metrics_html}
<h2>所属产业链环节<span class="sub">真实公开归类 · 同属一条产业链 ≠ 谁给谁供货</span></h2>
<div class="chips">{''.join(f"<span class='chip'>{esc(b)}</span>" for b in boards) or '<span class=note>无</span>'}</div>
{'' if not peers else f'<p class="note">同行业有 {peers} 家公司在产业链图谱中与本司共享环节。</p>'}
<h2>上下游关系<span class="sub">模型推断的模拟数据，未经核实</span></h2>
<div class="warn">以下连线是按行业步进表 + 环节归属<b>推断的结构示意</b>，不代表真实的供货关系。</div>
<div class="grid2"><div>{rel_html('up', up)}</div><div>{rel_html('down', down)}</div></div>
<span class="open-app"><a href="{SITE_BASE}/#/c/{esc(t)}">在交互图谱中打开 →</a></span>
"""
    desc = (f"{c['name']}（{t}）的产业链位置：所属{c['industry']}行业，"
            f"归入 {len(boards)} 个产业链环节；上下游关系为模型推断示意，不构成投资建议。")
    return page_shell(f"{c['name']}（{t}）的产业链位置 · 链谱 ChainAtlas", desc,
                      f"pages/c/{t}.html", body)


# ---------------------------------------------------------------- 行业页
def chg_class(v):
    if v is None:
        return "flat"
    return "rise" if v > 0 else ("fall" if v < 0 else "flat")


def industry_page(ind):
    members = graph["industries"].get(ind, [])
    member_set = set(members)
    # 环节分布
    freq = {}
    for tk in members:
        for bi in graph["boardIdxOf"].get(tk, []):
            freq[bi] = freq.get(bi, 0) + 1
    dist = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    top = dist[:TOP_BOARDS]
    rest = len(dist) - len(top)
    # 统计
    cap = chg_sum = chg_n = 0
    for tk in members:
        c = by_ticker.get(tk)
        if not c:
            continue
        cap += c.get("marketCap") or 0
        if c.get("changePercent") is not None:
            chg_sum += c["changePercent"]
            chg_n += 1
    avg = chg_sum / chg_n if chg_n else None
    # 龙头（按市值）
    leaders = sorted((by_ticker[tk] for tk in member_set if tk in by_ticker),
                     key=lambda c: -(c.get("marketCap") or 0))[:TOP_COMPANIES]

    dist_rows = "".join(
        f"<tr><td>{esc(board_list[bi])}</td><td class='num'>{n}</td></tr>" for bi, n in top)
    if rest > 0:
        dist_rows += f"<tr><td class='note'>…… 还有 {rest} 个环节</td><td></td></tr>"

    lead_rows = "".join(
        f"<tr><td><a href='../c/{c['ticker']}.html'>{esc(c['name'])}</a>"
        f"<span class='tk' style='color:var(--faint);font-size:13px'> {esc(c['ticker'])}</span></td>"
        f"<td class='num'>{fmt_price(c.get('price'))}</td>"
        f"<td class='num {chg_class(c.get('changePercent'))}'>{fmt_pct(c.get('changePercent'))}</td>"
        f"<td class='num'>{fmt_cap(c.get('marketCap'))}</td></tr>"
        for c in leaders)

    body = f"""
<h1>{esc(ind)}行业 · 产业链图谱</h1>
<div class="stats">
  <div class="stat"><b>{len(members)}</b><span>家上市公司</span></div>
  <div class="stat"><b>{len(dist)}</b><span>个产业链环节</span></div>
  <div class="stat"><b>{fmt_cap(cap)}</b><span>市值合计</span></div>
  <div class="stat"><b class="{chg_class(avg)}">{fmt_pct(avg)}</b><span>平均涨跌幅</span></div>
</div>
<h2>产业链环节分布<span class="sub">按环节内的公司数排序</span></h2>
<table><tr><th>环节</th><th class='num'>公司数</th></tr>{dist_rows}</table>
<h2>龙头公司<span class="sub">按市值排序 · 点击进公司页</span></h2>
<table><tr><th>公司</th><th class='num'>最新价</th><th class='num'>涨跌幅</th><th class='num'>总市值</th></tr>
{lead_rows}</table>
<div class="warn">行业与环节归属为真实公开归类；公司页的上下游连线为模型推断的模拟数据，未经核实。不构成投资建议。</div>
<span class="open-app"><a href="{SITE_BASE}/#/i/{quote(ind)}">在交互图谱中打开 →</a></span>
"""
    desc = (f"{ind}行业产业链图谱：{len(members)} 家 A 股上市公司、{len(dist)} 个产业链环节，"
            f"环节分布与龙头公司一览。数据截至 {GENERATED_AT}。")
    return page_shell(f"{ind}行业产业链图谱 · 链谱 ChainAtlas", desc,
                      f"pages/{industry_url(ind)}", body,
                      extra_head=f'<meta property="og:image" content="{esc(SITE_BASE)}/assets/og/{quote(ind)}.png" />')


# ---------------------------------------------------------------- 主流程
def write_page(rel, html):
    path = os.path.join(PAGES, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    # 样式单独立一份（4,095 个页面共用，别每个文件内联一遍）
    os.makedirs(PAGES, exist_ok=True)
    with open(os.path.join(PAGES, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)

    industries = idx["industryList"]
    print(f"① 行业页 × {len(industries)}")
    for ind in industries:
        write_page(industry_url(ind), industry_page(ind))

    print(f"② 公司页 × {len(companies)}")
    for c in companies:
        write_page(company_url(c["ticker"]), company_page(c))

    print("③ sitemap.xml / robots.txt")
    urls = [("/pages/" + industry_url(i), "0.8") for i in industries]
    urls += [(f"/pages/c/{c['ticker']}.html", "0.6") for c in companies]
    urls.insert(0, ("/", "1.0"))
    sm = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
          "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"]
    sm += [f"  <url><loc>{SITE_BASE}{quote(u, safe='/%')}</loc><priority>{p}</priority></url>"
           for u, p in urls]
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")
    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n")

    print(f"   共 {len(urls)} 个地址（SITE_BASE={SITE_BASE}）")
    print("完。")


if __name__ == "__main__":
    main()
