"""本地运行态字体 helper。

通过系统字体名称匹配为 matplotlib 配置 CJK 字体，不依赖文件路径。
"""

from __future__ import annotations


PREFERRED_FONT_FAMILIES = (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "SimHei",
    "Microsoft YaHei",
    "DengXian",
    "Arial Unicode MS",
    "PingFang SC",
    "Heiti SC",
)


def setup_cn_font(*, quiet: bool = False) -> dict[str, str | bool | None]:
    """配置 matplotlib 中文字体，找不到字体时安静降级。

    按 PREFERRED_FONT_FAMILIES 顺序匹配系统已安装字体。
    返回 {"ok": True/False, "font_name": "..."}。
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except Exception as exc:
        if not quiet:
            print(f"[AIASys] matplotlib 不可用，跳过中文字体初始化: {exc}")
        return {"ok": False, "font_name": None}

    available_families = {font.name for font in font_manager.fontManager.ttflist}

    for family in PREFERRED_FONT_FAMILIES:
        if family not in available_families:
            continue
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        if not quiet:
            print(f"[AIASys] 中文字体已配置: {family}")
        return {"ok": True, "font_name": family}

    if not quiet:
        print("[AIASys] 未找到可用中文字体，保持 matplotlib 默认配置")
    return {"ok": False, "font_name": None}
