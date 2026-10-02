# -*- coding: utf-8 -*-
"""fetch_profiles.py 的超时看门狗：单批有界、整轮无限续跑。

背景：个别 HTTP 请求会永久挂起（akshare 底层无读超时），一个挂起的 socket
能冻住整轮抓取（2026-10-02 实测：进程活着但 100 分钟无产出）。
对策：每批最多 300 家 / 10 分钟，超时就杀掉进程开新批——缓存断点续抓，
被杀那家没写缓存，下批自动重试，不会丢也不会卡。

用法：python _crawl_watchdog.py
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
CACHE = os.path.join("real", "profiles")

BATCH = "300"
BATCH_TIMEOUT = 600      # 秒。300 家正常约 9 分钟，超时即判定有请求挂死


def remaining():
    sel = json.load(open(os.path.join("real", "selected.json"), encoding="utf-8"))
    return [c["ticker"] for c in sel["companies"]
            if not os.path.exists(os.path.join(CACHE, c["ticker"] + ".json"))]


def main():
    rnd = 0
    while True:
        todo = remaining()
        print(f"== 第 {rnd} 批：剩余 {len(todo)} 家 ==", flush=True)
        if not todo:
            break
        t0 = time.time()
        try:
            subprocess.run([sys.executable, "fetch_profiles.py",
                            "--batch", BATCH], timeout=BATCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"== 批次超时（>{BATCH_TIMEOUT}s），强杀开新批；"
                  f"本批耗时 {time.time()-t0:.0f}s ==", flush=True)
        rnd += 1
    n = len(os.listdir(os.path.join("..", "data", "p")))
    print(f"[done] 全部抓完，data/p/ 共 {n} 家", flush=True)


if __name__ == "__main__":
    main()
