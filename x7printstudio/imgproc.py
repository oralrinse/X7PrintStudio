# -*- coding: utf-8 -*-
"""图像处理开关(打印前作用于灰度)。热敏机表现: 高对比比连续灰阶更稳。"""
from PIL import Image, ImageOps


def gray(im: Image.Image) -> Image.Image:
    return im.convert("L")


def high_contrast(im: Image.Image, threshold: int = 128) -> Image.Image:
    """两值化: v>=threshold -> 白(255), 否则黑(0)。"""
    return im.convert("L").point(lambda v: 255 if v >= threshold else 0)


def invert(im: Image.Image) -> Image.Image:
    return ImageOps.invert(im.convert("L"))


MODES = {
    "gray": "原图灰阶",
    "bw": "黑白高对比",
    "invert": "反白",
}


def apply(mode: str, im: Image.Image, threshold: int = 128) -> Image.Image:
    if mode == "bw":
        return high_contrast(im, threshold)
    if mode == "invert":
        return invert(im)
    return gray(im)
