# -*- coding: utf-8 -*-
"""
本地预览服务（带 no-store，专治"改了代码浏览器还在用旧版"）

为什么不用 python -m http.server：
它只发 Last-Modified、不发 Cache-Control，浏览器于是按"启发式"自行决定缓存多久——
规则大致是"距上次修改时间的 10%"。文件越久没改，它敢缓存的时间就越长：
一个昨天下午改过的 app.js，今天上午打开会被浏览器缓存一个多小时，期间刷新根本不问服务器。
表现就是"改了代码、刷新、还是旧页面"，而且控制台一句报错都没有。

用法：
    python serve.py [端口]        # 默认 8123

只监听 127.0.0.1（本机），不对外暴露。
"""

import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
ROOT = os.path.dirname(os.path.abspath(__file__))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # 三件套都发：老的 HTTP/1.0 代理只认 Pragma/Expires
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # 静音：默认会把每个请求都刷到控制台，没必要


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True   # 重启时不会因为端口还在 TIME_WAIT 而失败
    daemon_threads = True


def main():
    try:
        with Server(("127.0.0.1", PORT), NoCacheHandler) as httpd:
            print()
            print("  链谱（ChainAtlas）—— 本地预览")
            print("  --------------------------------------------------")
            print(f"  在浏览器打开:  http://127.0.0.1:{PORT}/")
            print("  停止服务:      按 Ctrl+C，或直接关掉这个窗口")
            print()
            print("  浏览期间请保持这个窗口开着。")
            print()
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    except OSError as e:
        print()
        print(f"  启动失败：{e}")
        print(f"  端口 {PORT} 可能已被占用（也许上次的服务还开着）。")
        print(f"  换个端口试试：python serve.py {PORT + 1}")
        print()


if __name__ == "__main__":
    main()
