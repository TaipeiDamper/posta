"""Node item creation and event binding."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsRectItem

from node_registry import NODE_MAP, resolve_registry_key
from ui_graphics import NodeItem


def bind_node_item_events(node_item, on_select, on_commit=None, is_restoring=lambda: False):
    def on_press(event, ni=node_item):
        QGraphicsRectItem.mousePressEvent(ni, event)
        on_select(ni.node_model)

    def on_release(event, ni=node_item):
        QGraphicsRectItem.mouseReleaseEvent(ni, event)
        if on_commit and not is_restoring():
            on_commit()

    node_item.mousePressEvent = on_press
    node_item.mouseReleaseEvent = on_release


class NodeFactory:
    def __init__(
        self,
        graph,
        scene,
        view,
        input_session,
        set_output_node,
        on_select_node,
        on_commit_state,
        is_restoring,
    ):
        self.graph = graph
        self.scene = scene
        self.view = view
        self.input_session = input_session
        self.set_output_node = set_output_node
        self.on_select_node = on_select_node
        self.on_commit_state = on_commit_state
        self.is_restoring = is_restoring

    def create_by_name(self, name, pos=None):
        key = resolve_registry_key(name)
        if key is None:
            return None

        display_name, cls = NODE_MAP[key]
        with self.scene.graph_lock():
            node = cls()
            if key == "Input":
                self.input_session.bind_node_to_global(node)
            elif key == "Output":
                self.set_output_node(node)
            node.name = display_name

            self.graph.add_node(node)
            node_item = NodeItem(node)
            self.scene.add_node(node_item)

            if pos is not None:
                node_item.setPos(pos)
            else:
                center = self.view.mapToScene(self.view.viewport().rect().center())
                off = (len(self.graph.nodes) % 10) * 20
                node_item.setPos(QPointF(center.x() - 75 + off, center.y() - 50 + off))

            bind_node_item_events(
                node_item,
                self.on_select_node,
                self.on_commit_state,
                self.is_restoring,
            )

        if not self.is_restoring():
            self.on_commit_state()
        return node_item
