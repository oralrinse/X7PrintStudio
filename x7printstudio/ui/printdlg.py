# -*- coding: utf-8 -*-
"""打印/导出对话框: 通道选择、份数、纸长/墨量预估, 打印或仅导出作业 .bin。"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
                               QLabel, QComboBox, QSpinBox, QCheckBox, QFileDialog,
                               QMessageBox, QPushButton, QHBoxLayout)
from PySide6.QtCore import Qt

from .. import lzojob
from .. import raster as R
from .. import printer
from ..doc import Document
from ..compose import rasterize
from ..spec import DPI


class PrintDialog(QDialog):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("打印 / 导出")
        lay = QVBoxLayout(self)

        # 预计算本作业(与打印一致): 渲染→抖动→编码
        gray = rasterize(doc)
        self.raster = R.fs_dither(gray)
        rows = len(self.raster) // 156
        job = lzojob.job_bytes(self.raster)
        ink = R.ink_ratio(self.raster)
        len_mm = rows / DPI * 25.4

        form = QFormLayout()

        self.queue = QComboBox()
        self.queues = printer.list_queues()
        if self.queues:
            for i, q in enumerate(self.queues):
                tag = "USB" if ("usb" in q["port"].lower() or q["port"].isdigit()) else "网/其他"
                self.queue.addItem(f"{q['name']}  [{tag} {q['port']}]", q["name"])
            fav = printer.find_usb_queue()
            if fav:
                self.queue.setCurrentIndex(max(0, self.queue.findData(fav["name"])))
        form.addRow("打印队列", self.queue)

        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.copies.setValue(1)
        form.addRow("份数", self.copies)

        self.est = QLabel()
        form.addRow("预估", self.est)
        self.set_est(rows, len_mm, ink, len(job))

        self.only_export = QCheckBox("仅导出 .bin(不发送到打印机)")
        form.addRow("", self.only_export)

        lay.addLayout(form)

        tip = QLabel("将按原生幅宽 1248px≈105mm 直印。连续纸建议把画布高(纸长)设为内容实际高度。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#777;")
        lay.addWidget(tip)

        btns = QHBoxLayout()
        self.btn_go = QPushButton("打印")
        self.btn_go.clicked.connect(self._go)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_go)
        btns.addWidget(self.btn_cancel)
        lay.addLayout(btns)

        if not self.queues:
            self.btn_go.setEnabled(False)
            self.est.setText(self.est.text() + "\n未发现本地打印队列 → 请只导出 .bin")

    def set_est(self, rows, len_mm, ink, joblen):
        self.est.setText(
            f"纸长 ≈ {len_mm:.0f} mm  ({rows:,} 行 @300dpi)\n"
            f"墨量 ≈ {ink * 100:.0f}%   作业 {joblen / 1024:.0f} KB")

    def _go(self):
        name = self.queue.currentData()
        copies = self.copies.value()
        job = lzojob.job_bytes(self.raster)

        if self.only_export.isChecked():
            path, _ = QFileDialog.getSaveFileName(self, "导出作业", "x7_job.bin",
                                                  "X7 作业 (*.bin);;所有文件 (*)")
            if not path:
                return
            with open(path, "wb") as f:
                f.write(job)
            QMessageBox.information(self, "已导出", f"作业已保存:\n{path}")
            self.accept()
            return

        if not name:
            QMessageBox.warning(self, "无队列", "未选择打印队列。")
            return
        sent = printer.raw_send(name, job, copies)
        if sent > 0:
            QMessageBox.information(self, "已发送",
                                    f"已发送 {sent} 份到\n{name}\n\n打印机应已开始出纸。")
            self.accept()
        else:
            QMessageBox.critical(self, "发送失败",
                                 "写队列失败。\n请确认打印机已 USB 连接且队列处于在线状态;\n"
                                 "可改为“仅导出 .bin”后再用蓝牙桥等其它通道发送。")
