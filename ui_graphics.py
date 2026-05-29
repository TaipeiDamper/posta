from contextlib import nullcontext

from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

from core_engine import can_connect_pins

SNAP_PIN_DISTANCE = 28.0

# ==================== Pin 連線點 ====================
class PinItem(QGraphicsEllipseItem):
    # 顏色映射表：不同資料類型不同顏色
    TYPE_COLORS = {
        "image": QColor(0, 200, 255),    # 青藍色
        "mask":  QColor(255, 255, 0),    # 黃色
        "value": QColor(180, 100, 255),  # 紫色
        "color": QColor(255, 120, 60),   # 橘色
    }

    def __init__(self, pin, is_input, parent=None):
        super().__init__(-10, -10, 20, 20, parent)
        self.pin = pin
        self.is_input = is_input
        
        color = self.TYPE_COLORS.get(pin.pin_type, QColor(200, 200, 200))
        if is_input:
            color = color.darker(120)
            
        self.setBrush(QBrush(color))
        self.setToolTip(f"{pin.name} ({pin.pin_type})")
        self.connections = []

    def shape(self):
        # 擴大判定範圍，讓點擊更容易命中
        path = QPainterPath()
        path.addEllipse(-18, -18, 36, 36)
        return path

    def add_connection(self, connection):
        self.connections.append(connection)

    def remove_connection(self, connection):
        if connection in self.connections:
            self.connections.remove(connection)

# ==================== 連線 ====================
class ConnectionItem(QGraphicsPathItem):
    # 連線顏色映射：根據輸出端 pin 類型決定
    TYPE_COLORS = {
        "image": QColor(100, 200, 255, 180),
        "mask":  QColor(255, 255, 100, 180),
        "value": QColor(180, 130, 255, 180),
        "color": QColor(255, 150, 80, 180),
    }

    def __init__(self, out_pin_item, in_pin_item=None):
        super().__init__()
        self.out_pin_item = out_pin_item
        self.in_pin_item = in_pin_item
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.target_pos = None
        self.edge_model = None
        
        # 依據 pin 類型設定線段顏色
        pin_type = out_pin_item.pin.pin_type if out_pin_item else "image"
        self._line_color = self.TYPE_COLORS.get(pin_type, QColor(200, 200, 200, 180))
        self.setPen(QPen(self._line_color, 2.5))
        
        self.weight_text = QGraphicsTextItem("1.0", self)
        self.weight_text.setDefaultTextColor(Qt.yellow)
        self.weight_text.hide()

    def shape(self):
        path_stroker = QPainterPathStroker()
        path_stroker.setWidth(8)
        return path_stroker.createStroke(self.path())

    def contextMenuEvent(self, event):
        if not self.edge_model: return
        menu = QMenu()
        set_weight_act = menu.addAction("設定權重 (Weight)")
        bypass_act = menu.addAction("啟用/停用 (Bypass)")
        del_act = menu.addAction("刪除線段 (Delete)")
        
        action = menu.exec(event.screenPos())
        if action == set_weight_act:
            val, ok = QInputDialog.getDouble(None, "設定權重", "權重 (Weight):", self.edge_model.weight, 0.0, 100.0, 2)
            if ok:
                self.edge_model.weight = val
                self.weight_text.setPlainText(str(val))
                scene = self.scene()
                if isinstance(scene, GraphScene):
                    scene.graph_structure_changed.emit()
        elif action == bypass_act:
            self.edge_model.bypassed = not self.edge_model.bypassed
            self.update()
            scene = self.scene()
            if isinstance(scene, GraphScene):
                scene.graph_structure_changed.emit()
                scene.graph_state_changed.emit()
        elif action == del_act:
            scene = self.scene()
            self.remove()
            if isinstance(scene, GraphScene):
                scene.graph_structure_changed.emit()
                scene.graph_state_changed.emit()
        event.accept()

    def paint(self, painter, option, widget=None):
        if self.edge_model and self.edge_model.bypassed:
            # Bypass 狀態：用灰色虛線表示
            pen = QPen(QColor(100, 100, 100, 120), 2, Qt.DashLine)
        elif self.isSelected():
            pen = QPen(QColor(255, 80, 80), 3)
        else:
            pen = QPen(self._line_color, 2.5)
        painter.setPen(pen)
        painter.drawPath(self.path())

    def remove(self, lock_graph=True):
        scene = self.scene()
        lock = scene.graph_lock() if lock_graph and isinstance(scene, GraphScene) else nullcontext()
        with lock:
            if self.out_pin_item:
                self.out_pin_item.remove_connection(self)
            if self.in_pin_item:
                self.in_pin_item.remove_connection(self)
                if self.edge_model:
                    self.in_pin_item.pin.disconnect_edge(self.edge_model)
            if self.scene():
                self.scene().removeItem(self)

    def update_path(self):
        start_pos = self.out_pin_item.scenePos()
        if self.in_pin_item:
            end_pos = self.in_pin_item.scenePos()
            self.setPen(QPen(self._line_color, 2.5))
        elif self.target_pos:
            end_pos = self.target_pos
            scene = self.scene()
            out_t = self.out_pin_item.pin.pin_type
            if scene and isinstance(scene, GraphScene):
                snap_pi = scene.find_nearest_compatible_input_pin(end_pos, out_t, SNAP_PIN_DISTANCE)
                if snap_pi is not None:
                    end_pos = snap_pi.scenePos()
            if scene:
                items = scene.items(end_pos)
                pin_item = next((item for item in items if isinstance(item, PinItem)), None)
                if pin_item and pin_item.is_input:
                    if can_connect_pins(out_t, pin_item.pin.pin_type):
                        end_pos = pin_item.scenePos()
                        self.setPen(QPen(QColor(0, 255, 0), 3))
                    else:
                        self.setPen(QPen(QColor(255, 0, 0), 3, Qt.DashLine))
                else:
                    self.setPen(QPen(self._line_color, 2.5))
        else:
            return

        path = QPainterPath()
        path.moveTo(start_pos)
        dx = end_pos.x() - start_pos.x()
        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(start_pos.x() + dx * 0.5, end_pos.y())
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)
        
        self.weight_text.setPos(end_pos.x() - 25, end_pos.y() - 20)

