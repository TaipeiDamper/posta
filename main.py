import sys
import cv2
import numpy as np
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

from core_engine import Graph
from core_nodes import ImageInputNode, ColorReplaceNode, EdgeDetectNode, BlurNode, MergeNode, OutputNode, TintNode, LuminanceNode, BlendNode, SwitcherNode, BrightnessContrastNode, InvertNode
from ui_graphics import GraphScene, NodeItem

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
        self.pixmap_scaled = None # Reset cache
        self.update()
        
    def clear_image(self):
        self.pixmap_original = None
        self.pixmap_scaled = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        
        if self.pixmap_original and not self.pixmap_original.isNull():
            # 只有在尺寸改變或快取失效時才重新縮放，大幅提升 UI 流暢度
            if self.pixmap_scaled is None or self.size() != self.last_size:
                self.pixmap_scaled = self.pixmap_original.scaled(
                    self.rect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
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
            if key == "image_path": continue # 將由全域原圖區接管
            
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(key))
            if isinstance(val, int):
                # 根據參數名稱設定更合理的數值範圍
                min_val = 0
                max_val = 100 # 預設改為 0~100，避免拉桿過於靈敏
                
                if "%" in key:
                    max_val = 100
                elif "kernel_size" in key:
                    min_val = 1
                    max_val = 101
                elif "tolerance" in key:
                    max_val = 255
                elif "threshold" in key:
                    max_val = 500
                
                slider = QSlider(Qt.Horizontal)
                slider.setRange(min_val, max_val)
                slider.setValue(val)
                
                spin = QSpinBox()
                spin.setRange(min_val, max_val)
                spin.setValue(val)
                
                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
                
                # 只有放開拉桿才運算，避免拖曳時瘋狂重算造成卡頓
                def on_slider_release(k=key, s=slider):
                    self.node.params[k] = s.value()
                    self.update_callback()
                    self.commit_param()
                
                slider.sliderReleased.connect(on_slider_release)
                
                def on_spin_change(v, k=key, s=slider):
                    if not s.isSliderDown():
                        self.node.params[k] = v
                        self.update_callback()
                        
                spin.valueChanged.connect(on_spin_change)
                spin.editingFinished.connect(self.commit_param)
                
                hbox.addWidget(slider)
                hbox.addWidget(spin)
            elif isinstance(val, list): # For RGB
                btn = QPushButton("選擇顏色")
                btn.setStyleSheet(f"background-color: rgb({val[0]}, {val[1]}, {val[2]}); color: black;")
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
                hbox.addWidget(edit)
            layout.addLayout(hbox)
        layout.addStretch()
        self.setLayout(layout)

    def update_param(self, key, val):
        self.node.params[key] = val
        self.update_callback()

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Posta - 半自動電子海報生成器")
        self.resize(1200, 900)
        
        self.global_input_image = None
        self.graph = Graph()
        self.scene = GraphScene(self.graph)
        self.scene.setParent(self) 
        self.view = CanvasView(self.scene, self)
        self.output_node = None
        
        self.history = []
        self.is_restoring = False
        
        self.setup_ui()
        self.setup_default_nodes()
        
        # 建立全局定時器以支援動態節點 (如 Switcher)
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer_tick)
        self.timer.start(500) # 每 0.5 秒檢查一次是否需要更新
        
        # Get actual screen available geometry to prevent overflowing
        screen_geo = QScreen.availableGeometry(QApplication.primaryScreen())
        
        # Calculate ideal width and height (leaving safe margins for Windows title bar and borders)
        w = min(1200, int(screen_geo.width() * 0.95))
        h = screen_geo.height() - 50 
        
        self.resize(w, h)
        
        # Center horizontally and align top vertically
        geo = self.frameGeometry()
        geo.moveCenter(screen_geo.center())
        geo.moveTop(screen_geo.top() + 5)
        self.move(geo.topLeft())

    def setup_ui(self):
        # --- Top Left: 原圖區 ---
        self.original_img_label = ImagePreviewLabel("原圖(貼上/點擊載入)")
        # 覆蓋 mousePressEvent 以支援點擊載入
        self.original_img_label.mousePressEvent = self.load_original_image
        self.original_img_label.setStyleSheet("border: 2px dashed #555; background-color: #2a2a2a;")
        
        clear_btn = QPushButton("清除輸入圖")
        clear_btn.clicked.connect(self.clear_input_image)
        
        left_top_layout = QVBoxLayout()
        left_top_layout.setContentsMargins(0, 0, 0, 0)
        left_top_layout.addWidget(self.original_img_label, stretch=1)
        left_top_layout.addWidget(clear_btn)
        left_top_widget = QWidget()
        left_top_widget.setLayout(left_top_layout)
        left_top_widget.setMinimumSize(50, 50) # Allow free shrinking
        
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self.paste_image)
        
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo)

        # --- Bottom Left: 工具區 ---
        self.node_palette = PaletteList()
        self.node_palette.addItems([
            "輸入 (Input)", "輸出 (Output)", 
            "染色 (Tint)", "替換顏色 (Color Replace)", 
            "明度選取 (Luma Key)", "邊緣擷取 (Edge Detect)",
            "亮度對比 (Brightness)", "負片 (Invert)", "高斯模糊 (Blur)",
            "圖層合併 (Merge)", "進階混合 (Blend)", "時間切換 (Switcher)"
        ])
        self.node_palette.itemDoubleClicked.connect(self.add_node_from_palette_event)
        self.node_palette.setDragEnabled(True)
        
        self.config_area = QScrollArea()
        self.config_area.setWidgetResizable(True)
        self.config_area.setMinimumHeight(50)
        
        # 改用 Splitter 讓使用者可以自由調整工具區與設定區的比例
        palette_splitter = QSplitter(Qt.Vertical)
        
        palette_top = QWidget()
        pt_layout = QVBoxLayout(palette_top)
        pt_layout.setContentsMargins(0, 0, 0, 0)
        pt_layout.addWidget(QLabel("可更動元件 (雙擊加入畫布):"))
        pt_layout.addWidget(self.node_palette)
        
        palette_bottom = QWidget()
        pb_layout = QVBoxLayout(palette_bottom)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        pb_layout.addWidget(QLabel("節點屬性設定:"))
        pb_layout.addWidget(self.config_area)
        
        palette_splitter.addWidget(palette_top)
        palette_splitter.addWidget(palette_bottom)
        palette_splitter.setSizes([150, 250])
        
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(left_top_widget)
        left_splitter.addWidget(palette_splitter)
        left_splitter.setSizes([300, 300])

        # --- Top Right: 預覽區 ---
        self.preview_label = ImagePreviewLabel("處理後圖片(準備輸出)")
        self.preview_label.setStyleSheet("border: 2px solid #000; background-color: #1a1a1a;")
        
        save_btn = QPushButton("儲存輸出圖")
        save_btn.clicked.connect(self.save_output_image)
        
        right_top_layout = QVBoxLayout()
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.addWidget(self.preview_label, stretch=1)
        right_top_layout.addWidget(save_btn)
        right_top_widget = QWidget()
        right_top_widget.setLayout(right_top_layout)
        right_top_widget.setMinimumSize(50, 50) # Allow free shrinking
        
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(left_splitter)
        top_splitter.addWidget(right_top_widget)
        top_splitter.setSizes([350, 850])

        # --- Bottom: 畫布 ---
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        
        canvas_container = QVBoxLayout()
        canvas_container.setContentsMargins(0,0,0,0)
        canvas_label = QLabel("資訊流位置 (節點連線區)")
        canvas_label.setStyleSheet("background-color: #333; font-weight: bold; padding: 5px;")
        canvas_container.addWidget(canvas_label)
        canvas_container.addWidget(self.view)
        canvas_widget = QWidget()
        canvas_widget.setLayout(canvas_container)
        canvas_widget.setMinimumSize(50, 50) # Allow free shrinking
        
        main_splitter.addWidget(canvas_widget)
        main_splitter.setSizes([500, 400])
        
        self.setCentralWidget(main_splitter)

    def setup_default_nodes(self):
        # 預設建立輸入與輸出節點
        input_node = self.add_node_by_name("Input")
        if input_node:
            input_node.setPos(-300, 0)
            
        output_node = self.add_node_by_name("Output")
        if output_node:
            output_node.setPos(300, 0)
        
        self.save_state()

    def load_original_image(self, event):
        fname, _ = QFileDialog.getOpenFileName(self, "開啟原圖", "", "Image Files (*.png *.jpg *.bmp)")
        if fname:
            img = cv2.imread(fname, cv2.IMREAD_UNCHANGED)
            self.set_global_image(img)

    def paste_image(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data.hasImage():
            qimg = clipboard.image()
            qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
            w, h = qimg.width(), qimg.height()
            ptr = qimg.constBits()
            arr = np.array(ptr).reshape(h, w, 4)
            img_bgra = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
            self.set_global_image(img_bgra)

    def set_global_image(self, img_bgra):
        if img_bgra is None: return
        
        if len(img_bgra.shape) == 2:
            img_bgra = cv2.cvtColor(img_bgra, cv2.COLOR_GRAY2BGRA)
        elif len(img_bgra.shape) == 3 and img_bgra.shape[2] == 3:
            img_bgra = cv2.cvtColor(img_bgra, cv2.COLOR_BGR2BGRA)
            
        self.global_input_image = img_bgra
        
        h, w, c = img_bgra.shape
        img_rgba = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2RGBA)
        qimg = QImage(img_rgba.data, w, h, 4*w, QImage.Format_RGBA8888)
        self.original_img_label.set_image(QPixmap.fromImage(qimg))
        
        self.evaluate_graph()

    def clear_input_image(self):
        self.global_input_image = None
        self.original_img_label.clear_image()
        self.original_img_label.text = "原圖(貼上/點擊載入)"
        self.original_img_label.update()
        self.evaluate_graph()

    def save_output_image(self):
        if self.preview_label.pixmap_original is None or self.preview_label.pixmap_original.isNull():
            return
        fname, _ = QFileDialog.getSaveFileName(self, "儲存圖片", "", "Image Files (*.png *.jpg *.bmp)")
        if fname:
            self.preview_label.pixmap_original.save(fname)

    def add_node_from_palette_event(self, item):
        self.add_node_by_name(item.text())

    def add_node_by_name(self, name, pos=None):
        node = None
        if "Input" in name: 
            node = ImageInputNode()
            node.process = lambda **kwargs: {"Image Out": self.global_input_image}
            node.name = "原圖輸入"
        elif "Color Replace" in name: 
            node = ColorReplaceNode()
            node.name = "替換顏色"
        elif "Edge Detect" in name: 
            node = EdgeDetectNode()
            node.name = "邊緣擷取"
        elif "Blur" in name: 
            node = BlurNode()
            node.name = "高斯模糊"
        elif "Tint" in name:
            node = TintNode()
        elif "Luma" in name:
            node = LuminanceNode()
        elif "Brightness" in name:
            node = BrightnessContrastNode()
        elif "Invert" in name:
            node = InvertNode()
        elif "Blend" in name:
            node = BlendNode()
        elif "Switcher" in name:
            node = SwitcherNode()
        elif "Merge" in name: 
            node = MergeNode()
            node.name = "圖層合併"
        elif "Output" in name: 
            node = OutputNode()
            node.name = "最終輸出"
            # 如果已經有輸出節點，就替換或只允許多個？先允許但不處理
            self.output_node = node
            
        if node:
            self.graph.add_node(node)
            n_item = NodeItem(node)
            self.scene.add_node(n_item)
            
            if pos is not None:
                n_item.setPos(pos)
            else:
                # 讓節點生成在目前視角的中心位置，不要一直往下掉
                center = self.view.mapToScene(self.view.viewport().rect().center())
                offset = (len(self.graph.nodes) % 10) * 20
                n_item.setPos(center.x() - 75 + offset, center.y() - 50 + offset)
            
            def mousePressEvent(event, ni=n_item):
                QGraphicsRectItem.mousePressEvent(ni, event)
                self.show_config(ni.node_model)
            n_item.mousePressEvent = mousePressEvent
            
            def mouseReleaseEvent(event, ni=n_item):
                QGraphicsRectItem.mouseReleaseEvent(ni, event)
                if not self.is_restoring:
                    self.save_state()
            n_item.mouseReleaseEvent = mouseReleaseEvent
            
            if not self.is_restoring:
                self.save_state()
            return n_item
        return None

    def on_timer_tick(self):
        # 檢查是否有 Switcher 類型的動態節點需要更新
        from core_nodes import SwitcherNode
        has_dynamic = any(isinstance(n, SwitcherNode) for n in self.graph.nodes)
        if has_dynamic:
            self.evaluate_graph()

    def show_config(self, node):
        panel = ConfigPanel(node, self.evaluate_graph)
        self.config_area.setWidget(panel)

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

    def show_image(self, img_bgra):
        if img_bgra is None: return
        h, w, c = img_bgra.shape
        img_rgba = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2RGBA)
        qimg = QImage(img_rgba.data, w, h, 4*w, QImage.Format_RGBA8888)
        self.preview_label.set_image(QPixmap.fromImage(qimg))

    def save_state(self):
        if self.is_restoring: return
        state = self.get_graph_state()
        self.history.append(state)
        if len(self.history) > 30:
            self.history.pop(0)

    def undo(self):
        if len(self.history) > 1:
            self.history.pop() # Remove current state
            state = self.history[-1]
            self.is_restoring = True
            self.restore_graph_state(state)
            self.is_restoring = False

    def get_graph_state(self):
        state = {"nodes": [], "edges": []}
        
        # O(N) 優化：先建立對映表，避免 O(N^2) 的陣列搜尋
        node_items_map = {item.node_model: item for item in self.scene.items() if isinstance(item, NodeItem)}
        
        for node in self.graph.nodes:
            item = node_items_map.get(node)
            pos = (item.scenePos().x(), item.scenePos().y()) if item else (0,0)
            state["nodes"].append({
                "id": node.id,
                "type": node.__class__.__name__,
                "name": node.name,
                "pos": pos,
                "params": dict(node.params)
            })
            for pin_name, in_pin in node.inputs.items():
                for edge in in_pin.edges:
                    state["edges"].append({
                        "out_node": edge.output_pin.node.id,
                        "out_pin": edge.output_pin.name,
                        "in_node": node.id,
                        "in_pin": pin_name,
                        "weight": edge.weight,
                        "bypassed": edge.bypassed
                    })
        return state

    def restore_graph_state(self, state):
        self.scene.clear()
        self.graph.nodes.clear()
        self.output_node = None
        
        node_map = {}
        for n_data in state["nodes"]:
            cls = globals().get(n_data["type"])
            if not cls: continue
            node = cls()
            node.id = n_data["id"]
            node.name = n_data["name"]
            node.params.update(n_data["params"])
            
            if n_data["type"] == "ImageInputNode":
                node.process = lambda n=node, **kwargs: {"Image Out": self.global_input_image}
            elif n_data["type"] == "OutputNode":
                self.output_node = node
                
            self.graph.add_node(node)
            node_map[node.id] = node
            
            n_item = NodeItem(node)
            n_item.setPos(n_data["pos"][0], n_data["pos"][1])
            self.scene.add_node(n_item)
            
            def mousePressEvent(event, ni=n_item):
                QGraphicsRectItem.mousePressEvent(ni, event)
                self.show_config(ni.node_model)
            n_item.mousePressEvent = mousePressEvent
            
        # O(N) 優化：建立 item 對映表供連線重建時快速查找
        item_map = {item.node_model.id: item for item in self.scene.items() if isinstance(item, NodeItem)}
            
        for e_data in state["edges"]:
            out_node = node_map.get(e_data["out_node"])
            in_node = node_map.get(e_data["in_node"])
            if not out_node or not in_node: continue
            
            out_pin = next((p for n, p in out_node.outputs.items() if p.name == e_data["out_pin"]), None)
            in_pin = next((p for n, p in in_node.inputs.items() if p.name == e_data["in_pin"]), None)
            
            if out_pin and in_pin:
                edge = in_pin.connect(out_pin)
                edge.weight = e_data["weight"]
                edge.bypassed = e_data["bypassed"]
                
                out_item = item_map.get(out_node.id)
                in_item = item_map.get(in_node.id)
                if out_item and in_item:
                    out_pin_item = out_item.pin_items.get(out_pin.id)
                    in_pin_item = in_item.pin_items.get(in_pin.id)
                    
                    conn = ConnectionItem(out_pin_item, in_pin_item)
                    conn.edge_model = edge
                    conn.weight_text.setPlainText(str(edge.weight))
                    if edge.weight != 1.0:
                        conn.weight_text.show()
                    self.scene.addItem(conn)
                    out_pin_item.add_connection(conn)
                    in_pin_item.add_connection(conn)
                    conn.update_path()
        
        self.config_area.setWidget(QWidget())
        self.evaluate_graph()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(40, 40, 40))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(60, 60, 60))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    app.setPalette(palette)
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
