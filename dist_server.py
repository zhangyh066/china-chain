# -*- coding: utf-8 -*-
"""发布目录专用静态服务（部署到平台上跑的就是这个文件）。

为什么不用平台自带的静态服务：python -m http.server 不发任何缓存指令，
浏览器会按"启发式"缓存旧页面——改了名字/改了数据，用户打开还是旧的，且零报错。
这里给**所有**响应都加 Cache-Control: no-store：HTML、JS、语言包、数据全部
每次实拉，配上游的 ?v= 版本号，做到"发版即生效"。

只依赖标准库；端口读 PORT 环境变量、绑定 0.0.0.0（平台托管的要求）。
"""
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "3000"))
HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *args):
        pass   # 访问日志静默（平台上没人看，还刷屏）


if __name__ == "__main__":
    print(f"链谱 · 静态服务已启动：0.0.0.0:{PORT}（目录 {HERE}，全部 no-store）", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
