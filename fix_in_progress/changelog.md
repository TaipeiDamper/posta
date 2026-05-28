# Posta 大檢修修改紀錄

日期：2026-05-28

## 整體影響總結

本次大檢修將 `main.py` 中的節點建立、輸入圖片狀態、匯入流程與場景變更協調拆成獨立模組，降低主視窗與圖元層的雙向耦合。模板 JSON 格式與既有快捷鍵維持相容。

## 修改項目

### UI 圖元與 MainWindow 解耦

- 檔案：`graph_controller.py`、`ui_graphics.py`、`main.py`
- 改動內容：新增 `GraphSceneController`，由 `GraphScene` 顯式持有 graph mutex 與節點移除回呼。
- 原因：避免 `ConnectionItem` / `NodeItem` 透過 `scene.views()[0].main_window` 反查主視窗。
- 風險/相容性：圖元刪除與連線建立仍會鎖住同一把 graph mutex；外部若直接建立 `GraphScene` 但未傳 controller，會退回無鎖模式。
- 驗證結果：`py_compile` 與 `test_refactor.py` 通過。

### 節點工廠抽離

- 檔案：`node_factory.py`、`main.py`、`graph_restore.py`
- 改動內容：新增 `NodeFactory.create_by_name()` 與 `bind_node_item_events()`，統一新建/還原節點的選取與釋放事件。
- 原因：移除 `main.py` 內節點建立細節，避免新建與還原兩條事件綁定路徑漂移。
- 風險/相容性：`MainWindow.add_node_by_name()` 保留為轉接方法，因此 palette、搜尋選單與匯入流程不需改呼叫端。
- 驗證結果：預設 Input / Output 建立與測試通過。

### 輸入圖片狀態抽離

- 檔案：`input_session.py`、`image_importer.py`、`main.py`
- 改動內容：新增 `InputSession` 管理 `global_image`、多張輸入圖片與基準尺寸；`ImageImportManager` 改依賴 session、scene 與 callbacks。
- 原因：讓剪貼簿、拖曳、檔案對話框匯入共用同一套狀態管理。
- 風險/相容性：`MainWindow.global_input_image`、`input_images`、`base_size` 保留唯讀/相容屬性，既有測試與外部讀取不需改。
- 驗證結果：`test_refactor.py` 的 clear input 回歸通過。

### 序列化路徑整併

- 檔案：`graph_state.py`、`core_engine.py`、`main.py`
- 改動內容：`get_graph_state()` 改接收節點位置 dict，不再 import `NodeItem`；刪除未使用的 `Graph.to_json()`；模板還原時先釋放 graph mutex 再排程 evaluate，避免同步評估死鎖。
- 原因：保留單一 JSON 匯出路徑，讓序列化層更接近純資料。
- 風險/相容性：JSON 欄位維持原本的 `nodes` / `edges` / `pos` 結構。
- 驗證結果：`py_compile` 通過。

### 未使用程式與產物清理

- 檔案：`history.py`、`graph_evaluator.py`、`.gitignore`
- 改動內容：刪除未使用的 `HistoryManager.push_initial()` 與 `GraphEvaluator.set_use_background()`；背景評估骨架保留但預設同步，避免無事件迴圈測試或關閉時遺留 QThread；新增 `.gitignore` 忽略 `__pycache__/`、`*.pyc`、`run_output.log`；移除現有產物檔。
- 原因：降低維護雜訊，避免測試產物持續污染工作樹。
- 風險/相容性：若外部腳本曾呼叫上述未使用方法，需要改用現有 `save_state()` 或 `_use_background` 設定流程。
- 驗證結果：`py_compile` 與 `test_refactor.py` 通過。

### 文件同步

- 檔案：`README.md`、`CONTRIBUTING.md`、`fix_in_progress/code_structure.md`、`fix_in_progress/uiux_design.md`
- 改動內容：更新專案結構、節點註冊說明、拖曳圖片匯入與本次模組化紀錄。
- 原因：讓文件反映目前的模組邊界與開發流程。
- 風險/相容性：無執行期影響。
- 驗證結果：人工對照主要模組與功能描述。

## 後續待辦

- 將 `core_nodes.py` 依節點類型拆成 `nodes/` 子套件。
- 將 `ConfigPanel` 對 `MainWindow` 的 mutex 存取改為顯式注入介面。
- 補齊模板匯入/匯出與拖曳圖片的自動化測試。
- 視需求導入裝飾器式節點註冊，進一步消除 `NODE_MAP` 與 `PALETTE_CATEGORIES` 的雙重維護。
