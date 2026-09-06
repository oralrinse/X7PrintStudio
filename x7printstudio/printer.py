# -*- coding: utf-8 -*-
"""USB 打印通道: 经 Windows 打印机队列以 RAW 数据格式原样发送明文作业。

X7 有线枚举为标准 USB 打印机(Class 07/01/02), Windows 自动建队列 + USB001 端口。
RAW 数据类型 = spooler 零渲染, 逐字节送 usbprint -> 打印机(已验证出纸)。
"""
from __future__ import annotations
import win32print

from .spec import DPI


def list_queues() -> list[dict]:
    """返回本地打印队列 [{name, port, driver}], USB 通道者优先排列。"""
    out = []
    try:
        names = [p[2] if isinstance(p, tuple) else p
                 for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL, None, 1)]
    except Exception:
        names = []
    for n in names:
        try:
            h = win32print.OpenPrinter(n)
            try:
                info = win32print.GetPrinter(h, 2)
            finally:
                win32print.ClosePrinter(h)
        except Exception:
            continue
        out.append({"name": info.get("pPrinterName", n),
                    "port": info.get("pPortName", ""),
                    "driver": info.get("pDriverName", "")})
    def key(q):
        port = q["port"].lower()
        nm = q["name"]
        if "usb" in port or q["port"].isdigit():
            return (0, -len(nm))          # USB 通道优先
        if q["port"]:
            return (1, 0)
        return (2, 0)
    out.sort(key=key)
    return out


def find_usb_queue() -> dict | None:
    """挑选最可能的 X7 队列: 端口含 USB 且名字含 得力/X7/相印 者最优先, 其次任一 USB 队列。"""
    qs = list_queues()
    for q in qs:
        if "usb" in q["port"].lower() and any(k in q["name"] for k in ("得力", "X7", "相印", "XiangYinBao")):
            return q
    for q in qs:
        if "usb" in q["port"].lower():
            return q
    return qs[0] if qs else None


def raw_send(queue_name: str, data: bytes, copies: int = 1) -> int:
    """RAW 直发明文作业; 返回成功发送的副本数(0=失败)。"""
    sent = 0
    h = win32print.OpenPrinter(queue_name)
    try:
        for _ in range(copies):
            try:
                job = win32print.StartDocPrinter(h, 1, ("X7 图文打印", None, "RAW"))
                try:
                    win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, data)
                    win32print.EndPagePrinter(h)
                finally:
                    win32print.EndDocPrinter(h)
                sent += 1
            except win32print.error:
                break
    finally:
        win32print.ClosePrinter(h)
    return sent


def estimate(raster_rows: int, raster_bytes: int, ink: float) -> dict:
    """纸长(mm)与墨量估算。"""
    return {
        "rows": raster_rows,
        "len_mm": round(raster_rows / DPI * 25.4, 1),
        "ink": round(ink * 100, 1),
    }
