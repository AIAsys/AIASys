#!/usr/bin/env python3
"""
Export ECharts JSON configs to PNG images.

This is a Python wrapper around `export_echarts_png.js` (Node.js + Playwright).
The Node.js script renders each ECharts config in a headless Chromium page and
saves a PNG screenshot.

Usage:
    # Export all charts in a directory
    python3 scripts/export_echarts_png.py --input research_views/echarts/ --output research_views/figures/

    # Export a single chart
    python3 scripts/export_echarts_png.py --input research_views/echarts/01_timeline.echarts.json --output research_views/figures/timeline.png

    # Custom size
    python3 scripts/export_echarts_png.py --input research_views/echarts/ --output research_views/figures/ --width 1600 --height 800

Environment:
    AIASYS_WORKSPACE_ROOT: workspace root directory
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH: optional custom Chromium path
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_workspace_root() -> Path:
    ws = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws:
        return Path(ws).resolve()
    return Path.cwd().resolve()


def find_node_script() -> Path:
    """Locate export_echarts_png.js next to this script."""
    return Path(__file__).with_suffix(".js").resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ECharts configs to PNG")
    parser.add_argument("--input", "-i", required=True, help="Input .echarts.json file or directory")
    parser.add_argument("--output", "-o", required=True, help="Output PNG file or directory")
    parser.add_argument("--width", "-w", type=int, default=1200, help="Screenshot width (default: 1200)")
    parser.add_argument("--height", "-H", type=int, default=600, help="Screenshot height (default: 600)")
    args = parser.parse_args()

    workspace = get_workspace_root()
    input_path = workspace / args.input
    output_path = workspace / args.output
    node_script = find_node_script()

    if not node_script.exists():
        print(f"error: Node.js script not found: {node_script}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        "node", str(node_script),
        "--input", str(input_path),
        "--output", str(output_path),
        "--width", str(args.width),
        "--height", str(args.height),
    ]

    env = os.environ.copy()
    # Ensure Node can find playwright from the web app node_modules
    web_node_modules = (workspace / "apps" / "web" / "node_modules").resolve()
    if web_node_modules.exists():
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = str(web_node_modules) + (os.pathsep + existing if existing else "")

    result = subprocess.run(cmd, env=env, cwd=str(workspace))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
