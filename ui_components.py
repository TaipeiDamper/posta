import cv2
import numpy as np
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

class ImagePreviewLabel(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self.text = text
        self.pixmap_original = None
        self.pixmap_scaled = None
        self.last_size = QSize(0, 0)
        self.setStyleSheet("background-color: #1a1a1a;")

    def set_image(self, pixmap):
        self.pixmap_original = pixmap
        self.pixmap_scaled = None
        self.update()

    def clear_image(self):
        self.pixmap_original = None
        self.pixmap_scaled = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        if self.pixmap_original and not self.pixmap_original.isNull():
            if self.pixmap_scaled is None or self.size() != self.last_size:
                self.pixmap_scaled = self.pixmap_original.scaled(
                    self.rect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.last_size = self.size()
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            x = (self.width() - self.pixmap_scaled.width()) // 2
            y = (self.height() - self.pixmap_scaled.height()) // 2
            painter.drawPixmap(x, y, self.pixmap_scaled)
        else:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text)

class ConfigPanel(QWidget):
    @staticmethod
    def _numeric_range_for_key(node, key, val):
        pm = getattr(node, "param_meta", None) or {}
        if key in pm:
            meta = pm[key]
            return int(meta.get("min", 0)), int(meta.get("max", 100))
        min_val, max_val = 0, 100
        if "%" in key:
            max_val = 100
        elif "kernel_size" in key:
            min_val, max_val = 1, 101
        elif "tolerance" in key:
            max_val = 255
        elif "threshold" in key:
            max_val = 500
        elif "brightness" in key or "contrast" in key:
            max_val = 100
        elif "font_scale" in key:
            min_val, max_val = 1, 20
        elif "pos_x" in key or "pos_y" in key:
            max_val = 2000
        elif "ratio_w" in key or "ratio_h" in key:
            min_val, max_val = 1, 32
        return min_val, max_val

    def __init__(self, node, update_callback):
        super().__init__()
        self.node = node
        self.update_callback = update_callback
        layout = QVBoxLayout()
        title = QLabel(f"設定: {node.name}")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFAAA5;")
        layout.addWidget(title)

        for key, val in node.params.items():
            if key == "image_path":
                continue
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(key))
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                min_val, max_val = self._numeric_range_for_key(self.node, key, val)
                pm = getattr(self.node, "param_meta", None) or {}
                meta = pm.get(key, {})
                is_float = isinstance(val, float) or isinstance(meta.get("step"), float)

                if is_float:
                    # 浮點數參數：僅使用 QDoubleSpinBox，可直接打字輸入
                    spin = QDoubleSpinBox()
                    spin.setRange(float(min_val), float(max_val))
                    spin.setDecimals(int(meta.get("decimals", 2)))
                    spin.setSingleStep(float(meta.get("step", 0.1)))
                    spin.setValue(float(val))

                    def on_float_changed(v, k=key):
                        self.node.params[k] = v
                        self.update_callback()
                    spin.valueChanged.connect(on_float_changed)
                    spin.editingFinished.connect(self.commit_param)
                    hbox.addWidget(spin)
                else:
                    # 整數參數：slider + QSpinBox 組合
                    slider = QSlider(Qt.Horizontal)
                    slider.setRange(int(min_val), int(max_val))
                    slider.setValue(int(val))
                    spin = QSpinBox()
                    spin.setRange(int(min_val), int(max_val))
                    spin.setValue(int(val))
                    slider.valueChanged.connect(spin.setValue)
                    spin.valueChanged.connect(slider.setValue)

                    def on_release(k=key, s=slider):
                        self.node.params[k] = s.value()
                        self.update_callback()
                        self.commit_param()
                    slider.sliderReleased.connect(on_release)

                    def on_spin(v, k=key, s=slider):
                        if not s.isSliderDown():
                            self.node.params[k] = v
                            self.update_callback()
                    spin.valueChanged.connect(on_spin)
                    spin.editingFinished.connect(self.commit_param)
                    hbox.addWidget(slider)
                    hbox.addWidget(spin)
            elif isinstance(val, list):
                btn = QPushButton("選擇顏色")
                btn.setStyleSheet(f"background-color: rgb({val[0]},{val[1]},{val[2]}); color: black;")
                btn.clicked.connect(lambda _, k=key, b=btn: self.pick_color(k, b))
                hbox.addWidget(btn)
            elif isinstance(val, str):
                if key == "mode":
                    edit = QComboBox()
                    edit.addItems(["Multiply", "Screen", "Overlay", "Add", "Normal"])
                    edit.setCurrentText(val)
                    edit.currentTextChanged.connect(lambda v, k=key: self.update_param(k, v))
                else:
                    edit = QLineEdit(val)
                    edit.textChanged.connect(lambda v, k=key: self.update_param(k, v))
                    edit.editingFinished.connect(lambda: (self.update_callback(), self.commit_param()))
                hbox.addWidget(edit)
            layout.addLayout(hbox)

        if node.__class__.__name__ in (
            "BrightnessContrastNode", "LuminanceNode", "PosterizeNode",
            "TintNode", "MidtoneKeyNode", "GradientMapNode",
        ):
            self.hist_label = QLabel()
            self.hist_label.setMinimumSize(230, 80)
            layout.addWidget(self.hist_label)
            self.update_histogram()

        layout.addStretch()
        self.setLayout(layout)

    def update_histogram(self):
        if not hasattr(self, "hist_label"):
            return
        img = None
        if hasattr(self.node, "_cached_outputs") and self.node._cached_outputs is not None:
            img = self.node._cached_outputs.get("Image Out")
        if img is None:
            return

        hist_w, hist_h = 230, 80
        hist_img = np.zeros((hist_h, hist_w, 3), dtype=np.uint8)
        colors = np.array([(255, 0, 0), (0, 255, 0), (0, 0, 255)], dtype=np.uint8)
        xs = np.arange(hist_w, dtype=np.int32)
        bin_idx = np.clip((xs * 256) // hist_w, 0, 255)

        for i, col in enumerate(colors):
            hist = cv2.calcHist([img], [i], None, [256], [0, 256]).flatten()
            cv2.normalize(hist, hist, alpha=0, beta=hist_h, norm_type=cv2.NORM_MINMAX)
            ys = hist_h - hist[bin_idx].astype(np.int32)
            ys = np.clip(ys, 0, hist_h - 1)
            hist_img[ys, xs] = col

        qimg = QImage(hist_img.data, hist_w, hist_h, 3 * hist_w, QImage.Format_BGR888)
        self.hist_label.setPixmap(QPixmap.fromImage(qimg.copy()))

    def update_param(self, key, val):
        self.node.params[key] = val

    def commit_param(self):
        if hasattr(self.window(), "save_state"):
            self.window().save_state()

    def pick_color(self, key, btn):
        color = QColorDialog.getColor()
        if color.isValid():
            rgb = [color.red(), color.green(), color.blue()]
            self.node.params[key] = rgb
            btn.setStyleSheet(f"background-color: {color.name()}; color: black;")
            self.update_callback()
            self.commit_param()

class PaletteList(QListWidget):
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            mimeData = QMimeData()
            mimeData.setText(item.text())
            drag = QDrag(self)
            drag.setMimeData(mimeData)
            drag.exec(supportedActions)

class CanvasView(QGraphicsView):
    def __init__(self, scene, main_window, node_map):
        super().__init__(scene)
        self.main_window = main_window
        self.node_map = node_map
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self._zoom = 1.0
        self._is_panning = False
        self._last_pan_pos = QPoint()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom *= factor
        self._zoom = max(0.1, min(5.0, self._zoom))
        self.setTransform(QTransform().scale(self._zoom, self._zoom))

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._last_pan_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.position().toPoint() - self._last_pan_pos
            self._last_pan_pos = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        name = event.mimeData().text()
        pos = self.mapToScene(event.position().toPoint())
        self.main_window.add_node_by_name(name, pos)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Tab):
            menu = SearchMenu(self, self.mapToScene(self.mapFromGlobal(QCursor.pos())), self.node_map)
            menu.move(QCursor.pos())
            if menu.exec() == QDialog.Accepted:
                name = menu.get_selected()
                if name:
                    self.main_window.add_node_by_name(name, menu.pos_scene)
            event.accept()
        else:
            super().keyPressEvent(event)

class SearchMenu(QDialog):
    def __init__(self, parent, pos_scene, node_map):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.pos_scene = pos_scene
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜尋節點 (Press Enter)...")
        self.list_widget = QListWidget()
        self.layout().addWidget(self.search_box)
        self.layout().addWidget(self.list_widget)

        self.all_items = [(display_name, key) for key, (display_name, _) in node_map.items()]
        for display_name, key in self.all_items:
            it = QListWidgetItem(display_name)
            it.setData(Qt.UserRole, key)
            self.list_widget.addItem(it)

        self.search_box.textChanged.connect(self.filter_list)
        self.list_widget.itemActivated.connect(self.accept)
        self.search_box.returnPressed.connect(self.on_enter)
        self.search_box.setFocus()

    def filter_list(self, text):
        self.list_widget.clear()
        t = text.lower()
        for display_name, key in self.all_items:
            if t in display_name.lower():
                it = QListWidgetItem(display_name)
                it.setData(Qt.UserRole, key)
                self.list_widget.addItem(it)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def on_enter(self):
        if self.list_widget.currentItem():
            self.accept()

    def get_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return None
        key = item.data(Qt.UserRole)
        return key if key else None
