import sys
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

class PinItem(QGraphicsEllipseItem):
    def __init__(self, pin, is_input, parent=None):
        super().__init__(-10, -10, 20, 20, parent)
        self.pin = pin
        self.is_input = is_input
        
        # 不同類型的點給予不同顏色方便辨識
        if pin.pin_type == "mask":
            color = QColor(255, 255, 0) # 黃色代表遮罩 (Mask)
        else:
            color = QColor(0, 255, 255) if not is_input else QColor(0, 200, 100) # 青色代表圖片 (Image)
            
        self.setBrush(QBrush(color))
        self.setToolTip(f"{pin.name} ({pin.pin_type})")
        self.connections = []

    def shape(self):
        # 擴大判定範圍，讓點擊更容易命中，不需要點得很精準
        path = QPainterPath()
        path.addEllipse(-18, -18, 36, 36)
        return path

    def add_connection(self, connection):
        self.connections.append(connection)

    def remove_connection(self, connection):
        if connection in self.connections:
            self.connections.remove(connection)

class ConnectionItem(QGraphicsPathItem):
    def __init__(self, out_pin_item, in_pin_item=None):
        super().__init__()
        self.out_pin_item = out_pin_item
        self.in_pin_item = in_pin_item
        self.setPen(QPen(Qt.white, 2))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.target_pos = None
        self.edge_model = None
        
        self.weight_text = QGraphicsTextItem("1.0", self)
        self.weight_text.setDefaultTextColor(Qt.yellow)
        self.weight_text.hide()

    def shape(self):
        path_stroker = QPainterPathStroker()
        path_stroker.setWidth(8) # 稍微縮小線段的判定區，避免干擾點擊 Pin
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
                if hasattr(self.scene().parent(), "evaluate_graph"):
                    self.scene().parent().evaluate_graph()
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
        if self.isSelected():
            painter.setPen(QPen(Qt.red, 3))
        else:
            painter.setPen(QPen(Qt.white, 2))
        super().paint(painter, option, widget)

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
        dy = end_pos.y() - start_pos.y()
        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(start_pos.x() + dx * 0.5, end_pos.y())
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)
        
        self.weight_text.setPos(end_pos.x() - 25, end_pos.y() - 20)

class NodeItem(QGraphicsRectItem):
    def __init__(self, node_model, parent=None):
        super().__init__(0, 0, 150, 100, parent)
        self.node_model = node_model
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setBrush(QBrush(QColor(40, 40, 40)))
        self.setPen(QPen(Qt.black))
        
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
            y += 20
            
        y = 30
        for name, pin in self.node_model.outputs.items():
            pi = PinItem(pin, False, self)
            pi.setPos(153, y)
            text = QGraphicsTextItem(name, self)
            text.setDefaultTextColor(Qt.lightGray)
            text.setPos(150 - text.boundingRect().width() - 10, y - 10)
            self.pin_items[pin.id] = pi
            y += 20
            
        # Adjust height
        self.setRect(0, 0, 150, max(60, y + 10))

    def contextMenuEvent(self, event):
        menu = QMenu()
        del_act = menu.addAction("刪除節點 (Delete)")
        
        action = menu.exec(event.screenPos())
        if action == del_act:
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

class GraphScene(QGraphicsScene):
    def __init__(self, graph, parent=None):
        super().__init__(parent)
        self.graph = graph
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.current_connection = None
        
    def add_node(self, node_item):
        self.addItem(node_item)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            items_to_remove = self.selectedItems()
            has_changes = False
            for item in items_to_remove:
                if isinstance(item, ConnectionItem) or isinstance(item, NodeItem):
                    item.remove()
                    has_changes = True
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
