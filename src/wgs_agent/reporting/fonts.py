"""Use installed or explicitly configured CJK fonts without downloading assets."""

import os
from pathlib import Path


def resolve_cjk_fonts() -> tuple[str, str]:
    bundled = Path(__file__).parents[1] / "tools/fonts"
    candidates = [
        (os.environ.get("WGS_REPORT_FONT_REGULAR", ""), os.environ.get("WGS_REPORT_FONT_BOLD", "")),
        (str(bundled / "MSYH.TTC"), str(bundled / "MSYHBD.TTC")),
        (str(bundled / "NotoSansSC.ttf"), str(bundled / "NotoSansSC-Bold.ttf")),
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", ""),
    ]
    for regular, bold in candidates:
        if regular and Path(regular).is_file():
            return regular, bold if bold and Path(bold).is_file() else regular
    raise RuntimeError("未找到中文字体，请安装 Noto CJK 或配置 WGS_REPORT_FONT_REGULAR。")
