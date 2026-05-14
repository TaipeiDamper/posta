import cv2
import numpy as np
from core_engine import Node

class ImageInputNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Input Image"
        self.add_output("Image Out")
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
            return {"Image Out": self._cached_image}
        return {"Image Out": None}

class EffectNode(Node):
    """
    Base class for nodes that apply an effect to an image, optionally constrained by a mask.
    """
    def __init__(self):
        super().__init__()
        self.add_input("Image In")
        self.add_input("Mask In", pin_type="mask")
        self.add_output("Image Out")
        self.params["blend_ratio (%)"] = 100
        
    def process(self, **kwargs):
        image = kwargs.get("Image In")
        mask = kwargs.get("Mask In")
        if image is None: return {"Image Out": None}
        
        result = self.apply_effect(image)
        
        ratio = float(self.params.get("blend_ratio (%)", 100)) / 100.0
        
        # 合併 mask 和 ratio 為單一混合操作，避免多次 float32 轉換
        if mask is not None:
            if mask.shape[:2] != image.shape[:2]:
                mask = cv2.resize(mask, (image.shape[1], image.shape[0]))
            # effective_ratio = mask * ratio，同時處理遮罩與比例
            effective_ratio = (mask.astype(np.float32) / 255.0 * ratio)
            effective_ratio = np.expand_dims(effective_ratio, axis=-1)
        elif ratio < 1.0:
            effective_ratio = ratio
        else:
            # ratio == 1.0 且無 mask，直接回傳結果，零額外運算
            return {"Image Out": result}
        
        img_f = image.astype(np.float32)
        res_f = result.astype(np.float32)
        blended = img_f + (res_f - img_f) * effective_ratio
        result = np.clip(blended, 0, 255).astype(np.uint8)
            
        return {"Image Out": result}

    def apply_effect(self, image):
        # Override this in subclasses
        return image

class ColorReplaceNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "Color Replace"
        self.add_output("Mask Out", pin_type="mask")
        self.params["target_color_rgb"] = [0, 0, 0] # 預設黑
        self.params["replace_color_rgb"] = [255, 255, 0] # 預設黃
        self.params["tolerance"] = 30
        self._cached_mask = None  # 快取 HSV+inRange 結果，避免重複計算

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        if image is None: return {"Image Out": None, "Mask Out": None}
        
        # 只做一次 HSV 轉換 + inRange，快取給 apply_effect 使用
        img_hsv = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2HSV)
        target_rgb = self.params["target_color_rgb"]
        target_bgr = np.uint8([[[target_rgb[2], target_rgb[1], target_rgb[0]]]])
        target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
        
        tol = self.params["tolerance"]
        lower = np.array([max(0, target_hsv[0]-tol), max(0, target_hsv[1]-tol), max(0, target_hsv[2]-tol)])
        upper = np.array([min(179, target_hsv[0]+tol), min(255, target_hsv[1]+tol), min(255, target_hsv[2]+tol)])
        
        self._cached_mask = cv2.inRange(img_hsv, lower, upper)
        
        # Apply base effect logic（內部會呼叫 apply_effect，直接使用 _cached_mask）
        effect_result = super().process(**kwargs)
        
        return {"Image Out": effect_result["Image Out"], "Mask Out": self._cached_mask}

    def apply_effect(self, image):
        result = image.copy()
        rep_rgb = self.params["replace_color_rgb"]
        result[self._cached_mask > 0, :3] = [rep_rgb[2], rep_rgb[1], rep_rgb[0]]
        return result

class EdgeDetectNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "Edge Detect"
        self.add_output("Mask Out", pin_type="mask")
        self.params["threshold1"] = 100
        self.params["threshold2"] = 200
        self.params["edge_color_rgb"] = [255, 0, 0] # 預設紅
        self._cached_edges = None  # 快取 Canny 結果，避免重複計算

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        if image is None: return {"Image Out": None, "Mask Out": None}
        
        # 只做一次灰階轉換 + Canny，快取給 apply_effect 使用
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        self._cached_edges = cv2.Canny(gray, self.params["threshold1"], self.params["threshold2"])
        
        effect_result = super().process(**kwargs)
        
        return {"Image Out": effect_result["Image Out"], "Mask Out": self._cached_edges}

    def apply_effect(self, image):
        result = np.zeros_like(image)
        ec = self.params["edge_color_rgb"]
        edge_mask = self._cached_edges > 0
        result[edge_mask, :3] = [ec[2], ec[1], ec[0]]
        result[edge_mask, 3] = image[edge_mask, 3]
        return result

class BlurNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "Gaussian Blur"
        self.params["kernel_size"] = 5

    def apply_effect(self, image):
        k = int(self.params["kernel_size"])
        if k % 2 == 0: k += 1
        if k < 1: k = 1
        return cv2.GaussianBlur(image, (k, k), 0)

class MergeNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Merge Overlay"
        self.add_input("Base In")
        self.add_input("Overlay In")
        self.add_output("Image Out")
        self.params["blend_ratio (%)"] = 100

    def process(self, **kwargs):
        base = kwargs.get("Base In")
        overlay = kwargs.get("Overlay In")
        if base is None: return {"Image Out": overlay}
        if overlay is None: return {"Image Out": base}
        
        if base.shape[:2] != overlay.shape[:2]:
            overlay = cv2.resize(overlay, (base.shape[1], base.shape[0]))
            
        alpha_overlay = overlay[:,:,3].astype(np.float32) / 255.0
        alpha_base = base[:,:,3].astype(np.float32) / 255.0
        
        ratio = float(self.params.get("blend_ratio (%)", 100)) / 100.0
        alpha_overlay *= ratio
        
        alpha_out = alpha_overlay + alpha_base * (1.0 - alpha_overlay)
        
        # 向量化處理全部 3 個通道，避免 Python for 迴圈開銷
        alpha_overlay_3 = alpha_overlay[:,:,np.newaxis]  # (H, W, 1)
        alpha_base_3 = alpha_base[:,:,np.newaxis]
        alpha_out_3 = alpha_out[:,:,np.newaxis]
        
        over_rgb = overlay[:,:,:3].astype(np.float32) * alpha_overlay_3
        base_rgb = base[:,:,:3].astype(np.float32) * alpha_base_3
        c_out = over_rgb + base_rgb * (1.0 - alpha_overlay_3)
        
        result = np.zeros_like(base)
        result[:,:,:3] = np.where(alpha_out_3 > 0, c_out / alpha_out_3, 0).astype(np.uint8)
        result[:,:,3] = np.clip(alpha_out * 255.0, 0, 255).astype(np.uint8)
        return {"Image Out": result}

class OutputNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "Final Output"
        self.add_input("Image In")
        self.final_image = None
        
    def process(self, **kwargs):
        self.final_image = kwargs.get("Image In")
        return {}

class TintNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "染色 (Tint)"
        self.params["tint_color_rgb"] = [100, 150, 255]

    def apply_effect(self, image):
        # 轉為浮點數進行運算
        img_f = image.astype(np.float32) / 255.0
        tint = self.params["tint_color_rgb"]
        # 使用簡易的染色法：保留亮度，改變色調
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        gray_3 = np.stack([gray, gray, gray], axis=-1)
        
        tint_f = np.array([tint[2], tint[1], tint[0]], dtype=np.float32) / 255.0
        colored = gray_3 * tint_f
        
        result = image.copy()
        result[:,:,:3] = np.clip(colored * 255.0, 0, 255).astype(np.uint8)
        return result

class LuminanceNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "明度選取 (Luma Key)"
        self.add_input("Image In")
        self.add_output("Mask Out", pin_type="mask")
        self.params["min_brightness"] = 128
        self.params["max_brightness"] = 255

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        if image is None: return {"Mask Out": None}
        
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        mask = cv2.inRange(gray, self.params["min_brightness"], self.params["max_brightness"])
        return {"Mask Out": mask}

class BrightnessContrastNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "亮度對比"
        self.params["brightness"] = 50 # 50 is neutral
        self.params["contrast"] = 50   # 50 is neutral

    def apply_effect(self, image):
        b = (self.params["brightness"] - 50) * 2.0
        c = (self.params["contrast"] / 50.0)
        result = cv2.convertScaleAbs(image, alpha=c, beta=b)
        result[:,:,3] = image[:,:,3] # Keep original alpha
        return result

class InvertNode(EffectNode):
    def __init__(self):
        super().__init__()
        self.name = "負片 (Invert)"

    def apply_effect(self, image):
        result = image.copy()
        result[:,:,:3] = 255 - image[:,:,:3]
        return result

class BlendNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "圖層混合 (Blend)"
        self.add_input("Base In")
        self.add_input("Overlay In")
        self.add_output("Image Out")
        self.params["mode"] = "Multiply" # Multiply, Screen, Overlay, Add, Normal
        self.params["opacity (%)"] = 100

    def process(self, **kwargs):
        base = kwargs.get("Base In")
        over = kwargs.get("Overlay In")
        if base is None: return {"Image Out": over}
        if over is None: return {"Image Out": base}
        
        if base.shape[:2] != over.shape[:2]:
            over = cv2.resize(over, (base.shape[1], base.shape[0]))
            
        b = base[:,:,:3].astype(np.float32) / 255.0
        o = over[:,:,:3].astype(np.float32) / 255.0
        mode = self.params.get("mode", "Multiply")
        
        if mode == "Multiply":
            res = b * o
        elif mode == "Screen":
            res = 1.0 - (1.0 - b) * (1.0 - o)
        elif mode == "Overlay":
            res = np.where(b < 0.5, 2.0 * b * o, 1.0 - 2.0 * (1.0 - b) * (1.0 - o))
        elif mode == "Add":
            res = b + o
        else:
            res = o
            
        ratio = self.params.get("opacity (%)", 100) / 100.0
        final_rgb = b * (1.0 - ratio) + res * ratio
        
        result = base.copy()
        result[:,:,:3] = np.clip(final_rgb * 255.0, 0, 255).astype(np.uint8)
        return {"Image Out": result}

class SwitcherNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "時間切換器 (Switcher)"
        self.add_input("In 1")
        self.add_input("In 2")
        self.add_input("In 3")
        self.add_output("Image Out")
        self.params["interval_s"] = 2
        self.current_idx = 0
        self.last_switch = 0 # timestamp

    def process(self, **kwargs):
        import time
        now = time.time()
        interval = max(0.1, float(self.params.get("interval_s", 2)))
        
        if now - self.last_switch > interval:
            self.current_idx = (self.current_idx + 1) % 3
            self.last_switch = now
            
        keys = ["In 1", "In 2", "In 3"]
        return {"Image Out": kwargs.get(keys[self.current_idx])}
