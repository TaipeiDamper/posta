import sys, json, cv2, numpy as np
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

from core_engine import Graph
from core_nodes import (ImageInputNode, ColorReplaceNode, EdgeDetectNode, BlurNode,
    MergeNode, OutputNode, TintNode, LuminanceNode, BlendNode, SwitcherNode,
    BrightnessContrastNode, InvertNode, TextNode, SmartCropNode, ValueNode,
    ColorOutputNode, RerouteNode)
from ui_graphics import GraphScene, NodeItem, ConnectionItem, BackdropItem, StickyNoteItem

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
    def __init__(self, node, update_callback):
        super().__init__()
        self.node = node
        self.update_callback = update_callback
        layout = QVBoxLayout()
        title = QLabel(f"設定: {node.name}")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFAAA5;")
        layout.addWidget(title)

        for key, val in node.params.items():
            if key == "image_path": continue
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(key))
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                min_val, max_val = 0, 100
                if "%" in key: max_val = 100
                elif "kernel_size" in key: min_val, max_val = 1, 101
                elif "tolerance" in key: max_val = 255
                elif "threshold" in key: max_val = 500
                elif "brightness" in key or "contrast" in key: max_val = 100
                elif "font_scale" in key: min_val, max_val = 1, 20
                elif "pos_x" in key or "pos_y" in key: max_val = 2000
                elif "ratio_w" in key or "ratio_h" in key: min_val, max_val = 1, 32

                slider = QSlider(Qt.Horizontal)
                slider.setRange(min_val, max_val)
                slider.setValue(int(val))
                spin = QSpinBox()
                spin.setRange(min_val, max_val)
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
        layout.addStretch()
        self.setLayout(layout)

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
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self._zoom = 1.0

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self._zoom *= factor
        self._zoom = max(0.1, min(5.0, self._zoom))
        self.setTransform(QTransform().scale(self._zoom, self._zoom))

    def dragEnterEvent(self, event):
        if event.mimeData().hasText(): event.acceptProposedAction()
    def dragMoveEvent(self, event):
        if event.mimeData().hasText(): event.acceptProposedAction()
    def dropEvent(self, event):
        name = event.mimeData().text()
        pos = self.mapToScene(event.position().toPoint())
        self.main_window.add_node_by_name(name, pos)
        event.acceptProposedAction()

