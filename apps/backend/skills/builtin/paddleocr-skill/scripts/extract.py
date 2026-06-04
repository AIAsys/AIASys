#!/usr/bin/env python3
"""文档提取脚本 — 基于 PaddleOCR Layout Parsing API 将 PDF/图片转换为 Markdown。

用法:
    python3 extract.py --file /workspace/doc.pdf --file_type 0 --output_dir /workspace/out
    python3 extract.py --file /workspace/scan.png --file_type 1 --output_dir /workspace/out

环境变量:
    PADDLEOCR_API_URL: Layout Parsing API 地址
    PADDLEOCR_TOKEN:   API 认证 token
    AIASYS_WORKSPACE_ROOT: 工作区根目录（由 Shell 自动注入）
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    cwd = Path.cwd()
    if (cwd / "metadata.json").exists():
        return cwd
    raise RuntimeError("无法确定工作区根目录，请设置 AIASYS_WORKSPACE_ROOT 环境变量")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = Path(*p.parts[1:]) if str(p).startswith("/workspace") else p
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 PDF/图片转换为 Markdown（PaddleOCR Layout Parsing）")
    parser.add_argument("--file", required=True, help="输入文件路径（相对或 /workspace/ 形式）")
    parser.add_argument("--file_type", type=int, default=0,
                        help="文件类型: 0=PDF, 1=图片 (默认 0)")
    parser.add_argument("--output_dir", default=None, help="输出目录（默认 <文件名>_extracted/）")
    parser.add_argument("--use_doc_orientation_classify", action="store_true",
                        help="启用文档方向分类")
    parser.add_argument("--use_doc_unwarping", action="store_true",
                        help="启用文档展平")
    parser.add_argument("--use_chart_recognition", action="store_true",
                        help="启用图表识别")
    return parser.parse_args()


def download_image(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False


def main():
    args = parse_args()

    api_url = os.environ.get("PADDLEOCR_API_URL", "").strip()
    token = os.environ.get("PADDLEOCR_TOKEN", "").strip()

    if not api_url:
        print(json.dumps({"error": "缺少 PADDLEOCR_API_URL 环境变量"}, ensure_ascii=False))
        sys.exit(1)
    if not token:
        print(json.dumps({"error": "缺少 PADDLEOCR_TOKEN 环境变量。请参考 .env.example 配置"}, ensure_ascii=False))
        sys.exit(1)

    try:
        workspace_root = get_workspace_root()
        host_path = resolve_path(args.file, workspace_root)

        if not host_path.exists():
            print(json.dumps({"error": f"文件不存在: {args.file}"}, ensure_ascii=False))
            sys.exit(1)

        if args.output_dir:
            output_dir = resolve_path(args.output_dir, workspace_root)
        else:
            output_dir = workspace_root / f"{host_path.stem}_extracted"

        output_dir.mkdir(parents=True, exist_ok=True)

        with open(host_path, "rb") as fh:
            file_bytes = fh.read()
        file_data = base64.b64encode(file_bytes).decode("ascii")

        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "file": file_data,
            "fileType": args.file_type,
            "useDocOrientationClassify": args.use_doc_orientation_classify,
            "useDocUnwarping": args.use_doc_unwarping,
            "useChartRecognition": args.use_chart_recognition,
        }

        resp = requests.post(api_url, json=payload, headers=headers, timeout=300)
        if resp.status_code != 200:
            print(json.dumps({
                "error": f"API 请求失败 (HTTP {resp.status_code}): {resp.text[:500]}"
            }, ensure_ascii=False))
            sys.exit(1)

        result = resp.json()["result"]
        saved_docs: list[str] = []
        saved_images: list[str] = []

        for i, res in enumerate(result["layoutParsingResults"]):
            # 保存 Markdown
            md_filename = output_dir / f"doc_{i}.md"
            md_filename.write_text(res["markdown"]["text"], encoding="utf-8")
            saved_docs.append(str(md_filename))

            # 下载 Markdown 中引用的图片
            for img_rel_path, img_url in res["markdown"]["images"].items():
                full_img_path = output_dir / img_rel_path
                if download_image(img_url, full_img_path):
                    saved_images.append(str(full_img_path))

            # 下载 outputImages 中的图片
            for img_name, img_url in res.get("outputImages", {}).items():
                img_dest = output_dir / f"{img_name}_{i}.jpg"
                if download_image(img_url, img_dest):
                    saved_images.append(str(img_dest))

        def to_visible(p: str) -> str:
            pp = Path(p).resolve()
            try:
                rel = pp.relative_to(workspace_root)
                return f"/workspace/{rel.as_posix()}"
            except ValueError:
                return str(pp)

        output = {
            "status": "success",
            "file": args.file,
            "file_type": "PDF" if args.file_type == 0 else "image",
            "output_dir": to_visible(str(output_dir)),
            "documents": [to_visible(d) for d in saved_docs],
            "images_count": len(saved_images),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
