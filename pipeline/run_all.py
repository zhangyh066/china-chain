# -*- coding: utf-8 -*-
"""一键跑完数据管线（README"数据管线"六步的封装）：

  ① fetch_real.py        行情与财务快照（全市场 4 次请求）
  ② fetch_industries.py  申万行业与成分股
  ③ fetch_concepts.py all 概念板块与成分股
  ④ select_companies.py  按筛选标准挑出入库公司 → real/selected.json
  ⑤ build_chain.py       组装 data/ 发布产物（index/graph/chain_steps 等）
  ⑥ fabricate_chains.py  行业级上下游推断连线

每步用子进程跑 sys.executable，前一步失败即停（exit 非零），不带着脏数据往下走。

开关：
  --with-history  追加第 ⑦ 步 fetch_history.py（逐股日线历史，约 4000 次请求，
                  全量要几个小时——日常刷新不建议开，抓过有缓存才快）
  --refresh       透传给支持它的子脚本（fetch_real.py 删行情缓存重拉、
                  fetch_history.py 无视缓存重抓；其余脚本本来就不吃这个参数）

末尾固定追加四步（依赖未就绪就跳过，不算失败）：build_trends.py（日线 →
行业/环节趋势指数，仅当 data/h/ 存在时跑）、build_chains.py（产业链深耕
产物，仅当 data/p/ 存在时跑）、build_transmission.py（传导时滞，离线，
仅当 data/chain/ 存在时跑）、build_purity.py（概念纯度，离线，仅当
data/p/ 存在时跑，读当轮 chain 产物）。

supply 之后是两个离线汇总步：build_chain_disclosure.py（链内披露连线，
读 supply.json + data/chain/）、build_health.py（数据健康度快照，只读 data/，
#/health 页渲染）。最后固定跑 prerender.py 重生成 pages/ 与 sitemap/robots
（公司名单变了静态页必须跟着变，否则 ci_check 的页数断言会把 CI 锁死）。

purity 之后还有本地专属一步 build_supply.py（披露级供应链：前五大客户/
供应商实名明细与集中度）：原始数据是 新建文件夹/ 下的 CNRDS 表，许可
红线——仅限本机使用，绝不入库、绝不外传（新建文件夹/ 已加 .gitignore）。
原始文件不存在（如 CI runner）时静默跳过，不算失败。

用法：
  python run_all.py                  # 六步，增量（有缓存的自动跳过联网）
  python run_all.py --refresh        # 六步，行情强制重拉
  python run_all.py --with-history   # 六步 + 日线历史增量补抓 + 趋势指数
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ("fetch_real.py", True),        # (脚本, 是否接受 --refresh)
    ("fetch_industries.py", False),
    ("fetch_concepts.py", False),   # 固定带 all 参数，见下
    ("select_companies.py", False),
    ("build_chain.py", False),
    ("fabricate_chains.py", False),
]
HISTORY_STEP = ("fetch_history.py", True)
PURITY_STEP = ("build_purity.py", False)
TRENDS_STEP = ("build_trends.py", False)
CHAINS_STEP = ("build_chains.py", False)
TRANSMISSION_STEP = ("build_transmission.py", False)
SUPPLY_STEP = ("build_supply.py", False)
DISCLOSURE_STEP = ("build_chain_disclosure.py", False)
HEALTH_STEP = ("build_health.py", False)
PRERENDER_STEP = ("prerender.py", False)


def run(script, args):
    cmd = [sys.executable, os.path.join(HERE, script)] + args
    print(f"\n{'=' * 70}\n>>> {script} {' '.join(args)}\n{'=' * 70}", flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE)
    dt = time.time() - t0
    if r.returncode != 0:
        print(f"\nXX {script} 失败（exit {r.returncode}，耗时 {dt/60:.1f} 分钟）"
              f"——后续步骤不执行", flush=True)
        return r.returncode
    print(f"<<< {script} 完成（{dt/60:.1f} 分钟）", flush=True)
    return 0


def main():
    refresh = "--refresh" in sys.argv
    with_history = "--with-history" in sys.argv

    steps = list(STEPS) + ([HISTORY_STEP] if with_history else [])
    t0 = time.time()
    for i, (script, takes_refresh) in enumerate(steps, 1):
        args = ["--refresh"] if (refresh and takes_refresh) else []
        if script == "fetch_concepts.py":
            args = ["all"]
        rc = run(script, args)
        if rc:
            print(f"\n[FAIL] 第 {i}/{len(steps)} 步中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc

    # 概念纯度（离线，依赖 data/p + graph.json + 当轮 chain 产物）：放在 chains 之后
    n_steps = len(steps)
    data_dir = os.path.join(os.path.dirname(HERE), "data")
    if os.path.isdir(os.path.join(data_dir, "h")):
        rc = run(TRENDS_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_trends.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_trends.py：data/h/ 不存在"
              "（先跑 --with-history 抓日线）", flush=True)

    # 产业链深耕产物依赖 data/p/ 公司档案：有档案才跑，缺了跳过（不算失败）
    if os.path.isdir(os.path.join(data_dir, "p")):
        rc = run(CHAINS_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_chains.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_chains.py：data/p/ 不存在"
              "（先跑前五步生成公司档案）", flush=True)

    # 传导时滞（离线，依赖 chain 产物与期货价格文件）：data/chain 在才跑
    if os.path.isdir(os.path.join(data_dir, "chain")):
        rc = run(TRANSMISSION_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_transmission.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_transmission.py：data/chain/ 不存在", flush=True)

    # 概念纯度（离线，依赖 data/p + graph.json + 当轮 chain 产物）：data/p 在才跑
    if os.path.isdir(os.path.join(data_dir, "p")):
        rc = run(PURITY_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_purity.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_purity.py：data/p/ 不存在", flush=True)

    # 披露级供应链（本地专属）：原始表在 新建文件夹/ 下才跑，CI 上没有就静默跳过。
    # 许可红线：原始数据仅限本机使用，绝不入库、绝不外传（新建文件夹/ 已加 .gitignore）
    raw_dir = os.path.join(os.path.dirname(HERE), "新建文件夹")
    has_raw = os.path.isdir(raw_dir) and any(
        "SC_TopFiveSaleInfo.xlsx" in files
        for _dp, _dn, files in os.walk(raw_dir))
    if has_raw:
        rc = run(SUPPLY_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_supply.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_supply.py：新建文件夹/ 无 CNRDS 原始表"
              "（本地专属数据，CI 上属预期）", flush=True)

    # 链内披露连线（离线，读已入库的 supply.json + data/chain/）：链页的披露区块与链评卡用
    if os.path.isfile(os.path.join(data_dir, "supply.json")) and os.path.isdir(os.path.join(data_dir, "chain")):
        rc = run(DISCLOSURE_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_chain_disclosure.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc

    # 数据健康度快照（离线，只读 data/）：放在所有产物步之后、prerender 之前，
    # #/health 页如实展示各源新旧
    rc = run(HEALTH_STEP[0], [])
    n_steps += 1
    if rc:
        print(f"\n[FAIL] build_health.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
        return rc

    # 静态页/sitemap 必须与 data/ 同步再生成：ci_check 断言"页数 = 公司数"，
    # 公司名单一变（IPO/退市/概念漂移），pages/ 不重跑整个 CI 就被页数断言锁死
    rc = run(PRERENDER_STEP[0], [])
    n_steps += 1
    if rc:
        print(f"\n[FAIL] prerender.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
        return rc

    print(f"\n[ok] {n_steps} 步全部完成，总耗时 {(time.time()-t0)/60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
