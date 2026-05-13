import uuid
from typing import Dict, List, Any
import cv2
import numpy as np

class Pin:
    def __init__(self, node, name: str, pin_type: str = "image"):
        self.node = node
        self.name = name
        self.pin_type = pin_type
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
        edge = Edge(output_pin, self)
        self.edges.append(edge)
        return edge

    def disconnect_edge(self, edge: Edge):
        if edge in self.edges:
            self.edges.remove(edge)

    def disconnect_all(self):
        self.edges.clear()

class OutputPin(Pin):
    def __init__(self, node, name: str, pin_type: str = "image"):
        super().__init__(node, name, pin_type)
        self.data = None

class Node:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.name = "Node"
        self.inputs: Dict[str, InputPin] = {}
        self.outputs: Dict[str, OutputPin] = {}
        self.params: Dict[str, Any] = {}

    def add_input(self, name: str, pin_type: str = "image"):
        self.inputs[name] = InputPin(self, name, pin_type)

    def add_output(self, name: str, pin_type: str = "image"):
        self.outputs[name] = OutputPin(self, name, pin_type)

    def evaluate(self):
        input_data = {}
        for name, pin in self.inputs.items():
            valid_edges = [e for e in pin.edges if not e.bypassed and e.output_pin.data is not None]
            
            if not valid_edges:
                input_data[name] = None
            else:
                if pin.pin_type == "image":
                    base_img = valid_edges[0].output_pin.data.copy()
                    
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
                            img = e.output_pin.data.astype(np.float32)
                            if img.shape[:2] != base_img.shape[:2]:
                                img = cv2.resize(img, (base_img.shape[1], base_img.shape[0]))
                            
                            base_rgb += img[:,:,:3] * (e.weight / total_weight)
                            base_alpha += img[:,:,3] * e.weight
                            
                        base_img[:,:,:3] = np.clip(base_rgb, 0, 255).astype(np.uint8)
                        base_img[:,:,3] = np.clip(base_alpha, 0, 255).astype(np.uint8)
                    
                    input_data[name] = base_img
                elif pin.pin_type == "mask":
                    def extract_mask(data):
                        if len(data.shape) > 2:
                            # If passed an RGBA or BGR image, extract Alpha or Grayscale
                            if data.shape[2] == 4:
                                return data[:,:,3]
                            else:
                                return cv2.cvtColor(data, cv2.COLOR_BGR2GRAY)
                        return data

                    base_mask = extract_mask(valid_edges[0].output_pin.data).astype(np.float32) * valid_edges[0].weight
                    for e in valid_edges[1:]:
                        m = extract_mask(e.output_pin.data).astype(np.float32)
                        if m.shape[:2] != base_mask.shape[:2]:
                            m = cv2.resize(m, (base_mask.shape[1], base_mask.shape[0]))
                        base_mask += m * e.weight
                    
                    input_data[name] = np.clip(base_mask, 0, 255).astype(np.uint8)
                else:
                    # Non-image fallback (just take first)
                    input_data[name] = valid_edges[0].output_pin.data
        
        output_data = self.process(**input_data)
        
        if output_data:
            for name, data in output_data.items():
                if name in self.outputs:
                    self.outputs[name].data = data

    def process(self, **kwargs) -> Dict[str, Any]:
        return {}

class Graph:
    def __init__(self):
        self.nodes: List[Node] = []

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

    def evaluate(self):
        visited = set()
        order = []

        def visit(n: Node):
            if n in visited:
                return
            for pin in n.inputs.values():
                for edge in pin.edges:
                    visit(edge.output_pin.node)
            visited.add(n)
            order.append(n)

        for node in self.nodes:
            visit(node)

        for node in order:
            node.evaluate()
