"""圖狀態序列化（純資料，不依賴 MainWindow）。"""

import json

from ui_graphics import NodeItem


def get_graph_state(graph, scene):
    state = {"nodes": [], "edges": []}
    nmap = {i.node_model: i for i in scene.items() if isinstance(i, NodeItem)}
    for node in graph.nodes:
        item = nmap.get(node)
        p = (item.scenePos().x(), item.scenePos().y()) if item else (0, 0)
        state["nodes"].append({
            "id": node.id,
            "type": node.__class__.__name__,
            "name": node.name,
            "pos": p,
            "params": dict(node.params),
            "bypassed": node.bypassed,
        })
        for pn, ip in node.inputs.items():
            for e in ip.edges:
                state["edges"].append({
                    "out_node": e.output_pin.node.id,
                    "out_pin": e.output_pin.name,
                    "in_node": node.id,
                    "in_pin": pn,
                    "weight": e.weight,
                    "bypassed": e.bypassed,
                })
    return state


def dump_json(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
