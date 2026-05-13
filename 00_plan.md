# 半自動節點式濾鏡系統 (Node-based Filter System) 開發計畫

根據您的需求，我們需要將現有的「線性處理管線 (Linear Pipeline)」升級為**「有向無環圖 (DAG, Directed Acyclic Graph)」架構**。這將允許您像拉線遊戲一樣，自由組合串聯 (Series) 與並聯 (Parallel) 的影像處理邏輯。

以下是針對您提供的架構草圖與需求所設計的系統開發計畫：

---

## 1. 系統架構概念 (Architecture)

### 核心運算元件
1. **Node (節點)**: 每個圖像操作（如模糊、邊緣偵測、量化）都是一個獨立的節點。
   - **Input Pins (輸入埠)**: 接收來自上游節點的影像資料（支援多輸入，如 Merge 節點）。
   - **Output Pins (輸出埠)**: 將處理完的影像資料傳遞給下游。
   - **Parameters (參數)**: 該節點專屬的控制滑桿或選項。
2. **Connection (連線)**: 定義資料的流向。允許「一對多」（原始影像同時給 A 和 B 處理，即**並聯**）與「多對一」（A 和 B 的結果合併，進入 C 處理）。
3. **Graph Engine (執行引擎)**: 
   - 負責解析畫布上的連線。
   - 透過**拓撲排序 (Topological Sort)** 計算出正確的執行順序（例如：必須先等 A 和 B 算完，才能算 C）。
   - 調度記憶體，確保並聯時原始影像不被互相污染。

---

## 2. 節點類型設計 (Node Types)

為了達成您的第三張範例圖，我們需要以下幾種基礎節點：

*   **InputNode (輸入節點)**: 整個圖的源頭，負責輸出您匯入/拖曳的原始基底圖片。
*   **FilterNode (濾鏡節點)**: 繼承自您現有的演算法：
    *   `BlurNode` (高斯模糊/保邊濾鏡)
    *   `EdgeNode` (邊緣偵測，擷取線條)
    *   `QuantizeNode` (色彩量化/階調壓縮)
    *   `DitherNode` (抖動處理)
*   **MergeNode (合併節點)**: **這是達成並聯後串聯的關鍵**。它擁有多個輸入埠，可將兩張圖片結合。包含不同模式：
    *   *Alpha 混合* (透明度疊加)
    *   *遮罩疊加* (用 A 的邊緣作為 Mask，套用在 B 上)
*   **OutputNode (輸出節點)**: 整個圖的終點，接收最終結果並顯示在右上角的成品區塊。

---

## 3. UI / UX 介面設計 (基於 PySide6)

我們將使用 PySide6 強大的 `QGraphicsScene` 與 `QGraphicsView` 來打造這個可互動的節點編輯器。

### 版面配置 (Layout)
1. **左側面板**:
   - **頂部 [原圖區]**: `QLabel` 顯示原始圖片，支援拖曳檔案 (Drag & Drop) 與快捷鍵貼上 (Ctrl+V)。
   - **底部 [可被拖曳的元件]**: 一個工具箱 (Node Palette)，包含所有可用的 Filter 與 Merge 節點。使用者將它們拖曳到下方畫布中。
2. **右上區塊 [最終成品圖]**:
   - 即時顯示 OutputNode 結果的大型視窗。
3. **下方區塊 [模組化流程畫布]**:
   - 無限延伸的 `QGraphicsScene` 畫布。
   - **節點外觀**: 圓角矩形，標題帶有輸入/輸出小圓點 (Pins)，並內建簡易的參數調整器。
   - **拉線互動**: 滑鼠點擊輸出的圓點拖曳至輸入圓點，會繪製出**貝茲曲線 (Bezier Curve)** 建立連線。

---

## 4. 開發實作階段 (Phases)

為了確保穩定開發，我們將計畫分為四個階段：

### Phase 1: 核心資料結構與引擎 (Backend DAG Engine)
*   建立基礎 `Node`、`Pin`、`Connection` 類別。
*   實作 `GraphExecutor`：給定一組 Node 和 Connection，能正確找出運算順序。
*   確保節點的 `process(inputs)` 是**純函數 (Pure Function)**：不修改傳入的原始陣列，而是回傳新陣列，這是並聯處理時資料不互相干擾的基礎。

### Phase 2: 演算法模組化 (Node Wrappers)
*   將 `valuelens.core.quantize` 中的演算法剝離出來。
*   把原本寫在 `FilterContext` 的邏輯，分別包裝成 `BlurNode`、`EdgeNode`、`QuantizeNode`。
*   新增 `MergeNode` 實作不同圖片合成的邏輯（如 `cv2.addWeighted`）。

### Phase 3: 視覺化節點編輯器 (Node UI)
*   開發 `NodeGraphicsItem` (自訂畫布元件)。
*   開發 `ConnectionGraphicsItem` (繪製節點間的連線)。
*   實作畫布上的拖曳、選取、刪除節點與連線邏輯。

### Phase 4: 系統整合與非同步計算
*   串接 UI 與 Backend Engine。
*   實作**即時響應系統**：當使用者拉了一條新線，或拖動了某個節點的參數滑桿，將觸發 Graph Engine 在背景執行緒 (`QThread`) 重新計算，並即時更新「最終成品圖」。

---

## 5. 與現有架構的共存策略

目前您程式中的 `FilterContext` 和 `ImageProcessWorker` 是寫死的線性順序。
在過渡期間：
1. 原本的 ValueLens 覆蓋視窗 (Overlay) 繼續使用線性流程，確保現有功能不受影響。
2. 開發新的 `NodeEditorWindow` 作為獨立的工作區。
3. 等節點系統完全穩定且效能達標後，未來的線性流程也可以被視為「一組預先連好的固定節點」，從底層統一架構。
