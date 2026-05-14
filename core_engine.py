import uuid
from typing import Dict, List, Any, Set
import cv2
import numpy as np

# 輸入 Pin 類型 -> 允許的輸出 Pin 類型（與 UI 連線規則一致）
INPUT_PIN_ACCEPTS_OUTPUT_TYPES: Dict[str, Set[str]] = {
    "image": {"image"},
    "mask": {"mask", "image"},
    "value": {"value"},
    "color": {"color"},
}


def can_connect_pins(output_pin_type: str, input_pin_type: str) -> bool:
    allowed = INPUT_PIN_ACCEPTS_OUTPUT_TYPES.get(input_pin_type)
    if allowed is None:
        return output_pin_type == input_pin_type
    return output_pin_type in allowed

class Pin:
    def __init__(self, node, name: str, pin_type: str = "image"):
        self.node = node
        self.name = name
        self.pin_type = pin_type  # "image", "mask", "value", "color"
        self.id = str(uuid.uuid4())

class Edge:
    def __init__(self, output_pin: 'OutputPin', input_pin: 'InputPin'):
        self.output_pin = output_pin
        self.input_pin = input_pin
        self.weight = 1.0
        self.bypassed = False
        self.id = str(uuid.uuid4())

class InputPin(Pin):
    def __init__(self, node, name: str, pin_type: str = "image"):
        super().__init__(node, name, pin_type)
        self.edges: List[Edge] = []

    def connect(self, output_pin: 'OutputPin') -> Edge:
        if not can_connect_pins(output_pin.pin_type, self.pin_type):
            raise ValueError(
                f"無法連線：輸出類型 {output_pin.pin_type!r} 與輸入 {self.name} ({self.pin_type!r}) 不相容"
            )
        edge = Edge(output_pin, self)
        self.edges.append(edge)
        if not hasattr(output_pin, "_downstream_edges") or output_pin._downstream_edges is None:
            output_pin._downstream_edges = []
        output_pin._downstream_edges.append(edge)
        # 標記下游節點為 dirty
        self.node.mark_dirty()
        return edge

    def disconnect_edge(self, edge: Edge):
        if edge in self.edges:
            self.edges.remove(edge)
            op = edge.output_pin
            ds = getattr(op, "_downstream_edges", None)
            if ds and edge in ds:
                ds.remove(edge)
            self.node.mark_dirty()

    def disconnect_all(self):
        for edge in list(self.edges):
            self.disconnect_edge(edge)

class OutputPin(Pin):
    def __init__(self, node, name: str, pin_type: str = "image"):
        super().__init__(node, name, pin_type)
        self.data = None
        self._downstream_edges: List[Edge] = []

class Node:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.name = "Node"
        self.inputs: Dict[str, InputPin] = {}
        self.outputs: Dict[str, OutputPin] = {}
        self.params: Dict[str, Any] = {}
        self._dirty = True            # 節點是否需要重新運算
        self._cached_outputs = None   # 上一次的運算結果快取
        self._last_params_hash = None # 用於偵測參數變動
        self.bypassed = False         # 節點層級的 bypass 開關
        self.param_meta = {}        # 參數 UI 範圍等元資料，子類可覆寫或填入

    def add_input(self, name: str, pin_type: str = "image"):
        self.inputs[name] = InputPin(self, name, pin_type)

    def add_output(self, name: str, pin_type: str = "image"):
        self.outputs[name] = OutputPin(self, name, pin_type)

    def mark_dirty(self):
        """標記此節點及所有下游節點為 dirty，需要重新運算。"""
        if self._dirty:
            return  # 已經 dirty 就不再傳遞，避免無窮遞迴
        self._dirty = True
        # 傳遞 dirty 給所有下游節點
        for out_pin in self.outputs.values():
            # 確保下游邊緣列表存在且可迭代
            edges = getattr(out_pin, '_downstream_edges', [])
            if edges:
                for edge in edges:
                    if edge and edge.input_pin and edge.input_pin.node:
                        edge.input_pin.node.mark_dirty()

    def _params_hash(self):
        """生成參數的簡易雜湊，用於偵測參數變動。"""
        try:
            return hash(str(sorted(self.params.items())))
        except TypeError:
            return hash(str(self.params))

    def check_params_changed(self):
        """檢查參數是否有變動，有的話標記 dirty。"""
        current_hash = self._params_hash()
        if current_hash != self._last_params_hash:
            self._last_params_hash = current_hash
            self._dirty = True

    @staticmethod
    def _extract_mask(data):
        """從任意格式的圖片資料中擷取單通道遮罩。"""
        if len(data.shape) > 2:
            if data.shape[2] == 4:
                return data[:,:,3]
            else:
                return cv2.cvtColor(data, cv2.COLOR_BGR2GRAY)
        return data

    def evaluate(self):
        # 先檢查參數是否有變動
        self.check_params_changed()

        # 如果節點沒有被標記為 dirty，直接跳過運算
        if not self._dirty and self._cached_outputs is not None:
            # 仍然要更新 output pin 的 data（因為下游會來讀取）
            for name, data in self._cached_outputs.items():
                if name in self.outputs:
                    self.outputs[name].data = data
            return

        input_data = {}
        for name, pin in self.inputs.items():
            valid_edges = [e for e in pin.edges if not e.bypassed and e.output_pin.data is not None]
            
            if not valid_edges:
                input_data[name] = None
            else:
                if pin.pin_type == "image":
                    base_img = valid_edges[0].output_pin.data.copy()
                    
                    if len(base_img.shape) == 2:
                        base_img = cv2.cvtColor(base_img, cv2.COLOR_GRAY2BGRA)
                    elif len(base_img.shape) == 3 and base_img.shape[2] == 3:
                        base_img = cv2.cvtColor(base_img, cv2.COLOR_BGR2BGRA)
                    
                    if len(valid_edges) == 1:
                        w = valid_edges[0].weight
                        base_img[:,:,3] = np.clip(base_img[:,:,3].astype(np.float32) * w, 0, 255).astype(np.uint8)
                    else:
                        total_weight = sum(e.weight for e in valid_edges)
                        if total_weight <= 0:
                            total_weight = 1e-6
                        
                        base_img_float = base_img.astype(np.float32)
                        base_rgb = base_img_float[:,:,:3] * (valid_edges[0].weight / total_weight)
                        base_alpha = base_img_float[:,:,3] * valid_edges[0].weight
                        
                        for e in valid_edges[1:]:
                            img = e.output_pin.data.copy()
                            if len(img.shape) == 2:
                                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
                            elif len(img.shape) == 3 and img.shape[2] == 3:
                                img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                            
                            img = img.astype(np.float32)
                            if img.shape[:2] != base_img.shape[:2]:
                                img = cv2.resize(img, (base_img.shape[1], base_img.shape[0]))
                            
                            base_rgb += img[:,:,:3] * (e.weight / total_weight)
                            base_alpha += img[:,:,3] * e.weight
                            
                        base_img[:,:,:3] = np.clip(base_rgb, 0, 255).astype(np.uint8)
                        base_img[:,:,3] = np.clip(base_alpha, 0, 255).astype(np.uint8)
                    
                    input_data[name] = base_img
                elif pin.pin_type == "mask":
                    base_mask = Node._extract_mask(valid_edges[0].output_pin.data).astype(np.float32) * valid_edges[0].weight
                    for e in valid_edges[1:]:
                        m = Node._extract_mask(e.output_pin.data).astype(np.float32)
                        if m.shape[:2] != base_mask.shape[:2]:
                            m = cv2.resize(m, (base_mask.shape[1], base_mask.shape[0]))
                        base_mask += m * e.weight
                    
                    input_data[name] = np.clip(base_mask, 0, 255).astype(np.uint8)
                else:
                    # Non-image fallback (value/color — just take first)
                    input_data[name] = valid_edges[0].output_pin.data
        
        output_data = self.process(**input_data)
        
        if output_data:
            self._cached_outputs = output_data
            for name, data in output_data.items():
                if name in self.outputs:
                    self.outputs[name].data = data
        
        self._dirty = False

    def process(self, **kwargs) -> Dict[str, Any]:
        return {}

