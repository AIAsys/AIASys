#!/usr/bin/env python3
"""PDF 翻译脚本 — 通过 pdf2zh 翻译当前工作区内的 PDF 文件。

用法:
    python3 translate.py --pdf_path /workspace/doc.pdf [--source_lang en] [--target_lang zh] [--translator google]
    python3 translate.py --pdf_path /workspace/doc.pdf --pages 1-10   # 只翻译前 10 页

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录（由 Shell 自动注入）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    cwd = Path.cwd()
    if (cwd / "metadata.json").exists():
        return cwd
    raise RuntimeError("无法确定工作区根目录，请设置 AIASYS_WORKSPACE_ROOT 环境变量")


def resolve_path(raw_path: str, workspace_root: Path) -> tuple[Path, str]:
    """解析用户传入的路径，返回 (宿主机绝对路径, 可见路径)。

    支持以下输入格式：
      - /workspace/foo.pdf  → 工作区根目录下的 foo.pdf
      - /workspace/sub/bar.pdf → 工作区根目录下的 sub/bar.pdf
      - foo.pdf              → 工作区根目录下的 foo.pdf（相对路径）
      - sub/bar.pdf          → 工作区根目录下的 sub/bar.pdf（相对路径）
    """
    raw_path = raw_path.strip()
    # 去掉 /workspace/ 前缀，映射到工作区根目录
    if raw_path.startswith("/workspace/"):
        rel_str = raw_path[len("/workspace/") :]
    elif raw_path == "/workspace":
        rel_str = "."
    elif raw_path.startswith("/"):
        # 其他绝对路径不处理，保持原样
        rel_str = raw_path.lstrip("/")
    else:
        rel_str = raw_path

    rel = Path(rel_str)
    host_path = (workspace_root / rel).resolve()
    try:
        host_path.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出当前 workspace: {raw_path}")

    visible = "/workspace/" + rel.as_posix() if rel != Path(".") else "/workspace"
    return host_path, visible


def get_pdf2zh_command() -> list[str]:
    """构建 pdf2zh 的隔离运行命令。

    pdf2zh 依赖 openai → pydantic → pydantic-core（Rust 扩展），
    在较新的 Python（如 3.14）上可能因 PyO3 版本不匹配而编译失败。
    指定 Python 3.12 兼容版本避免此问题。
    """
    py_version = "3.12"
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--python", py_version, "--from", "pdf2zh", "pdf2zh"]
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "run", "--python", py_version, "--from", "pdf2zh", "pdf2zh"]
    raise RuntimeError(
        "未找到 uvx 或 uv，无法启动隔离的 pdf2zh 运行环境。\n"
        "请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    )


def run_translate(
    *,
    pdf_path: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
    translator: str,
    ignore_cache: bool,
    pages: str | None,
) -> tuple[str, str]:
    runner = get_pdf2zh_command()
    command = [
        *runner,
        "--service",
        translator,
        "--lang-in",
        source_lang,
        "--lang-out",
        target_lang,
        "--output",
        str(output_dir),
    ]
    if ignore_cache:
        command.append("--ignore-cache")
    if pages:
        command.extend(["--pages", pages])
    command.append(str(pdf_path))

    # 流式输出：pdf2zh 的进度信息打到 stderr，实时透传给调用方
    # 不再使用 capture_output=True（会导致长时间无输出、无法看到进度）
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # 透传 pdf2zh 的输出，同时收集用于错误判断
    collected: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        line_stripped = line.rstrip()
        if line_stripped:
            print(f"[pdf2zh] {line_stripped}", file=sys.stderr, flush=True)
            collected.append(line_stripped)

    return_code = process.wait(timeout=1800)

    if return_code != 0:
        output = "\n".join(collected[-20:])  # 最后 20 行用于错误诊断
        raise RuntimeError(f"pdf2zh 执行失败 (exit {return_code}):\n{output or '未知错误'}")

    mono = output_dir / f"{pdf_path.stem}-mono.pdf"
    dual = output_dir / f"{pdf_path.stem}-dual.pdf"
    if not mono.exists() or not dual.exists():
        # 列出输出目录内容辅助排查
        existing = [f.name for f in output_dir.iterdir()] if output_dir.exists() else []
        raise RuntimeError(
            f"pdf2zh 执行完成，但未生成预期的 mono/dual PDF 文件。\n"
            f"期望: {mono.name}, {dual.name}\n"
            f"目录内容: {existing or '空目录'}"
        )
    return str(mono), str(dual)


def main():
    parser = argparse.ArgumentParser(description="翻译 PDF 文件（基于 pdf2zh）")
    parser.add_argument("--pdf_path", required=True, help="PDF 文件路径（相对或 /workspace/ 形式）")
    parser.add_argument(
        "--output_dir", default=None, help="输出目录（默认 pdf_translations/<文件名>/）"
    )
    parser.add_argument("--source_lang", default="en", help="源语言代码（默认 en）")
    parser.add_argument("--target_lang", default="zh", help="目标语言代码（默认 zh）")
    parser.add_argument("--translator", default="google", help="翻译服务: google/openai/gemini")
    parser.add_argument("--ignore_cache", action="store_true", help="忽略 pdf2zh 缓存")
    parser.add_argument(
        "--pages",
        default=None,
        help="只翻译指定页（如 '1-10'、'1,3,5'、'1-5,10'），适合大文件试译",
    )
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        host_pdf, visible_pdf = resolve_path(args.pdf_path, workspace_root)

        if not host_pdf.exists():
            print(json.dumps({"error": f"文件不存在: {visible_pdf}"}, ensure_ascii=False))
            sys.exit(1)
        if host_pdf.suffix.lower() != ".pdf":
            print(json.dumps({"error": f"不是 PDF 文件: {visible_pdf}"}, ensure_ascii=False))
            sys.exit(1)

        if args.output_dir:
            output_host, output_visible = resolve_path(args.output_dir, workspace_root)
        else:
            output_host = workspace_root / "pdf_translations" / host_pdf.stem
            output_visible = f"/workspace/pdf_translations/{host_pdf.stem}"

        output_host.mkdir(parents=True, exist_ok=True)

        # 提示翻译开始
        print(
            json.dumps(
                {
                    "status": "translating",
                    "source_pdf": visible_pdf,
                    "translator": args.translator,
                    "pages": args.pages or "all",
                    "message": f"开始翻译 {visible_pdf}（{args.translator}）...",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        mono_path, dual_path = run_translate(
            pdf_path=host_pdf,
            output_dir=output_host,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            translator=args.translator,
            ignore_cache=args.ignore_cache,
            pages=args.pages,
        )

        def to_visible(p: str) -> str:
            pp = Path(p).resolve()
            try:
                rel = pp.relative_to(workspace_root)
                return f"/workspace/{rel.as_posix()}"
            except ValueError:
                return str(pp)

        result = {
            "status": "success",
            "source_pdf": visible_pdf,
            "output_dir": output_visible,
            "mono_pdf": to_visible(mono_path),
            "dual_pdf": to_visible(dual_path),
            "translator": args.translator,
            "source_lang": args.source_lang,
            "target_lang": args.target_lang,
            "pages": args.pages or "all",
        }

        manifest = output_host / "translation_manifest.json"
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["manifest"] = to_visible(str(manifest))

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
