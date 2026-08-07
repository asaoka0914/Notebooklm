---
name: book-reader
description: 透過已授權的 notebooklm_tools 或 nlm CLI 操作 NotebookLM，讀取指定筆記本並生成完整涵蓋所有章節、忠於原文的讀書報告（Briefing Document）。當使用者說「幫我整理notebooklm + 筆記名稱」（例如「幫我整理notebooklm AI導論」「幫我整理notebooklm+機器學習筆記」）、或明確提到「book-reader」時，一律觸發此技能。即使使用者只是隨口提到「幫我把 XX 筆記整理成報告」而沒有精確講出「notebooklm」四個字，只要情境明顯是指 NotebookLM 筆記本，也應該觸發。
---

# book-reader

透過本機已授權的 `notebooklm_tools` Python CLI 或 `nlm` MCP CLI，找到使用者指定的 NotebookLM 筆記本，並依照 `讀書報告核心概念.md` 的規則生成一份完整涵蓋所有章節、忠於原文、不摻雜個人觀點的讀書報告。

## 為什麼要照這個流程走

NotebookLM 本身的報告生成是黑箱——你送進去的 query 決定了它的表現，但它不保證涵蓋所有章節或不加自己的詮釋。這個技能的核心價值不是「呼叫 API」這件事本身，而是**在生成前先建立真實章節基準（Ground Truth），生成後嚴格對照基準核對輸出**。跳過核對步驟、只憑 CLI 回傳「成功」就交差，正是之前在 Agent 協作中吃過的大虧（因生成截斷僅涵蓋半本書，卻被誤判為完成）。

---

## 執行流程與自動化 Pipeline 腳本

本技能已整合自動化 Python 腳本（位於本技能 `scripts/` 目錄下），所有腳本內部皆已以 `BASE_DIR` 絕對路徑進行檔案儲存與讀取。Agent 執行任務時**應優先呼叫此套 Python 腳本**處理：

- `01_init_notebook.py`: 初始化筆記本、自動認證過期恢復 (`ensure_auth`)、解析 EPUB 目錄 (Ground Truth) 與提取封面圖片（縮放 50% 轉 Base64 寫入 `final/<book_title>/cover.jpg`）。
- `02_batch_generate.py`: 批次查詢 NotebookLM（建議每批 2 章以確保單章篇幅達 1000 字以上）、防限流退避與帳號切換處理（輸出暫存至 `raw_outputs/<book_title>/`）。
- `03_assemble_report.py`: 組裝 Markdown 報告、自動清理殘留主觀解讀詞、頂部內嵌 50% 封面 Base64 圖片，並動態搜尋 Obsidian 目錄自動備份。
- `04_qc_check.py`: 自動進行 Ground Truth 1 對 1 章節覆蓋度 Hard-Fail 驗證。

> **註**：執行腳本時建議定位至技能目錄或透過絕對路徑呼叫 Python 腳本（如 `python <SKILL_DIR>/scripts/01_init_notebook.py`）。

---

### 0. 防亂碼與 Token 節省規範 (Windows 環境)

為避免 Windows 控制台 (CP950) 輸出中文亂碼導致 Agent 反複嘗試浪費 Token：
1. **優先使用 `scripts/` 下的 Python 腳本**：所有輸出與中間檔案一律以 UTF-8 寫入檔。
2. **禁止在主機控制台直接印出大量中文內容**（如完整目錄或 CLI 輸出的 JSON 列表）。
3. **終端機指令編碼**：執行 PowerShell/CMD 時，若有輸出需求，優先使用 `PYTHONIOENCODING=utf-8` 或切換 Code Page。

### 1. 解析使用者指定的筆記名稱

從使用者訊息中取出筆記本名稱（例如「幫我整理notebooklm AI導論」→ 名稱是「AI導論」）。如果使用者的講法很模糊、沒辦法確定是哪個筆記本，先列出候選再問，不要用猜的送進下一步。

### 2. 確認 CLI 已授權與 API 限流退避機制

- **確認授權與自動恢復**：執行前 `01_init_notebook.py` 會透過 `ensure_auth()` 自動檢視 Token，若過期會自動嘗試開啓/對接 Chrome remote debugging port 9223 進行重認證。
- **RESOURCE_EXHAUSTED / 429 限流與帳號切換處理**：
  - 當呼叫 API 遇到 `RESOURCE_EXHAUSTED` 限流或配額用盡時，自動啟動退避機制。
  - 主動提示使用者：「偵測到 Google 帳號 API 配額限制，是否切換 Google 帳號？」
  - 使用者同意後，執行認證登入流程彈出 Chrome 視窗供使用者手動登入新帳號，絕不硬幹或無限重試。
