# -*- coding: utf-8 -*-
"""主窗口: 中央 1248px 画布 + 左图层面板 + 右属性面板 + 工具栏。

画布逻辑坐标 = 文档像素(1px = 1px@300dpi), 白色纸面 ≈ 105mm 宽连续纸。
鼠标: 单击选中(顶层优先) -> 拖拽移动; 图片选中后拉四角缩放; 双击文字=编辑内容。
所有几何都落回 doc.py 模型, 之后仅重渲染预览。
"""
from __future__ import annotations
import os

from PySide6.QtCore import Qt, QTimer, QPointF, QEvent
from PySide6.QtGui import (QAction, QColor, QImage, QPainter, QPen, QPixmap,
                           QBrush, QFont)
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                               QScrollArea, QFormLayout, QLabel, QComboBox,
                               QSpinBox, QCheckBox, QSlider, QPushButton,
                               QFileDialog, QMessageBox, QDockWidget, QGroupBox,
                               QToolBar)

from PIL import Image

from ..spec import WIDTH, ROWW, DPI, PAPER_MM, DEFAULT_CANVAS_H
from .. import raster as R
from ..compose import rasterize, measure_text, resolve_maxw
from ..doc import Document, TextItem, ImageItem
from .layers import LayersPanel
from .textdlg import TextDialog
from .imagedlg import pick_image

_MARGIN = 40
_BG_OUT = QColor(0xEC, 0xEC, 0xEC)
_SEL = QColor(0x1B, 0x9E, 0xFF)


def pil_l_to_qimage(im: Image.Image) -> QImage:
    w, h = im.size
    data = im.tobytes()
    qi = QImage(data, w, h, w, QImage.Format.Format_Grayscale8)
    return qi.convertToFormat(QImage.Format.Format_ARGB32)


def raster_to_qimage(raster: bytes) -> QImage:
    """FS 抖动后的 1bpp -> 灰阶预览(位1=黑)。"""
    rows = len(raster) // ROWW
    im = Image.new("L", (WIDTH, rows), 255)
    px = im.load()
    for y in range(rows):
        base = y * ROWW
        for b in range(ROWW):
            v = raster[base + b]
            for k in range(8):
                if v & (0x80 >> k):
                    px[b * 8 + k, y] = 0
    return pil_l_to_qimage(im)