# ==================== 節點 ====================
class NodeItem(QGraphicsRectItem):
    def _get_color_for_node(self, node):
        """根據節點型別決定顏色"""
        name = node.__class__.__name__
        if name == "ApplyMaskNode":
            return QColor(192, 57, 43) # 紅寶石色 (核心運算)
        elif "Input" in name or "Output" in name:
            return QColor(44, 62, 80) # 深藍
        elif name in ("EdgeDetectNode", "SobelEdgeNode", "ThresholdContourNode", "PencilSketchNode", "BlurNode", "HalftoneNode", "GrainNode"):
            return QColor(39, 174, 96) # 綠色 (濾鏡)
        elif name in ("LuminanceNode", "MidtoneKeyNode", "BrightnessContrastNode", "InvertNode", "MaskInvertNode", "TintNode", "ColorReplaceNode", "PosterizeNode", "GradientMapNode"):
            return QColor(211, 84, 0)  # 橘色 (顏色)
        elif name in ("MergeNode", "BlendNode", "SwitcherNode"):
            return QColor(41, 128, 185) # 青藍 (合成)
        elif name in ("TextNode", "SmartCropNode"):
            return QColor(142, 68, 173) # 紫色 (變形/文字)
        elif name in ("ValueNode", "ColorOutputNode", "RerouteNode"):
            return QColor(70, 70, 70)   # 灰黑色 (工具/輔助)
        return QColor(50, 50, 50)     # 預設深灰

    def __init__(self, node_model, scene=None):
        super().__init__()
        self.node_model = node_model
        if scene: scene.addItem(self)
        
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        
        self.setBrush(QBrush(self._get_color_for_node(node_model)))
        self.setPen(QPen(QColor(100, 100, 100), 1))
        
        self.title = QGraphicsTextItem(node_model.name, self)
        self.title.setDefaultTextColor(Qt.white)
        self.title.setPos(5, 5)
        
        self.thumbnail = QGraphicsPixmapItem(self)
        self.is_collapsed = False
        
        self.pin_items = {}
        self.create_pins()

    def create_pins(self):
        y = 30
        for name, pin in self.node_model.inputs.items():
            pi = PinItem(pin, True, self)
            pi.setPos(-3, y)
            text = QGraphicsTextItem(name, self)
            text.setDefaultTextColor(Qt.lightGray)
            text.setPos(10, y - 10)
            self.pin_items[pin.id] = pi
            y += 22
            
        y_out = 30
        for name, pin in self.node_model.outputs.items():
            pi = PinItem(pin, False, self)
            pi.setPos(153, y_out)
            text = QGraphicsTextItem(name, self)
            text.setDefaultTextColor(Qt.lightGray)
            text.setPos(150 - text.boundingRect().width() - 10, y_out - 10)
            self.pin_items[pin.id] = pi
            y_out += 22
            
        # Adjust height
        max_y = max(y, y_out)
        self.collapsed_height = max_y + 10
        self.expanded_height = self.collapsed_height
        self.setRect(0, 0, 150, self.expanded_height)

    def update_thumbnail(self):
        if self.is_collapsed:
            return
        if not (hasattr(self.node_model, '_cached_outputs') and self.node_model._cached_outputs is not None
                and 'Image Out' in self.node_model._cached_outputs):
            return
        import cv2
        img = self.node_model._cached_outputs['Image Out']
        if img is not None:
            h, w = img.shape[:2]
            thumb_max = 128
            scale = thumb_max / max(h, w, 1)
            if scale < 1.0:
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                small = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            else:
                small = img
            sh, sw = small.shape[:2]
            rgba = cv2.cvtColor(small, cv2.COLOR_BGRA2RGBA)
            qimg = QImage(rgba.data, sw, sh, 4 * sw, QImage.Format_RGBA8888).copy()
            pix = QPixmap.fromImage(qimg).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail.setPixmap(pix)
            self.thumbnail.setPos(75 - pix.width() // 2, self.collapsed_height)
            self.expanded_height = self.collapsed_height + pix.height() + 10
            self.setRect(0, 0, 150, self.expanded_height)
        else:
            self.thumbnail.setPixmap(QPixmap())
            self.expanded_height = self.collapsed_height
            self.setRect(0, 0, 150, self.expanded_height)

    def mouseDoubleClickEvent(self, event):
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.setRect(0, 0, 150, self.collapsed_height)
            self.thumbnail.hide()
        else:
            self.setRect(0, 0, 150, self.expanded_height)
            self.thumbnail.show()
        event.accept()

    def paint(self, painter, option, widget=None):
        rect = self.rect()
        status = getattr(self.node_model, '_status', 'normal')
        
        if self.node_model.bypassed:
            # Bypass 狀態：暗化 + 半透明紅色邊框
            painter.setBrush(QBrush(QColor(30, 30, 30, 120)))
            painter.setPen(QPen(QColor(200, 60, 60, 180), 2, Qt.DashLine))
        elif status == 'running':
            painter.setBrush(self.brush())
            painter.setPen(QPen(QColor(255, 255, 0), 3))
        elif status == 'error':
            painter.setBrush(self.brush())
            painter.setPen(QPen(QColor(255, 50, 50), 3))
        elif self.isSelected():
            painter.setBrush(self.brush())
            painter.setPen(QPen(QColor(255, 180, 100), 2))
        else:
            painter.setBrush(self.brush())
            painter.setPen(self.pen())
        
        painter.drawRoundedRect(rect, 4, 4)

    def contextMenuEvent(self, event):
        menu = QMenu()
        bypass_act = menu.addAction("跳過節點 (Bypass)" if not self.node_model.bypassed else "恢復節點")
        del_act = menu.addAction("刪除節點 (Delete)")
        
        action = menu.exec(event.screenPos())
        if action == bypass_act:
            self.node_model.bypassed = not self.node_model.bypassed
            self.update()
            scene = self.scene()
            if isinstance(scene, GraphScene):
                scene.graph_structure_changed.emit()
                scene.graph_state_changed.emit()
        elif action == del_act:
            scene = self.scene()
            self.remove()
            if isinstance(scene, GraphScene):
                scene.graph_structure_changed.emit()
                scene.graph_state_changed.emit()
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for pin_item in self.pin_items.values():
                for conn in pin_item.connections:
                    conn.update_path()
        elif change == QGraphicsItem.ItemPositionChange and self.scene():
            # Snap to Grid (20px)
            new_pos = value
            x = round(new_pos.x() / 20) * 20
            y = round(new_pos.y() / 20) * 20
            return QPointF(x, y)
        return super().itemChange(change, value)

    def remove(self):
        scene = self.scene()
        lock = scene.graph_lock() if isinstance(scene, GraphScene) else nullcontext()
        with lock:
            for pin_item in self.pin_items.values():
                for conn in list(pin_item.connections):
                    conn.remove(lock_graph=False)
            if isinstance(scene, GraphScene):
                scene.notify_node_removed(self.node_model)
                scene.graph.remove_node(self.node_model)
                scene.removeItem(self)
            elif self.scene():
                self.scene().removeItem(self)

# ==================== 群組外框 (Backdrop) ====================
class BackdropItem(QGraphicsRectItem):
    def __init__(self, x, y, w=400, h=300, parent=None):
        super().__init__(x, y, w, h, parent)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(-100)  # 確保在所有節點之下
        
        self._color = QColor(60, 80, 120, 60)
        self.setBrush(QBrush(self._color))
        self.setPen(QPen(QColor(100, 140, 200, 120), 2, Qt.DashLine))
        
        self.title = QGraphicsTextItem("群組", self)
        self.title.setDefaultTextColor(QColor(180, 210, 255))
        font = self.title.font()
        font.setPointSize(12)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setPos(x + 10, y + 5)
        
        # 允許調整大小的控制點
        self._resizing = False
        self._resize_start = None

    def paint(self, painter, option, widget=None):
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), 8, 8)
        
        # 繪製右下角的縮放把手
        rect = self.rect()
        handle = QRectF(rect.right() - 16, rect.bottom() - 16, 14, 14)
        painter.setBrush(QBrush(QColor(150, 180, 220, 100)))
        painter.drawRect(handle)

    def contextMenuEvent(self, event):
        menu = QMenu()
        color_act = menu.addAction("變更顏色")
        rename_act = menu.addAction("重新命名")
        del_act = menu.addAction("刪除群組")
        
        action = menu.exec(event.screenPos())
        if action == color_act:
            color = QColorDialog.getColor(self._color)
            if color.isValid():
                color.setAlpha(60)
                self._color = color
                self.setBrush(QBrush(color))
                self.update()
        elif action == rename_act:
            text, ok = QInputDialog.getText(None, "群組名稱", "名稱:", text=self.title.toPlainText())
            if ok and text:
                self.title.setPlainText(text)
        elif action == del_act:
            if self.scene():
                self.scene().removeItem(self)
        event.accept()

    def mousePressEvent(self, event):
        rect = self.rect()
        handle = QRectF(rect.right() - 20, rect.bottom() - 20, 20, 20)
        if handle.contains(event.pos()):
            self._resizing = True
            self._resize_start = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_start:
            delta = event.pos() - self._resize_start
            rect = self.rect()
            new_w = max(100, rect.width() + delta.x())
            new_h = max(80, rect.height() + delta.y())
            self.setRect(rect.x(), rect.y(), new_w, new_h)
            self._resize_start = event.pos()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_start = None
        super().mouseReleaseEvent(event)

