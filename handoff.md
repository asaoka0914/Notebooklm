# Handoff (交接紀錄)

- **最後更新時間**: 2026-08-21 22:25
- **最後操作裝置**: 家裡電腦 (AsaokaHTPC)
- **當前狀態**: 🟢 完成 Concept Schema 標準結構建立、繁中 Title 防呆加固、長篇書籍 6 大深度模組升級（與 wiki-ingest 解耦），全域技能同步與 GitHub 推送完畢。
- **目前做到哪**: 
  - **概念筆記結構規範 (Concept Schema) 確立**：
    - 在 `Project/Notebooklm/SKILL.md` 正式訂立 `wiki/concepts/` 標準 4 大章節結構（📌 概念定義、🧠 運作機制與核心價值、⚠️ 常見誤區與邊界條件、🔗 關聯資料）。
    - **【繁中 Title 防呆】**：強制要求概念筆記檔名為英文 slug，但 Frontmatter 中的 `title` 必須為繁體中文名稱（如 `title: "直覺決策 (Intuitive Decision)"`），嚴禁直接以英文 slug 當 title。
    - **【提煉 SOP】**：明定 Stage 2 建立概念時，必須直接自 Summary 模組二提煉機制定義與核心價值，嚴禁只擷取一行無關字串。
  - **長篇書籍專屬 6 大深度模組升級與解耦**：
    - 將 `book-reader` 與 `wiki-ingest` 短篇摘要解耦，確立長篇書籍專用之 6 大模組架構（全書核心、核心心智模型、結構脈絡、實踐清單、案例與金句、雙向概念網絡）。
    - 同步更新 `scripts/06_generate_book_summary.py` Prompt 結構與 `SKILL.md` 範本。
  - **wiki-ingest 概念與驗收規範對齊**：
    - 同步升級 `Project/wiki-ingest/SKILL.md`，納入 Concept Schema、繁中 Title 與 `audit_concept_links.py` 驗收關卡，全域部署與 GitHub 推送完成。
  - **全域技能同步與 GitHub 備份**：
    - 執行 `install.ps1` 同步更新至 Gemini 與 Claude 全域目錄。
    - 成功推送最新代碼與文檔至 GitHub 遠端儲存庫。
- **下一次開工建議**: 
  - 可直接呼叫本地 Agent，針對 `wiki/summaries/` 既有長篇書籍摘要（如《被討厭的勇氣》等）依照最新 6 大深度模組重新升級。
  - 亦可引導 Agent 針對建立不完整的概念筆記（如 `intuitive-decision.md`、`mindfulness.md` 等）依照新版 Concept Schema 進行內容提煉與升級。

