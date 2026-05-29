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
        self._external_image_fn = None

    def set_external_image_source(self, fn):
        """若設定，process 優先回傳 fn()（例如主視窗的全域輸入圖）。"""
        self._external_image_fn = fn

    def process(self, **kwargs):
        img = None
        if self._external_image_fn is not None:
            img = self._external_image_fn()
        else:
            path = self.params.get("image_path", "")
            if path:
                if path != self._cached_path or self._cached_image is None:
                    try:
                        read_img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                        if read_img is not None:
                            if len(read_img.shape) == 2:
                                read_img = cv2.cvtColor(read_img, cv2.COLOR_GRAY2BGRA)
                            elif len(read_img.shape) == 3 and read_img.shape[2] == 3:
                                read_img = cv2.cvtColor(read_img, cv2.COLOR_BGR2BGRA)
                            self._cached_image = read_img
                            self._cached_path = path
                        else:
                            self._cached_image = None
                    except Exception:
                        self._cached_image = None
                img = self._cached_image

        if img is not None:
            scale = getattr(self.graph, "proxy_scale", 1.0) if self.graph else 1.0
            if scale != 1.0:
                h, w = img.shape[:2]
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        return {"Image Out": img}

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
        self.param_meta["blend_ratio (%)"] = {"min": 0, "max": 100}

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
        self.param_meta["tolerance"] = {"min": 0, "max": 255}

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
        self.param_meta["threshold1"] = {"min": 0, "max": 500}
        self.param_meta["threshold2"] = {"min": 0, "max": 500}

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
        self.param_meta["kernel_size"] = {"min": 1, "max": 101}

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
        self.param_meta["blend_ratio (%)"] = {"min": 0, "max": 100}

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
        result[:,:,:3] = np.clip(np.where(alpha_out_3 > 0, c_out / alpha_out_3, 0), 0, 255).astype(np.uint8)
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
        self.param_meta["min_brightness"] = {"min": 0, "max": 255}
        self.param_meta["max_brightness"] = {"min": 0, "max": 255}

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
        self.param_meta["brightness"] = {"min": 0, "max": 100}
        self.param_meta["contrast"] = {"min": 0, "max": 100}

    def apply_effect(self, image):
        b = (self.params["brightness"] - 50) * 2.0
        c = (self.params["contrast"] / 50.0)
        result = cv2.convertScaleAbs(image, alpha=c, beta=b)
        result[:,:,3] = image[:,:,3] # Keep original alpha
        return result

class InvertNode(EffectNode):
    """負片效果：反轉 RGB 顏色"""
    def __init__(self):
        super().__init__()
        self.name = "負片 (Invert)"

    def apply_effect(self, image):
        res_rgb = 255 - image[:,:,:3]
        return np.dstack([res_rgb, image[:,:,3]])

class MaskInvertNode(Node):
    """反向選取：反轉遮罩範圍。"""
    def __init__(self):
        super().__init__()
        self.name = "反向選取 (Mask Invert)"
        self.add_input("Mask In", pin_type="mask")
        self.add_output("Mask Out", pin_type="mask")

    def process(self, **kwargs):
        mask = kwargs.get("Mask In")
        if mask is None:
            return {"Mask Out": None}
        if len(mask.shape) > 2:
            mask = Node._extract_mask(mask)
        return {"Mask Out": 255 - mask}

class BlendNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "圖層混合 (Blend)"
        self.add_input("Base In")
        self.add_input("Overlay In")
        self.add_output("Image Out")
        self.params["mode"] = "Multiply" # Multiply, Screen, Overlay, Add, Normal
        self.params["opacity (%)"] = 100
        self.param_meta["opacity (%)"] = {"min": 0, "max": 100}

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
        self.params["interval_s"] = 0.5
        self.params["smooth"] = 0  # 0 = 硬切, 1 = 平滑過渡
        self.current_idx = 0
        self._blend_progress = 0.0
        import time
        self.last_switch = time.time()
        self.param_meta["interval_s"] = {"min": 0.0, "max": 2.0, "step": 0.1, "decimals": 2}
        self.param_meta["smooth"] = {"min": 0, "max": 1}

    def advance_if_due(self) -> bool:
        """由主視窗計時器呼叫：硬切模式僅在到期時切換；平滑模式持續更新混合進度。"""
        import time
        now = time.time()
        interval = max(0.05, float(self.params.get("interval_s", 0.5)))
        elapsed = now - self.last_switch
        is_smooth = self.params.get("smooth", 0)

        if is_smooth:
            # 平滑模式：持續更新混合進度
            self._blend_progress = min(1.0, elapsed / interval)
            if elapsed >= interval:
                self.current_idx = (self.current_idx + 1) % 3
                self.last_switch = now
                self._blend_progress = 0.0
            self.mark_dirty()
            return True
        else:
            # 硬切模式
            if elapsed < interval:
                return False
            self.current_idx = (self.current_idx + 1) % 3
            self.last_switch = now
            self._blend_progress = 0.0
            self.mark_dirty()
            return True

    def process(self, **kwargs):
        keys = ["In 1", "In 2", "In 3"]
        current_img = kwargs.get(keys[self.current_idx])

        if self.params.get("smooth", 0) and self._blend_progress > 0.001:
            next_idx = (self.current_idx + 1) % 3
            next_img = kwargs.get(keys[next_idx])
            if current_img is not None and next_img is not None:
                if current_img.shape[:2] != next_img.shape[:2]:
                    next_img = cv2.resize(next_img, (current_img.shape[1], current_img.shape[0]))
                alpha = self._blend_progress
                blended = cv2.addWeighted(current_img, 1.0 - alpha, next_img, alpha, 0)
                return {"Image Out": blended}

        return {"Image Out": current_img}

# ============== 新增節點 ==============

class TextNode(Node):
    """文字渲染節點：將文字繪製到透明背景的圖片上。"""
    def __init__(self):
        super().__init__()
        self.name = "文字 (Text)"
        self.add_input("Image In")  # 選填，作為底圖尺寸參考
        self.add_output("Image Out")
        self.params["text"] = "Hello"
        self.params["font_scale"] = 2
        self.params["thickness"] = 3
        self.params["text_color_rgb"] = [255, 255, 255]
        self.params["pos_x"] = 50
        self.params["pos_y"] = 50

    def process(self, **kwargs):
        base = kwargs.get("Image In")
        
        text = str(self.params.get("text", "Hello"))
        scale = max(0.1, float(self.params.get("font_scale", 2)))
        thick = max(1, int(self.params.get("thickness", 3)))
        rgb = self.params.get("text_color_rgb", [255, 255, 255])
        bgr = (rgb[2], rgb[1], rgb[0])
        px = int(self.params.get("pos_x", 50))
        py = int(self.params.get("pos_y", 50))
        
        if base is not None:
            result = base.copy()
            cv2.putText(result, text, (px, py), cv2.FONT_HERSHEY_SIMPLEX, scale, bgr, thick, cv2.LINE_AA)
        else:
            result = np.zeros((512, 512, 4), dtype=np.uint8)
            mask = np.zeros((512, 512), dtype=np.uint8)
            cv2.putText(mask, text, (px, py), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thick, cv2.LINE_AA)
            result[mask > 0, 0] = bgr[0]
            result[mask > 0, 1] = bgr[1]
            result[mask > 0, 2] = bgr[2]
            result[:, :, 3] = mask
        
        return {"Image Out": result}

