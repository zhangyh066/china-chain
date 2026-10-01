# -*- coding: utf-8 -*-
"""把"要发布的那一部分"复制到 dist/。

为什么需要这一步：整个 china-chain/ 有 183 MB，其中 .venv 147M、pipeline 30M
（抓取缓存 + 原始响应）、_verify 1.9M（测试截图）。这些都不该跟着站点上传——
又慢，又把不该公开的东西一起发出去。

站点本身只需要约 6 MB：外壳 + 三个 js/css + locales + content + data（含 f/ 行情明细）。

用法：
    python build_dist.py          # 重建 dist/
    python build_dist.py --check  # 只看会复制什么，不写盘
"""
import argparse
import filecmp
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

# 站点运行时真正会请求的东西。加东西前先想清楚：前端有没有 fetch 它？
INCLUDE_FILES = ["index.html", "app.js", "styles.css", "i18n.js",
                 "dist_server.py", "manifest.webmanifest",
                 "sitemap.xml", "robots.txt"]
INCLUDE_DIRS = ["locales", "content", "data", "assets", "pages"]

# 分享卡片 / sitemap 里的绝对地址。生产部署时应通过环境变量覆盖成真实域名：
#   SITE_BASE=https://example.com/ python build_dist.py
SITE_BASE = os.environ.get("SITE_BASE", "").rstrip("/") \
    or "https://0ebad93a143e456cbd2e30cb01966249.app.workbuddy.host"

# 明确排除的（列出来是为了让"为什么不发"有据可查，而不是靠印象）
EXCLUDE = [".venv", "pipeline", "_verify", "dist", "node_modules", ".git"]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n:.0f} B"
        n /= 1024


def tree_size(path):
    total = 0
    count = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            total += os.path.getsize(os.path.join(dirpath, f))
            count += 1
    return total, count


def build(check_only=False):
    # 安全检查：只允许删自己生成的 dist/，且必须就在项目根目录下
    if os.path.basename(DIST) != "dist" or os.path.dirname(DIST) != ROOT:
        sys.exit(f"拒绝执行：dist 路径异常 {DIST}")

    missing = [f for f in INCLUDE_FILES if not os.path.exists(os.path.join(ROOT, f))]
    missing += [d for d in INCLUDE_DIRS if not os.path.isdir(os.path.join(ROOT, d))]
    if missing:
        sys.exit(f"缺少必要文件/目录：{', '.join(missing)}")

    staging = DIST + ".tmp"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    for f in INCLUDE_FILES:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(staging, f))
    for d in INCLUDE_DIRS:
        shutil.copytree(os.path.join(ROOT, d), os.path.join(staging, d),
                        ignore=shutil.ignore_patterns(*EXCLUDE))

    size, count = tree_size(staging)
    print(f"  复制 {len(INCLUDE_FILES)} 个文件 + {len(INCLUDE_DIRS)} 个目录 → {count} 个文件，{human(size)}")

    # 版本号注入：源码里的 __BUILD__ 占位符换成构建时间戳（精确到分钟）。
    # 发布平台的服务器不带 Cache-Control，浏览器按启发式缓存旧文件——
    # 用户会看到"改了名字还显示旧页面"。版本参数让每次发版都强制拉新。
    build_id = time.strftime("%Y%m%d%H%M")
    built = []
    for f in ("index.html", "app.js", "i18n.js"):
        p = os.path.join(staging, f)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            n = txt.replace("__BUILD__", build_id).replace("__SITE_BASE__", SITE_BASE)
            if n != txt:
                open(p, "w", encoding="utf-8", newline="\n").write(n)
                built.append(f)
    print(f"  版本号注入 __BUILD__ → {build_id}；__SITE_BASE__ → {SITE_BASE}（{', '.join(built) or '无文件含占位符'}）")

    if check_only:
        shutil.rmtree(staging)
        print("  --check：已撤销，没有写盘")
        return

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.rename(staging, DIST)

    # 复制完之后逐字节验一遍，别让"看起来复制了"蒙过去
    bad = []
    for dirpath, _dirnames, filenames in os.walk(DIST):
        for f in filenames:
            a = os.path.join(dirpath, f)
            rel = os.path.relpath(a, DIST)
            if rel in ("index.html", "app.js", "i18n.js"):
                # 这三个文件被注入过版本号/站点地址，与源"应该"不同；只验证占位符确实被换掉了
                txt = open(a, encoding="utf-8", errors="replace").read()
                if "__BUILD__" in txt or "__SITE_BASE__" in txt:
                    bad.append(rel + "（占位符未注入）")
                continue
            b = os.path.join(ROOT, rel)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                bad.append(rel)
    src_size, _ = tree_size(ROOT)
    print(f"  字节级复核：{count - len(bad)}/{count} 个文件与源一致")
    if bad:
        sys.exit(f"  校验失败，以下文件与源不一致：{bad[:5]}")

    print(f"\n  dist/ 就绪：{human(size)}（源目录 {human(src_size)}）")
    for d in EXCLUDE:
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            print(f"    未包含 {d}/（{human(tree_size(p)[0])}）")
    print("\n  本地验证：python -m http.server 8124 --directory dist")
    print("  然后浏览器打开 http://127.0.0.1:8124/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只看会复制什么，不写盘")
    build(ap.parse_args().check)