- **CLI 標準指令速查（僅備用試錯）**：
  - 列出筆記本：`python -c "from notebooklm_tools.cli.main import app; app(['notebook', 'list'])"`
  - 建立筆記本：`python -c "from notebooklm_tools.cli.main import app; app(['notebook', 'create', '筆記本名稱'])"`
  - 新增檔案：`python -c "from notebooklm_tools.cli.main import app; app(['source', 'add', '<NOTEBOOK_ID>', '--file', r'G:\路徑\檔案.epub'])"`
- **絕對禁止**：嚴禁呼叫未經授權的 `npx notebooklm`，亦**禁止多次反覆執行 `--help` 試錯**。

### 3. 比對筆記本名稱 → Notebook ID

拿到 `notebook list` 的結果後，用使用者提供的名稱做比對：
- **完全比對**：優先找名稱完全相符的筆記本。
- **核心書名比對**：若無完全相符，僅比對「核心書名/標題」（例如《非理性成功》）。**嚴禁使用作者姓名（如 Ken Fisher）做廣泛比對**，避免混淆同作者的其他書籍。
- **無相符筆記本**：若找不到相符筆記本，**直接列出已有筆記本清單詢問使用者**（或詢問是否要上傳/建立新筆記本），**絕對禁止**調用 API 開啟或查詢其他無關筆記本的來源內容（Source）進行細節比對。

### 3.5 擷取來源目錄 (Ground Truth) 與封面圖片處理

1. **章節目錄 Ground Truth Baseline**：
   - 解析 `.ncx` 或 `nav.xhtml` 並**直接寫入 UTF-8 暫存檔**，過濾非內文頁面（如目錄、版權頁），確定全書章節總數 $N$。
2. **封面圖片擷取與 50% 縮放內嵌**：
   - 從 EPUB 檔案中提取 `cover.jpg` / `cover.png` 封面圖片。
   - 使用 Pillow (PIL) 將圖片長寬**各縮小至 50%**（使其面積與檔案大小降至約原本的 1/4，符合輕能化規範）。
   - 將縮放後的封面圖片轉為 `data:image/jpeg;base64,...` 字串，準備嵌入 Markdown 最頂部。

### 4. 載入報告生成規則與發送查詢

讀取 `讀書報告核心概念.md` 的完整內容，作為送給 NotebookLM 的查詢需求（query），呼叫 Python 腳本或 SDK 進行批次擷取（建議每批 2 章以保證每章內容廣度與深度）。

### 5. 用真實輸出與 Ground Truth 比對核對 (QC Check)

執行 `scripts/04_qc_check.py` 或比對邏輯：
1. **Ground Truth 1 對 1 涵蓋度比對**：將報告內文出現的 `## [章節名稱]` 與 Ground Truth 清單對照。
2. **截斷補全**：若 $M < N$，觸發補全機制（上限 3 次 `MAX_RETRY_BATCH = 3`），補齊缺漏章節。

### 6. 交付結果與自動存檔 (Markdown 格式)

產出的讀書報告**必須為 Markdown 格式 (`.md`)**，並自動儲存至 Obsidian 筆記目錄：

1. **動態搜尋 Obsidian 儲存路徑**：
   - 腳本將自動掃描桌面與雲端硬碟中的 `Obsidian/BoBo-wiki/raw` 目錄，無縫支援家中與公司電腦環境。
2. **寫入與備份檔案**：
   - 最頂部內嵌長寬 50% 的 Base64 封面圖片：`![封面](data:image/jpeg;base64,...)`
   - 檔名規範：`[書名/筆記本名稱]_讀書報告.md`
   - 使用 `UTF-8` 編碼將完整 Markdown 內文寫入，並自動備份複製至搜尋到的 Obsidian raw 目錄。
3. **對話視窗回報**：
   - 避免在聊天視窗輸出整篇冗長內文（可節省大量 Token），僅需向使用者回報：
     - 全書總章數 $N$ 與報告完整涵蓋狀況。
     - 是否觸發過分批補全或帳號切換。
     - **Markdown 檔案存檔連結**：`[點此開啟讀書報告](file:///完整檔案路徑)`。
     - **本次任務之 Token 使用量與執行摘要**。

---

## Guardrails

- 所有動作都在既有全域工程行為準則之下：不確定的 API/CLI 行為要先查證，查不到就標 `UNVERIFIED`，不能把「看起來合理」當成已驗證。
- 這個技能只做讀取與報告生成，不修改、不刪除使用者 NotebookLM 裡的任何筆記本或來源文件。
- 遇到授權失敗、找不到筆記本、生成內容截斷且補全失敗這幾種情況，一律先如實告知使用者，不要自行用替代方案掩蓋問題。

## 檔案位置

本技能與 `讀書報告核心概念.md` 應放在既有的跨裝置技能共享路徑 `~/.gemini/config/skills/book-reader/` 下（透過 `~/.claude/skills` 的 symlink 同步給 Claude/Antigravity 共用），不要另外在別處建立第二份定義。
