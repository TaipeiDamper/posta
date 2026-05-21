import sys
import traceback

import cv2
import numpy as np
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

from core_engine import Graph
from core_nodes import ImageInputNode, SwitcherNode
from ui_graphics import GraphScene, NodeItem

from node_registry import NODE_MAP, PALETTE_CATEGORIES, resolve_registry_key
from graph_state import get_graph_state, dump_json, load_json
from graph_restore import GraphRestoreContext, restore_graph_state, bind_restore_node_press
from image_io import (
    normalize_to_bgra,
    bgra_to_qpixmap,
    clipboard_rgba_to_bgra,
    align_image_to_base,
    copy_bgra_to_clipboard,
)
from history import HistoryManager
from graph_evaluator import GraphEvaluator
from ui_components import ImagePreviewLabel, ConfigPanel, PaletteList, CanvasView, SearchMenu


class MainWindow(QMainWindow):
    _EVAL_DEBOUNCE_MS = 40

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Posta - Node-Based Image Engine")
        self.resize(1400, 900)

        self.graph = Graph()
        self.input_images = []
        self.base_size = None
        self.output_node = None
        self.global_input_image = None

        self.scene = GraphScene(self.graph)
        self.view = CanvasView(self.scene, self, NODE_MAP)
        self.view.main_window = self

        self._graph_evaluator = GraphEvaluator(self.graph, self)
        self._graph_evaluator.evaluation_done.connect(self._on_background_eval_done)

        self._history = HistoryManager(
            lambda: get_graph_state(self.graph, self.scene),
            self._restore_graph_state,
        )

        self._eval_timer = QTimer(self)
        self._eval_timer.setSingleShot(True)
        self._eval_timer.timeout.connect(self.evaluate_graph)

        self.setup_ui()
        self.setup_menu()

        self.scene.graph_structure_changed.connect(
            lambda: self.schedule_evaluate(immediate=True))
        self.scene.graph_state_changed.connect(self.save_state)

        self.setup_default_nodes()
        self.evaluate_graph()

        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer_tick)
        self.timer.start(500)

        screen_geo = QScreen.availableGeometry(QApplication.primaryScreen())
        w = min(1200, int(screen_geo.width() * 0.95))
        h = screen_geo.height() - 50
        self.resize(w, h)
        geo = self.frameGeometry()
        geo.moveCenter(screen_geo.center())
        geo.moveTop(screen_geo.top() + 5)
        self.move(geo.topLeft())

        # 延遲至佈局完成後置中畫面，確保啟動時兩個預設節點皆可見
        def _fit_default_view():
            rect = self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
            self.view.fitInView(rect, Qt.KeepAspectRatio)
            self.view._zoom = self.view.transform().m11()
        QTimer.singleShot(0, _fit_default_view)

    @property
    def is_restoring(self):
        return self._history.is_restoring

    def setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("檔案")
        file_menu.addAction("匯出範本 (JSON)", self.export_template)
        file_menu.addAction("匯入範本 (JSON)", self.import_template)
        file_menu.addSeparator()
        file_menu.addAction("儲存輸出圖", self.save_output_image)

        view_menu = menubar.addMenu("檢視")
        self.proxy_action = view_menu.addAction("代理預覽 (50%)")
        self.proxy_action.setCheckable(True)
        self.proxy_action.toggled.connect(self.toggle_proxy)

    def setup_ui(self):
        self.node_palette = PaletteList()

        for header, color, items in PALETTE_CATEGORIES:
            header_item = QListWidgetItem(header)
            header_item.setForeground(QBrush(QColor(100, 100, 100)))
            self.node_palette.addItem(header_item)
            for name in items:
                item = QListWidgetItem(name)
                item.setForeground(QBrush(color))
                self.node_palette.addItem(item)

        self.node_palette.itemDoubleClicked.connect(self.add_node_from_palette_event)
        self.node_palette.setDragEnabled(True)
        self.node_palette.setFixedWidth(160)

        left_sidebar = QWidget()
        ls_layout = QVBoxLayout(left_sidebar)
        ls_layout.setContentsMargins(2, 2, 2, 2)
        ls_label = QLabel(" 節點選單")
        ls_label.setStyleSheet("font-weight: bold; color: #888;")
        ls_layout.addWidget(ls_label)
        ls_layout.addWidget(self.node_palette)

        self.preview_label = ImagePreviewLabel("最終輸出預覽")
        self.preview_label.setStyleSheet("border: 1px solid #444; background-color: #000;")

        preview_header = QWidget()
        ph_layout = QHBoxLayout(preview_header)
        ph_layout.setContentsMargins(5, 2, 5, 2)
        ph_layout.addWidget(QLabel("成果展示 (Result View)"))
        ph_layout.addStretch()
        copy_btn = QPushButton("複製 (Copy)")
        copy_btn.setFixedWidth(100)
        copy_btn.clicked.connect(self.copy_output_to_clipboard)
        ph_layout.addWidget(copy_btn)
        save_btn = QPushButton("儲存 (Save)")
        save_btn.setFixedWidth(100)
        save_btn.clicked.connect(self.save_output_image)
        ph_layout.addWidget(save_btn)

        preview_container = QWidget()
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setSpacing(0)
        pc_layout.addWidget(preview_header)
        pc_layout.addWidget(self.preview_label, stretch=1)

        canvas_container = QWidget()
        cc_layout = QVBoxLayout(canvas_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(0)
        canvas_header = QLabel(" 節點工作區 (Node Graph)")
        canvas_header.setStyleSheet("background-color: #333; font-weight: bold; padding: 3px;")
        cc_layout.addWidget(canvas_header)
        cc_layout.addWidget(self.view)

        center_splitter = QSplitter(Qt.Vertical)
        center_splitter.addWidget(preview_container)
        center_splitter.addWidget(canvas_container)
        center_splitter.setSizes([450, 450])

        self.original_img_label = ImagePreviewLabel("原圖")
        self.original_img_label.mousePressEvent = self.load_original_image
        self.original_img_label.setFixedHeight(120)

        self.config_area = QScrollArea()
        self.config_area.setWidgetResizable(True)
        self.config_area.setStyleSheet("border: none; background: #252525;")

        right_sidebar = QWidget()
        rs_layout = QVBoxLayout(right_sidebar)
        rs_layout.setContentsMargins(5, 5, 5, 5)
        rs_layout.addWidget(QLabel("原始輸入 (Input Source):"))
        rs_layout.addWidget(self.original_img_label)
        clear_btn = QPushButton("清除輸入")
        clear_btn.clicked.connect(self.clear_input_image)
        rs_layout.addWidget(clear_btn)
        rs_layout.addSpacing(10)
        rs_layout.addWidget(QLabel("屬性編輯 (Properties):"))
        rs_layout.addWidget(self.config_area, stretch=1)

        self.main_h_splitter = QSplitter(Qt.Horizontal)
        self.main_h_splitter.addWidget(left_sidebar)
        self.main_h_splitter.addWidget(center_splitter)
        self.main_h_splitter.addWidget(right_sidebar)
        self.main_h_splitter.setSizes([160, 800, 240])
        self.setCentralWidget(self.main_h_splitter)

        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self.paste_image)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self.redo)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.export_template)

    def setup_default_nodes(self):
        self.add_node_by_name("Input", QPointF(-400, 0))
        self.add_node_by_name("Output", QPointF(400, 0))
        self.save_state()

    def schedule_evaluate(self, immediate=False):
        if immediate:
            self._eval_timer.stop()
            self.evaluate_graph()
            return
        self._eval_timer.start(self._EVAL_DEBOUNCE_MS)

    def _on_background_eval_done(self, revision):
        if not self._graph_evaluator.is_revision_current(revision):
            return
        self._apply_evaluate_ui()

    def _sync_input_nodes_to_global(self):
        for item in self.scene.items():
            if isinstance(item, NodeItem) and isinstance(item.node_model, ImageInputNode):
                item.node_model.set_external_image_source(lambda: self.global_input_image)

    def load_original_image(self, event):
        fname, _ = QFileDialog.getOpenFileName(self, "開啟原圖", "", "Image Files (*.png *.jpg *.bmp)")
        if fname:
            try:
                img = cv2.imdecode(np.fromfile(fname, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            except Exception:
                img = None
            if img is None:
                self.statusBar().showMessage("無法讀取影像檔案", 3000)
                return
            self.set_global_image(img)

    def paste_image(self):
        # 若焦點在文字輸入控件上，將貼上動作轉交給該控件
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit)):
            focus.paste()
            return
        if isinstance(focus, QSpinBox):
            if focus.lineEdit():
                focus.lineEdit().paste()
            return

        clipboard = QApplication.clipboard()
        if not clipboard.mimeData().hasImage():
            return
        
        locker = QMutexLocker(self._graph_evaluator.mutex)
        try:
            new_img, w, h = clipboard_rgba_to_bgra(clipboard.image())
            if new_img is None:
                return
            if self.base_size is None:
                self.base_size = (w, h)
            processed_img, _ = align_image_to_base(new_img, self.base_size)

            img_idx = len(self.input_images)
            self.input_images.append(processed_img)

            n_item = None
            if img_idx == 0:
                for item in self.scene.items():
                    if isinstance(item, NodeItem) and isinstance(item.node_model, ImageInputNode):
                        n_item = item
                        break
            if not n_item:
                n_item = self.add_node_by_name("輸入 (Input)")
            if n_item:
                n_item.node_model.set_external_image_source(
                    lambda idx=img_idx: self.input_images[idx])

            self.global_input_image = processed_img
            self.original_img_label.set_image(bgra_to_qpixmap(processed_img))
            self.graph.mark_all_dirty()
            self.schedule_evaluate(immediate=True)
        except Exception as e:
            traceback.print_exc()
            print(f"貼上圖片失敗: {e}")

    def select_node(self, node):
        if node is None:
            return
        self.config_area.setWidget(ConfigPanel(node, self.schedule_evaluate))

    def copy_output_to_clipboard(self):
        if self.output_node and hasattr(self.output_node, "_cached_outputs") and self.output_node._cached_outputs:
            img = self.output_node._cached_outputs.get("Image Out")
            if img is not None:
                copy_bgra_to_clipboard(img)
                self.statusBar().showMessage("已複製影像到剪貼簿", 2000)
            else:
                self.statusBar().showMessage("目前無輸出影像可複製", 2000)
        else:
            self.statusBar().showMessage("尚未產生輸出", 2000)

    def set_global_image(self, img):
        if img is None:
            return
        img = normalize_to_bgra(img)
        if img is None:
            return
        locker = QMutexLocker(self._graph_evaluator.mutex)
        self.global_input_image = img.copy()
        h, w = self.global_input_image.shape[:2]
        self.base_size = (w, h)
        if self.input_images:
            self.input_images[0] = self.global_input_image
        else:
            self.input_images = [self.global_input_image]
        self._sync_input_nodes_to_global()
        self.original_img_label.set_image(bgra_to_qpixmap(self.global_input_image))
        self.graph.mark_all_dirty()
        self.schedule_evaluate(immediate=True)

    def clear_input_image(self):
        locker = QMutexLocker(self._graph_evaluator.mutex)
        self.global_input_image = None
        self.original_img_label.clear_image()
        self.original_img_label.text = "原圖(貼上/點擊載入)"
        self.original_img_label.update()
        self.graph.mark_all_dirty()
        self.schedule_evaluate(immediate=True)

    def save_output_image(self):
        if not self.preview_label.pixmap_original or self.preview_label.pixmap_original.isNull():
            return
        fname, _ = QFileDialog.getSaveFileName(self, "儲存圖片", "", "Image Files (*.png *.jpg *.bmp)")
        if fname:
            self.preview_label.pixmap_original.save(fname)

    def add_node_from_palette_event(self, item):
        self.add_node_by_name(item.text())

    def add_node_by_name(self, name, pos=None):
        locker = QMutexLocker(self._graph_evaluator.mutex)
        key = resolve_registry_key(name)
        if key is None:
            return None
        display_name, cls = NODE_MAP[key]
        node = cls()
        if key == "Input":
            node.set_external_image_source(lambda: self.global_input_image)
        elif key == "Output":
            self.output_node = node
        node.name = display_name

        self.graph.add_node(node)
        n_item = NodeItem(node)
        self.scene.add_node(n_item)

        if pos:
            n_item.setPos(pos)
        else:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            off = (len(self.graph.nodes) % 10) * 20
            n_item.setPos(center.x() - 75 + off, center.y() - 50 + off)

        def on_press(event, ni=n_item):
            QGraphicsRectItem.mousePressEvent(ni, event)
            self.select_node(ni.node_model)

        def on_release(event, ni=n_item):
            QGraphicsRectItem.mouseReleaseEvent(ni, event)
            if not self.is_restoring:
                self.save_state()

        n_item.mousePressEvent = on_press
        n_item.mouseReleaseEvent = on_release

        if not self.is_restoring:
            self.save_state()
        return n_item

    def on_timer_tick(self):
        any_switch = False
        need_fast = False
        for n in self.graph.nodes:
            if isinstance(n, SwitcherNode):
                if n.params.get("smooth", 0):
                    need_fast = True
                if n.advance_if_due():
                    any_switch = True
        # 動態調整計時器間隔：平滑模式 50ms (~20fps)，否則 500ms
        target_interval = 50 if need_fast else 500
        if self.timer.interval() != target_interval:
            self.timer.setInterval(target_interval)
        if any_switch:
            self.schedule_evaluate(immediate=True)

    def show_config(self, node):
        self.config_area.setWidget(ConfigPanel(node, self.schedule_evaluate))

    def toggle_proxy(self, checked):
        self.graph.proxy_scale = 0.5 if checked else 1.0
        self.graph.mark_all_dirty()
        self.schedule_evaluate(immediate=True)

    def evaluate_graph(self):
        try:
            if self._graph_evaluator._use_background:
                self._graph_evaluator.request_background_evaluate()
                return
            self._graph_evaluator.evaluate_sync()
            self._apply_evaluate_ui()
        except Exception as e:
            traceback.print_exc()
            print(f"Error: {e}")

    def _apply_evaluate_ui(self):
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                item.update_thumbnail()
                msg = getattr(item.node_model, "_error_message", None)
                item.setToolTip(msg or "")
                item.update()

        w = self.config_area.widget()
        if w and hasattr(w, "update_histogram"):
            w.update_histogram()

        if self.output_node and hasattr(self.output_node, "final_image") and self.output_node.final_image is not None:
            self.show_image(self.output_node.final_image)
        else:
            self.preview_label.clear_image()
            self.preview_label.text = "等待連線或無有效輸出"
            self.preview_label.update()

    def show_image(self, img):
        if img is None:
            return
        self.preview_label.set_image(bgra_to_qpixmap(img))

    def save_state(self):
        self._history.save_state()

    def undo(self):
        self._history.undo()

    def redo(self):
        self._history.redo()

    def _restore_graph_state(self, state):
        locker = QMutexLocker(self._graph_evaluator.mutex)
        ctx = GraphRestoreContext(
            scene=self.scene,
            graph=self.graph,
            get_global_input_image=lambda: self.global_input_image,
            set_output_node=lambda n: setattr(self, "output_node", n),
            on_node_item_created=lambda ni, nm: bind_restore_node_press(
                ni, nm, self.show_config),
            clear_config_panel=lambda: self.config_area.setWidget(QWidget()),
            on_evaluate=lambda: self.schedule_evaluate(immediate=True),
        )
        restore_graph_state(state, ctx)

    def export_template(self):
        state = get_graph_state(self.graph, self.scene)
        fname, _ = QFileDialog.getSaveFileName(self, "匯出範本", "", "JSON Files (*.json)")
        if fname:
            dump_json(fname, state)

    def import_template(self):
        fname, _ = QFileDialog.getOpenFileName(self, "匯入範本", "", "JSON Files (*.json)")
        if fname:
            state = load_json(fname)
            self._history.restore_quiet(state)
            self.save_state()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(40, 40, 40))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor(25, 25, 25))
    pal.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    pal.setColor(QPalette.ToolTipBase, Qt.white)
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor(60, 60, 60))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.Link, QColor(42, 130, 218))
    app.setPalette(pal)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
