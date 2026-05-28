# Posta UI/UX 優化與設計指南

本文件整理節點式影像工具常見的 UX 方向，並**對照目前工作區程式庫**標註實作程度，方便後續迭代時以「單一真相」對齊規格與落差。

> **實作紀錄**：與程式合併後的對照請見 [§0 實作紀錄（供 Review）](#0-實作紀錄供-review)；細節亦與 [code_structure.md §0](code_structure.md) 摘要表一致。

---

## 目錄

0. [實作紀錄（供 Review）](#0-實作紀錄供-review)
1. [快速搜尋與新增節點](#1-快速搜尋與新增節點-quick-search-menu)
2. [節點內顯微縮圖](#2-節點內顯微縮圖-node-thumbnails)
3. [節點收縮功能](#3-節點收縮功能-collapsible-nodes)
4. [畫布網格與吸附](#4-畫布網格與吸附-grid--snapping)
5. [智慧連線與類型防呆](#5-智慧連線與類型防呆-smart-connections--validation)
6. [節點內嵌常用控件](#6-節點內嵌常用控件-on-node-widgets)
7. [運算狀態視覺化](#7-運算狀態視覺化-status-indicators)
8. [屬性面板的高階應用](#8-屬性面板的高階應用-sidebar-enhancements)

---

## 0. 實作紀錄（供 Review）

以下為**與本 UX 文件直接相關**、已在程式中落地的項目（便於與 `code_structure.md` 交叉 review）。

| 建議項 | 實作摘要 | 主要位置 |
|--------|----------|----------|
| §1 快速搜尋 | `SearchMenu` 清單項目 `Qt.UserRole` 存 registry **key**；`add_node_by_name` 搭配 `DISPLAY_NAME_TO_KEY`，從搜尋選單選取可穩定建節點 | `main.py` |
| §5 智慧連線 | `can_connect_pins()` 與引擎 `INPUT_PIN_ACCEPTS_OUTPUT_TYPES` 一致；拖線綠／紅筆、釋放驗證；**拖線時**輸入 Pin 透明度弱化（相容＝1.0、不相容＝0.3）；**磁吸**至相容輸入 Pin（`SNAP_PIN_DISTANCE`） | `ui_graphics.py`、`core_engine.py` |
| §7 錯誤狀態 | `Graph.evaluate` 每節點 `try/except`，設定 `_status='error'` 與 `_error_message`；`evaluate_graph` 後將訊息寫入 `NodeItem.setToolTip`；`NodeItem.paint` 紅框分支會被使用 | `core_engine.py`、`main.py` |
| §7 Running | 先前在 `evaluate_graph` 內對全節點設 `_status='running'` 的短暫黃框已移除；改由評估過程中的錯誤狀態為主（若需 Running 動畫，可改在非同步 evaluate 時再做） | `main.py`（行為變更，review 時請注意） |
| Redo（與操作流） | `Ctrl+Shift+Z` / `Ctrl+Y`；新操作清空 redo 堆疊 | `main.py` |
| Signal 解耦 | 場景內不再假設 `parent()` 為 `MainWindow` 來呼叫 `evaluate_graph`／`save_state` | `ui_graphics.py`、`main.py` |
| 拖曳圖片匯入 | PNG/JPG/BMP/WebP/TIFF 檔案或 image MIME 拖入工作區時，走與貼上相同的匯入管線並建立/綁定 Input 節點 | `image_importer.py`、`input_session.py`、`ui_components.py` |
| 場景變更解耦 | `GraphSceneController` 顯式提供 graph mutex 與節點移除回呼，圖元不再反查 `main_window` | `graph_controller.py`、`ui_graphics.py` |

**仍未做（本文件原列）**：§6 節點內嵌控件；§8 Accordion；拖線「錯誤震動」動畫；Bypass 節點整體再降透明度（僅維持既有虛線／樣式者可再強化）。

---

**對照摘要（高層）**

| 建議項 | 狀態 | 說明 |
|--------|------|------|
| 1 快速搜尋 | **已實作** | `Space`/`Tab` + `SearchMenu`；registry key 與 `add_node_by_name` 已對齊（見 §0） |
| 2 節點縮圖 | 已實作 | `NodeItem.thumbnail` + `update_thumbnail()` |
| 3 節點收合 | 已實作 | 雙擊切換 `is_collapsed`；收合時隱藏縮圖 |
| 4 網格與吸附 | 已實作 | `GraphScene.drawBackground` 點狀網格；`NodeItem.itemChange` 20px 吸附 |
| 5 智慧連線 | **部分→強化** | 綠／紅筆、釋放拒絕、**Pin 弱化**、**磁吸**、與引擎 `can_connect_pins` 一致；尚無震動動畫 |
| 拖曳圖片匯入 | **已實作** | 工作區與主視窗接收圖片 MIME / 本機影像檔 URL，匯入效果與貼上圖片一致 |
| 6 節點內控件 | 未實作 | 參數仍以左側 `ConfigPanel` 為主 |
| 7 運算狀態 | **部分→強化** | **Error** 已接 `_status` + Tooltip；**Running** 黃框已自同步 evaluate 路徑移除（見 §0） |
| 8 側欄強化 | 部分實作 | 直方圖已有；Accordion 未做 |

---

## 1. 快速搜尋與新增節點 (Quick Search Menu)

**設計痛點**：僅依賴左下角 palette 時，畫布放大後動線過長，打斷心流。

**UX 建議**：

- 在游標附近以 `Space` / `Tab` 彈出輕量搜尋框（與目前 `CanvasView.keyPressEvent` + `SearchMenu` 方向一致）。
- 模糊搜尋、鍵盤選取、`Enter` 在場景座標建立節點。

**與現況對照**

- **已做**：`SearchMenu` 依顯示名稱篩選（子字串、`lower`）；`Enter` / 雙擊清單可接受；建立位置使用游標對應場景座標。
- **已修正（原落差）**：清單項目以 `Qt.UserRole` 保存 **registry key**；`add_node_by_name` 支援 key、精確顯示名（`DISPLAY_NAME_TO_KEY`）、以及 palette 字串 `key in name` 三層解析。
- **可加強**：拼音／編輯距離模糊搜尋；更明確的鍵盤導覽說明（目前依 `QListWidget` 預設行為）。

---

## 2. 節點內顯微縮圖 (Node Thumbnails)

**設計痛點**：中間節點輸出不可見，不利理解管線。

**UX 建議**：節點內 80–100px 預覽；必要時背景更新避免阻塞 UI。

**與現況對照**：**已實作**（約 100px，`evaluate_graph` 後對具 `_cached_outputs['Image Out']` 的節點更新）。尚為同步更新；超大圖若卡頓再考慮背景執行緒或降採樣頻率。

---

## 3. 節點收縮功能 (Collapsible Nodes)

**設計痛點**：複雜圖視覺過載。

**UX 建議**：雙擊標題區收合成細條（保留 Pin）。

**與現況對照**：**已實作**（雙擊整個 `NodeItem` 切換 `is_collapsed`，收合時隱藏縮圖並縮小高度）。若希望「僅標題列觸發」，可再縮小可點擊區域與文字衝突。

---

## 4. 畫布網格與吸附 (Grid & Snapping)

**設計痛點**：手動對齊費時。

**UX 建議**：低對比點狀網格；拖曳釋放對齊網格。

- **已實作**：**向量化優化**（使用 `np.ogrid` 與 `np.where` 進行批量網格運算，效能極佳）。
- **網格與吸附**：背景點距 20px，與節點 `itemChange` 20px 吸附對齊。

---

## 5. 智慧連線與類型防呆 (Smart Connections & Validation)

**設計痛點**：錯誤型別連線導致難以理解的結果。

**UX 建議**：

- 拖線時僅相容輸入 Pin 高亮，其餘變暗。
- 磁吸至相容 Pin。
- 強行連接時紅線 + 微震動（若產品允許「嘗試失敗」動畫）。

**與現況對照**

- **已做**：拖曳中 `ConnectionItem.update_path` 依 `can_connect_pins` 顯示綠／紅筆；釋放於不相容輸入 Pin 時不建立 edge 並移除暫存線。
- **已補**：拖線時 `GraphScene.set_pin_drag_highlight` — 相容輸入 Pin `opacity=1.0`，不相容 `0.3`，輸出 Pin 略暗 `0.45`；相容輸入 Pin **磁吸**（`SNAP_PIN_DISTANCE`）；引擎 `InputPin.connect` 與 UI 共用 `can_connect_pins`（見 `code_structure.md` §5.1）。
- **未做**：錯誤連線「震動」動畫；更誇張的發光高亮（目前以透明度為主）。

---

## 6. 節點內嵌常用控件 (On-Node Widgets)

**設計痛點**：小參數頻繁切換左側面板動線長。

**UX 建議**：例如 `TintNode` 色塊、`ValueNode` 數值框做在節點上。

**與現況對照**：**未實作**；可作為下一階段，並注意與 `QGraphicsView` 內嵌 widget 或純繪圖 hit-test 的取捨。

---

## 7. 運算狀態視覺化 (Status Indicators)

**設計痛點**：長運算與錯誤缺乏回饋。

**UX 建議**：Running／Error／Bypass 等狀態邊框與 Tooltip。

**與現況對照**

- **Running**：先前在 `evaluate_graph` 開頭對所有節點設 `_status='running'` 的黃框，在同步、極短評估下幾乎不可見；**目前已移除該段**，以免誤導。若未來導入非同步長任務，可再於「真正等待結果」期間顯示 Running。
- **Error**：**已實作** — `Graph.evaluate` 每節點 `try/except`，失敗節點 `_status='error'`、`_error_message`；`evaluate_graph` 後對 `NodeItem` `setToolTip`；`NodeItem.paint` 紅框會反映。
- **Bypass**：節點與連線皆有虛線／灰階處理；可再加整體透明度（規格可選）。

---

## 8. 屬性面板的高階應用 (Sidebar Enhancements)

**設計痛點**：參數多時版面擁擠；色彩調整缺乏數據輔助。

**UX 建議**：Accordion 分組；亮度／色彩相關節點顯示直方圖。

**與現況對照**

- **直方圖**：**已實作**（`ConfigPanel` 對 `BrightnessContrastNode`、`LuminanceNode`、`PosterizeNode`、`TintNode`、`MidtoneKeyNode`、`GradientMapNode` 等附加 `hist_label`）。
- **參數範圍**：**部分** — `Node.param_meta` + `ConfigPanel._numeric_range_for_key` 已接上，多數鍵仍可走字串後備規則（見 `code_structure.md` §3.2）。
- **Accordion**：**未實作**；進階參數預設摺疊仍可列為後續工作。

---

## 後續實作檢查清單（已更新）

1. ~~修正快速搜尋與 `add_node_by_name` 的識別規則~~（**已完成**）
2. 若重新導入 **Running** 狀態：建議與 **非同步 evaluate** 一併設計，避免同步路徑無意義閃爍
3. ~~錯誤路徑：統一例外處理 → 節點 `_status` + tooltip~~（**已完成**）
4. ~~連線 UX：與引擎型別相容表對齊後，拖線時全域 Pin 弱化／高亮~~（**已完成**；磁吸已加）
5. **未排**：§6 節點內控件、§8 Accordion、連線錯誤震動、非同步評估
