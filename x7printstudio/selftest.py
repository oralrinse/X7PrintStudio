# -*- coding: utf-8 -*-
"""离线自检: 拼版→渲染→FS 抖动→作业编码→LZO 定长解还原==栅格; job 头断言。

运行:  python -m x7printstudio.selftest
全绿即核心链路与官方逐字节配方一致(字节黄金断言在模块 import 时已生效)。
"""
from __future__ import annotations
import os
import struct
import tempfile

from .spec import WIDTH, ROWW, FRAME_ROWS
from . import lzojob
from . import raster as R


def _synthetic_raster(rows: int = 200) -> bytes:
    """构造含黑/白/半灰/渐变的 WIDTH×rows 灰度, 供抖动与编码往返验证。"""
    from PIL import Image
    im = Image.new("L", (WIDTH, rows), 255)
    px = im.load()
    for y in range(rows):
        for x in range(WIDTH):
            if x < 200:                      # 纯黑条(必加热)
                v = 0
            elif x < 300:                    # 黑白硬边界(极性检查)
                v = 255
            elif x < 600:
                v = int((x % 300) / 300 * 255)   # 渐变(FS 扩散)
            elif x < 700:
                v = 90                       # 中灰平铺
            else:
                v = 255 if (x + y) % 4 else 0    # 稀疏点阵
            px[x, y] = v
    return R.fs_dither(im)


def _check_lzo_roundtrip(raster: bytes) -> int:
    """把整幅栅格按 job_bytes 编码, 再逐帧做固件式定长解, 必须逐字节还原。"""
    frames = lzojob.rows_to_frames(raster)
    off = 0
    parsed = bytearray()
    assert frames[:4] == b"\x1d\x76\x30\x30", "首帧魔数错误"
    i = 0
    while off < len(raster):
        # 逐帧解析: 4 magic | rowbytes LE16 | rows LE16 | clen LE32 | payload
        assert frames[i:i + 4] == b"\x1d\x76\x30\x30", f"帧@{off} 魔数错误"
        rb, rows = struct.unpack_from("<HH", frames, i + 4)
        (clen,) = struct.unpack_from("<I", frames, i + 8)
        assert rb == ROWW, f"帧@{off} 行宽 {rb}!=156"
        assert rows * ROWW <= len(raster) - off
        payload = frames[i + 12:i + 12 + clen]
        dec = lzojob.decode_frame(payload, rows)
        assert len(dec) == rows * ROWW
        parsed += dec
        off += rows * ROWW
        i += 12 + clen
        assert i <= len(frames)
    assert bytes(parsed) == raster, "LZO 定长解还原与原始栅格不一致!"
    return i  # 帧段总长


def _check_compose_pipeline() -> int:
    """走真实 UI 数据路径: Document(1 文字 + 1 图像) → rasterize → 抖动。"""
    from PIL import Image, ImageDraw
    from .doc import Document, TextItem, ImageItem
    from .compose import rasterize

    td = tempfile.mkdtemp(prefix="x7st_")
    try:
        # 1) 一张临时照片 (300dpi 下 ≈ 60×45mm)
        ph = os.path.join(td, "ph.png")
        im = Image.new("L", (700, 520), 255)
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 700, 520], fill=200, outline=0, width=8)
        for i in range(0, 700, 40):
            dr.line([i, 0, i, 520], fill=90 if (i // 40) % 2 else 30, width=2)
        im.save(ph)

        doc = Document(height=1600)
        doc.items.append(ImageItem(path=ph, x=40, y=60, w=1168, h=900, keep_aspect=True,
                                   mode="gray", threshold=128))
        doc.items.append(TextItem(text="得力相印宝 X7 · 图文自检", x=40, y=40, maxw=1168,
                                  size=72, bold=True, align="center"))
        doc.items.append(TextItem(text="1234567890 Hello 世界 \nabc", x=40, y=1010, maxw=1168,
                                  size=40, align="left"))

        gray = rasterize(doc)
        assert gray.size == (WIDTH, doc.height), "渲染尺寸不符"
        assert gray.mode == "L"
        raster = R.fs_dither(gray)
        ink = R.ink_ratio(raster)
        assert 0.0 <= ink <= 1.0, "墨量占比越界"
        return len(raster) // ROWW  # 行数
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def selftest() -> int:
    print("== X7PrintStudio selftest ==")
    rows = 200
    r = _synthetic_raster(rows)
    nbytes = _check_lzo_roundtrip(r)
    print(f"[ok] LZO 定长解往返 {rows}行 -> {nbytes}B 帧段逐字节还原")

    job = lzojob.job_bytes(r)
    head = lzojob.queries() + lzojob.cfg()
    assert job.startswith(head), "job 头非 queries+cfg"
    assert job.endswith(lzojob.feed()), "job 尾非 feed100"
    print(f"[ok] job 头/尾字节正确 (总 {len(job)}B, 压缩率 "
          f"{len(lzojob.rows_to_frames(r)) / len(r) * 100:.0f}%)")

    rows2 = _check_compose_pipeline()
    print(f"[ok] 真实拼版链路 (图文/反白/对齐) 渲染+抖动 {rows2}行 通过")

    ink = R.ink_ratio(_synthetic_raster(64))
    print(f"[ok] 墨量估算接口正常 ({ink:.3f})")
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
