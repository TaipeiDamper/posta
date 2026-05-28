# Posta 節點開發指南

本文件說明如何為 Posta 新增自訂節點。

## 節點類別架構

```
Node (基類)
├── EffectNode (效果節點基類，自帶 Image In / Mask In / Image Out / blend_ratio)
│   ├── ColorReplaceNode
│   ├── EdgeDetectNode
│   ├── SobelEdgeNode
│   ├── ThresholdContourNode
│   ├── PencilSketchNode
│   ├── BlurNode
│   ├── TintNode
│   ├── BrightnessContrastNode
│   ├── InvertNode
│   ├── PosterizeNode
│   ├── GradientMapNode
│   ├── HalftoneNode
│   └── GrainNode
├── MergeNode
├── BlendNode
├── TextNode
├── SmartCropNode
├── LuminanceNode
├── MidtoneKeyNode
├── SwitcherNode
├── ValueNode
├── ColorOutputNode
├── RerouteNode
├── ImageInputNode
└── OutputNode
```

## 新增一個簡單的效果節點

如果你的節點是「輸入一張圖 → 處理 → 輸出一張圖」，繼承 `EffectNode` 最簡單：

```python
# core_nodes.py

class SepiaNode(EffectNode):
    """懷舊色調節點"""
    def __init__(self):
        super().__init__()
        self.name = "懷舊色調 (Sepia)"
        self.params["intensity"] = 80

    def apply_effect(self, image):
        # image 格式固定為 BGRA (4 通道, uint8)
        gray = cv2.cvtColor(image[:,:,:3], cv2.COLOR_BGR2GRAY)
        intensity = self.params["intensity"] / 100.0
        sepia = np.zeros_like(image[:,:,:3], dtype=np.float32)
        sepia[:,:,0] = gray * 0.686 * intensity + gray * (1 - intensity)  # B
        sepia[:,:,1] = gray * 0.769 * intensity + gray * (1 - intensity)  # G
        sepia[:,:,2] = gray * 0.900 * intensity + gray * (1 - intensity)  # R
        result = image.copy()
        result[:,:,:3] = np.clip(sepia, 0, 255).astype(np.uint8)
        return result
```

`EffectNode` 會自動幫你處理：
- `blend_ratio (%)` 滑桿
- `Mask In` 遮罩輸入
- 上述兩者的混合運算

## 新增一個自訂節點（非效果類）

如果你需要自訂輸入/輸出 Pin：

```python
class MyCustomNode(Node):
    def __init__(self):
        super().__init__()
        self.name = "自訂節點"
        self.add_input("Base In")         # pin_type 預設為 "image"
        self.add_input("Mask In", pin_type="mask")
        self.add_output("Image Out")
        self.add_output("Debug Out", pin_type="mask")
        self.params["my_param"] = 50

    def process(self, **kwargs):
        base = kwargs.get("Base In")       # numpy array (BGRA) 或 None
        mask = kwargs.get("Mask In")       # numpy array (單通道) 或 None
        if base is None:
            return {"Image Out": None, "Debug Out": None}
        
        # ... 你的處理邏輯 ...
        
        return {"Image Out": result, "Debug Out": debug_mask}
```

## 註冊節點到介面

在 `node_registry.py` 的 `NODE_MAP` 中加入一行：

```python
NODE_MAP = {
    # ... 現有節點 ...
    "Sepia": ("懷舊色調", SepiaNode),  # 新增這行
}
```

並在同檔的 `PALETTE_CATEGORIES` 中加入對應的選單項目：

```python
PALETTE_CATEGORIES = [
    # ... 現有分類 ...
    ("--- 亮度與色調 ---", QColor(255, 180, 100), [
        # ... 現有節點 ...
        "懷舊色調 (Sepia)",  # 新增這行
    ]),
]
```

記得在 `node_registry.py` 頂部的 import 中加入你的節點類別。節點建立流程由 `node_factory.py` 統一處理，不需要修改 `main.py`。

## Pin 類型

| 類型 | 說明 | 資料格式 |
|------|------|----------|
| `"image"` | 圖片 | numpy array, shape=(H,W,4), dtype=uint8, BGRA |
| `"mask"` | 遮罩 | numpy array, shape=(H,W), dtype=uint8, 0~255 |
| `"value"` | 數值 | int 或 float |
| `"color"` | 顏色 | list [R, G, B], 0~255 |

## 參數類型與 UI 自動生成

`ConfigPanel` 會根據 `self.params` 中的值類型自動生成對應的 UI 控件：

| Python 類型 | UI 控件 | 備註 |
|-------------|---------|------|
| `int` / `float` | Slider + SpinBox | 範圍依 key 名稱自動設定 |
| `list` (3 元素) | 顏色選擇按鈕 | 視為 RGB 值 |
| `str` | QLineEdit 或 QComboBox | key 為 `"mode"` 時用下拉選單 |

### 參數名稱與範圍對映

| 參數名稱含有 | 範圍 |
|-------------|------|
| `%` | 0 ~ 100 |
| `kernel_size` | 1 ~ 101 |
| `tolerance` | 0 ~ 255 |
| `threshold` | 0 ~ 500 |
| 其他 | 0 ~ 100 (預設) |
