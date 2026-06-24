from __future__ import annotations

import http.server
import os
import socketserver
import urllib.error
import urllib.request
from pathlib import Path


# 打包后路径: resources/web/scripts/committed/local_preview_server.py
# dist 目录在 resources/web/dist，需要从 __file__ 向上退 3 级
ROOT = Path(__file__).resolve().parent.parent.parent / "dist"
BACKEND = os.environ.get("AIASYS_PREVIEW_BACKEND_URL", "http://127.0.0.1:13001")
HOST = os.environ.get("AIASYS_PREVIEW_HOST", "127.0.0.1")
PORT = int(os.environ.get("AIASYS_PREVIEW_PORT", "13000"))
CHUNK_SIZE = 64 * 1024
_LONG_LIVED_STREAM_PATHS = {"/api/agent/execute/stream"}
SSE_READ_SIZE = 4 * 1024

# TODO: 当前 preview server 基于 http.server，没有实现 WebSocket Upgrade 代理。
# 在桌面版中，终端 WebSocket 已由 Electron 主进程把后端地址注入前端，前端直接连接后端端口，
# 因此不受此限制影响。若单独运行 preview server（非桌面打包场景），终端面板需要额外配置
# 支持 WebSocket 的反向代理（如 nginx），或为本脚本增加原生 WebSocket 代理能力。


class ThreadingPreviewServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        # 过滤路径穿越：把路径拆成段，拒绝任何 ".." 段
        relative = path.lstrip("/").lstrip("\\")
        segments = [p for p in relative.replace("\\", "/").split("/") if p and p != "."]
        if any(segment == ".." for segment in segments):
            return str(ROOT / "__forbidden__")
        return str(ROOT / "/".join(segments))

    def _proxy_timeout(self) -> int:
        if self.path.startswith(tuple(_LONG_LIVED_STREAM_PATHS)):
            return 60 * 60
        return 60

    def _is_long_lived_stream(self) -> bool:
        return self.path.startswith(tuple(_LONG_LIVED_STREAM_PATHS))

    def _stream_sse_body(self, source: urllib.request.addinfourl) -> None:
        reader = getattr(source, "read1", None)
        if callable(reader):
            while True:
                chunk = reader(SSE_READ_SIZE)
                if not chunk:
                    return
                self.wfile.write(chunk)
                self.wfile.flush()
            return

        while True:
            line = source.readline()
            if not line:
                return
            self.wfile.write(line)
            self.wfile.flush()

    def _stream_response_body(self, source: urllib.request.addinfourl) -> None:
        if self._is_long_lived_stream():
            self._stream_sse_body(source)
            return

        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                return
            self.wfile.write(chunk)
            self.wfile.flush()

    def _proxy(self) -> None:
        target = BACKEND + self.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        # 先把请求体读入内存再转发；http.server 的 self.rfile 直接传给 urllib
        # 在 Windows 上会导致 POST/PUT 请求挂起，因此显式读取。
        body = self.rfile.read(length) if length > 0 else None

        request = urllib.request.Request(target, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() in {"host", "connection"}:
                continue
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=self._proxy_timeout()) as response:
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self._stream_response_body(response)
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in {"transfer-encoding", "connection"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self._stream_response_body(exc)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - local preview fallback
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"frontend proxy error: {exc}".encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/") or self.path == "/health":
            self._proxy()
            return

        file_path = Path(self.translate_path(self.path))
        if file_path.is_file():
            super().do_GET()
            return

        self.path = "/index.html"
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path.startswith("/api/") or self.path == "/health":
            self._proxy()
            return

        file_path = Path(self.translate_path(self.path))
        if file_path.is_file():
            super().do_HEAD()
            return

        self.path = "/index.html"
        super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()


def main() -> None:
    os.chdir(ROOT)
    with ThreadingPreviewServer((HOST, PORT), PreviewHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
