# Posta 系統架構與 UI/UX 設計指南

本文件為 Posta 專案的長期開發與設計指引，整併了系統架構設計與 UI/UX 實作規範，提供協作者在擴充節點、修改介面或優化效能時的單一參考基準。

---

## 1. 整體架構總覽

Posta 採用模組化架構，將 UI 呈現、節點運算與資料流引擎進行了解耦。主要模組關係如下：

```
main.py                    → 應用程式進入點與 MainWindow 佈局編排
  ├── core_engine.py        → DAG（有向無環圖）核心引擎（Graph / Node / Pin / Edge / Dirty Flag）
  ├── core_nodes.py         → 具體節點的圖像運算定義
  ├── node_registry.py      → 節點註冊表與調色盤分類
  ├── node_factory.py       → 節點實例建立與事件綁定
  ├── input_session.py      → 全域輸入圖片狀態管理
  ├── image_importer.py     │ 剪貼簿、拖曳、檔案對話框的匯入管線
  ├── image_io.py          │ OpenCV / NumPy / Qt 影像格式轉換工具
  ├── graph_controller.py   → GraphScene 的執行緒鎖與節點移除協調器
  ├── graph_state.py       │ 節點圖狀態序列化 (JSON 匯出)
  ├── graph_restore.py     │ 狀態還原 (JSON 匯入)
  ├── history.py           │ Undo / Redo 歷史變更堆疊
  ├── ui_graphics.py       → 畫布圖元繪製（NodeItem / PinItem / ConnectionItem / Backdrop / StickyNote）
  └── ui_components.py     → 側邊屬性面板、直方圖、預覽視窗、搜尋選單、CanvasView
```

### 核心運作機制
1. **DAG 引擎**：`Graph` 管理所有節點與連線，藉由拓撲排序 (Topological Sort) 計算出正確的運算順序。
2. **增量運算 (Dirty Flag)**：當參數變動或連線更改時，僅將受影響的下游節點標記為 Dirty，在 `evaluate()` 時跳過未變動的節點快取，以大幅提升效能。
3. **事件解耦**：畫布圖元與場景不直接反查 `MainWindow`，而是透過 Qt Signals（如 `graph_structure_changed`）或中介的 `GraphSceneController` 協調狀態變更。

---

## 2. 節點開發與註冊規範

### 2.1 新增節點步驟
開發新節點時，請遵循以下步驟以確保模組獨立性：
1. **定義運算邏輯**（於 `core_nodes.py`）：
   * 一般濾鏡（單輸入、單輸出圖像處理）繼承 `EffectNode`。它會自動處理 `blend_ratio`（混合比例）與遮罩輸入。
   * 特殊節點（多輸入/輸出、或非圖像資料型別）繼承 `Node`，並自行實作 `process()` 方法。
2. **聲明元資料 (Metadata)**：
   * 在節點類別中定義 `param_meta`，指定參數的範圍（如 `min`, `max`）或特殊編輯器類型，避免依賴 `ConfigPanel` 的字串條件判定。
3. **註冊至系統**（於 `node_registry.py`）：
   * 在 `NODE_MAP` 中加入類別註冊。
   * 在 `PALETTE_CATEGORIES` 中加入對應的分類與顯示名稱。

### 2.2 未來改進方向
* **裝飾器式節點註冊**：導入類別裝飾器自動收集節點元資料，消除 `NODE_MAP` 與 `PALETTE_CATEGORIES` 的雙重手動維護成本。
* **參數策略模式 (Strategy Pattern)**：讓 `ConfigPanel` 完全依賴節點的 `param_meta` 產生對應的 UI 控件，移除剩餘的硬編碼字串分支。

---

## 3. UI/UX 設計指引

為了提供流暢且專業的節點編輯體驗，UI/UX 實作需符合以下設計準則：

### 3.1 畫布與視覺反饋
* **網格吸附 (Snapping)**：畫布背景應維持點狀網格（預設間距 20px），節點拖曳釋放時自動吸附至最近的網格點，以保持排版整齊。
* **縮圖預覽 (Thumbnails)**：節點內部應保留 80-100px 的顯微縮圖，在運算完成後即時更新，方便使用者理解中間過程。當節點處於收合狀態 (`is_collapsed`) 時，應隱藏縮圖以節省空間。
* **節點收合 (Collapsible)**：支援雙擊節點標題收合為細條狀，僅保留 Pins 以簡化複雜圖表的視覺負荷。

### 3.2 智慧連線與型別防呆
* **顏色編碼**：Pins 與連線必須依資料類型嚴格區分顏色：
  * 青藍 (Blue)：`Image` 圖像流
  * 黃色 (Yellow)：`Mask` 遮罩流
  * 紫色 (Purple)：`Value` 數值流
  * 橘色 (Orange)：`Color` 顏色流
* **動態高亮與弱化**：在拖曳連線時，呼叫 `can_connect_pins()` 檢查相容性。相容的輸入 Pin 維持正常亮度，不相容的輸入 Pin 降低透明度至 `0.3`，以引導正確連線。
* **磁吸功能 (Pin Snapping)**：拖曳中的連線末端與相容 Pin 距離小於磁吸閾值時，自動吸附至該 Pin。
* **非相容拒絕**：釋放連線時若型別不符，必須拒絕建立連線並移除暫存線段。

### 3.3 運算狀態視覺化
* **Error 狀態**：當節點內部運算拋出例外時，`Graph.evaluate` 應捕獲錯誤，將狀態標記為 `error`，並在畫布上將該節點外框標示為紅色，同時將錯誤訊息寫入 `ToolTip` 以供滑鼠懸停查閱。
* **Bypass 狀態**：被跳過的節點與連線應以虛線及半透明/灰階樣式繪製，清晰表達資料流已繞過該節點。

---

## 4. 效能優化與進階架構

### 4.1 影像運算向量化
* 新增或修改圖像處理演算法時，應優先使用 NumPy 的向量化運算（如 `np.ogrid` 與 `np.where`），避免在 Python 層級使用雙重迴圈處理像素，以確保即時預覽的流暢度。

### 4.2 暫存與快取機制
* 對於高成本的隨機生成運算（如底片顆粒 `GrainNode`），應根據輸入參數（如尺寸、強度、種子值）快取產生的雜訊圖，避免重複計算。

### 4.3 未來重構與非同步評估
* **非同步評估引擎**：目前圖評估仍在 UI 主執行緒執行。未來規劃導入 `QThread` 或 `QRunnable` 進行背景運算，並在計算完成後將影像傳回主執行緒更新，避免大圖運算時介面凍結。
