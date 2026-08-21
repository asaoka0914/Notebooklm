# NotebookLM 導讀報告自動化生成 Skill (NotebookLM Report Skill)

本工具為基於 `notebooklm-mcp-cli` / `nlm` 的自動化書籍導讀報告生成工作流。專為長篇書籍導讀、重點擷取與 Obsidian 筆記庫整合而設計。

---

## 🌟 核心功能特色

1. **真實目錄驗證與動態 Batch 生成 (Ground Truth TOC)**：
   - **最高權威 (SSOT)**：優先解析本機 `.epub` (OPF/NCX) 或 `.pdf` 的真實章節目錄，徹底杜絕 AI 因固定批次暗示而發生的「捏造章節」問題。
   - **雙重保險**：支援於 `book_config.yaml` 人工配置 1~50 章節合法上限健檢。

2. **本機封面提取與 Base64 單檔內嵌**：
   - 自動解壓 EPUB 實體高畫質封面圖，並於合成 Markdown 時將圖片轉為 `data:image/jpeg;base64,...` URI 寫入檔頭。
   - 產出的 Markdown 可單檔隨意複製與移轉，Obsidian 100% 免外部圖檔即可渲染封面。

3. **報告品質自動過濾與即時監控 (QC & Live Check)**：
   - 批次生成時實時於 console 輸出 `📋 涵蓋度自我檢查清單`。
   - 合成腳本自動過濾報告內非必要的腳註標號 (`[1]`, `[2]`) 與自我檢查清單段落，保持內文乾淨。
   - QC 腳本具備章節號硬性比對與 Hard-Fail 攔截機制。

---

## ⚡ 跨電腦一鍵安裝與動態環境設定 (One-Click Setup)

本專案支援 Windows 跨電腦快速安裝與自動 Obsidian Vault 探索：

```powershell
# 於專案根目錄執行一鍵安裝腳本
powershell -ExecutionPolicy Bypass -File install.ps1
```

**安裝腳本自動執行：**
1. **自動佈署 Skills 目錄**：自動將最新程式與 Skill 同步至 Gemini (`~/.gemini/config/skills/book-reader`) 與 Claude (`~/.claude/skills/book-reader`)。
2. **安裝 Python 依賴套件**：自動透過 `requirements.txt` 安裝最新 `PyYAML`、`python-dotenv`、`opencc-python-reimplemented`。
3. **動態探索 Obsidian Vault**：內建 `scripts/env_config.py` 自動解析 `obsidian.json` 系統設定檔與跨磁碟候選清單（支援公司筆電/家裡筆電/Google Drive），免手動寫死路徑。

---

### v5.0.5 (2026-08-21)
- **概念雙向連結客觀稽核與防禦閉環 (Concept Bidirectional Link Audit)**：
  - 新增 `check/audit_concept_links.py` 獨立稽核工具，對 `wiki/summaries/` 與 `wiki/concepts/` 進行真實檔案掃描與多維度連結分析（支援路徑前綴、後綴判定、同名歧義提示與 Exit Code 阻斷）。
  - 徹底替換寫死的假健康檢查，`__sync_script.py` 改為自動調用稽核腳本產出真實掃描數據覆寫 `outputs/sync-status.md`。
  - 升級 `SKILL.md` 與 `BoBo-wiki/agents.md`，在 Stage 2 步驟 4「概念關聯」建立強制程式驗收關卡，消除「AI 自我宣告完成」漏洞。
  - **概念雙括號語法防呆加固**：於 `SKILL.md` 模板與 `06_generate_book_summary.py` Prompt 明確強制 `[[english-slug|中文名稱]]` 格式，嚴禁純中文裸連結流入 Vault。
  - **確立標準概念筆記結構規範 (Concept Schema)**：於 `SKILL.md` 正式訂立 `wiki/concepts/` 結構標準（概念定義、運作機制與核心價值、誤區與邊界、關聯資料），明定 Stage 2 Agent 必須自 Summary 模組二精準提煉機制與價值，杜絕純字串盲目截取。
- **長篇書籍生成管線健全化 (Rate Limit & Duplication Fixes)**：
  - 於 `02_batch_generate.py` 實作智能滑動視窗限流與連續錯誤指數退避（RateLimiter），全局耗盡時拋出 `RateLimitExhaustedError` 安全退出。
  - 於 `01_init_notebook.py` 實作 `plan_batches()` 防止批次規劃章節範圍重疊，於 `04_qc_check.py` 增加重複章節偵測。
  - 統一所有腳本入口之 Windows UTF-8 控制台編碼防護（TextIOWrapper），全套 37 項單元測試 100% 通過。

