# Handoff (交接紀錄)

- **最後更新**: 2026-09-12 15:10
- **最後操作裝置**: 家裡電腦 (AsaokaHTPC)
- **當前狀態**: 🟢 完成 Longform（逐字稿）模式規格 v3 升級、全套 41 項測試 100% 通過、已同步全域技能（Gemini / Claude Code / Claude Desktop）並推送至 GitHub 遠端。
- **程式修改與核心成果**:
  - **1. 逐字稿錨點生成與批次策略 (`scripts/01_init_notebook.py`)**：
    - 新增 `--source-type [book|transcript]` 參數。
    - 實作 `_split_paragraph_aligned()` 與 `build_transcript_anchors()`，依段落邊界自動切分 25,000 字元大區塊，擷取時間戳（`HH:MM:SS`）或開頭短句作為原文錨點清單，塞入既有 chapters 欄位與 `ground_truth_toc.json`（單批次大小預設為 1）。
  - **2. 專屬 Prompt 分流 (`scripts/02_batch_generate.py`)**：
    - 依 `source_type == "transcript"` 分流 Prompt，明確要求小節標題逐字採用錨點、保留對話情境、金句翻譯與發言者標明，徹底相容後續 03 組裝與 04 QC 比對。
  - **3. 單元測試與自動化驗證 (`tests/test_improvements.py`)**：
    - 新增逐字稿時間戳與無時間戳錨點生成單元測試，全套 41 項測試全部通過（Ran 41 tests, OK）。
  - **4. 本地全域技能與 GitHub 遠端同步**：
    - 已同步至 `~/.gemini/config/skills/book-reader/`、`~/.claude/skills/book-reader/` 與 `~/Claude/skills/global-skills/book-reader/`。
    - GitHub 遠端儲存庫已執行 `git push origin master`（Commit `ddab169`）。
- **下一次開工建議**:
  - 可直接使用逐字稿模式處理音訊訪談或 Podcast 逐字稿文字檔：
    `python scripts/01_init_notebook.py --book-path "逐字稿.txt" --title "訪談標題" --source-type transcript`
  - 依序執行 `02_batch_generate.py` → `03_assemble_report.py` → `04_qc_check.py --auto-backfill` → `06_generate_book_summary.py` 驗收長文生成管線。
