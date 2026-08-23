# Handoff (交接紀錄)

- **最後更新**: 2026-08-23 21:23
- **最後操作裝置**: 家裡電腦 (AsaokaHTPC)
- **當前狀態**: 🟢 完成多 Profile 獨立隔離法實作、QC 涵蓋度比對加固與 EPUB 封面防呆修復，並全數通過驗收。
- **程式修改與核心成果**:
  - **1. 多 Profile 獨立資料夾隔離法 (`~/.notebooklm/chrome_profiles/<account_id>`)**：
    - 於 `scripts/_auth_pool.py` 實作獨立目錄優先判定與 `--login <account_id>` 一次性登入 CLI。
    - 於 `scripts/_auth_utils.py` 支援 `custom_user_data_dir` 與 Chrome `--headless=new` 參數，100% 徹底解決 Windows Chrome 搶鎖 (`Profile Lock`) 與日常開著 Chrome 衝突問題。
  - **2. 04_qc_check.py 支援 H3 巢狀標題提取**：
    - 解決區塊內子小節被誤判缺漏的問題，確保 Ground Truth TOC 1對1核對精準度。
  - **3. 01_init_notebook.py EPUB 封面提取防呆**：
    - 優先比對 `properties="cover-image"` 並強制排除 `backcover` / `back_cover`，徹底解決封面誤取封底圖問題。
  - **4. 全域技能同步**：
    - 所有修改後之 Python 腳本均已同步更新至全域技能目錄（`~/.gemini/config/skills/book-reader/`）。
- **下一次開工建議**:
  - 可直接呼叫 `book-reader` 整理新書籍。若需為備用帳號建立獨立無痕 Profile，只需執行 `python scripts/_auth_pool.py --login <account_id>` 一次性登入即可。
