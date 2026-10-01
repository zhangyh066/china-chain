# -*- coding: utf-8 -*-
"""一键日更：拉最新行情 → 重建数据 → 自检 → 重建发布目录。

按顺序做五件事，任一步失败立即退出（非 0），后面的步骤不跑：
  1. fetch_real.py --refresh   清掉行情缓存，重新拉（4 个请求：全市场快照 + 三期业绩）
  2. build_chain.py            用新行情重组 data/*.json（index / graph / fundamentals…）
  3. fabricate_chains.py       按新市值重推上下游 → data/chains.json
  4. 自检：公司数 / 边数 / 孤立点 / generatedAt 必须是今天
  5. build_dist.py             重建发布目录（含字节级复核）

行业与环节（fetch_industries / fetch_concepts，合计 216 个请求）**不在日更范围**：
它们月度级别才变，缓存一直在 pipeline/real/ 下，改口径时单独跑。

日志按行追加到 refresh_log.txt：时间 / 总耗时 / 关键数字。
用法：.venv/Scripts/python.exe daily_refresh.py [--skip-fetch]
"""
import json
import os
import subprocess
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(HERE, "refresh_log.txt")
PY = sys.executable


def run(label, args, cwd=HERE):
    t0 = time.time()
    print(f"\n=== {label} ===")
    # 剥掉代理环境变量：实测本机 shell 里的 http_proxy 会让东财接口
    # 直接断连（RemoteDisconnected），东财是国内站，直连就行。
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    r = subprocess.run([PY] + args, cwd=cwd, env=env)
    dt = time.time() - t0
    print(f"--- {label} 用时 {dt:.1f}s，退出码 {r.returncode}")
    if r.returncode != 0:
        print(f"✗ {label} 失败，日更中止")
        log_line(False, label=f"{label} 失败（退出码 {r.returncode}）")
        sys.exit(r.returncode)
    return dt


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def log_line(ok, **kw):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "\t" + ("OK " if ok else "FAIL") + "\t" + \
        "  ".join(f"{k}={v}" for k, v in kw.items())
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def self_check():
    idx = load(os.path.join(DATA, "index.json"))
    comp = idx["companies"]
    fund = load(os.path.join(DATA, "fundamentals.json"))
    chains = load(os.path.join(DATA, "chains.json"))
    links = chains.get("links", {})
    edges = sum(len(v.get("u", [])) + len(v.get("d", [])) for v in links.values())
    orphans = [c["ticker"] for c in comp if c.get("nodeCount") == 0]
    sim = [t for t, v in fund["quotes"].items() if v.get("simulated")]
    today = date.today().isoformat()

    problems = []
    if idx.get("generatedAt") != today:
        problems.append(f"generatedAt={idx.get('generatedAt')} 不是今天")
    if len(comp) < 4000:
        problems.append(f"公司数 {len(comp)} 异常（应约 4071）")
    if len(fund["quotes"]) != len(comp):
        problems.append(f"行情条数 {len(fund['quotes'])} != 公司数 {len(comp)}")
    if sim:
        problems.append(f"有 {len(sim)} 家是模拟行情（应为 0）：{sim[:5]}")
    if orphans:
        problems.append(f"孤立点 {len(orphans)} 家：{orphans[:5]}")
    if edges < 20000:
        problems.append(f"边数 {edges} 异常（应约 2.6 万）")

    print(f"\n=== 自检 ===")
    print(f"  公司 {len(comp)} · 行业 {len(idx.get('industries', []))} · "
          f"环节 {idx.get('totals', {}).get('boards', '?')} · 边 {edges} · "
          f"孤立点 {len(orphans)} · 模拟行情 {len(sim)} · generatedAt {idx.get('generatedAt')}")
    if problems:
        print("  ✗ " + "；".join(problems))
        return False, {}
    print("  ✓ 全部通过")
    return True, {
        "companies": len(comp), "edges": edges,
        "orphans": len(orphans), "links": len(links),
        "asOf": fund["quotes"][comp[0]["ticker"]].get("asOf"),
    }


def main():
    t0 = time.time()
    if "--skip-fetch" not in sys.argv:
        # 东财这条线**间歇性断连**（同一条命令隔几分钟结果就不同，2026-09-26 实测），
        # 所以失败后等 5 分钟整轮重试一次；两次都不行就认输记日志，绝不硬撞。
        for rnd in range(2):
            try:
                run("① 拉最新行情（4 个请求）", ["fetch_real.py", "--refresh"])
                break
            except SystemExit:
                if rnd == 0:
                    print("\n… 第一轮失败，等 5 分钟再试一轮（断连是间歇性的）…")
                    time.sleep(300)
                else:
                    log_line(False, label="两轮拉取均失败（网络间歇断连）")
                    sys.exit(1)
    else:
        print("① 跳过联网（--skip-fetch），直接用现有缓存组装")
    run("② 重建 data/*.json", ["build_chain.py"])
    run("③ 重推上下游", ["fabricate_chains.py"])
    ok, stats = self_check()
    if not ok:
        log_line(False, **stats)
        sys.exit(2)
    run("④ 重建发布目录", ["build_dist.py"], cwd=ROOT)
    total = time.time() - t0
    print(f"\n✓ 日更完成，总耗时 {total/60:.1f} 分钟")
    log_line(True, total=f"{total:.0f}s", **stats)


if __name__ == "__main__":
    main()
