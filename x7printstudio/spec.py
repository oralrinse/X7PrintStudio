# -*- coding: utf-8 -*-
"""X7 硬件/协议常量与字体工具。所有数值均经真机逆向与打印验证, 勿改。"""
import os

# 打印头
WIDTH = 1248          # 一行像素 (300dpi)
ROWW = WIDTH // 8     # 156 B/行
DPI = 300
PAPER_MM = round(WIDTH * 25.4 / DPI, 1)   # ≈105.7mm

# 栅格帧: 每帧行数
FRAME_ROWS = 16

# 打印作业: 深/浅浓度档位 (对应官方 set 参数; 保持官方实测值)
DENSITY = 0
SPEED = 10            # s=10 由官方会话捕获

# 缺省画布高度(px)≈ 一张竖版照片
DEFAULT_CANVAS_H = 1824

# Windows 内置中文字体候选 (编辑器渲染文字用)
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",    # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
]


def first_font() -> str:
    """返回第一个真实存在的字体路径, 否则抛异常。"""
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    raise FileNotFoundError("未找到可用系统字体(需任一: " + ", ".join(FONT_CANDIDATES) + ")")


def font_for(kind: str = "regular") -> str:
    """kind: regular / bold。返回字体文件路径。"""
    if kind == "bold":
        for f in FONT_CANDIDATES:
            if "bd" in f.lower() and os.path.exists(f):
                return f
    return first_font()
