"""本地运行态字体 helper。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


PREFERRED_FONT_FILE_NAMES = (
    "NotoSansCJKsc.otf",
    "NotoSansSC-Regular.otf",
    "SourceHanSansSC-Regular.otf",
    "SourceHanSansCN-Regular.otf",
)
PREFERRED_FONT_FAMILIES = (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "SimHei",
    "Microsoft YaHei",
)


def _bundled_font_paths() -> list[Path]:
    helper_root = Path(__file__).resolve().parent.parent
    fonts_dir = helper_root / "fonts"
    return [fonts_dir / name for name in PREFERRED_FONT_FILE_NAMES]


def _candidate_font_paths(
    *,
    workspace: Path | None = None,
    extra_paths: Iterable[str] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _append(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    if extra_paths:
        for raw in extra_paths:
            if raw:
                raw_path = Path(raw)
                if raw_path.is_dir():
                    for name in PREFERRED_FONT_FILE_NAMES:
                        _append(raw_path / name)
                else:
                    _append(raw_path)

    for bundled in _bundled_font_paths():
        _append(bundled)

    if workspace is not None:
        for name in PREFERRED_FONT_FILE_NAMES:
            _append(workspace / "fonts" / name)
            _append(workspace / name)

    return candidates


def setup_cn_font(
    *,
    workspace: Path | None = None,
    extra_paths: Iterable[str] | None = None,
    quiet: bool = False,
) -> dict[str, str | bool | None]:
    """配置 matplotlib 中文字体，找不到字体时安静降级。"""
    try:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except Exception as exc:
        if not quiet:
            print(f"[AIASys] matplotlib 不可用，跳过中文字体初始化: {exc}")
        return {"ok": False, "font_path": None, "font_name": None}

    for font_path in _candidate_font_paths(
        workspace=workspace,
        extra_paths=extra_paths,
    ):
        resolved = font_path.expanduser().resolve()
        if not resolved.exists():
            continue

        try:
            font_manager.fontManager.addfont(str(resolved))
            font_name = font_manager.FontProperties(fname=str(resolved)).get_name()
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return {
                "ok": True,
                "font_path": str(resolved),
                "font_name": font_name,
            }
        except Exception as exc:
            if not quiet:
                print(f"[AIASys] 中文字体初始化失败: {resolved} -> {exc}")

    available_families = {font.name for font in font_manager.fontManager.ttflist}
    for family in PREFERRED_FONT_FAMILIES:
        if family not in available_families:
            continue
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        return {
            "ok": True,
            "font_path": None,
            "font_name": family,
        }

    if not quiet:
        print("[AIASys] 未找到可用中文字体，保持 matplotlib 默认配置")
    return {"ok": False, "font_path": None, "font_name": None}
