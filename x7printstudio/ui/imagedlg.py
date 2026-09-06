# -*- coding: utf-8 -*-
"""插入图片: 选文件即按等比满宽铺进画布(供后续拖动/缩放/处理开关微调)。"""
from __future__ import annotations
from PySide6.QtWidgets import QFileDialog

from PIL import Image

from ..spec import WIDTH
from ..doc import ImageItem


def pick_image(parent, last_dir: str = "") -> tuple[str, ImageItem | None]:
    """弹窗选图; 返回 (源目录, 新 ImageItem)。用户取消返回 ("", None)。"""
    path, _ = QFileDialog.getOpenFileName(
        parent, "选择图片", last_dir,
        "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;所有文件 (*)")
    if not path:
        return last_dir, None
    try:
        with Image.open(path) as im:
            sw, sh = im.size
    except Exception:
        return last_dir, None
    if sw <= 0 or sh <= 0:
        sw, sh = WIDTH, 1248
    # 等比: 满宽 1168(留 ~40px 边距), 高按原比例
    w = WIDTH - 80
    h = max(40, int(w * sh / sw))
    it = ImageItem(path=path, x=40, y=0, w=w, h=h, keep_aspect=True,
                   mode="gray", threshold=128)
    import os
    return os.path.dirname(path), it
