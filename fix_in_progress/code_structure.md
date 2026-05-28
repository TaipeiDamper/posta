# Posta 程式碼架構審查報告

> 審查範圍：`main.py` / `core_engine.py` / `core_nodes.py` / `ui_graphics.py`  
> 初稿審查日期：2026-05-14  
> **本文件已依目前工作區程式庫對照修訂**（修訂基準：與 repo 內實際檔案一致）  
> **實作紀錄**：見下方 [§0 實作紀錄（供 Review）](#0-實作紀錄供-review) 與各節內「與現況對照」更新。

---

## 目錄

0. [實作紀錄（供 Review）](#0-實作紀錄供-review)
1. [整體架構總覽](#1-整體架構總覽)
2. [緊急修正 (Bug Fix)](#2-緊急修正)
3. [模組化重構建議](#3-模組化重構建議)
4. [效能優化建議](#4-效能優化建議)
5. [架構設計改善](#5-架構設計改善)
6. [優先順序總表](#6-優先順序總表)

---

## 0. 實作紀錄（供 Review）

以下為依本文件與 `uiux_design.md` 計畫**已落地程式碼**的摘要（便於 PR / self-review 對照）。未列項目多為「尚未做」或僅部分完成。

| 主題 | 檔案 | 做了什麼 |
|------|------|----------|
| 貼圖防呆 | `main.py` | `paste_image`：`isNull()`、寬高、`sizeInBytes()` 檢查、`qimg.copy()` 後 `np.frombuffer(qimg.bits(), …).reshape((h,w,4))` |
| Dirty 下游索引 | `core_engine.py` | `InputPin.connect` 寫入 `output_pin._downstream_edges`；`disconnect_edge` / `disconnect_all` 同步移除；`OutputPin` 預設 `_downstream_edges = []` |
| 搜尋選單 ↔ 建節點 | `main.py` | `SearchMenu` 用 `Qt.UserRole` 存 registry **key**；`DISPLAY_NAME_TO_KEY` + `add_node_by_name` 先 key、再顯示名、再 `key in name`（palette 相容） |
| 類別還原 | `main.py` | `CLASS_BY_TYPENAME` 由 `NODE_MAP` 建表；`restore_graph_state` 不再用 `globals().get` |
| ImageInput 注入 | `core_nodes.py`、`main.py` | `ImageInputNode.set_external_image_source(fn)`；建立／還原時綁定 `lambda: self.global_input_image`，不再覆寫 `process` |
| 節點參數 meta | `core_engine.py`、`core_nodes.py`、`main.py` | `Node.param_meta`；`ConfigPanel._numeric_range_for_key` 優先讀 meta，否則沿用字串規則；多節點已填 `param_meta` |
| Switcher 定時重算 | `core_nodes.py`、`main.py` | `advance_if_due()` 僅在間隔到期時切索引並 `mark_dirty()`；`on_timer_tick` 僅在回傳 True 時 `evaluate_graph()` |
| Halftone 優化 | `core_nodes.py` | **已完成向量化**：使用 `np.ogrid` 建立座標網格並透過 `np.where` 進行批量運算，取代原本的 Python 雙迴圈 |
| Grain 快取 | `core_nodes.py` | `seed` 參數、`np.random.default_rng(seed)`、依 `(h,w,intensity,color_noise,seed)` 快取雜訊陣列 |
| Pin 型別（引擎 + UI） | `core_engine.py`、`ui_graphics.py` | `INPUT_PIN_ACCEPTS_OUTPUT_TYPES` + `can_connect_pins()`；`InputPin.connect` 驗證；拖線／釋放與筆色共用同一套規則 |
| 單節點錯誤 | `core_engine.py`、`main.py` | `Graph.evaluate` 每節點 `try/except`，`_status` / `_error_message`；`evaluate_graph` 後對 `NodeItem` `setToolTip` |
| Redo | `main.py` | `redo_stack`、`redo()`、`save_state` 清空 redo；快捷鍵 `Ctrl+Shift+Z`、`Ctrl+Y` |
| UI 與主視窗解耦 | `ui_graphics.py`、`main.py` | `GraphScene.graph_structure_changed` / `graph_state_changed` Signal；連線／節點／刪除鍵改 `emit`，不再 `scene.parent().evaluate_graph` |
| 啟動時評估 | `main.py` | `setup_default_nodes` 後接 `evaluate_graph()`，與 Signal 連線後再跑，避免初始畫面不同步 |
| 連線 UX（磁吸／Pin 弱化） | `ui_graphics.py` | 拖線時 `set_pin_drag_highlight`；相容輸入 Pin 磁吸（`SNAP_PIN_DISTANCE`）；`mouseRelease` 與 `ConnectionItem.update_path` 與 `can_connect_pins` 一致 |
| 圖片匯入獨立化 | `image_importer.py`、`input_session.py`、`main.py` | 剪貼簿、檔案對話框、拖曳圖片共用 `ImageImportManager`；輸入圖狀態集中於 `InputSession` |
| 節點工廠 | `node_factory.py`、`main.py`、`graph_restore.py` | `add_node_by_name` 委派 `NodeFactory`；新建與還原節點共用 `bind_node_item_events` |
| 場景控制器 | `graph_controller.py`、`ui_graphics.py` | `GraphSceneController` 提供 graph mutex 與節點移除回呼；`ui_graphics.py` 不再反查 `main_window` |
| 序列化純化 | `graph_state.py`、`main.py` | `get_graph_state` 改接收節點位置 dict，不再 import `NodeItem`；移除未使用 `Graph.to_json()` |
| 產物清理 | `.gitignore` | 忽略 `__pycache__/`、`*.pyc`、`run_output.log`，避免測試產物進入版本控制 |

**仍未做（與本文件原建議對照）**：裝飾器式 `NODE_REGISTRY`、全節點 `param_meta` 覆蓋、完整評估結果快照通道、`core_nodes.py` 依節點類型拆包。（Halftone 向量化與主要 `main.py` 拆檔已見 §0，不再列於此。）

---

## 1. 整體架構總覽

```
main.py                    → MainWindow 與應用編排
  ├── core_engine.py        → DAG 圖引擎
  ├── core_nodes.py         → 節點運算定義
  ├── node_registry.py      → 節點註冊與 palette 分類
  ├── node_factory.py       → 節點建立與事件綁定
  ├── input_session.py      → 輸入圖片狀態
  ├── image_importer.py     → 剪貼簿 / 拖曳 / 檔案匯入
  ├── graph_controller.py   → GraphScene 變更協調
  ├── graph_state.py        → 狀態序列化
  ├── graph_restore.py      → 狀態還原
  └── ui_graphics.py        → 場景 / 節點 / 連線繪製
```

**現狀評價**：核心引擎、UI 圖元、節點建立、輸入狀態、匯入流程、歷史與序列化已拆成獨立模組。`main.py` 仍是整合點，但不再直接承擔圖片匯入、節點工廠與場景變更細節。

---

## 2. 緊急修正

### 2.1 `paste_image` 崩潰 — 空剪貼簿圖片

- **檔案**：`main.py` 中 `paste_image`（約 `paste_image` 方法內 `reshape` 前）
- **錯誤**：`ValueError: cannot reshape array of size 1 into shape (0,0,4)` 等（依 Qt / 剪貼簿內容而異）
- **根因**：`QImage.constBits()` 在圖片寬高為 0 或無效影像時，buffer 與 `reshape(h, w, 4)` 假設不一致。
- **與現況對照（已實作）**：`main.py` 的 `paste_image` 已加入 `isNull()`、寬高、`sizeInBytes()` 檢查，並以 `copy()` + `frombuffer(bits())` 再 `reshape`。
- **修正方向（後續可選）**：無效剪貼簿時可改為狀態列或對話框提示，而非靜默 return。

### 2.2 Dirty Flag 下游傳播失效

- **檔案**：`core_engine.py` 中 `Node.mark_dirty()`、`InputPin` / `OutputPin`
- **原問題（歷史）**：`mark_dirty()` 依賴 `out_pin._downstream_edges`，但 `InputPin.connect()` 曾未維護該列表，dirty 無法沿邊傳遞。
- **與現況對照（已實作）**：`InputPin.connect` 會 append 至 `output_pin._downstream_edges`；`disconnect_edge` 從該列表移除；`disconnect_all` 改為逐一 `disconnect_edge`（不再 `edges.clear()` 漏清索引）；`OutputPin.__init__` 初始化 `_downstream_edges = []`。
- **修正方向（後續可選）**：若未來允許「同一對 pin 多條 edge」，需再檢查重複 append／移除語意。

---

## 3. 模組化重構建議

### 3.1 NODE_MAP 手動維護

- **檔案**：`main.py` 中 `NODE_MAP`、頂端 `import`、`node_palette.addItems(...)` 等
- **問題**：新增節點類別時，常需同步修改多處，易漏。
- **與現況對照**：仍以集中式 `NODE_MAP` + 手動 palette 為主；**已補** `DISPLAY_NAME_TO_KEY`、`CLASS_BY_TYPENAME` 由 `NODE_MAP` 自動生成，減少還原／搜尋與類別對照的手動錯誤。**尚未**導入裝飾器註冊表或自動產生 palette 文案。
- **修正方向**：採用註冊表（裝飾器或類別屬性）單一來源產生 palette 與匯入清單（見初稿 3.1 範例，實作時與現有 `NODE_MAP` 鍵值策略對齊）。

### 3.2 ConfigPanel 參數策略模式

- **檔案**：`main.py` 中 `ConfigPanel`
- **問題**：數值範圍仍大量依賴 `if "kernel_size" in key` 等字串分支，脆弱。
- **與現況對照（部分已實作）**：`Node.param_meta` + `ConfigPanel._numeric_range_for_key` 已接上；多數節點仍可依賴舊字串後備規則。尚未全面為每個參數鍵補齊 meta。
- **修正方向**：由節點或基底類別宣告 `min` / `max` / `editor` 型別，`ConfigPanel` 僅讀 meta 產生控件。

### 3.3 main.py 職責拆分 (🚨 最優先項目)

- **問題**：`MainWindow` 仍混合多種職責，程式碼長度已達 850+ 行，嚴重影響可讀性與後續非同步評估的實作。
- **目標**：將業務邏輯、I/O、歷史管理等抽離，使 `main.py` 僅負責 UI 編排。
- **建議拆分**：

```
main.py              → 進入點 + MainWindow（偏 UI 編排）
image_io.py          → 圖片載入 / 貼上 / 儲存
node_factory.py      → 節點建立與 NODE_MAP / 搜尋選單共用邏輯
history_manager.py   → save_state / undo / redo
serializer.py        → export / import / restore_graph_state
```

### 3.4 UI 與引擎的耦合

- **檔案**：`ui_graphics.py`（歷史上曾直接 `scene.parent()`）
- **問題**：圖形項直接假設 parent 為 `MainWindow`，型別與生命週期耦合高。
- **與現況對照（已實作）**：`GraphScene` 已提供 `graph_structure_changed` / `graph_state_changed`，`MainWindow` 連至 `evaluate_graph` / `save_state`；場景內連線與節點操作改為 `emit`。若日後抽出「控制器」可再收斂連線處。
- **修正方向（後續可選）**：若需與外部編輯器或外掛整合，可再抽出 `GraphController` 統一訂閱 Signal。

---

## 4. 效能優化建議

### 4.1 HalftoneNode 網格迴圈

- **檔案**：`core_nodes.py` 中 `HalftoneNode.apply_effect`
- **現況**：**已實作向量化**（使用 `np.ogrid` 與 `np.where`）。
- **優點**：顯著提升大圖運算速度，移除 Python 層級的雙重迴圈開銷。
- **後續**：可進一步考慮多線程支援。

### 4.2 SwitcherNode 定時全量重算

- **檔案**：`main.py` 中 `on_timer_tick`（約 500ms）
- **問題（歷史）**：場上存在任一 `SwitcherNode` 即 `mark_all_dirty()` + `evaluate_graph()`，未切換時也全圖重算。
- **與現況對照（已實作）**：`SwitcherNode.advance_if_due()` + `MainWindow.on_timer_tick` 僅在索引切換時 `mark_dirty` 並 `evaluate_graph()`。
- **修正方向（後續可選）**：若 `interval_s` 改為浮點 UI，需對應 `ConfigPanel` 的 double 控件。

### 4.3 GrainNode 每次重新生成亂數

- **檔案**：`core_nodes.py` 中 `GrainNode`
- **問題（歷史）**：每次 `apply_effect` 呼叫 `np.random.normal`，大圖成本高；且畫面會持續跳動。
- **與現況對照（已實作）**：`seed` 參數、`default_rng(seed)`、依 `(h, w, intensity, color_noise, seed)` 快取雜訊陣列。
- **修正方向（後續可選）**：大圖仍可能耗記憶體，可改為 tile 快取或降解析度雜訊再上採樣。

### 4.4 非同步運算（進階）

- **問題**：圖評估仍在 UI 執行緒。
- **修正方向**：`QThread` / `QRunnable` + 結果回傳主執行緒更新（需注意執行緒安全與取消）。

---

## 5. 架構設計改善

### 5.1 Pin 類型安全連線驗證

- **檔案**：`core_engine.py` 中 `InputPin.connect`；`ui_graphics.py` 中拖線釋放判斷
- **問題**：模型層 `connect` 未驗證 `pin_type`；UI 層已拒絕不相容釋放，但繞過 UI 或未來 API 重複連線時仍可能不一致。
- **與現況對照（已實作）**：`INPUT_PIN_ACCEPTS_OUTPUT_TYPES`、`can_connect_pins()`；`InputPin.connect` 開頭驗證；`ui_graphics` 拖線／釋放／筆色與磁吸皆呼叫同一 helper。
- **修正方向（後續可選）**：若產品要允許「image 輸出接 image 輸入」以外的更寬鬆規則，僅需改表與文件敘述一致。

### 5.2 Undo/Redo 完整支援

- **檔案**：`main.py` 歷史相關方法
- **問題**：僅單向 `history` + `undo`，無 redo。
- **與現況對照（已實作）**：`redo_stack`、`redo()`、`save_state` 時清空 redo；快捷鍵 `Ctrl+Shift+Z` / `Ctrl+Y`。
- **修正方向（後續可選）**：歷史深度上限目前仍主要在 `save_state` 修剪，可依需求在 `redo` 路徑一併限制。

### 5.3 ImageInputNode 的 Lambda 覆寫

- **檔案**：`main.py` 中 `add_node_by_name`、`restore_graph_state`
- **問題**：以 `lambda` 覆寫 `process` 注入全域圖，還原與序列化路徑需重複相同邏輯。
- **與現況對照（已實作）**：`set_external_image_source`；`add_node_by_name` / `restore_graph_state` 已改用，不再 `node.process = lambda …`。

### 5.4 `globals()` 類別查找

- **檔案**：`main.py` 中 `restore_graph_state`
- **問題**：`cls = globals().get(nd["type"])` 依賴模組全域命名空間。
- **與現況對照（已實作）**：`CLASS_BY_TYPENAME`（由 `NODE_MAP` 內所有類別 `__name__` 建表）。

---

## 6. 優先順序總表

| 優先級 | 項目 | 類型 | 影響範圍 | 難度 | 實作狀態 |
|:---:|------|------|----------|:---:|:---:|
| P0 | 2.1 paste_image 崩潰 | Bug | 貼上無效／異常剪貼簿內容 | ⭐ | 已處理 |
| P0 | 2.2 Dirty 下游傳播 | Bug | 快取與拓撲可能不一致 | ⭐⭐ | 已處理 |
| P1 | 4.2 Switcher 全量重算 | 效能 | 有 Switcher 時持續重算 | ⭐ | 已處理（條件 dirty） |
| P0 | 3.3 main 拆分 | 模組化 | 可維護性 / 開發基準 | ⭐⭐⭐ | **即將執行** |
| P1 | 4.4 非同步運算 | 效能 | UI 流暢度 | ⭐⭐⭐ | 未做 |
| P2 | 3.1 節點註冊表 | 模組化 | 新增節點維護成本 | ⭐⭐ | 未做（僅衍生表） |
| P2 | 3.2 ConfigPanel 元資料 | 模組化 | 參數 UI 可維護性 | ⭐⭐ | 部分（meta + 後備） |
| P3 | 4.1 Halftone 向量化 | 效能 | 大圖運算速度 | ⭐⭐ | **已完成** |

**建議執行順序**：
1. **[當前首要]** 執行 **3.3 main.py 職責拆分**，建立乾淨的架構底座。
2. 基於拆分後的架構，導入 **4.4 非同步 evaluate**。
3. 補齊 **3.1 NODE_REGISTRY** 與其餘 P2 項目。
