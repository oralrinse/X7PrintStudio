# -*- coding: utf-8 -*-
"""左侧图层面板: 列表 + 排序/增删按钮。UI 只负责展示与转发, 逻辑在 MainWindow。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QLabel)
from PySide6.QtCore import Signal


class LayersPanel(QWidget):
    select = Signal(int)          # 列表选中行 -> 画布同步
    move_up = Signal()
    move_down = Signal()
    duplicate = Signal()
    remove = Signal()
    edit = Signal()
    add_text = Signal()
    add_image = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lab = QLabel("图层 (自下而上打印; 顶行=最上层)")
        lab.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(lab)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.select.emit)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit.emit())
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        for txt, sig in (("⬆", self.move_up), ("⬇", self.move_down),
                         ("⧉复制", self.duplicate), ("✕删除", self.remove),
                         ("编辑", self.edit)):
            b = QPushButton(txt)
            b.clicked.connect(sig.emit)
            b.setFixedHeight(26)
            row.addWidget(b)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        b1 = QPushButton("＋ 图片")
        b2 = QPushButton("＋ 文字")
        b1.clicked.connect(self.add_image.emit)
        b2.clicked.connect(self.add_text.emit)
        b1.setFixedHeight(28)
        b2.setFixedHeight(28)
        row2.addWidget(b1)
        row2.addWidget(b2)
        lay.addLayout(row2)

    def set_items(self, labels: list[str], current: int):
        self.list.blockSignals(True)
        self.list.clear()
        for lb in labels:
            QListWidgetItem(lb, self.list)
        self.list.setCurrentRow(current if 0 <= current < len(labels) else -1)
        self.list.blockSignals(False)

    def current_row(self) -> int:
        return self.list.currentRow()