class Graph:
    def __init__(self):
        self.nodes: List[Node] = []
        self.proxy_scale = 1.0  # 1.0 = 全解析度, 0.5 = 半解析度

    def add_node(self, node: Node):
        self.nodes.append(node)

    def remove_node(self, node: Node):
        if node in self.nodes:
            for pin in node.inputs.values():
                pin.disconnect_all()
            for other_node in self.nodes:
                for in_pin in other_node.inputs.values():
                    edges_to_remove = [e for e in in_pin.edges if e.output_pin.node == node]
                    for e in edges_to_remove:
                        in_pin.disconnect_edge(e)
            self.nodes.remove(node)

    def mark_all_dirty(self):
        """強制標記所有節點為 dirty，需要全部重算。"""
        for node in self.nodes:
            node._dirty = True

    def evaluate(self):
        visited = set()
        order = []

        def visit(n: Node):
            if n is None or n in visited:
                return
            # 確保 inputs 存在且可迭代
            inputs = getattr(n, 'inputs', {})
            if inputs is None: inputs = {}
            
            for pin in inputs.values():
                if pin is None: continue
                # 確保 edges 存在且可迭代
                edges = getattr(pin, 'edges', [])
                if edges is None: edges = []
                
                for edge in edges:
                    if edge and edge.output_pin and edge.output_pin.node:
                        visit(edge.output_pin.node)
            visited.add(n)
            order.append(n)

        # 確保 nodes 列表存在
        nodes_to_process = getattr(self, 'nodes', [])
        if nodes_to_process is None: nodes_to_process = []
        
        for node in nodes_to_process:
            visit(node)

        for node in order:
            if node is None: continue
            try:
                node.evaluate()
                node._status = "normal"
                if hasattr(node, "_error_message"):
                    node._error_message = None
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                print(f"!!! 節點運算崩潰 !!!\n節點: {getattr(node, 'name', 'Unknown')}\n型別: {node.__class__.__name__}\n原因: {e}\n詳情:\n{error_detail}")
                node._status = "error"
                node._error_message = str(e)

    def to_json(self):
        """匯出圖表為可序列化的字典。"""
        data = {"nodes": [], "edges": []}
        for node in self.nodes:
            data["nodes"].append({
                "id": node.id,
                "type": node.__class__.__name__,
                "name": node.name,
                "params": dict(node.params),
                "bypassed": node.bypassed,
            })
            for pin_name, in_pin in node.inputs.items():
                for edge in in_pin.edges:
                    data["edges"].append({
                        "out_node": edge.output_pin.node.id,
                        "out_pin": edge.output_pin.name,
                        "in_node": node.id,
                        "in_pin": pin_name,
                        "weight": edge.weight,
                        "bypassed": edge.bypassed,
                    })
        return data
