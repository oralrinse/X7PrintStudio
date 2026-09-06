# -*- coding: utf-8 -*-
"""文档 -> 画布渲染(1248×H)。输出灰度图供抖动打印; 灰阶预览也由此得出。"""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont

from .spec import WIDTH, font_for, first_font
from . import imgproc
from .doc import Document, ImageItem, TextItem

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)


def _load_font(size: int, bold: bool):
    fp = font_for("bold" if bold else "regular")
    return ImageFont.truetype(fp, size)


def wrap_text(text: str, font, maxw: int) -> list[str]:
    """按像素宽断行(中英混排): 空格断词, CJK 逐字, 超长硬切。"""
    lines: list[str] = []
    for hard in text.split("\n"):
        if hard == "":
            lines.append("")
            continue
        cur = ""
        for seg in hard.split(" "):
            trial = cur + (" " if cur else "") + seg
            if font.getlength(trial) <= maxw or not cur:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                # seg 本身可能仍超宽 -> 按字硬切
                cur = ""
                for ch in seg:
                    t2 = cur + ch
                    if font.getlength(t2) <= maxw:
                        cur = t2
                    else:
                        lines.append(cur)
                        cur = ch
        lines.append(cur)
    return lines


def resolve_maxw(it: TextItem) -> int:
    """文字的实际排版宽度上限(px)。"""
    m = it.maxw if it.maxw > 0 else (WIDTH - it.x)
    return m if m > 0 else 0


def measure_text(it: TextItem) -> int:
    """按与绘制相同的断行/行高, 估出整段文字像素高(供点选/落点定位)。"""
    if not it.text:
        return 0
    maxw = resolve_maxw(it)
    if not maxw:
        return 0
    font = _load_font(it.size, it.bold)
    lines = wrap_text(it.text, font, maxw)
    return int(it.size * 1.18) * max(1, len(lines))


def _draw_text(cv: ImageDraw.ImageDraw, it: TextItem, doc: Document):
    font = _load_font(it.size, it.bold)
    maxw = resolve_maxw(it)
    if not maxw:
        return
    lines = wrap_text(it.text, font, maxw)
    fill = _BLACK if it.color == "k" else _WHITE
    lh = int(it.size * 1.18)
    y = it.y
    for ln in lines:
        w = font.getlength(ln)
        if it.align == "center":
            x = it.x + (maxw - w) / 2
        elif it.align == "right":
            x = it.x + maxw - w
        else:
            x = it.x
        cv.text((x, y), ln, font=font, fill=fill)
        y += lh


def _draw_image(cv: ImageDraw.ImageDraw, canvas: Image.Image, it: ImageItem):
    src = it.rendered()
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return
    box_w, box_h = it.w, it.h
    if it.keep_aspect:
        # 等比适配进方框(居中), 不留形变
        k = min(box_w / sw, box_h / sh)
        dw, dh = max(1, int(sw * k)), max(1, int(sh * k))
        dx = it.x + (box_w - dw) // 2
        dy = it.y + (box_h - dh) // 2
    else:
        dw, dh, dx, dy = box_w, box_h, it.x, it.y
    proc = imgproc.apply(it.mode, src, it.threshold).convert("L")
    small = proc.resize((dw, dh), Image.LANCZOS)
    canvas.paste(small.convert("RGB"), (dx, dy))


def rasterize(doc: Document) -> Image.Image:
    """渲染成宽 WIDTH 的灰度 PIL 图(0=黑底可见? 输出 L, 白=255)。"""
    h = max(16, int(doc.height))
    bg = _WHITE if doc.bg == "w" else _BLACK
    canvas = Image.new("RGB", (WIDTH, h), bg)
    cv = ImageDraw.Draw(canvas)
    for it in doc.items:
        try:
            if isinstance(it, ImageItem):
                _draw_image(cv, canvas, it)
            elif isinstance(it, TextItem):
                _draw_text(cv, it, doc)
        except Exception:
            continue  # 单个图层坏(如图片文件缺失)不拖垮整张
    return canvas.convert("L")
