# Handoff (交接紀錄)

- **最後更新時間**: 2026-08-15 16:22
- **最後操作裝置**: 家裡電腦 (AsaokaNotebook-9527)
- **當前狀態**: 🟢 Notebooklm / book-reader v5.0.4 正式完成並發佈（16 項單元測試 100% 通過、全域技能同步完成）
- **目前做到哪**: 
  - **B1 繁簡同化安全機制**：`04_qc_check.py` 於模組層級安全初始化 OpenCC 轉換器（支援全形彎引號），避免重複載入字典，套件缺失時優雅降級不 crash；`requirements.txt` 增補 `opencc-python-reimplemented`。
  - **B2 雙路徑前導詞過濾與關鍵字擴充**：`01_init_notebook.py` 在標準 XML 與 Fallback 雙路徑全面套用 `FRONTMATTER_KEYWORDS`（子字串匹配），並擴充 `CHAPTER_MARKERS` 納入「篇、Part、Unit、Lesson、法則、夜、卷、節、講」等多種章節命名架構。
  - **B4 Obsidian 流程解耦**：`03_assemble_report.py` 與 `book_config.yaml.template` 增加 `assemble_copy_to_cleanup: false` 開關（附詳細 YAML 註解），符合 v5.0 雙檔分流規範。
  - **全套單元測試閉環**：新增 7 項單元測試（包含正體中文書籍回歸測試、簡繁同化覆蓋測試、無 OpenCC 降級測試、擴充章節標記測試），全套 16 項單元測試全數通過（`OK`）。
  - **全域技能與環境同步**：已執行 `install.ps1` 同步更新至 Gemini 與 Claude 全域 Skills 目錄。
- **下一次開工建議**: 
  - 換到其他電腦時，只需在專案目錄執行 `powershell -ExecutionPolicy Bypass -File install.ps1` 即可瞬間完成設定並直接調用 `book-reader` 進行書籍導讀報告生成。

- **待處理與追蹤事項 (Pending Follow-up & Tasks)**:
  1. **舊程式隔離目錄清理 (低優先)**：`old data/` 資料夾已安全隔離且納入 `.gitignore`，後續可視需要進行封存備份或手動刪除。
  2. **新書實體驗證**：下次處理新書籍時，可直接挑選各類型 EPUB 實跑完整管線，驗證端到端無縫生成。