# ==================== 便利貼 (Sticky Note) ====================
class StickyNoteItem(QGraphicsRectItem):
    def __init__(self, x, y, parent=None):
        super().__init__(x, y, 180, 100, parent)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-50)
        
        self.setBrush(QBrush(QColor(255, 250, 150, 200)))
        self.setPen(QPen(QColor(200, 190, 100), 1))
        
        self.text_item = QGraphicsTextItem("備忘錄...", self)
        self.text_item.setDefaultTextColor(QColor(60, 50, 20))
        self.text_item.setPos(x + 5, y + 5)
        self.text_item.setTextWidth(170)
        
    def paint(self, painter, option, widget=None):
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), 3, 3)
        # 小陰影效果
        shadow = self.rect().adjusted(2, 2, 2, 2)
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(shadow, 3, 3)

    def contextMenuEvent(self, event):
        menu = QMenu()
        edit_act = menu.addAction("編輯文字")
        del_act = menu.addAction("刪除便利貼")
        
        action = menu.exec(event.screenPos())
        if action == edit_act:
            text, ok = QInputDialog.getMultiLineText(None, "便利貼", "文字:", self.text_item.toPlainText())
            if ok:
                self.text_item.setPlainText(text)
        elif action == del_act:
            if self.scene():
                self.scene().removeItem(self)
        event.accept()

