# implementation_plan.md — book-reader 技能 v3 完整修復計畫 (含 4 點審核意見強化)

本計畫針對 `book-reader-correction-plan v3.md` 與使用者審核提出的 4 點關鍵補充，進行不降級、完全自動化的端到端修復規劃。

## 需使用者審核項目 (User Review Required)

> [!IMPORTANT]
> - **拒絕設計降級（問題 C 完整實作）**：本輪將完成「Ground Truth 解析 + 1對1核對 Hard-Fail + 自動補跑缺漏章節（`MAX_RETRY_BATCH = 3`）」之完整閉環，絕不止步於告警。
> - **執行中途 Token 失效重載 Client**：在 `_auth_utils.py` 成功重刷憑證後，`02` 批次迴圈強制重新呼叫 `load_profile()` 並建立全新 `NotebookLMClient` 物件。
> - **配額耗盡輪詢依據具體化**：監控 `auth` Profile 檔案 `mtime` 與 `session_id` 變更 + `check_auth(live=True)`。

---

## 擬變更內容 (Proposed Changes)

### 元件一：共用認證模組 (`scripts/_auth_utils.py` [NEW])

#### [NEW] [scripts/_auth_utils.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/_auth_utils.py)
- 提供 `ensure_auth()` 與 `is_auth_error(e)`。
- 提供 `get_profile_metadata()`：回傳現有 `session_id` 與 Token 檔 `mtime`，供 `02` 具體判斷帳號切換。

---

### 元件二：初始化腳本 (`scripts/01_init_notebook.py`)

#### [修改] [01_init_notebook.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/01_init_notebook.py)
- 解析 EPUB TOC（或 `discover_actual_toc()`）並將真實章節清單儲存至 `config/ground_truth_toc.json`。

---

### 元件三：批次生成與帳號切換 (`scripts/02_batch_generate.py`)

#### [修改] [02_batch_generate.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/02_batch_generate.py)
- 捕獲 Auth 錯誤時，呼叫 `ensure_auth()` 救回後，**重新執行 `auth.load_profile()` 並重新實例化 `NotebookLMClient`**。
- 遭遇 `RESOURCE_EXHAUSTED` 時，記錄當前 `session_id` 與 `mtime`，進入最長 300 秒輪詢；一旦發現 `session_id` 改變且 `check_auth(live=True)` 通過，自動重試當前批次。

---

### 元件四：品管檢查與自動補課 (`scripts/04_qc_check.py` & `scripts/05_backfill.py` [NEW])

#### [修改] [04_qc_check.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/04_qc_check.py)
- 讀取 `config/ground_truth_toc.json`，與報告中的 `## [章節]` 做 1 對 1 比對。
- 若有缺漏，回傳缺漏章節列表；若設定 `--auto-backfill` 則自動呼叫 `05_backfill.py`。

#### [NEW] [scripts/05_backfill.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/05_backfill.py)
- 接收缺漏章節清單，針對缺漏章節獨立發送 NotebookLM Query，儲存為 `batch_backfill_N.json`。
- 上限 `MAX_RETRY_BATCH = 3` 次，補齊後重新觸發 `03_assemble_report.py`。

---

### 元件五：規則與 SKILL 檔案同步

#### [修改] [讀書報告核心概念.md](file:///g:/我的雲端硬碟/Project/Notebooklm/讀書報告核心概念.md)
- 補齊完整 8 大禁止詞清單。

#### [修改] [SKILL.md](file:///g:/我的雲端硬碟/Project/Notebooklm/SKILL.md) / [book-reader_SKILL.md](file:///g:/我的雲端硬碟/Project/Notebooklm/book-reader_SKILL.md)
- 更新自動補全與中途認證說明，並複製同步至全域技能與 `chezmoi`。

---

## 驗證計畫 (Verification Plan)

### 端到端與模組測試
1. **語法與匯入檢查**：對所有腳本執行 `python -m py_compile`。
2. **中途 Token 失效自動重載 Client 測試**：在 `02` 執行中人為破壞 `client.csrf_token`，驗證其是否觸發 `ensure_auth()` 救回、重新 `load_profile()` 並成功完成該批次。
3. **缺漏章節自動補全端到端測試**：模擬一份缺少第 3 章的報告與 `ground_truth_toc.json`，執行 `04_qc_check.py --auto-backfill`，驗證是否自動調用 `05_backfill.py` 補齊第 3 章並重新組裝。
4. **配額切換輪詢測試**：驗證當 `mtime` 或 `session_id` 變更時，輪詢能否在 300 秒內即時感知並 Resume。
