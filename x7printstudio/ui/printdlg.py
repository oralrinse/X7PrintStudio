# -*- coding: utf-8 -*-
"""打印/导出对话框: 通道选择、份数、纸长/墨量预估, 打印或仅导出作业 .bin。"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
                               QLabel, QComboBox, QSpinBox, QCheckBox, QFileDialog,
                               QMessageBox, QPushButton, QHBoxLayout, QWidget)
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
        qrow = QWidget()
        qh = QHBoxLayout(qrow)
        qh.setContentsMargins(0, 0, 0, 0)
        qh.addWidget(self.queue, 1)
        btn_refresh = QPushButton("刷新队列")
        btn_refresh.clicked.connect(self._reload_queues)
        qh.addWidget(btn_refresh)
        form.addRow("打印队列", qrow)

        self.conn = QLabel("…")
        self.conn.setWordWrap(True)
        form.addRow("连接情况", self.conn)
        self.queue.currentIndexChanged.connect(self._update_conn)

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

        self._fill_queues(select_fav=True)

        if not self.queues:
            self.btn_go.setEnabled(False)
            self.est.setText(self.est.text() + "\n未发现本地打印队列 → 请只导出 .bin")

    def _fill_queues(self, select_fav: bool):
        """重扫本地队列填入下拉; 尽量选中最可能的 X7 队列。"""
        self.queues = printer.list_queues()
        self.queue.blockSignals(True)
        self.queue.clear()
        for q in self.queues:
            tag = "USB" if printer.is_usb_port(q["port"]) else "网/其他"
            self.queue.addItem(f"{q['name']}  [{tag} {q['port']}]", q["name"])
        self.queue.blockSignals(False)
        if select_fav and self.queues:
            fav = printer.find_usb_queue()
            if fav:
                self.queue.setCurrentIndex(max(0, self.queue.findData(fav["name"])))
        self.btn_go.setEnabled(bool(self.queues))
        self._update_conn()

    def _reload_queues(self):
        """用户点“刷新队列”: 保留原选择, 若队列消失则自动选最优。"""
        prev = self.queue.currentData()
        self._fill_queues(select_fav=False)
        if not self.queues:
            return
        idx = self.queue.findData(prev) if prev else -1
        if idx < 0:
            fav = printer.find_usb_queue()
            idx = self.queue.findData(fav["name"]) if fav else 0
        if idx >= 0:
            self.queue.setCurrentIndex(idx)
        self._update_conn()

    def _update_conn(self):
        q = None
        name = self.queue.currentData()
        if name:
            q = next((x for x in self.queues if x["name"] == name), None)
        txt, ok = self._conn_text(q)
        color = "#1b7f3b" if ok else ("#b02010" if q else "#8a6d00")
        self.conn.setText(txt)
        self.conn.setStyleSheet(f"color:{color};")

    @staticmethod
    def _conn_text(q):
        """生成“连接情况”文案。返回 (文本, 是否就绪)。"""
        if q is None:
            return ("Windows 中尚未添加 X7 打印队列。\n"
                    "接好 USB 并开机后, 若系统没有自动出现, 请手动添加一次:\n"
                    "设置 → 打印机和扫描仪 → 添加设备 → 我需要的打印机不在列表中\n"
                    "→ 手动添加本地打印机 → 使用现有端口: 选以 USB 开头、\n"
                    "  括号内含 X7 设备名的端口(如 USB001, 不要选 LPT)\n"
                    "→ 厂商 Generic / 型号 Generic / Text Only → 完成\n"
                    "然后在右侧点“刷新队列”。在此之前可先“仅导出 .bin”。", False)
        is_usb = printer.is_usb_port(q["port"])
        is_x7 = printer.is_x7_queue(q)
        st = printer.queue_status(q["name"])
        if is_x7:
            head = "✓ 已识别得力 X7(USB)"
        elif is_usb:
            head = "USB 队列(名称未见 X7/得力, 型号待确认)"
        else:
            head = "非 USB 通道"
        lines = [head]
        if st["error"]:
            lines.append("✗ 无法读取该队列状态(可能已被移除)。")
            return "\n".join(lines), False
        if st["online"]:
            lines.append(f"✓ 在线 · 端口 {q['port']} · 可发送 RAW 作业")
            return "\n".join(lines), True
        reasons = list(st["flags"])
        if st["work_offline"]:
            reasons.append("脱机工作(作业被挂起)")
        lines.append("✗ 未在线: " + ("、".join(reasons) if reasons else "状态未知"))
        if is_usb:
            lines.append("  请检查 USB 线 / 打印机电源; 接好后再点“刷新队列”。")
        else:
            lines.append("  提示: 应选择端口为 USB、名称带 X7/得力 的队列。")
        return "\n".join(lines), False

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