class Canvas(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.zoom = 1.0
        self._pix = QPixmap()
        self._pix_need = (0, 0)
        self._mode = None          # None | move | resize
        self._grab = (0, 0)        # move: 指针相对item左上; resize: 角号0..3
        self._orig = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---- 布局/重绘 ----
    def rebuild(self):
        w = int(WIDTH * self.zoom) + _MARGIN * 2
        h = int(self.mw.doc.height * self.zoom) + _MARGIN * 2
        self.setMinimumSize(max(64, w), max(64, h))
        self._pix = QPixmap()
        self._pix_need = (0, 0)
        self.update()

    def set_zoom(self, z):
        self.zoom = max(0.05, min(8.0, z))
        self.rebuild()

    def _ensure_pix(self):
        img = self.mw.preview_image()
        if img is None:
            return
        need = (int(WIDTH * self.zoom), int(self.mw.doc.height * self.zoom))
        if self._pix_need == need and not self._pix.isNull():
            return
        self._pix = QPixmap.fromImage(img).scaled(
            need[0], need[1], Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._pix_need = need

    def paintEvent(self, _e):
        self._ensure_pix()
        p = QPainter(self)
        p.fillRect(self.rect(), _BG_OUT)
        ox, oy, z = _MARGIN, _MARGIN, self.zoom
        p.drawPixmap(ox, oy, self._pix)
        pw = int(WIDTH * z)
        ph = int(self.mw.doc.height * z)
        p.setPen(QPen(QColor(0, 0, 0, 50), 1))
        p.drawRect(ox, oy, pw, ph)
        sel = self.mw.sel
        if sel is not None:
            bb = self.mw.item_bbox(sel)
            if bb:
                x, y, w, h = bb
                p.setPen(QPen(_SEL, max(1, round(1.6 * z))))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(round(ox + x * z), round(oy + y * z),
                           max(1, round(w * z)), max(1, round(h * z)))
                if isinstance(self.mw.doc.items[sel], ImageItem):   # 图: 角点可拉
                    hs = max(4, round(4 * z))
                    for hx, hy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                        p.fillRect(round(ox + hx * z) - hs, round(oy + hy * z) - hs,
                                   hs * 2, hs * 2, _SEL)
        p.end()

    # ---- 坐标换算与命中 ----
    def _doc_pt(self, ev) -> tuple:
        return ((ev.position().x() - _MARGIN) / self.zoom,
                (ev.position().y() - _MARGIN) / self.zoom)

    def _hit(self, x, y) -> int:
        items = self.mw.doc.items
        for i in range(len(items) - 1, -1, -1):
            bx, by, bw, bh = self.mw.item_bbox(i)
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return i
        return -1

    def _corner(self, i, x, y, tol=14) -> int:
        bx, by, bw, bh = self.mw.item_bbox(i)
        pts = ((bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh))
        for k, (cx, cy) in enumerate(pts):
            if abs(x - cx) <= tol and abs(y - cy) <= tol:
                return k
        return -1

    # ---- 交互 ----
    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(ev)
        self.setFocus()
        x, y = self._doc_pt(ev)
        mw = self.mw
        i = self._hit(x, y)
        self._mode = None
        self._orig = None
        if i >= 0:
            it = mw.doc.items[i]
            self._orig = (it.x, it.y, it.w if isinstance(it, ImageItem) else 0,
                          it.h if isinstance(it, ImageItem) else 0)
            if isinstance(it, ImageItem) and self._corner(i, x, y) >= 0:
                self._mode = "resize"
                self._grab = self._corner(i, x, y)
            else:
                self._mode = "move"
                self._grab = (x - it.x, y - it.y)
        mw.select_index(i)
        mw.reload_panels()

    def mouseMoveEvent(self, ev):
        mw = self.mw
        x, y = self._doc_pt(ev)
        if self._mode and mw.sel is not None:
            it = mw.doc.items[mw.sel]
            if self._mode == "move":
                it.x = round(x - self._grab[0])
                it.y = round(y - self._grab[1])
            else:
                self._resize_image(it, x, y)
            mw.refresh_fast()
        else:
            h = self._hit(x, y)
            self.setCursor(Qt.CursorShape.SizeAllCursor if h >= 0
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):
        if self._mode:
            self._mode = None
            self._orig = None
            self.mw.finish_drag()
        x, y = self._doc_pt(ev)
        h = self._hit(x, y)
        self.setCursor(Qt.CursorShape.SizeAllCursor if h >= 0
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def _resize_image(self, it: ImageItem, x: float, y: float):
        c = self._grab
        ox, oy, ow, oh = self._orig
        if ow <= 0 or oh <= 0:
            return
        # 与所抓角相对的对角固定为锚
        ax = ox + ow if c in (0, 1) else ox
        ay = oy + oh if c in (0, 2) else oy
        if it.keep_aspect:
            k = max(0.0, (x - ax) / ow)
            w2 = max(8, round(ow * k))
            h2 = max(8, round(oh * k))
        else:
            w2 = max(8, round(abs(x - ax)))
            h2 = max(8, round(abs(y - ay)))
        nx = ax - w2 if c in (0, 1) else ax
        ny = ay - h2 if c in (0, 2) else ay
        it.x, it.y, it.w, it.h = nx, ny, w2, h2

    def keyPressEvent(self, ev):
        mw = self.mw
        i = mw.sel
        if ev.key() == Qt.Key.Key_Delete and i is not None:
            mw.remove_current()
        elif ev.key() == Qt.Key.Key_D and (ev.modifiers() & Qt.KeyboardModifier.ControlModifier):
            mw.dup_current()
        elif ev.key() == Qt.Key.Key_Return and i is not None:
            mw.edit_current()
        elif i is not None and ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                                            Qt.Key.Key_Up, Qt.Key.Key_Down):
            it = mw.doc.items[i]
            dx = -1 if ev.key() == Qt.Key.Key_Left else (1 if ev.key() == Qt.Key.Key_Right else 0)
            dy = -1 if ev.key() == Qt.Key.Key_Up else (1 if ev.key() == Qt.Key.Key_Down else 0)
            it.x += dx
            it.y += dy
            mw.refresh_soon()
        else:
            super().keyPressEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("X7 图文打印工作室")
        self.resize(1280, 860)
        self.doc = Document(height=DEFAULT_CANVAS_H)
        self.path = ""
        self.sel = -1
        self._gray_img = None
        self._dither_on = False
        self._dither_img = None
        self._building = False
        self.last_dir = os.path.expanduser("~")

        self.canvas = Canvas(self)
        sc = QScrollArea()
        sc.setWidget(self.canvas)
        sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sc.viewport().installEventFilter(self)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sc = sc
        self._fit = True          # 编辑区宽度自动适配可视区(无横向滚动条)
        self.setCentralWidget(sc)

        self._build_toolbar()
        self._build_docks()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._do_refresh)
        self._fast = QTimer(self)          # 拖拽期间的快速刷新节拍
        self._fast.setSingleShot(True)
        self._fast.setInterval(10)
        self._fast.timeout.connect(self._do_fast)
        self._dith_t = QTimer(self)
        self._dith_t.setSingleShot(True)
        self._dith_t.setInterval(350)
        self._dith_t.timeout.connect(self._compute_dither)
        self._upd_mm()
        self.refresh_soon()

    # ---------- 工具栏 ----------
    def _build_toolbar(self):
        tb = QToolBar("主")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text, slot, tip="", sc=None, check=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            a.setToolTip(tip)
            if sc:
                a.setShortcut(sc)
            if check:
                a.setCheckable(True)
            tb.addAction(a)
            return a

        act("新建", self.new_doc, "新建工程", "Ctrl+N")
        act("打开…", self.open_doc, "打开 .x7proj 工程", "Ctrl+O")
        act("保存", self.save_doc, "保存工程", "Ctrl+S")
        tb.addSeparator()
        act("＋图片", self.add_image, "插入图片")
        act("＋文字", self.add_text, "插入文字")
        tb.addSeparator()
        act("－", lambda: self._zoom_man(self.canvas.zoom / 1.25), "缩小(取消宽度自动适配)")
        act("＋", lambda: self._zoom_man(self.canvas.zoom * 1.25), "放大(取消宽度自动适配)")
        act("适合宽", self.fit_width, "重新开启宽度自动适配")
        self.act_dith = act("1bpp效果", self.toggle_dither, "预览抖动打印效果", check=True)
        tb.addSeparator()
        act("导出PNG…", self.export_png)
        tb.addSeparator()
        act("打印/导出作业…", self.open_print, "打印或导出 .bin", "Ctrl+P")

    def fit_width(self):
        """工具"适合宽": 重新开启宽度自动适配。"""
        self._fit = True
        self.sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fit_view()

    def _zoom_man(self, z):
        """手动缩放: 取消宽度自动适配, 允许横向平移查看放大细节。"""
        self._fit = False
        self.sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas.set_zoom(z)

    def _fit_view(self):
        """把纸宽(1248px)缩放到恰好在可视区内; 只留左衬边距, 无横向滚动条。"""
        vw = self.sc.viewport().width()
        if vw <= 0:
            return
        avail = max(160, vw - _MARGIN - 16)
        self.canvas.zoom = max(0.05, min(3.0, avail / WIDTH))
        self.canvas.rebuild()

    def showEvent(self, ev):
        super().showEvent(ev)
        if self._fit:
            QTimer.singleShot(0, self._fit_view)

    def eventFilter(self, obj, ev):
        if obj is self.sc.viewport() and ev.type() == QEvent.Type.Resize and self._fit:
            QTimer.singleShot(0, self._fit_view)
        return super().eventFilter(obj, ev)

    # ---------- 停靠面板 ----------
    def _build_docks(self):
        self.layers = LayersPanel()
        d = QDockWidget("图层", self)
        d.setWidget(self.layers)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)
        self.layers.select.connect(self._list_row_selected)
        self.layers.move_up.connect(self._list_move)
        self.layers.move_down.connect(lambda: self._list_move(False))
        self.layers.duplicate.connect(self.dup_current)
        self.layers.remove.connect(self.remove_current)
        self.layers.edit.connect(self.edit_current)
        self.layers.add_text.connect(self.add_text)
        self.layers.add_image.connect(self.add_image)

        self.prop_host = QWidget()
        pl = QVBoxLayout(self.prop_host)
        pl.setContentsMargins(6, 6, 6, 6)
        self._build_doc_props(pl)
        self.item_group = QGroupBox("选中图层")
        self.item_form = QFormLayout(self.item_group)
        self.item_group.setEnabled(False)
        pl.addWidget(self.item_group)
        pl.addStretch(1)
        d2 = QDockWidget("属性", self)
        d2.setWidget(self.prop_host)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d2)

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

    def _build_doc_props(self, pl):
        g = QGroupBox("画布  宽 1248px ≈ %.1fmm" % PAPER_MM)
        f = QFormLayout(g)
        self.p_bg = QComboBox()
        self.p_bg.addItem("白底", "w")
        self.p_bg.addItem("黑底(反白场景)", "k")
        self.p_bg.currentIndexChanged.connect(self._doc_bg)
        f.addRow("底色", self.p_bg)
        self.p_h = QSpinBox()
        self.p_h.setRange(64, 60000)
        self.p_h.setSuffix(" px")
        self.p_h.valueChanged.connect(self._doc_h)
        f.addRow("纸长(高)", self.p_h)
        self.p_h_mm = QLabel("")
        f.addRow("预估", self.p_h_mm)
        pl.addWidget(g)

    def _doc_bg(self, _):
        if self._building:
            return
        self.doc.bg = self.p_bg.currentData()
        self._dither_img = None
        self.refresh_soon()

    def _doc_h(self, v):
        if self._building:
            return
        self.doc.height = int(v)
        self._upd_mm()
        self._dither_img = None
        self.refresh_soon()

    def _upd_mm(self):
        self.p_h_mm.setText(f"纸长 ≈ {self.doc.height / DPI * 25.4:.0f} mm ({self.doc.height:,}px)")

    # ---------- 图层列表 ----------
    def _list_row_selected(self, row):
        if row < 0:
            return
        self.sel = len(self.doc.items) - 1 - row
        self.canvas.update()
        self.reload_panels()

    def _list_move(self, up=True):
        row = self.layers.current_row()
        n = len(self.doc.items)
        if row < 0 or n < 2:
            return
        target = row - 1 if up else row + 1
        if not (0 <= target < n):
            return
        # 画布上层 = 模型尾: 显示上移 1 行 => 模型 index +1; 下移 => -1
        m_cur = n - 1 - row
        self.doc.move(m_cur, 1 if up else -1)
        self.sel = (m_cur + 1) if up else (m_cur - 1)
        self._sync_all()

    # ---------- 常用操作 ----------
    def select_index(self, i):
        self.sel = i
        self.canvas.update()

    def _sync_all(self):
        self.reload_layers()
        self.reload_panels()
        self.canvas.update()

    def remove_current(self):
        if not (0 <= self.sel < len(self.doc.items)):
            return
        self.doc.remove(self.sel)
        self.sel = min(self.sel, len(self.doc.items) - 1)
        self._sync_all()
        self.refresh_soon()

    def dup_current(self):
        if not (0 <= self.sel < len(self.doc.items)):
            return
        self.sel = self.doc.duplicate(self.sel)
        self._sync_all()
        self.refresh_soon()

    def edit_current(self):
        i = self.sel
        if not (0 <= i < len(self.doc.items)):
            return
        it = self.doc.items[i]
        if isinstance(it, TextItem):
            TextDialog(it, self).exec()
        else:
            self._repick_image(it)

    def add_text(self):
        y = 40
        for o in self.doc.items:
            _x, _y, _w, h = self.item_bbox_of(o)
            y = max(y, _y + h + 40)
        it = TextItem(text="在此输入文字", x=60, y=y, maxw=WIDTH - 120,
                      size=44, align="left")
        self.doc.items.append(it)
        self.sel = len(self.doc.items) - 1
        self._sync_all()
        self.refresh_soon()
        TextDialog(it, self).exec()

    def add_image(self):
        self.last_dir, it = pick_image(self, self.last_dir)
        if it is None:
            return
        y = 40
        for o in self.doc.items:
            _x, _y, _w, h = self.item_bbox_of(o)
            y = max(y, _y + h + 40)
        it.y = y
        self.doc.items.append(it)
        self.sel = len(self.doc.items) - 1
        self._sync_all()
        self.refresh_soon()

    def _repick_image(self, it: ImageItem):
        p, _ = QFileDialog.getOpenFileName(self, "更换图片", it.path,
                                           "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        if p:
            it.path = p
            it._cache = {}
            self._sync_all()
            self.refresh_soon()

    # ---------- 几何 ----------
    def item_bbox(self, i):
        if not (0 <= i < len(self.doc.items)):
            return None
        return self.item_bbox_of(self.doc.items[i])

    def item_bbox_of(self, it):
        if isinstance(it, ImageItem):
            return it.x, it.y, it.w, it.h
        w = resolve_maxw(it) if resolve_maxw(it) else (WIDTH - it.x)
        return it.x, it.y, max(8, w), measure_text(it) or int(it.size * 1.18)

    # ---------- 预览 ----------
    def preview_image(self):
        if self._gray_img is None:
            self._render_gray()
        if self._dither_on and self._dither_img is not None:
            return self._dither_img
        return self._gray_img

    def _render_gray(self):
        g = rasterize(self.doc)
        self._gray_img = pil_l_to_qimage(g)

    def _compute_dither(self):
        if not self._dither_on:
            return
        try:
            g = rasterize(self.doc)
            rb = R.fs_dither(g)
            self._dither_img = raster_to_qimage(rb)
        except Exception:
            return
        self.canvas.update()

    def toggle_dither(self, on):
        self._dither_on = bool(on)
        self._dither_img = None
        if on:
            self._compute_dither()
        self.canvas.update()

    def request_doc_refresh(self):
        self._timer.start()

    def refresh_soon(self):
        self._timer.start()

    def refresh_fast(self):
        """拖拽期间的即时刷新: 合并到 ~10ms 节拍, 不重算 1bpp 抖动。"""
        if not self._fast.isActive():
            self._fast.start()

    def finish_drag(self):
        if self._fast.isActive():
            self._fast.stop()
        self.refresh_soon()

    def _do_fast(self):
        self._grow_if_needed()
        self._render_gray()
        self._dither_img = None
        self.canvas.rebuild()
        self.canvas.update()

    def _do_refresh(self):
        bottom = self._grow_if_needed()
        self._render_gray()
        self._dither_img = None
        if self._dither_on:
            self._dith_t.start()
        self.canvas.rebuild()
        self.canvas.update()
        self.statusBar().showMessage(
            f"图层 {len(self.doc.items)} · 内容至底 {bottom}px · 纸高 {self.doc.height}px · 显示 {self.canvas.zoom * 100:.0f}%")

    def _grow_if_needed(self) -> int:
        """内容超出画布底时自动加长纸高; 返回内容最底 y。"""
        bottom = 0
        for it in self.doc.items:
            _x, _y, _w, h = self.item_bbox_of(it)
            bottom = max(bottom, _y + h)
        if bottom > self.doc.height - 20:
            self.doc.height = max(self.doc.height, bottom + 60)
            self._upd_mm()
        return bottom

    # ---------- 面板同步 ----------
    def reload_layers(self):
        labels, n = [], len(self.doc.items)
        for dd in range(n):
            it = self.doc.items[n - 1 - dd]
            if isinstance(it, ImageItem):
                labels.append(f"{dd + 1:02d} 图 {os.path.basename(it.path)}")
            else:
                labels.append(f"{dd + 1:02d} 文 {it.text.replace(chr(10), ' ')[:14]}")
        self.layers.set_items(labels, (n - 1 - self.sel) if 0 <= self.sel < n else -1)

    def reload_panels(self):
        self._building = True
        try:
            self.p_bg.setCurrentIndex(max(0, self.p_bg.findData(self.doc.bg)))
            self.p_h.blockSignals(True)
            self.p_h.setValue(int(self.doc.height))
            self.p_h.blockSignals(False)
            self._upd_mm()
            self._rebuild_item_form()
        finally:
            self._building = False

    def _rebuild_item_form(self):
        self._clear_layout(self.item_form)
        i = self.sel
        if not (0 <= i < len(self.doc.items)):
            self.item_group.setEnabled(False)
            self.item_group.setTitle("选中图层 — 未选择")
            return
        self.item_group.setEnabled(True)
        it = self.doc.items[i]
        self.item_group.setTitle(f"{'图' if isinstance(it, ImageItem) else '文'} 第 {i + 1}/{len(self.doc.items)} 层")

        def spin(v, lo, hi, fn):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.blockSignals(True)
            s.setValue(int(v))
            s.blockSignals(False)
            s.valueChanged.connect(lambda x, f=fn: self._edit(f, int(x)))
            return s

        def clr():
            self._dither_img = None
            self.refresh_soon()

        if isinstance(it, ImageItem):
            self.item_form.addRow("X", spin(it.x, -4000, 8000, lambda v, it=it: setattr(it, "x", v)))
            self.item_form.addRow("Y", spin(it.y, -4000, 60000, lambda v, it=it: setattr(it, "y", v)))
            self.item_form.addRow("宽", spin(it.w, 8, 6000, lambda v, it=it: setattr(it, "w", v)))
            self.item_form.addRow("高", spin(it.h, 8, 60000, lambda v, it=it: setattr(it, "h", v)))

            ka = QCheckBox("保持纵横比")
            ka.setChecked(it.keep_aspect)
            ka.toggled.connect(lambda b, it=it: (setattr(it, "keep_aspect", b), clr()))
            self.item_form.addRow("", ka)

            md = QComboBox()
            for k, nm in (("gray", "原图灰阶"), ("bw", "黑白高对比"), ("invert", "反白")):
                md.addItem(nm, k)
            md.blockSignals(True)
            md.setCurrentIndex(max(0, md.findData(it.mode)))
            md.blockSignals(False)
            md.currentIndexChanged.connect(lambda _, it=it, md=md: (setattr(it, "mode", md.currentData()),
                                                                    self._thr.setEnabled(it.mode == "bw"), clr()))
            self.item_form.addRow("图像处理", md)

            self._thr = QSlider(Qt.Orientation.Horizontal)
            self._thr.setRange(0, 255)
            self._thr.blockSignals(True)
            self._thr.setValue(it.threshold)
            self._thr.blockSignals(False)
            self._thr.setEnabled(it.mode == "bw")
            self._thr.valueChanged.connect(lambda v, it=it: (setattr(it, "threshold", int(v)), clr()))
            self.item_form.addRow("阈值", self._thr)

            b = QPushButton("更换图片…")
            b.clicked.connect(lambda: self._repick_image(it))
            self.item_form.addRow("", b)
        else:
            self.item_form.addRow("X", spin(it.x, -4000, 8000, lambda v, it=it: setattr(it, "x", v)))
            self.item_form.addRow("Y", spin(it.y, -4000, 60000, lambda v, it=it: setattr(it, "y", v)))
            self.item_form.addRow("宽度", spin(it.maxw if it.maxw > 0 else WIDTH - it.x,
                                              60, 6000, lambda v, it=it: setattr(it, "maxw", v)))
            self.item_form.addRow("字号", spin(it.size, 6, 720, lambda v, it=it: setattr(it, "size", v)))
            al = QComboBox()
            for k, nm in (("left", "左"), ("center", "中"), ("right", "右")):
                al.addItem(nm, k)
            al.setCurrentIndex(max(0, al.findData(it.align)))
            al.currentIndexChanged.connect(lambda _, it=it, al=al: (setattr(it, "align", al.currentData()), clr()))
            self.item_form.addRow("对齐", al)
            self.item_form.addRow("文字高(估)", QLabel(f"≈ {measure_text(it)} px"))
            b = QPushButton("编辑文字内容…")
            b.clicked.connect(lambda: TextDialog(it, self).exec())
            self.item_form.addRow("", b)

    def _edit(self, fn, v):
        if self._building:
            return
        fn(v)
        self._dither_img = None
        self.refresh_soon()

    # ---------- 文件 ----------
    def new_doc(self):
        self.doc = Document(height=DEFAULT_CANVAS_H)
        self.path = ""
        self.sel = -1
        self._gray_img = None
        self._dither_img = None
        self.setWindowTitle("X7 图文打印工作室")
        self._sync_all()
        self.refresh_soon()

    def open_doc(self):
        p, _ = QFileDialog.getOpenFileName(self, "打开工程", self.last_dir,
                                           "X7 工程 (*.x7proj);;所有文件 (*)")
        if not p:
            return
        try:
            self.doc = Document.load(p)
        except Exception as ex:
            QMessageBox.warning(self, "打不开", f"工程解析失败:\n{ex}")
            return
        self.path = p
        self.last_dir = os.path.dirname(p)
        self.sel = -1
        self._gray_img = None
        self._dither_img = None
        self.setWindowTitle(f"X7 图文打印工作室 — {os.path.basename(p)}")
        self._sync_all()
        self.refresh_soon()

    def save_doc(self):
        if not self.path:
            p, _ = QFileDialog.getSaveFileName(self, "保存工程", "未命名.x7proj",
                                               "X7 工程 (*.x7proj)")
            if not p:
                return
            if not p.lower().endswith(".x7proj"):
                p += ".x7proj"
            self.path = p
        self.doc.save(self.path)
        self.last_dir = os.path.dirname(self.path)
        self.setWindowTitle(f"X7 图文打印工作室 — {os.path.basename(self.path)}")
        self.statusBar().showMessage("已保存", 2000)

    def export_png(self):
        p, _ = QFileDialog.getSaveFileName(self, "导出灰度 PNG", "x7_preview.png", "PNG (*.png)")
        if not p:
            return
        if not p.lower().endswith(".png"):
            p += ".png"
        rasterize(self.doc).save(p)
        self.statusBar().showMessage("已导出 " + p, 3000)

    def open_print(self):
        from .printdlg import PrintDialog
        if not self.doc.items:
            QMessageBox.information(self, "空白画布", "请先插入图片或文字。")
            return
        PrintDialog(self.doc, self).exec()
