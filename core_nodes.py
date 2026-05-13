import cv2
import numpy as np
from core_engine import Node

class ImageInputNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Input Image"
        self.add_output("image")
        self.params["image_path"] = ""
        self._cached_image = None
        self._cached_path = ""

    def process(self, **kwargs):
        path = self.params.get("image_path", "")
        if path:
            if path != self._cached_path or self._cached_image is None:
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    # 如果不是 BGRA，轉換為 BGRA
                    if len(img.shape) == 2: # Grayscale
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
                    elif len(img.shape) == 3 and img.shape[2] == 3:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                    self._cached_image = img
                    self._cached_path = path
                else:
                    self._cached_image = None
            return {"image": self._cached_image}
        return {"image": None}

class ColorReplaceNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Color Replace"
        self.add_input("image")
        self.add_output("image")
        self.params["target_color_rgb"] = [0, 0, 0] # 預設黑
        self.params["replace_color_rgb"] = [255, 255, 0] # 預設黃
        self.params["tolerance"] = 30

    def process(self, image=None):
        if image is None: return {"image": None}
        
        img_hsv = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2HSV)
        target_rgb = self.params["target_color_rgb"]
        target_bgr = np.uint8([[[target_rgb[2], target_rgb[1], target_rgb[0]]]])
        target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
        
        tol = self.params["tolerance"]
        lower = np.array([max(0, target_hsv[0]-tol), max(0, target_hsv[1]-tol), max(0, target_hsv[2]-tol)])
        upper = np.array([min(179, target_hsv[0]+tol), min(255, target_hsv[1]+tol), min(255, target_hsv[2]+tol)])
        
        mask = cv2.inRange(img_hsv, lower, upper)
        
        result = image.copy()
        rep_rgb = self.params["replace_color_rgb"]
        result[mask > 0] = [rep_rgb[2], rep_rgb[1], rep_rgb[0], 255] # BGRA
        
        return {"image": result}

class EdgeDetectNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Edge Detect"
        self.add_input("image")
        self.add_output("image")
        self.params["threshold1"] = 100
        self.params["threshold2"] = 200
        self.params["edge_color_rgb"] = [255, 0, 0] # 預設紅

    def process(self, image=None):
        if image is None: return {"image": None}
        
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.params["threshold1"], self.params["threshold2"])
        
        result = np.zeros_like(image)
        ec = self.params["edge_color_rgb"]
        result[edges > 0, :3] = [ec[2], ec[1], ec[0]]
        result[edges > 0, 3] = image[edges > 0, 3]
        
        return {"image": result}

class BlurNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Gaussian Blur"
        self.add_input("image")
        self.add_output("image")
        self.params["kernel_size"] = 5

    def process(self, image=None):
        if image is None: return {"image": None}
        k = int(self.params["kernel_size"])
        if k % 2 == 0: k += 1
        if k < 1: k = 1
        result = cv2.GaussianBlur(image, (k, k), 0)
        return {"image": result}

class MergeNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Merge Overlay"
        self.add_input("base")
        self.add_input("overlay")
        self.add_output("image")

    def process(self, base=None, overlay=None):
        if base is None: return {"image": overlay}
        if overlay is None: return {"image": base}
        
        if base.shape[:2] != overlay.shape[:2]:
            overlay = cv2.resize(overlay, (base.shape[1], base.shape[0]))
            
        alpha_overlay = overlay[:,:,3].astype(np.float32) / 255.0
        alpha_base = base[:,:,3].astype(np.float32) / 255.0
        
        alpha_out = alpha_overlay + alpha_base * (1.0 - alpha_overlay)
        
        result = np.zeros_like(base)
        for c in range(0, 3):
            c_over = overlay[:,:,c].astype(np.float32) * alpha_overlay
            c_base = base[:,:,c].astype(np.float32) * alpha_base
            c_out = c_over + c_base * (1.0 - alpha_overlay)
            result[:,:,c] = np.where(alpha_out > 0, (c_out / alpha_out), 0)
            
        result[:,:,3] = np.clip(alpha_out * 255.0, 0, 255).astype(np.uint8)
        return {"image": result}
        
class OutputNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Final Output"
        self.add_input("image")
        self.final_image = None
        
    def process(self, image=None):
        self.final_image = image
        return {}
