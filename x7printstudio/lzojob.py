# -*- coding: utf-8 -*-
"""作业字节流装配 —— 逐字节复刻官方 App 会话 (全部经真机打印验证)。

根因结论(勿改): X7 固件用"定长 LZO 解码"。python-lzo 的 lzo.compress(raw) 输出带
5 字节前导 `f0 00 00 <lenLE16>`, 固件不认 -> 整帧静默丢弃(全白)。原生 libLZO 风味
= `lzo.compress(raw)[5:]`。重编码官方 100 帧 100/100 逐字节一致。

帧:   1D 76 30 30 | 156 LE16 | rows LE16 | clen LE32 | 载荷
明文流: queries(1B1264/1B1273x2) -> cfg(1D set p0/s10/w1248) -> 帧段 -> feed100
USB 通道直发明文即可(BT 的 set mm 握手+XOR 是 SPP 专属, 本项目不需要)。
"""
import struct
import lzo

from .spec import ROWW, FRAME_ROWS, WIDTH


def queries() -> bytes:
    return b"\x1b\x12\x64" + b"\x1b\x12\x73" + b"\x1b\x12\x73"


def cfg(density: int = 0, speed: int = 10, width: int = WIDTH) -> bytes:
    """官方实测字节 = `1D "set" p0 | 1D "set" s10 | 1D "set" w1248`(无空格)。"""
    return (b"\x1d" + b"set" + b"p" + bytes([density])
            + b"\x1d" + b"set" + b"s" + bytes([speed])
            + b"\x1d" + b"set" + b"w" + bytes([width & 0xff, width >> 8]))


def official_lzo(raw: bytes) -> bytes:
    """原生 libLZO 风味压缩 = python-lzo 输出去 5 字节前导。"""
    return lzo.compress(raw)[5:]


def lzo_frame(raw: bytes) -> bytes:
    """一帧: 1D 76 30 30 | rowbytes LE16 | rows LE16 | clen LE32 | official-flavor 载荷。
    raw 长必须为 ROWW 的整数倍。"""
    rows = len(raw) // ROWW
    assert rows * ROWW == len(raw) and 0 < rows <= 0xFFFF, "raw 长须为行宽整数倍"
    c = official_lzo(raw)
    return (bytes([0x1d, 0x76, 0x30, 0x30])
            + struct.pack("<HH", ROWW, rows)
            + struct.pack("<I", len(c)) + c)


def feed(feed_dots: int = 100) -> bytes:
    """连续纸收尾: setPrintFeed(100)。"""
    return b"\x1b\x1b\x01" + bytes([feed_dots & 0xff, feed_dots >> 8])


def rows_to_frames(raster: bytes) -> bytes:
    """整幅栅格(156B/行)按 16 行一块切帧。末块不足 16 行也能打(帧内 rows 如实)。"""
    out = bytearray()
    for off in range(0, len(raster), ROWW * FRAME_ROWS):
        out += lzo_frame(raster[off:off + ROWW * FRAME_ROWS])
    return bytes(out)


def job_bytes(raster: bytes) -> bytes:
    """栅格 -> 完整明文作业 (queries + cfg + 帧 + feed)。"""
    return queries() + cfg() + rows_to_frames(raster) + feed()


def decode_frame(payload: bytes, rows: int) -> bytes:
    """固件同款"定长解", 供自检/预览还原。"""
    return lzo.decompress(payload, False, ROWW * rows)


# ---- 出厂自检: 结构常量不得漂移 ----
_CFG_GOLD = (b"\x1d" + b"set" + b"p" + b"\x00"
             + b"\x1d" + b"set" + b"s" + b"\x0a"
             + b"\x1d" + b"set" + b"w" + b"\xe0\x04")
assert cfg() == _CFG_GOLD, "cfg 字节与官方捕获不一致!"
assert queries() == b"\x1b\x12\x64\x1b\x12\x73\x1b\x12\x73"
assert feed() == b"\x1b\x1b\x01\x64\x00"
