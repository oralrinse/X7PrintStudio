# -*- coding: utf-8 -*-
"""灰度 -> 1bpp 栅格 (Floyd–Steinberg 抖动)。

极性: 位 1 = 黑 = 加热; 白 = 0。MSB 先行内第一像素。
幅宽固定 1248px = 156B/行。本实现已真机打印验证。
"""
from typing import Union

from .spec import WIDTH, ROWW


def fs_dither(gray) -> bytes:
    """入参: 宽恰为 WIDTH 的 PIL "L" 图(或 2D 0..255 数值)。出: ROWW*H 字节。"""
    try:
        w, h = gray.size
        px = gray.load()
    except AttributeError:
        import numpy as np
        a = np.asarray(gray, dtype=float)
        h, w = a.shape
        px = None
    if w != WIDTH:
        raise ValueError("栅格宽必须为 %dpx, 实为 %d" % (WIDTH, w))
    out = bytearray(ROWW * h)
    errR = [0.0] * WIDTH
    errD = [0.0] * WIDTH
    for y in range(h):
        errDn = [0.0] * WIDTH
        base = y * ROWW
        for x in range(WIDTH):
            if px is not None:
                v = px[x, y] + errR[x] + errD[x]
            else:
                v = a[y, x] + errR[x] + errD[x]
            bit = 1 if v < 128.0 else 0
            err = v - (0.0 if bit else 255.0)
            if x + 1 < WIDTH:
                errR[x + 1] = err * 7.0 / 16.0
            if x > 0:
                errDn[x - 1] += err * 3.0 / 16.0
            errDn[x] += err * 5.0 / 16.0
            if x + 1 < WIDTH:
                errDn[x + 1] += err * 1.0 / 16.0
            if bit:
                out[base + (x >> 3)] |= (0x80 >> (x & 7))
        errR = [0.0] * WIDTH
        errD = errDn
    return bytes(out)


def ink_ratio(raster: bytes) -> float:
    """墨量占比 0..1(供打印预估)。"""
    if not raster:
        return 0.0
    return sum(b.bit_count() for b in raster) / (len(raster) * 8)
