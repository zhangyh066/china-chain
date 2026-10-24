# -*- coding: utf-8 -*-
"""代码段 → 市场/交易所 的统一映射（全管线共用，别再各抄一份）。

A 股 6 位代码段：
  6 开头 = 沪市（600/601/603/605 主板、688/689 科创板）；900xxx = 沪 B
  0 开头 = 深市（000/001/002/003 主板、300/301 创业板）；200xxx = 深 B
  4/8 开头 = 北交所（430/83x/87x/88x）；920xxx = 北交所新代码段
  ⚠ 920 要先于"9=沪 B"判断。

当前入选名单（selected.json）只有 0/3/6 开头，北交所分支是潜伏修复：
东财概念板块含北交所标的，入选只是时间问题。北交所的接口前缀
（腾讯 bj / 东财主营构成 BJ）未经真实标的验证，真有北交所公司入选时
留意首抓日志。
"""


def exchange_cn(code: str) -> str:
    """中文交易所名（站点展示口径，与 board_of 的兜底一致）。"""
    if code.startswith(("4", "8", "92")):
        return "北交所"
    return "上交所" if code.startswith(("6", "9")) else "深交所"


def tencent_sym(code: str) -> str:
    """腾讯日 K 接口（stock_zh_a_hist_tx）的 sh/sz/bj 前缀代码。"""
    pfx = ("bj" if code.startswith(("4", "8", "92"))    # 92 先于 9（沪 B）判
           else "sh" if code.startswith(("6", "9")) else "sz")
    return pfx + code


def em_zygc_sym(code: str) -> str:
    """东财主营构成接口（stock_zygc_em）的 SH/SZ/BJ 前缀代码。"""
    pfx = ("BJ" if code.startswith(("4", "8", "92"))    # 92 先于 9（沪 B）判
           else "SH" if code.startswith(("6", "9")) else "SZ")
    return pfx + code
