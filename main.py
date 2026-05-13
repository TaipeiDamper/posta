import sys
import cv2
import numpy as np
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

from core_engine import Graph
from core_nodes import ImageInputNode, ColorReplaceNode, EdgeDetectNode, BlurNode, MergeNode, OutputNode
from ui_graphics import GraphScene, NodeItem

class ImagePreviewLabel(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self.text = text
        self.pixmap_original = None
        self.setStyleSheet("background-color: #1a1a1a;")

    def set_image(self, pixmap):
        self.pixmap_original = pixmap
        self.update()
        
    def clear_image(self):
        self.pixmap_original = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        
        if self.pixmap_original and not self.pixmap_original.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            scaled_pixmap = self.pixmap_original.scaled(
                self.rect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
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
                spin = QSpinBox()
                spin.setRange(0, 1000)
                spin.setValue(val)
                spin.valueChanged.connect(lambda v, k=key: self.update_param(k, v))
                hbox.addWidget(spin)
            elif isinstance(val, list): # For RGB
                btn = QPushButton("選擇顏色")
                btn.setStyleSheet(f"background-color: rgb({val[0]}, {val[1]}, {val[2]}); color: black;")
                btn.clicked.connect(lambda _, k=key, b=btn: self.pick_color(k, b))
                hbox.addWidget(btn)
            elif isinstance(val, str):
                edit = QLineEdit(val)
                edit.textChanged.connect(lambda v, k=key: self.update_param(k, v))
                hbox.addWidget(edit)
            layout.addLayout(hbox)
        layout.addStretch()
        self.setLayout(layout)

    def update_param(self, key, val):
        self.node.params[key] = val
        self.update_callback()

    def pick_color(self, key, btn):
        color = QColorDialog.getColor()
        if color.isValid():
            rgb = [color.red(), color.green(), color.blue()]
            self.node.params[key] = rgb
            btn.setStyleSheet(f"background-color: {color.name()}; color: black;")
            self.update_callback()


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
        
        self.setup_ui()
        self.setup_default_nodes()

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
        
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self.paste_image)

        # --- Bottom Left: 工具區 ---
        self.node_palette = PaletteList()
        self.node_palette.addItems(["輸入節點 (Input)", "替換顏色 (Color Replace)", "邊緣擷取 (Edge Detect)", "高斯模糊 (Gaussian Blur)", "圖層合併 (Merge Overlay)", "最終輸出 (Output)"])
        self.node_palette.itemDoubleClicked.connect(self.add_node_from_palette_event)
        self.node_palette.setDragEnabled(True)
        
        self.config_area = QScrollArea()
        self.config_area.setWidgetResizable(True)
        self.config_area.setMinimumHeight(150)
        
        palette_layout = QVBoxLayout()
        palette_layout.addWidget(QLabel("可更動元件 (雙擊加入畫布):"))
        palette_layout.addWidget(self.node_palette)
        palette_layout.addWidget(QLabel("節點屬性設定:"))
        palette_layout.addWidget(self.config_area)
        palette_widget = QWidget()
        palette_widget.setLayout(palette_layout)
        
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(left_top_widget)
        left_splitter.addWidget(palette_widget)
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
            node.process = lambda **kwargs: {"image": self.global_input_image}
            node.name = "原圖輸入"
        elif "Color Replace" in name: 
            node = ColorReplaceNode()
            node.name = "替換顏色"
        elif "Edge Detect" in name: 
            node = EdgeDetectNode()
            node.name = "邊緣擷取"
        elif "Gaussian Blur" in name: 
            node = BlurNode()
            node.name = "高斯模糊"
        elif "Merge Overlay" in name: 
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
            return n_item
        return None

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