# ==================== 場景 ====================
class GraphScene(QGraphicsScene):
    graph_structure_changed = Signal()
    graph_state_changed = Signal()

    def __init__(self, graph, parent=None, controller=None):
        super().__init__(parent)
        self.graph = graph
        self.controller = controller
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.current_connection = None

    def set_controller(self, controller):
        self.controller = controller

    def graph_lock(self):
        if self.controller:
            return self.controller.lock()
        return nullcontext()

    def notify_node_removed(self, node):
        if self.controller:
            self.controller.node_removed(node)

    def iter_pin_items(self):
        for it in self.items():
            if isinstance(it, NodeItem):
                for pi in it.pin_items.values():
                    yield pi

    def set_pin_drag_highlight(self, out_pin_type):
        for pi in self.iter_pin_items():
            if pi.is_input:
                ok = can_connect_pins(out_pin_type, pi.pin.pin_type)
                pi.setOpacity(1.0 if ok else 0.3)
            else:
                pi.setOpacity(0.45)

    def clear_pin_drag_highlight(self):
        for pi in self.iter_pin_items():
            pi.setOpacity(1.0)

    def find_nearest_compatible_input_pin(self, scene_pos, out_pin_type, max_dist):
        best = None
        best_d = max_dist * max_dist
        for it in self.items():
            if not isinstance(it, NodeItem):
                continue
            for pi in it.pin_items.values():
                if not pi.is_input:
                    continue
                if not can_connect_pins(out_pin_type, pi.pin.pin_type):
                    continue
                p = pi.scenePos()
                dx, dy = p.x() - scene_pos.x(), p.y() - scene_pos.y()
                d2 = dx * dx + dy * dy
                if d2 <= best_d:
                    best_d = d2
                    best = pi
        return best

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(30, 30, 30))
        left = int(rect.left()) - (int(rect.left()) % 20)
        top = int(rect.top()) - (int(rect.top()) % 20)
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        for x in range(left, int(rect.right()), 20):
            for y in range(top, int(rect.bottom()), 20):
                painter.drawPoint(x, y)

    def add_node(self, node_item):
        self.addItem(node_item)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.scenePos(), QTransform())
        if item is None:
            menu = QMenu()
            backdrop_act = menu.addAction("新增群組外框 (Backdrop)")
            note_act = menu.addAction("新增便利貼 (Note)")

            action = menu.exec(event.screenPos())
            pos = event.scenePos()
            if action == backdrop_act:
                bd = BackdropItem(pos.x(), pos.y())
                self.addItem(bd)
            elif action == note_act:
                note = StickyNoteItem(pos.x(), pos.y())
                self.addItem(note)
            event.accept()
            return
        super().contextMenuEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            items_to_remove = self.selectedItems()
            has_changes = False
            for item in items_to_remove:
                if isinstance(item, ConnectionItem) or isinstance(item, NodeItem):
                    item.remove()
                    has_changes = True
                elif isinstance(item, BackdropItem) or isinstance(item, StickyNoteItem):
                    self.removeItem(item)
            if has_changes:
                self.graph_structure_changed.emit()
                self.graph_state_changed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        items = self.items(event.scenePos())
        pin_item = next((item for item in items if isinstance(item, PinItem)), None)

        if pin_item and not pin_item.is_input:
            self.current_connection = ConnectionItem(pin_item)
            self.addItem(self.current_connection)
            pin_item.add_connection(self.current_connection)
            self.set_pin_drag_highlight(pin_item.pin.pin_type)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_connection:
            self.current_connection.target_pos = event.scenePos()
            self.current_connection.update_path()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_connection:
            connection_created = False
            self.clear_pin_drag_highlight()
            pos = event.scenePos()
            snap_pi = self.find_nearest_compatible_input_pin(
                pos,
                self.current_connection.out_pin_item.pin.pin_type,
                SNAP_PIN_DISTANCE,
            )
            if snap_pi is not None:
                pos = snap_pi.scenePos()
            items = self.items(pos)
            pin_item = next((item for item in items if isinstance(item, PinItem)), None)

            if pin_item and pin_item.is_input and can_connect_pins(
                self.current_connection.out_pin_item.pin.pin_type,
                pin_item.pin.pin_type,
            ):
                with self.graph_lock():
                    self.current_connection.in_pin_item = pin_item
                    pin_item.add_connection(self.current_connection)
                    self.current_connection.update_path()

                    edge = pin_item.pin.connect(self.current_connection.out_pin_item.pin)
                    self.current_connection.edge_model = edge
                    self.current_connection.weight_text.show()
                    connection_created = True
                self.current_connection = None
                if connection_created:
                    self.graph_structure_changed.emit()
                    self.graph_state_changed.emit()
            else:
                view = self.views()[0] if self.views() else None
                if view and hasattr(view, "node_map") and hasattr(view, "main_window"):
                    from ui_components import SearchMenu
                    global_pos = QCursor.pos()
                    menu = SearchMenu(view, pos, view.node_map)
                    menu.move(global_pos)
                    
                    if menu.exec() == QDialog.Accepted:
                        node_key = menu.get_selected()
                        if node_key:
                            with self.graph_lock():
                                old_nodes = [item for item in self.items() if item.__class__.__name__ == "NodeItem"]
                                view.main_window.add_node_by_name(node_key, pos)
                                new_nodes = [item for item in self.items() if item.__class__.__name__ == "NodeItem" and item not in old_nodes]
                                
                                if new_nodes:
                                    new_node_item = new_nodes[0]
                                    out_type = self.current_connection.out_pin_item.pin.pin_type
                                    target_pin_item = None
                                    for pi in new_node_item.pin_items.values():
                                        if pi.is_input and can_connect_pins(out_type, pi.pin.pin_type):
                                            target_pin_item = pi
                                            break
                                            
                                    if target_pin_item:
                                        self.current_connection.in_pin_item = target_pin_item
                                        target_pin_item.add_connection(self.current_connection)
                                        self.current_connection.update_path()
                                        
                                        edge = target_pin_item.pin.connect(self.current_connection.out_pin_item.pin)
                                        self.current_connection.edge_model = edge
                                        self.current_connection.weight_text.show()
                                        connection_created = True
                            
                            if connection_created:
                                self.graph_structure_changed.emit()
                                self.graph_state_changed.emit()
                            else:
                                self.current_connection.out_pin_item.remove_connection(self.current_connection)
                                self.removeItem(self.current_connection)
                        else:
                            self.current_connection.out_pin_item.remove_connection(self.current_connection)
                            self.removeItem(self.current_connection)
                    else:
                        self.current_connection.out_pin_item.remove_connection(self.current_connection)
                        self.removeItem(self.current_connection)
                else:
                    self.current_connection.out_pin_item.remove_connection(self.current_connection)
                    self.removeItem(self.current_connection)
                self.current_connection = None
        super().mouseReleaseEvent(event)
