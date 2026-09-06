# -*- coding: utf-8 -*-
"""文字编辑对话框。"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
                               QPlainTextEdit, QSpinBox, QCheckBox, QComboBox)
from PySide6.QtCore import Qt

from ..doc import TextItem


class TextDialog(QDialog):
    """编辑一段文字的内容/字号/粗细/对齐/反白。直接修改传入的 item。"""

    def __init__(self, item: TextItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("文字")
        lay = QVBoxLayout(self)

        self.ed = QPlainTextEdit()
        self.ed.setPlainText(item.text)
        self.ed.setPlaceholderText("输入文字, 换行即另起一段…")
        self.ed.setFixedHeight(120)
        lay.addWidget(self.ed)

        form = QFormLayout()
        self.size = QSpinBox()
        self.size.setRange(8, 720)
        self.size.setValue(item.size)
        self.size.setSuffix(" px")
        form.addRow("字号", self.size)

        self.bold = QCheckBox("粗体")
        self.bold.setChecked(item.bold)
        form.addRow("", self.bold)

        self.align = QComboBox()
        self.align.addItem("左对齐", "left")
        self.align.addItem("居中", "center")
        self.align.addItem("右对齐", "right")
        self.align.setCurrentIndex(max(0, self.align.findData(item.align)))
        form.addRow("对齐", self.align)

        self.color = QComboBox()
        self.color.addItem("黑字(白/浅底)", "k")
        self.color.addItem("白字(反白, 用于深色底)", "w")
        self.color.setCurrentIndex(max(0, self.color.findData(item.color)))
        form.addRow("颜色", self.color)

        self.color.currentIndexChanged.connect(self._live)
        self.size.valueChanged.connect(self._live)
        lay.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _live(self):
        self._apply()
        self._parent_repaint()

    def _apply(self):
        it = self.item
        it.text = self.ed.toPlainText()
        it.size = self.size.value()
        it.bold = self.bold.isChecked()
        it.align = self.align.currentData()
        it.color = self.color.currentData()

    def _parent_repaint(self):
        p = self.parentWidget()
        while p is not None and not hasattr(p, "request_doc_refresh"):
            p = p.parentWidget()
        if p is not None:
            p.request_doc_refresh()

    def accept(self):
        self._apply()
        self._parent_repaint()
        super().accept()
