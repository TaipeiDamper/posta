# Posta - 半自動電子海報生成器

基於節點 (Node-Based) 架構的圖像處理工具，使用 PySide6 + OpenCV 打造。透過直覺的視覺化連線介面，將多種影像處理效果串接成可重複使用的自動化流程。

## 功能特色

### 🎨 節點式影像處理
- **視覺化資料流**：拖曳連線即可建構複雜的影像處理管線
- **即時預覽**：參數調整後立即看到結果
- **Dirty Flag 增量運算**：只重算真正有變動的節點，大幅提升效能

### 🧩 內建節點一覽

| 類別 | 節點 | 功能描述 |
|------|------|----------|
| **輸入/輸出** | 原圖輸入 (Input) | 載入圖片或從剪貼簿貼上 |
| | 最終輸出 (Output) | 將結果顯示在預覽區 |
| **邊緣與輪廓** | 邊緣擷取 (Edge Detect) | Canny 邊緣偵測，輸出邊緣遮罩與上色結果 |
| | 索伯邊緣 (Sobel) | 保留梯度的邊緣提取，具有厚度感 |
| | 輪廓提取 (Contour) | 二值化後提取閉合輪廓，適合描邊效果 |
| | 鉛筆素描 (Sketch) | 快速產生手繪感線條 |
| **亮度與色調** | 明度選取 (Luma Key) | 以明度百分比區間生成遮罩，支援邊緣軟化 |
| | 中間調選取 (Midtone) | 專門選取指定明度百分比區間，預設範圍為 30%~70% 且可自由調整，支援邊緣軟化 |

| | 亮度對比 (Brightness) | 調整亮度與對比度 |
| | 負片 (Invert) | 反轉 RGB 色彩 |
| | 染色 (Tint) | 保留亮度細節，改變整體色調 |
| | 替換顏色 (Color Replace) | 選取目標顏色並替換，可調容差 |
| | 色階分離 (Posterize) | 減少色彩階層，創造插畫風格 |
| | 漸層對映 (Grad Map) | 根據圖片明度對映到兩種顏色 |
| **質感與雜訊** | 高斯模糊 (Blur) | 可調核心大小的高斯模糊 |
| | 半調子網點 (Halftone) | 模仿印刷網點效果，根據明度決定圓點大小 |
| | 底片顆粒 (Grain) | 增加隨機雜訊，具備彩色/單色切換 |
| **合成/混合** | 圖層合併 (Merge) | Alpha 透明度疊合兩張圖片 |
| | 進階混合 (Blend) | Multiply / Screen / Overlay / Add 混合模式 |
| **變形與文字** | 文字 (Text) | 在圖片上渲染文字，可調位置/大小/顏色 |
| | 智慧裁切 (Crop) | 自動偵測主體並裁切為指定比例 |
| **工具** | 時間切換 (Switcher) | 自動循環切換最多 3 組輸入 |
| | 轉向 (Reroute) | 純轉發節點，整理連線走位 |
| | 數值 (Value) | 輸出全域數值，可同時接多個節點 |
| | 顏色 (ColorOut) | 輸出全域顏色值 |

### 🔌 連線點顏色辨識

| 顏色 | 資料類型 | 說明 |
|------|----------|------|
| 🔵 青藍 | Image | 圖片資料流 |
| 🟡 黃色 | Mask | 遮罩資料流 |
| 🟣 紫色 | Value | 數值資料流 |
| 🟠 橘色 | Color | 顏色資料流 |

### 🖥️ 介面功能

- **群組外框 (Backdrop)**：在畫布空白處右鍵 → 新增群組外框，可拖曳、縮放、變色、命名
- **便利貼 (Sticky Note)**：在畫布空白處右鍵 → 新增便利貼，記錄備忘
- **節點跳過 (Bypass)**：右鍵節點 → 跳過節點，暗化顯示 + 虛線邊框
- **連線 Bypass**：右鍵連線 → 啟用/停用，灰色虛線表示
- **畫布縮放**：滾輪縮放 (0.1x ~ 5.0x)
- **圖片拖曳匯入**：可直接將 PNG / JPG / BMP 等圖片拖入工作區，效果與貼上圖片一致
- **可調介面佈局**：所有面板均可自由拖曳分割線調整大小

## 快捷鍵

| 快捷鍵 | 功能 |
|--------|------|
| `Ctrl+V` | 從剪貼簿貼上圖片 |
| `Ctrl+Z` | 復原上一步 (最多 30 步) |
| `Ctrl+Shift+Z` / `Ctrl+Y` | 重做下一步 |
| `Ctrl+S` | 匯出範本 (JSON) |
| `Delete` / `Backspace` | 刪除選中的節點或連線 |
| 滾輪 | 縮放畫布 |

## 選單列

### 檔案
- **匯出範本 (JSON)**：將目前的節點配置存成 `.json` 檔，下次可直接載入套用不同圖片
- **匯入範本 (JSON)**：載入先前儲存的節點配置
- **儲存輸出圖**：將處理結果存為 PNG / JPG / BMP

### 檢視
- **代理預覽 (50%)**：開啟後以半解析度運算，大幅加速預覽。輸出時仍為全解析度。

## 安裝與執行

### 環境需求
- Python 3.9+
- PySide6
- OpenCV (opencv-python)
- NumPy

### 安裝步驟

```bash
pip install PySide6 opencv-python numpy
```

### 啟動

```bash
python main.py
```

## 專案結構

```
posta/
├── main.py              # MainWindow 與應用程式編排
├── core_engine.py       # 核心引擎：Graph / Node / Pin / Edge / Dirty Flag
├── core_nodes.py        # 節點運算實作
├── node_registry.py     # 節點註冊表與 palette 分類
├── node_factory.py      # 節點建立與 NodeItem 事件綁定
├── input_session.py     # 輸入圖片狀態（全域輸入、多張貼上/拖曳）
├── image_importer.py    # 剪貼簿、檔案對話框、拖曳圖片匯入
├── image_io.py          # OpenCV / NumPy / Qt 影像轉換工具
├── graph_controller.py  # GraphScene 的鎖與節點移除協調
├── graph_evaluator.py   # 同步/背景圖評估
├── graph_state.py       # JSON 狀態序列化
├── graph_restore.py     # JSON 狀態還原到 graph/scene
├── history.py           # Undo / Redo 歷史堆疊
├── ui_graphics.py       # 畫布圖元：Pin / Node / Connection / Backdrop / StickyNote
├── ui_components.py     # 側欄、預覽、屬性面板、搜尋選單、CanvasView
└── test_refactor.py     # 輕量回歸測試
```

## 架構概覽

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  ImageInput  │────▶│  EffectNode  │────▶│  OutputNode  │
│  (原圖輸入)  │     │  (任意效果)  │     │  (最終輸出)  │
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                     ┌─────▼─────┐
                     │ Mask Pin  │ (選填遮罩輸入)
                     └───────────┘
```

- **Graph**：管理所有節點，負責拓撲排序 + 增量運算
- **Node**：每個節點擁有 Input/Output Pin，透過 Edge 連接
- **Dirty Flag**：參數或連線變動時自動標記，evaluate 時跳過未變動節點
- **EffectNode**：效果節點基類，自動處理 Mask 混合 + blend_ratio 控制

## 授權

MIT License
