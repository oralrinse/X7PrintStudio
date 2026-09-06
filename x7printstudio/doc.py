# -*- coding: utf-8 -*-
"""文档/图层模型 + .x7proj 存读。坐标为 1248px 画布空间的整数 px。"""
from __future__ import annotations
import json, os, threading
from dataclasses import dataclass, field, asdict

from .spec import WIDTH


@dataclass
class ImageItem:
    kind: str = "image"
    path: str = ""
    x: int = 0
    y: int = 0
    w: int = 1248          # 目标显示宽(px)
    h: int = 1248          # 目标显示高(px)
    keep_aspect: bool = True
    rot: int = 0           # 顺时针旋转角度: 0/90/180/270
    mode: str = "gray"     # gray | bw | invert
    threshold: int = 128
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
    _lock: object = field(default_factory=threading.Lock, repr=False, compare=False)

    def rendered(self):
        """按 mode 处理后的 PIL 图(缓存)。"""
        from PIL import Image
        with self._lock:
            key = (self.path, os.path.getmtime(self.path) if self.path and os.path.exists(self.path) else 0, self.mode, self.threshold)
            if self._cache.get("key") != key:
                im = Image.open(self.path).convert("RGB")
                self._cache["im"] = im
                self._cache["key"] = key
            return self._cache["im"]


@dataclass
class TextItem:
    kind: str = "text"
    text: str = ""
    x: int = 0
    y: int = 0
    maxw: int = 0            # 0 = 画布宽 - x
    size: int = 48           # px @ 300dpi
    bold: bool = False
    font_path: str = ""      # 空 = 自动
    align: str = "left"      # left | center | right
    color: str = "k"         # k 黑 / w 白(用于深底)


Item = ImageItem | TextItem


@dataclass
class Document:
    height: int = 1824
    bg: str = "w"            # w 白 / k 黑
    items: list = field(default_factory=list)
    title: str = "未命名"

    def width(self):
        return WIDTH

    # ---------------- 图层操作 ----------------
    def move(self, idx: int, delta: int):
        if not (0 <= idx < len(self.items)):
            return
        j = idx + delta
        if 0 <= j < len(self.items):
            it = self.items.pop(idx)
            self.items.insert(j, it)

    def remove(self, idx: int):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)

    def duplicate(self, idx: int) -> int:
        import copy
        if not (0 <= idx < len(self.items)):
            return idx
        it = copy.deepcopy(self.items[idx])
        it.y += 20
        self.items.insert(idx + 1, it)
        return idx + 1

    # ---------------- 序列化 ----------------
    def to_dict(self):
        return {"height": self.height, "bg": self.bg, "title": self.title,
                "items": [asdict(i) for i in self.items]}

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)

    @staticmethod
    def load(path: str) -> "Document":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        doc = Document(height=d.get("height", 1824), bg=d.get("bg", "w"),
                       title=d.get("title", os.path.basename(path)))
        for it in d.get("items", []):
            if it.get("kind") == "image":
                doc.items.append(ImageItem(**{k: v for k, v in it.items() if k not in ("_cache", "_lock")}))
            elif it.get("kind") == "text":
                doc.items.append(TextItem(**{k: v for k, v in it.items()}))
        return doc
