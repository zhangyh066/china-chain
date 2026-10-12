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

末尾固定追加两步：build_trends.py（日线 → 行业/环节趋势指数，仅当 data/h/
目录存在时跑）与 build_lithium.py（锂电产业链深耕产物，仅当 data/p/ 存在时跑）
——依赖未就绪就跳过，不算失败。

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
TRENDS_STEP = ("build_trends.py", False)
LITHIUM_STEP = ("build_lithium.py", False)


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

    # 趋势指数依赖 data/h/ 日线：抓过才跑，没抓过就跳过（不算失败）
    n_steps = len(steps)
    if os.path.isdir(os.path.join(os.path.dirname(HERE), "data", "h")):
        rc = run(TRENDS_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_trends.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_trends.py：data/h/ 不存在"
              "（先跑 --with-history 抓日线）", flush=True)

    # 锂电深耕产物依赖 data/p/ 公司档案：有档案才跑，缺了跳过（不算失败）
    if os.path.isdir(os.path.join(os.path.dirname(HERE), "data", "p")):
        rc = run(LITHIUM_STEP[0], [])
        n_steps += 1
        if rc:
            print(f"\n[FAIL] build_lithium.py 中断，总耗时 {(time.time()-t0)/60:.1f} 分钟")
            return rc
    else:
        print("\n-- 跳过 build_lithium.py：data/p/ 不存在"
              "（先跑前五步生成公司档案）", flush=True)

    print(f"\n[ok] {n_steps} 步全部完成，总耗时 {(time.time()-t0)/60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
