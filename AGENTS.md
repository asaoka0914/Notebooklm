# Antigravity 專案日誌與初始化通用規則

## 1. 專案自動辨識與初始化

**專案名稱 (PROJECT_NAME) 與 根目錄 (PROJECT_ROOT) 判定規則**（動態適應跨電腦路徑）：
1. **優先判定**：檢視目前開啟檔案或工作區的完整路徑，自動擷取 `PROJECT_NAME` 與 `PROJECT_ROOT`：
   - 家中筆電：`g:\我的雲端硬碟\Project\Notebooklm`
   - 公司筆電：`C:\Users\asaoka.zhong\Desktop\Project\Notebooklm`
2. **Obsidian 根目錄 (OBSIDIAN_ROOT)**：
   - 家中筆電：`g:\我的雲端硬碟\Obsidian`
   - 公司筆電：`C:\Users\asaoka.zhong\Desktop\obsidian`
3. **安全警示**：如果偵測到工作區中包含整個 `Project` 根目錄，應主動警告使用者：「您開啟了整個 Project 目錄，可能會導致對話上下文污染。建議關閉此視窗，改為開啟單一專案工作區。」

**初始化觸發**：
判定 `PROJECT_NAME` 後，檢查以下路徑是否存在：
- `[OBSIDIAN_ROOT]\程式開發\Notebooklm\CONTEXT.md`
- `[PROJECT_ROOT]`

若不存在，自動在 Terminal 執行（定位到 `[OBSIDIAN_ROOT]`）：
```powershell
python init-project.py Notebooklm
```
執行完成後，引導使用者至 Obsidian 填寫 `CONTEXT.md` 與 `PLAN.md`，填完後說「繼續」。

---

## 2. 對話開始時自動載入脈絡

判定 `PROJECT_NAME` 後，依序讀取以下檔案：

1. `[PROJECT_ROOT]\AGENTS.md`
   **優先讀取專案藍圖與 Guardrails**；若不存在，才讀取 `[OBSIDIAN_ROOT]\程式開發\Notebooklm\CONTEXT.md`（相容未遷移舊專案）。

2. `[OBSIDIAN_ROOT]\程式開發\Notebooklm\PLAN.md`
   （實作計畫、當前階段、待辦項目）

3. `[PROJECT_ROOT]\check\changelog_index.json`
   **優先讀取此索引檔**，若不存在則讀取 `[OBSIDIAN_ROOT]\程式開發\Notebooklm\CHANGELOG.md` (只讀最新 5 筆)，藉此快速掌握最近修改並節省 token。

4. `[OBSIDIAN_ROOT]\程式開發\Notebooklm\LESSONS.md`
   （**常駐地雷警示檔**：若存在則讀取，載入「條件 → 動作」防錯機制）

5. `[OBSIDIAN_ROOT]\程式開發\Notebooklm\SNAPSHOT.md`
   **只在以下情況才讀取**：
   - 距上次工作超過 7 天
   - 我明確詢問歷史記錄

讀取完畢後，用 2~3 句話摘要該專案目前進度，並確認今天的工作目標後開始。

---

## 3. 每次修改完成後自動寫入日誌

不需要我提醒，每次任務完成後自動執行：

**1. 寫入** `[OBSIDIAN_ROOT]\程式開發\Notebooklm\CHANGELOG.md`：
- 檢查檔案中是否已存在今天的日期標題 `## [YYYY-MM-DD]`。
- **若已存在**：在該日期標題下方 **Prepend** 插入本次修改的子區塊：
  ```markdown
  ### [HH:MM] 一句話標題
  - 修改檔案：[檔案名稱](file:///完整路徑)
  - 做了什麼：
  - 原因：
  - 狀態：✅完成 / ⚠️待測試 / 🔲待辦
  - 下次注意：（若有則填，沒有則省略）
  ```
- **若不存在**：在檔案最上方 **Prepend** 建立新的日期大標題與第一筆紀錄：
  ```markdown
  ## [YYYY-MM-DD]
  ### [HH:MM] 一句話標題
  - 修改檔案：[檔案名稱](file:///完整路徑)
  - 做了什麼：
  - 原因：
  - 狀態：✅完成 / ⚠️待測試 / 🔲待辦
  - 下次注意：（若有則填，沒有則省略）
  ```

**2. 同步 Prepend 寫入一筆簡短的 JSON 記錄**至 `[PROJECT_ROOT]\check\changelog_index.json`：
格式為：
```json
{
  "time": "YYYY-MM-DD HH:MM",
  "title": "一句話標題",
  "files": ["修改的檔案名稱"],
  "status": "✅完成"
}
```

**日誌滾動壓縮**（自動觸發）：
若 CHANGELOG.md 中的日期大標題 `## [YYYY-MM-DD]` 已有 5 個以上：
1. 取出最舊一天的所有紀錄
2. 壓縮成一行格式：`[日期] 標題1、標題2... — 狀態`
3. Append 寫入 SNAPSHOT.md
4. 從 CHANGELOG.md 刪除該天的紀錄與大標題

---

## 4. 開發通用禁止事項

- 不改動非本次目標的檔案
- 不刪除已通過測試的邏輯
- 不自行假設需求，不確定就問我
- 修改前先確認該檔案目前的完整內容
- **NotebookLM 工具調用規範**：查詢或操作雲端 NotebookLM 時，務必優先調用已認證的 Python 工具 `python -c "from notebooklm_tools.cli.main import app; app(['notebook', 'list'])"` 或使用 `nlm` / `notebooklm-mcp-cli`，**嚴禁調用未認證的 `npx notebooklm`**。