### v5.0.4 (2026-08-15)
- **OpenCC 簡繁同化與比對加固 (B1/B3)**：`04_qc_check.py` 於模組層級安全初始化 OpenCC 轉換器，支援簡繁目錄同化比對與全形彎引號（`\u2018`, `\u2019`, `\u201c`, `\u201d`），解決簡體 EPUB TOC 與繁體產出內容比對 Hard-Fail；套件缺失時優雅降級不 crash。
- **雙路徑前導詞過濾與章節標記關鍵字擴充 (B2)**：`01_init_notebook.py` 在標準 XML 與 Fallback 雙路徑同步採用子字串前導詞過濾（排除前言、推薦序、致謝等），並擴充 `CHAPTER_MARKERS` 納入「篇、Part、Unit、Lesson、法則、夜、卷、節、講」等多種章節結構。
- **Obsidian 流程解耦開關 (B4)**：`03_assemble_report.py` 與 `book_config.yaml.template` 增加 `assemble_copy_to_cleanup: false` 開關與詳細註解，預設關閉以符合 v5.0 雙檔分流規範。
- **全套自動化測試擴充**：單元測試擴充至 16 項（涵蓋正體中文回歸測試、簡繁同化、無 OpenCC 降級、擴充章節標記），100% 通過。

### v5.0.3 (2026-08-15)
- **新增跨電腦一鍵安裝腳本 (`install.ps1`)**：一鍵完成 Gemini / Claude Skills 佈署、依賴安裝與環境診斷。
- **新增動態 Obsidian Vault 搜尋模組 (`scripts/env_config.py`)**：自動解析系統設定檔與常用路徑，無縫適應多裝置/跨電腦切換。
- **優化報告自動導出邏輯**：`03_assemble_report.py` 整合動態 Vault 搜尋，自動定位 `raw/` 目錄。
- **EPUB 目錄提取深度加固 (`html.parser`)**：針對非良構 XML 或破損 `<a>` 標籤，採用 `HTMLParser` 狀態機取代純非貪婪正則，杜絕章節標題跨標籤越界黏合，並補齊閉環單元測試。

### v5.0.2 (2026-08-15)
- **架構重構與主程式統一**：以 `book-reader` 最新主程式全面取代舊有根目錄腳本，舊歷史檔案與暫存移入 `old data/` 封存。
- **嚴格 QC 前置守門 (QC Guard)**：`06_generate_book_summary.py` 加入三道防線（`qc_status.json` 存在性、書名一致性與 `passed_all == True` 硬性檢查），未通過前禁止生成摘要。
- **EPUB 目錄提取擴充**：`01_init_notebook.py` 擴充支援 `toc.xhtml` 及容錯標籤抽取。
- **YAML Frontmatter 自動串流注入**：`03_assemble_report.py` 支援將產出報告自動注入 Frontmatter 並相容 Obsidian 知識庫規範。
- **自動化單元測試覆蓋**：新增針對 QC Guard、EPUB TOC 與 Frontmatter 注入之 `unittest` 測試套件。

### v5.0.1 (2026-08-14)
- **修復 03/05 自動補課組裝崩潰 Bug**：拆分 assemble_report_core 消除動態 import 參數污染。
- **強化 QC 狀態嚴格判定**：04_qc_check 產出 qc_status.json，06_generate_book_summary 嚴格檢驗。
- **新增 06 全書 6 模組深度摘要生成腳本**：產出 6 大核心模組。
- **明定雙檔分流與舊版相容說明**：03 既有複製保留相容，正式產出由階段二 Agent 接手。

### v1.1.0 (2026-08-02)
- **新增 EPUB/PDF 地面真相目錄解析 (`extract_epub_toc`)**：
  - 改為由本機檔案直接解析權威目錄，避免向模型詢問未知的長度。
- **新增 Base64 封面圖片內嵌**：
  - 產出的 `.md` 檔案完全獨立無依賴，Obsidian 免多帶 `cover.jpg`。
- **新增即時檢查清單輸出與 QC 攔截機制**：
  - `02_batch_generate.py` 即時列印檢查清單。
  - `04_qc_check.py` 加入章節數量與未授權章節 Hard-Fail 攔截。
- **修正繁體中文與阿拉伯數字正則匹配**：
  - 統一支援 `第 1 章`、`第一章`、`CHAPTER 1` 三種語法。

### v1.0.0 (2026-08-02)
- 初始版本：建立四階段批次生成 pipeline (`01_init_notebook.py` ~ `04_qc_check.py`)。

---

## 🔒 隱私與安全規範 (Security Rules)

- **嚴禁提交 API Keys / Cookies / Credentials**：所有的 `.env`、`credentials.json`、`profiles/` 及認證憑證均已納入 `.gitignore`。
- **嚴禁提交書籍原始檔與生成報告**：所有 `*.epub`、`*.pdf`、`raw_outputs/` 及 `final/` 資料夾均保持本地端私有，不推送至 GitHub。