class SmartCropNode(Node):
    """智慧裁切節點：自動偵測主體並裁切成指定比例。"""
    def __init__(self):
        super().__init__()
        self.name = "智慧裁切 (Crop)"
        self.add_input("Image In")
        self.add_output("Image Out")
        self.params["ratio_w"] = 9
        self.params["ratio_h"] = 16

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        if image is None: return {"Image Out": None}
        
        h, w = image.shape[:2]
        target_r = self.params["ratio_w"] / max(1, self.params["ratio_h"])
        current_r = w / h
        
        if current_r > target_r:
            # 圖片太寬，從左右裁切
            new_w = int(h * target_r)
            # 嘗試以灰階找到主體質心來決定中心偏移
            gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
            M = cv2.moments(thresh)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
            else:
                cx = w // 2
            
            x1 = max(0, min(cx - new_w // 2, w - new_w))
            result = image[:, x1:x1+new_w]
        else:
            # 圖片太高，從上下裁切
            new_h = int(w / target_r)
            gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
            M = cv2.moments(thresh)
            if M["m00"] > 0:
                cy = int(M["m01"] / M["m00"])
            else:
                cy = h // 2
            
            y1 = max(0, min(cy - new_h // 2, h - new_h))
            result = image[y1:y1+new_h, :]
        
        return {"Image Out": result}

class ValueNode(Node):
    """全域數值節點：輸出一個浮點數值，可以同時接到多個節點的參數。"""
    def __init__(self):
        super().__init__()
        self.name = "數值 (Value)"
        self.add_output("Value Out", pin_type="value")
        self.params["value"] = 50

    def process(self, **kwargs):
        return {"Value Out": self.params.get("value", 50)}

class ColorOutputNode(Node):
    """全域顏色節點：輸出一個 RGB 顏色值。"""
    def __init__(self):
        super().__init__()
        self.name = "顏色 (Color)"
        self.add_output("Color Out", pin_type="color")
        self.params["output_color_rgb"] = [255, 255, 255]

    def process(self, **kwargs):
        return {"Color Out": self.params.get("output_color_rgb", [255, 255, 255])}

class RerouteNode(Node):
    """轉向點節點：純粹轉發資料，用於整理連線走位。"""
    def __init__(self):
        super().__init__()
        self.name = "轉向 (Reroute)"
        self.add_input("In")
        self.add_output("Out")

    def process(self, **kwargs):
        return {"Out": kwargs.get("In")}

# ============== 邊緣與輪廓類 (Edge & Contour) ==============

class SobelEdgeNode(EffectNode):
    """索伯邊緣偵測：保留梯度的邊緣提取"""
    def __init__(self):
        super().__init__()
        self.name = "索伯邊緣 (Sobel)"
        self.params["ksize"] = 3  # 卷積核大小 (1, 3, 5, 7)

    def apply_effect(self, image):
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        k = int(self.params["ksize"])
        if k % 2 == 0: k += 1 # 確保為奇數
        if k < 1: k = 1
        
        grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=k)
        grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=k)
        
        abs_grad_x = cv2.convertScaleAbs(grad_x)
        abs_grad_y = cv2.convertScaleAbs(grad_y)
        
        # 合并梯度
        edge = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)
        
        # 轉回 BGRA 格式輸出
        res_rgb = cv2.cvtColor(edge, cv2.COLOR_GRAY2BGR)
        result = np.dstack([res_rgb, image[:,:,3]]) # 保持原始 Alpha
        return result

class ThresholdContourNode(EffectNode):
    """輪廓提取：二值化後提取閉合輪廓"""
    def __init__(self):
        super().__init__()
        self.name = "輪廓提取 (Contour)"
        self.params["threshold"] = 127
        self.params["thickness"] = 1

    def apply_effect(self, image):
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        thresh_val = int(self.params["threshold"])
        _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        # 建立全黑背景
        res_rgb = np.zeros_like(image[:,:,:3])
        thick = int(self.params["thickness"])
        if thick < 1: thick = 1
        cv2.drawContours(res_rgb, contours, -1, (255, 255, 255), thick)
        
        result = np.dstack([res_rgb, image[:,:,3]])
        return result

class PencilSketchNode(EffectNode):
    """鉛筆素描：快速產生手繪感線條"""
    def __init__(self):
        super().__init__()
        self.name = "鉛筆素描 (Sketch)"
        self.params["blur_size"] = 21

    def apply_effect(self, image):
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        inv_gray = 255 - gray
        
        k = int(self.params["blur_size"])
        if k % 2 == 0: k += 1
        if k < 1: k = 1
        
        blur = cv2.GaussianBlur(inv_gray, (k, k), 0)
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        
        res_rgb = cv2.cvtColor(sketch, cv2.COLOR_GRAY2BGR)
        result = np.dstack([res_rgb, image[:,:,3]])
        return result

# ============== 亮度與色調細分類 (Luma & Tone) ==============

class MidtoneKeyNode(Node):
    """中間調選取：專門選取明度區間"""
    def __init__(self):
        super().__init__()
        self.name = "中間調選取 (Midtone)"
        self.add_input("Image In")
        self.add_output("Mask Out", pin_type="mask")
        self.params["min_brightness"] = 76   # ~30%
        self.params["max_brightness"] = 178  # ~70%
        self.param_meta["min_brightness"] = {"min": 0, "max": 255}
        self.param_meta["max_brightness"] = {"min": 0, "max": 255}

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        if image is None: return {"Mask Out": None}
        
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        min_b = int(self.params["min_brightness"])
        max_b = int(self.params["max_brightness"])
        mask = cv2.inRange(gray, min_b, max_b)
        return {"Mask Out": mask}

class PosterizeNode(EffectNode):
    """色階分離：減少色彩階層"""
    def __init__(self):
        super().__init__()
        self.name = "色階分離 (Posterize)"
        self.params["levels"] = 4  # 分成幾個階層
        self.param_meta["levels"] = {"min": 2, "max": 32}

    def apply_effect(self, image):
        levels = max(2, int(self.params["levels"])) # 至少2階
        # 轉換公式：floor(v * n / 255) * (255 / (n - 1))
        tmpi = image[:,:,:3].astype(np.float32)
        factor = 255.0 / (levels - 1)
        result_rgb = np.round((tmpi / 255.0) * (levels - 1)) * factor
        result = np.dstack([np.clip(result_rgb, 0, 255).astype(np.uint8), image[:,:,3]])
        return result

class GradientMapNode(EffectNode):
    """漸層對映：根據圖片的明度對映到兩種顏色"""
    def __init__(self):
        super().__init__()
        self.name = "漸層對映 (Grad Map)"
        self.params["shadow_color_rgb"] = [0, 0, 100]    # 深色
        self.params["highlight_color_rgb"] = [255, 200, 0] # 亮色

    def apply_effect(self, image):
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        
        shadow = np.array(self.params["shadow_color_rgb"])[::-1].astype(np.float32) # RGB to BGR
        highlight = np.array(self.params["highlight_color_rgb"])[::-1].astype(np.float32)
        
        # 線性插值
        res_rgb = shadow * (1 - gray[:,:,np.newaxis]) + highlight * gray[:,:,np.newaxis]
        
        result = np.dstack([np.clip(res_rgb, 0, 255).astype(np.uint8), image[:,:,3]])
        return result

# ============== 質感與雜訊類 (Texture & Noise) ==============

class HalftoneNode(EffectNode):
    """半調子點陣：模仿印刷網點效果"""
    def __init__(self):
        super().__init__()
        self.name = "半調子網點 (Halftone)"
        self.params["dot_size"] = 10
        self.param_meta["dot_size"] = {"min": 2, "max": 64}

    def apply_effect(self, image):
        dot_size = max(2, int(self.params["dot_size"]))
        h, w = image.shape[:2]
        
        # 1. 產生灰階圖並縮放到與 dot_size 匹配的網格
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        
        # 2. 建立網格座標系
        y, x = np.ogrid[:h, :w]
        # 計算每個像素點到其所屬網格中心的距離
        dist_y = (y % dot_size) - (dot_size / 2.0)
        dist_x = (x % dot_size) - (dot_size / 2.0)
        dist_sq = dist_y**2 + dist_x**2
        
        # 3. 獲取每個網格的平均亮度 (使用 Resize 作為快速近似)
        small_gray = cv2.resize(gray, (max(1, w // dot_size), max(1, h // dot_size)), interpolation=cv2.INTER_AREA)
        grid_brightness = cv2.resize(small_gray, (w, h), interpolation=cv2.INTER_NEAREST).astype(np.float32) / 255.0
        
        # 4. 根據亮度決定半徑閾值：亮度越低(黑)，網點半徑越大
        max_radius_sq = (dot_size / 2.0) ** 2 * 1.5 
        threshold_sq = (1.0 - grid_brightness) * max_radius_sq
        
        # 5. 生成黑白遮罩 (符合閾值的設為 0(黑)，否則 255(白))
        mask = np.where(dist_sq < threshold_sq, 0, 255).astype(np.uint8)
        
        # 6. 應用遮罩 (黑點白底)
        res_rgb = cv2.merge([mask, mask, mask])
        result = np.dstack([res_rgb, image[:,:,3]])
        return result

class GrainNode(EffectNode):
    """底片顆粒：增加隨機雜訊"""
    def __init__(self):
        super().__init__()
        self.name = "底片顆粒 (Grain)"
        self.params["intensity"] = 30
        self.params["color_noise"] = 0 # 0 = 單色雜訊, 1 = 彩色雜訊
        self.params["seed"] = 0
        self.param_meta["intensity"] = {"min": 0, "max": 100}
        self.param_meta["seed"] = {"min": 0, "max": 99999}
        self._noise_cache_key = None
        self._noise_cache = None

    def apply_effect(self, image):
        intensity = self.params["intensity"] / 100.0
        if intensity <= 0:
            return image

        h, w = image.shape[:2]
        seed = int(self.params.get("seed", 0))
        color_noise = 1 if self.params.get("color_noise", 0) > 0.5 else 0
        key = (h, w, int(intensity * 10000), color_noise, seed)
        if self._noise_cache_key == key and self._noise_cache is not None:
            noise = self._noise_cache
        else:
            rng = np.random.default_rng(seed)
            if color_noise:
                noise = rng.normal(0, 255 * intensity, (h, w, 3)).astype(np.float32)
            else:
                noise_gray = rng.normal(0, 255 * intensity, (h, w)).astype(np.float32)
                noise = np.dstack([noise_gray, noise_gray, noise_gray])
            self._noise_cache_key = key
            self._noise_cache = noise

        res_rgb = image[:,:,:3].astype(np.float32) + noise
        result = np.dstack([np.clip(res_rgb, 0, 255).astype(np.uint8), image[:,:,3]])
        return result

class BloomNode(EffectNode):
    """輝光節點 (Bloom / Glow)：提取圖像中的亮部進行高斯模糊並與原圖加算混合。"""
    def __init__(self):
        super().__init__()
        self.name = "輝光 (Bloom)"
        self.params["threshold"] = 200
        self.params["blur_size"] = 21
        self.params["intensity"] = 50
        self.param_meta["threshold"] = {"min": 0, "max": 255}
        self.param_meta["blur_size"] = {"min": 1, "max": 101}
        self.param_meta["intensity"] = {"min": 0, "max": 100}

    def apply_effect(self, image):
        # 1. 轉灰階以計算亮度
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        
        # 2. 提取高於閾值的亮部
        thresh_val = int(self.params["threshold"])
        _, mask = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
        
        # 3. 將遮罩轉回 3 通道，並只保留亮部色彩
        mask_3 = cv2.merge([mask, mask, mask])
        bright = cv2.bitwise_and(image[:,:,:3], mask_3)
        
        # 4. 對亮部進行高斯模糊
        k = int(self.params["blur_size"])
        if k % 2 == 0: k += 1
        if k < 1: k = 1
        blurred = cv2.GaussianBlur(bright, (k, k), 0)
        
        # 5. 依據強度疊加回原圖 (加算混合)
        factor = float(self.params["intensity"]) / 100.0
        glow = blurred.astype(np.float32) * factor
        
        res_rgb = image[:,:,:3].astype(np.float32) + glow
        result = np.dstack([np.clip(res_rgb, 0, 255).astype(np.uint8), image[:,:,3]])
        return result

class ChannelSplitNode(Node):
    """通道分離節點：將彩色圖像的 R、G、B、A 分離成 4 個獨立的遮罩輸出。"""
    def __init__(self):
        super().__init__()
        self.name = "通道分離 (Channel Split)"
        self.add_input("Image In")
        self.add_output("R Out", pin_type="mask")
        self.add_output("G Out", pin_type="mask")
        self.add_output("B Out", pin_type="mask")
        self.add_output("A Out", pin_type="mask")

    def process(self, **kwargs):
        img = kwargs.get("Image In")
        if img is None:
            return {"R Out": None, "G Out": None, "B Out": None, "A Out": None}
            
        b, g, r, a = cv2.split(img)
        return {"R Out": r, "G Out": g, "B Out": b, "A Out": a}

class ChannelMergeNode(Node):
    """通道合併節點：接收 R、G、B、A 獨立遮罩輸入，重新合併成彩色圖像。"""
    def __init__(self):
        super().__init__()
        self.name = "通道合併 (Channel Merge)"
        self.add_input("R In", pin_type="mask")
        self.add_input("G In", pin_type="mask")
        self.add_input("B In", pin_type="mask")
        self.add_input("A In", pin_type="mask")
        self.add_output("Image Out")

    def process(self, **kwargs):
        r = kwargs.get("R In")
        g = kwargs.get("G In")
        b = kwargs.get("B In")
        a = kwargs.get("A In")
        
        # 尋找參考尺寸
        ref_shape = None
        for m in (r, g, b, a):
            if m is not None:
                ref_shape = m.shape[:2]
                break
                
        if ref_shape is None:
            return {"Image Out": None}
            
        h, w = ref_shape
        
        # 處理缺失通道：RGB 預設 0，A 預設 255
        def prepare_channel(ch, default_val):
            if ch is None:
                return np.ones((h, w), dtype=np.uint8) * default_val
            if ch.shape[:2] != (h, w):
                return cv2.resize(ch, (w, h))
            return ch

        r_ch = prepare_channel(r, 0)
        g_ch = prepare_channel(g, 0)
        b_ch = prepare_channel(b, 0)
        a_ch = prepare_channel(a, 255)
        
        merged = cv2.merge([b_ch, g_ch, r_ch, a_ch])
        return {"Image Out": merged}


class ApplyMaskNode(Node):
    """套用遮罩節點：將選取的遮罩 (Mask) 作為透明度 (Alpha) 套用到彩色圖像上。"""
    def __init__(self):
        super().__init__()
        self.name = "套用遮罩 (Apply Mask)"
        self.add_input("Image In")
        self.add_input("Mask In", pin_type="mask")
        self.add_output("Image Out")

    def process(self, **kwargs):
        image = kwargs.get("Image In")
        mask = kwargs.get("Mask In")
        
        if image is None:
            return {"Image Out": None}
        if mask is None:
            # 若無輸入遮罩，預設回傳原圖
            return {"Image Out": image}
            
        # 確保尺寸一致
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(mask, (image.shape[1], image.shape[0]))
            
        result = image.copy()
        # 乘算原圖透明度與遮罩，使原圖本就透明的像素維持透明
        orig_alpha = image[:,:,3].astype(np.float32) / 255.0
        mask_alpha = mask.astype(np.float32) / 255.0
        new_alpha = np.clip(orig_alpha * mask_alpha * 255.0, 0, 255).astype(np.uint8)
        
        result[:,:,3] = new_alpha
        return {"Image Out": result}


