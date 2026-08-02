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

## 📝 專案更新日誌 (Changelog & Version History)

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
