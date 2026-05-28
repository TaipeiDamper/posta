"""圖狀態序列化（純資料，不依賴 MainWindow）。"""

import json


def get_graph_state(graph, node_positions=None):
    state = {"nodes": [], "edges": []}
    node_positions = node_positions or {}
    for node in graph.nodes:
        p = node_positions.get(node.id, (0, 0))
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
