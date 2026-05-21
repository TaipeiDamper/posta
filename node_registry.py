"""節點註冊表：NODE_MAP、palette 分類、名稱解析。"""

from PySide6.QtGui import QColor

from core_nodes import (
    ImageInputNode,
    ColorReplaceNode,
    EdgeDetectNode,
    BlurNode,
    MergeNode,
    OutputNode,
    TintNode,
    LuminanceNode,
    BlendNode,
    SwitcherNode,
    BrightnessContrastNode,
    InvertNode,
    TextNode,
    SmartCropNode,
    ValueNode,
    ColorOutputNode,
    RerouteNode,
    SobelEdgeNode,
    ThresholdContourNode,
    PencilSketchNode,
    MidtoneKeyNode,
    PosterizeNode,
    GradientMapNode,
    HalftoneNode,
    GrainNode,
)

NODE_MAP = {
    "Input": ("原圖輸入", ImageInputNode),
    "Output": ("最終輸出", OutputNode),
    "Tint": ("染色", TintNode),
    "Color Replace": ("替換顏色", ColorReplaceNode),
    "Luma": ("明度選取", LuminanceNode),
    "Midtone": ("中間調選取", MidtoneKeyNode),
    "Edge Detect": ("邊緣擷取", EdgeDetectNode),
    "Sobel": ("索伯邊緣", SobelEdgeNode),
    "Contour": ("輪廓提取", ThresholdContourNode),
    "Sketch": ("鉛筆素描", PencilSketchNode),
    "Brightness": ("亮度對比", BrightnessContrastNode),
    "Invert": ("負片", InvertNode),
    "Posterize": ("色階分離", PosterizeNode),
    "Grad Map": ("漸層對映", GradientMapNode),
    "Blur": ("高斯模糊", BlurNode),
    "Halftone": ("半調子網點", HalftoneNode),
    "Grain": ("底片顆粒", GrainNode),
    "Merge": ("圖層合併", MergeNode),
    "Blend": ("進階混合", BlendNode),
    "Switcher": ("時間切換", SwitcherNode),
    "Text": ("文字", TextNode),
    "Crop": ("智慧裁切", SmartCropNode),
    "Value": ("數值", ValueNode),
    "ColorOut": ("顏色輸出", ColorOutputNode),
    "Reroute": ("轉向", RerouteNode),
}

DISPLAY_NAME_TO_KEY = {display: key for key, (display, _) in NODE_MAP.items()}

CLASS_BY_TYPENAME = {}
for _k, (_d, _cls) in NODE_MAP.items():
    CLASS_BY_TYPENAME[_cls.__name__] = _cls

# 左側 palette 分類（header, 項目色, 顯示名稱列表）
PALETTE_CATEGORIES = [
    ("--- 輸入/輸出 ---", QColor(150, 200, 255), ["輸入 (Input)", "輸出 (Output)"]),
    ("--- 邊緣與輪廓 ---", QColor(150, 255, 150), ["邊緣擷取 (Edge Detect)", "索伯邊緣 (Sobel)", "輪廓提取 (Contour)", "鉛筆素描 (Sketch)"]),
    ("--- 亮度與色調 ---", QColor(255, 180, 100), ["明度選取 (Luma)", "中間調選取 (Midtone)", "亮度對比 (Brightness)", "負片 (Invert)", "反向選取 (Mask Invert)", "染色 (Tint)", "替換顏色 (Color Replace)", "色階分離 (Posterize)", "漸層對映 (Grad Map)"]),
    ("--- 質感與雜訊 ---", QColor(150, 255, 200), ["高斯模糊 (Blur)", "半調子網點 (Halftone)", "底片顆粒 (Grain)"]),
    ("--- 變形與文字 ---", QColor(200, 150, 255), ["文字 (Text)", "智慧裁切 (Crop)"]),
    ("--- 合成與工具 ---", QColor(100, 200, 255), ["圖層合併 (Merge)", "進階混合 (Blend)", "時間切換 (Switcher)", "數值 (Value)", "顏色 (ColorOut)", "轉向 (Reroute)"]),
]


def resolve_registry_key(name):
    """由 registry key、顯示名或 palette 字串解析 NODE_MAP 鍵。"""
    if not name or (isinstance(name, str) and name.startswith("---")):
        return None
    if isinstance(name, str) and name in NODE_MAP:
        return name
    if isinstance(name, str):
        key = DISPLAY_NAME_TO_KEY.get(name)
        if key:
            return key
        for nk in NODE_MAP:
            if nk in name:
                return nk
    return None
