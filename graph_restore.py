"""從序列化狀態還原圖與場景項目。"""

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtWidgets import QGraphicsRectItem

from node_registry import CLASS_BY_TYPENAME
from ui_graphics import NodeItem, ConnectionItem


@dataclass
class GraphRestoreContext:
    """還原所需的主視窗／場景依賴（避免 graph_restore import MainWindow）。"""

    scene: Any
    graph: Any
    get_global_input_image: Callable[[], Any]
    set_output_node: Callable[[Any], None]
    on_node_item_created: Callable[[Any, Any], None]  # (node_item, node_model)
    clear_config_panel: Callable[[], None]
    on_evaluate: Callable[[], None]


def restore_graph_state(state: dict, ctx: GraphRestoreContext) -> None:
    ctx.scene.clear()
    ctx.graph.nodes.clear()
    ctx.set_output_node(None)
    node_map = {}

    for nd in state["nodes"]:
        cls = CLASS_BY_TYPENAME.get(nd["type"])
        if not cls:
            continue
        node = cls()
        node.id = nd["id"]
        node.name = nd["name"]
        node.params.update(nd["params"])
        node.bypassed = nd.get("bypassed", False)
        if nd["type"] == "ImageInputNode":
            node.set_external_image_source(ctx.get_global_input_image)
        elif nd["type"] == "OutputNode":
            ctx.set_output_node(node)
        ctx.graph.add_node(node)
        node_map[node.id] = node
        ni = NodeItem(node)
        ni.setPos(nd["pos"][0], nd["pos"][1])
        ctx.scene.add_node(ni)
        ctx.on_node_item_created(ni, node)

    imap = {i.node_model.id: i for i in ctx.scene.items() if isinstance(i, NodeItem)}
    for ed in state["edges"]:
        on = node_map.get(ed["out_node"])
        inn = node_map.get(ed["in_node"])
        if not on or not inn:
            continue
        op = next((p for _, p in on.outputs.items() if p.name == ed["out_pin"]), None)
        ip = next((p for _, p in inn.inputs.items() if p.name == ed["in_pin"]), None)
        if op and ip:
            edge = ip.connect(op)
            edge.weight = ed["weight"]
            edge.bypassed = ed["bypassed"]
            oi, ii = imap.get(on.id), imap.get(inn.id)
            if oi and ii:
                opi, ipi = oi.pin_items.get(op.id), ii.pin_items.get(ip.id)
                if opi and ipi:
                    conn = ConnectionItem(opi, ipi)
                    conn.edge_model = edge
                    conn.weight_text.setPlainText(str(edge.weight))
                    if edge.weight != 1.0:
                        conn.weight_text.show()
                    ctx.scene.addItem(conn)
                    opi.add_connection(conn)
                    ipi.add_connection(conn)
                    conn.update_path()

    ctx.clear_config_panel()
    ctx.on_evaluate()


def bind_restore_node_press(node_item, node_model, on_select_config: Callable) -> None:
    def mp(event, n=node_item, nm=node_model):
        QGraphicsRectItem.mousePressEvent(n, event)
        on_select_config(nm)

    node_item.mousePressEvent = mp
