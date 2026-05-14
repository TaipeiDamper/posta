import sys
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

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
                if scene and scene.parent() and hasattr(scene.parent(), "evaluate_graph"):
                    scene.parent().evaluate_graph()
        elif action == bypass_act:
            self.edge_model.bypassed = not self.edge_model.bypassed
            self.update()
            scene = self.scene()
            if scene and scene.parent() and hasattr(scene.parent(), "evaluate_graph"):
                scene.parent().evaluate_graph()
                if hasattr(scene.parent(), "save_state"):
                    scene.parent().save_state()
        elif action == del_act:
            scene = self.scene()
            self.remove()
            if scene and hasattr(scene.parent(), "evaluate_graph"):
                scene.parent().evaluate_graph()
                if hasattr(scene.parent(), "save_state"):
                    scene.parent().save_state()
        
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

    def remove(self):
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
        elif self.target_pos:
            end_pos = self.target_pos
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
    def __init__(self, node_model, parent=None):
        super().__init__(0, 0, 150, 100, parent)
        self.node_model = node_model
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setBrush(QBrush(QColor(50, 50, 50)))
        self.setPen(QPen(QColor(80, 80, 80)))
        
        self.title = QGraphicsTextItem(node_model.name, self)
        self.title.setDefaultTextColor(Qt.white)
        self.title.setPos(5, 5)
        
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
        self.setRect(0, 0, 150, max(60, max(y, y_out) + 10))

    def paint(self, painter, option, widget=None):
        rect = self.rect()
        
        if self.node_model.bypassed:
            # Bypass 狀態：暗化 + 半透明紅色邊框
            painter.setBrush(QBrush(QColor(30, 30, 30, 160)))
            painter.setPen(QPen(QColor(200, 60, 60, 180), 2, Qt.DashLine))
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
            if scene and scene.parent() and hasattr(scene.parent(), "evaluate_graph"):
                scene.parent().evaluate_graph()
                if hasattr(scene.parent(), "save_state"):
                    scene.parent().save_state()
        elif action == del_act:
            scene = self.scene()
            self.remove()
            if scene and scene.parent() and hasattr(scene.parent(), "evaluate_graph"):
                scene.parent().evaluate_graph()
                if hasattr(scene.parent(), "save_state"):
                    scene.parent().save_state()
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for pin_item in self.pin_items.values():
                for conn in pin_item.connections:
                    conn.update_path()
        return super().itemChange(change, value)

    def remove(self):
        for pin_item in self.pin_items.values():
            for conn in list(pin_item.connections):
                conn.remove()
        if self.scene():
            if hasattr(self.scene(), "graph"):
                self.scene().graph.remove_node(self.node_model)
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
    def __init__(self, graph, parent=None):
        super().__init__(parent)
        self.graph = graph
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.current_connection = None
        
    def add_node(self, node_item):
        self.addItem(node_item)

    def contextMenuEvent(self, event):
        # 只在空白區域顯示場景級右鍵選單
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
            if has_changes and hasattr(self.parent(), "evaluate_graph"):
                self.parent().evaluate_graph()
                if hasattr(self.parent(), "save_state"):
                    self.parent().save_state()
        super().keyPressEvent(event)
        
    def mousePressEvent(self, event):
        # 優先判定點擊到的 PinItem，即使與其他物件重疊
        items = self.items(event.scenePos())
        pin_item = next((item for item in items if isinstance(item, PinItem)), None)
        
        if pin_item and not pin_item.is_input:
            self.current_connection = ConnectionItem(pin_item)
            self.addItem(self.current_connection)
            pin_item.add_connection(self.current_connection)
            event.accept() # 攔截事件，防止觸發背景或節點拖曳
            return
            
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_connection:
            self.current_connection.target_pos = event.scenePos()
            self.current_connection.update_path()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_connection:
            items = self.items(event.scenePos())
            pin_item = next((item for item in items if isinstance(item, PinItem)), None)
            
            if pin_item and pin_item.is_input:
                self.current_connection.in_pin_item = pin_item
                pin_item.add_connection(self.current_connection)
                self.current_connection.update_path()
                
                # Logic connection
                edge = pin_item.pin.connect(self.current_connection.out_pin_item.pin)
                self.current_connection.edge_model = edge
                self.current_connection.weight_text.show()
                # trigger update on parent view
                if hasattr(self.parent(), "evaluate_graph"):
                    self.parent().evaluate_graph()
                    if hasattr(self.parent(), "save_state"):
                        self.parent().save_state()
            else:
                self.current_connection.out_pin_item.remove_connection(self.current_connection)
                self.removeItem(self.current_connection)
            self.current_connection = None
        super().mouseReleaseEvent(event)