# ==================== 節點名稱到類別的映射 ====================
NODE_MAP = {
    "Input": ("原圖輸入", ImageInputNode),
    "Output": ("最終輸出", OutputNode),
    "Tint": ("染色", TintNode),
    "Color Replace": ("替換顏色", ColorReplaceNode),
    "Luma": ("明度選取", LuminanceNode),
    "Edge Detect": ("邊緣擷取", EdgeDetectNode),
    "Brightness": ("亮度對比", BrightnessContrastNode),
    "Invert": ("負片", InvertNode),
    "Blur": ("高斯模糊", BlurNode),
    "Merge": ("圖層合併", MergeNode),
    "Blend": ("進階混合", BlendNode),
    "Switcher": ("時間切換", SwitcherNode),
    "Text": ("文字", TextNode),
    "Crop": ("智慧裁切", SmartCropNode),
    "Value": ("數值", ValueNode),
    "ColorOut": ("顏色輸出", ColorOutputNode),
    "Reroute": ("轉向", RerouteNode),
}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Posta - 半自動電子海報生成器")
        self.global_input_image = None
        self.graph = Graph()
        self.scene = GraphScene(self.graph)
        self.scene.setParent(self)
        self.view = CanvasView(self.scene, self)
        self.output_node = None
        self.history = []
        self.is_restoring = False

        self.setup_ui()
        self.setup_menu()
        self.setup_default_nodes()

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
        self.original_img_label = ImagePreviewLabel("原圖(貼上/點擊載入)")
        self.original_img_label.mousePressEvent = self.load_original_image
        self.original_img_label.setStyleSheet("border: 2px dashed #555; background-color: #2a2a2a;")

        clear_btn = QPushButton("清除輸入圖")
        clear_btn.clicked.connect(self.clear_input_image)

        left_top_layout = QVBoxLayout()
        left_top_layout.setContentsMargins(0,0,0,0)
        left_top_layout.addWidget(self.original_img_label, stretch=1)
        left_top_layout.addWidget(clear_btn)
        left_top_widget = QWidget()
        left_top_widget.setLayout(left_top_layout)
        left_top_widget.setMinimumSize(50, 50)

        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self.paste_image)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.export_template)

        self.node_palette = PaletteList()
        self.node_palette.addItems([
            "輸入 (Input)", "輸出 (Output)",
            "染色 (Tint)", "替換顏色 (Color Replace)",
            "明度選取 (Luma Key)", "邊緣擷取 (Edge Detect)",
            "亮度對比 (Brightness)", "負片 (Invert)", "高斯模糊 (Blur)",
            "圖層合併 (Merge)", "進階混合 (Blend)", "時間切換 (Switcher)",
            "文字 (Text)", "智慧裁切 (Crop)",
            "數值 (Value)", "顏色 (ColorOut)", "轉向 (Reroute)"
        ])
        self.node_palette.itemDoubleClicked.connect(self.add_node_from_palette_event)
        self.node_palette.setDragEnabled(True)

        self.config_area = QScrollArea()
        self.config_area.setWidgetResizable(True)
        self.config_area.setMinimumHeight(50)

        palette_splitter = QSplitter(Qt.Vertical)
        pt = QWidget(); ptl = QVBoxLayout(pt); ptl.setContentsMargins(0,0,0,0)
        ptl.addWidget(QLabel("可更動元件 (雙擊加入畫布):"))
        ptl.addWidget(self.node_palette)
        pb = QWidget(); pbl = QVBoxLayout(pb); pbl.setContentsMargins(0,0,0,0)
        pbl.addWidget(QLabel("節點屬性設定:"))
        pbl.addWidget(self.config_area)
        palette_splitter.addWidget(pt)
        palette_splitter.addWidget(pb)
        palette_splitter.setSizes([150, 250])

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(left_top_widget)
        left_splitter.addWidget(palette_splitter)
        left_splitter.setSizes([300, 300])

        self.preview_label = ImagePreviewLabel("處理後圖片(準備輸出)")
        self.preview_label.setStyleSheet("border: 2px solid #000; background-color: #1a1a1a;")
        save_btn = QPushButton("儲存輸出圖")
        save_btn.clicked.connect(self.save_output_image)
        rtl = QVBoxLayout(); rtl.setContentsMargins(0,0,0,0)
        rtl.addWidget(self.preview_label, stretch=1); rtl.addWidget(save_btn)
        rtw = QWidget(); rtw.setLayout(rtl); rtw.setMinimumSize(50,50)

        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(left_splitter)
        top_splitter.addWidget(rtw)
        top_splitter.setSizes([350, 850])

        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        cl = QVBoxLayout(); cl.setContentsMargins(0,0,0,0)
        lbl = QLabel("資訊流位置 (節點連線區)")
        lbl.setStyleSheet("background-color: #333; font-weight: bold; padding: 5px;")
        cl.addWidget(lbl); cl.addWidget(self.view)
        cw = QWidget(); cw.setLayout(cl); cw.setMinimumSize(50,50)
        main_splitter.addWidget(cw)
        main_splitter.setSizes([500, 400])
        self.setCentralWidget(main_splitter)

    def setup_default_nodes(self):
        inp = self.add_node_by_name("Input"); 
        if inp: inp.setPos(-300, 0)
        out = self.add_node_by_name("Output")
        if out: out.setPos(300, 0)
        self.save_state()

    # ========== 圖片操作 ==========
    def load_original_image(self, event):
        fname, _ = QFileDialog.getOpenFileName(self, "開啟原圖", "", "Image Files (*.png *.jpg *.bmp)")
        if fname:
            self.set_global_image(cv2.imread(fname, cv2.IMREAD_UNCHANGED))

    def paste_image(self):
        cb = QApplication.clipboard()
        if cb.mimeData().hasImage():
            qimg = cb.image().convertToFormat(QImage.Format_RGBA8888)
            w, h = qimg.width(), qimg.height()
            arr = np.array(qimg.constBits()).reshape(h, w, 4)
            self.set_global_image(cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA))

    def set_global_image(self, img):
        if img is None: return
        if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif len(img.shape) == 3 and img.shape[2] == 3: img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        self.global_input_image = img
        h, w = img.shape[:2]
        rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        self.original_img_label.set_image(QPixmap.fromImage(QImage(rgba.data, w, h, 4*w, QImage.Format_RGBA8888)))
        self.graph.mark_all_dirty()
        self.evaluate_graph()

    def clear_input_image(self):
        self.global_input_image = None
        self.original_img_label.clear_image()
        self.original_img_label.text = "原圖(貼上/點擊載入)"
        self.original_img_label.update()
        self.graph.mark_all_dirty()
        self.evaluate_graph()

    def save_output_image(self):
        if not self.preview_label.pixmap_original or self.preview_label.pixmap_original.isNull(): return
        fname, _ = QFileDialog.getSaveFileName(self, "儲存圖片", "", "Image Files (*.png *.jpg *.bmp)")
        if fname: self.preview_label.pixmap_original.save(fname)

    # ========== 節點操作 ==========
    def add_node_from_palette_event(self, item):
        self.add_node_by_name(item.text())

    def add_node_by_name(self, name, pos=None):
        node = None
        for key, (display_name, cls) in NODE_MAP.items():
            if key in name:
                node = cls()
                if key == "Input":
                    node.process = lambda **kw: {"Image Out": self.global_input_image}
                elif key == "Output":
                    self.output_node = node
                node.name = display_name
                break
        if not node: return None

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
            self.show_config(ni.node_model)
        n_item.mousePressEvent = on_press

        def on_release(event, ni=n_item):
            QGraphicsRectItem.mouseReleaseEvent(ni, event)
            if not self.is_restoring: self.save_state()
        n_item.mouseReleaseEvent = on_release

        if not self.is_restoring: self.save_state()
        return n_item

    def on_timer_tick(self):
        if any(isinstance(n, SwitcherNode) for n in self.graph.nodes):
            self.graph.mark_all_dirty()
            self.evaluate_graph()

    def show_config(self, node):
        self.config_area.setWidget(ConfigPanel(node, self.evaluate_graph))

    def toggle_proxy(self, checked):
        self.graph.proxy_scale = 0.5 if checked else 1.0
        self.graph.mark_all_dirty()
        self.evaluate_graph()

    # ========== 運算 ==========
    def evaluate_graph(self):
        try:
            self.graph.evaluate()
            if self.output_node and hasattr(self.output_node, 'final_image') and self.output_node.final_image is not None:
                self.show_image(self.output_node.final_image)
            else:
                self.preview_label.clear_image()
                self.preview_label.text = "等待連線或無有效輸出"
                self.preview_label.update()
        except Exception as e:
            print(f"Error: {e}")

    def show_image(self, img):
        if img is None: return
        h, w = img.shape[:2]
        rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        self.preview_label.set_image(QPixmap.fromImage(QImage(rgba.data, w, h, 4*w, QImage.Format_RGBA8888)))

    # ========== 歷史 (Undo) ==========
    def save_state(self):
        if self.is_restoring: return
        self.history.append(self.get_graph_state())
        if len(self.history) > 30: self.history.pop(0)

    def undo(self):
        if len(self.history) > 1:
            self.history.pop()
            self.is_restoring = True
            self.restore_graph_state(self.history[-1])
            self.is_restoring = False

    def get_graph_state(self):
        state = {"nodes": [], "edges": []}
        nmap = {i.node_model: i for i in self.scene.items() if isinstance(i, NodeItem)}
        for node in self.graph.nodes:
            item = nmap.get(node)
            p = (item.scenePos().x(), item.scenePos().y()) if item else (0,0)
            state["nodes"].append({"id": node.id, "type": node.__class__.__name__,
                "name": node.name, "pos": p, "params": dict(node.params), "bypassed": node.bypassed})
            for pn, ip in node.inputs.items():
                for e in ip.edges:
                    state["edges"].append({"out_node": e.output_pin.node.id, "out_pin": e.output_pin.name,
                        "in_node": node.id, "in_pin": pn, "weight": e.weight, "bypassed": e.bypassed})
        return state

    def restore_graph_state(self, state):
        self.scene.clear()
        self.graph.nodes.clear()
        self.output_node = None
        node_map = {}
        for nd in state["nodes"]:
            cls = globals().get(nd["type"])
            if not cls: continue
            node = cls()
            node.id = nd["id"]; node.name = nd["name"]
            node.params.update(nd["params"])
            node.bypassed = nd.get("bypassed", False)
            if nd["type"] == "ImageInputNode":
                node.process = lambda **kw: {"Image Out": self.global_input_image}
            elif nd["type"] == "OutputNode":
                self.output_node = node
            self.graph.add_node(node)
            node_map[node.id] = node
            ni = NodeItem(node); ni.setPos(nd["pos"][0], nd["pos"][1])
            self.scene.add_node(ni)
            def mp(event, n=ni):
                QGraphicsRectItem.mousePressEvent(n, event)
                self.show_config(n.node_model)
            ni.mousePressEvent = mp

        imap = {i.node_model.id: i for i in self.scene.items() if isinstance(i, NodeItem)}
        for ed in state["edges"]:
            on = node_map.get(ed["out_node"]); inn = node_map.get(ed["in_node"])
            if not on or not inn: continue
            op = next((p for _,p in on.outputs.items() if p.name==ed["out_pin"]), None)
            ip = next((p for _,p in inn.inputs.items() if p.name==ed["in_pin"]), None)
            if op and ip:
                edge = ip.connect(op); edge.weight = ed["weight"]; edge.bypassed = ed["bypassed"]
                oi, ii = imap.get(on.id), imap.get(inn.id)
                if oi and ii:
                    opi, ipi = oi.pin_items.get(op.id), ii.pin_items.get(ip.id)
                    if opi and ipi:
                        conn = ConnectionItem(opi, ipi); conn.edge_model = edge
                        conn.weight_text.setPlainText(str(edge.weight))
                        if edge.weight != 1.0: conn.weight_text.show()
                        self.scene.addItem(conn)
                        opi.add_connection(conn); ipi.add_connection(conn); conn.update_path()
        self.config_area.setWidget(QWidget())
        self.evaluate_graph()

    # ========== 匯出/匯入 JSON ==========
    def export_template(self):
        state = self.get_graph_state()
        fname, _ = QFileDialog.getSaveFileName(self, "匯出範本", "", "JSON Files (*.json)")
        if fname:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

    def import_template(self):
        fname, _ = QFileDialog.getOpenFileName(self, "匯入範本", "", "JSON Files (*.json)")
        if fname:
            with open(fname, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.is_restoring = True
            self.restore_graph_state(state)
            self.is_restoring = False
            self.save_state()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(40,40,40))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor(25,25,25))
    pal.setColor(QPalette.AlternateBase, QColor(40,40,40))
    pal.setColor(QPalette.ToolTipBase, Qt.white)
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor(60,60,60))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.Link, QColor(42,130,218))
    app.setPalette(pal)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
