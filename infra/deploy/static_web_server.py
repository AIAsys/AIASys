#!/usr/bin/env python3
"""轻量静态站点服务器，支持 SPA fallback。"""

import argparse
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


class SPARequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: Optional[str] = None, **kwargs):
        self._base_dir = Path(directory or ".").resolve()
        super().__init__(*args, directory=str(self._base_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "3")
            self.end_headers()
            return
        super().do_HEAD()

    def end_headers(self) -> None:
        request_path = self.path.split("?", 1)[0].split("#", 1)[0]
        if request_path in {"/", "/index.html"} or request_path.endswith(".html"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif request_path.startswith("/assets/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()

    def send_head(self):  # type: ignore[override]
        candidate = Path(super().translate_path(self.path))
        if candidate.exists():
            return super().send_head()

        request_path = self.path.split("?", 1)[0].split("#", 1)[0]
        if request_path.startswith("/api/") or Path(request_path).suffix:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        self.path = "/index.html"
        return super().send_head()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a SPA dist directory.")
    parser.add_argument("--dir", default="dist", help="静态资源目录")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=13000, help="监听端口")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    directory = Path(args.dir).resolve()
    if not directory.exists():
        raise SystemExit(f"dist 目录不存在: {directory}")

    handler = partial(SPARequestHandler, directory=str(directory))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
