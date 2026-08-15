# book-reader v5.0.2 修正計畫 (Phase 1 規劃與對齊)

針對 [book-reader-v5.0.2-fix-plan.md](file:///g:/我的雲端硬碟/Project/Notebooklm/book-reader-v5.0.2-fix-plan.md) 第十三節之專業審查建議，進行完整需求分析、邊界質疑與實作規劃。

---

## 一、需求與規格轉化 (Spec)

### 1. 目標問題清單
- **B1**: 簡繁同化問題 — `04_qc_check.py` 需加入 OpenCC 簡繁同化，且必須採用**安全動態匯入機制**（當 `opencc` 缺失時優雅降級不 crash，並於 `requirements.txt` 增補依賴）。
- **B2**: TOC 前導詞誤收錄 — `01_init_notebook.py` 的 `extract_epub_toc()` 需排除 `FRONTMATTER_KEYWORDS`（子字串匹配），且**必須同步修復 XML 成功路徑與 HTMLParser/正則 Fallback 路徑**。
- **B3**: 正規化標點與彎引號強化 — `_normalize()` 補足全形彎引號（`\u2018`, `\u2019`, `\u201c`, `\u201d`）與清理多餘字符。
- **B4**: 03 自動複製流程衝突 — `book_config.yaml.template` 與 `03_assemble_report.py` 增設 `assemble_copy_to_cleanup: false` 開關，預設關閉以符合 v5.0 雙檔分流規範。

---

## 二、邊界條件與架構質疑 (Grill & Boundary Alignment)

1. **環境相依性與 Windows 相容性**：
   - 採用 `opencc-python-reimplemented` 作為純 Python 實現，避免 Windows 下編譯 C++ 擴展依賴問題。
   - 頂部使用 `try...except`，無 opencc 時僅印出 Notice 並跳過繁簡同化，維持向後相容。
2. **Fallback 路徑一致性**：
   - 損壞 XML 的 EPUB 在走入 `html.parser` 或備援正則時，前導詞過濾規則與標準 XML 解析路徑 100% 共享一致的 `_is_chapter_candidate` 邏輯。
3. **設定預設值安全性**：
   - 若使用者自訂的 `book_config.yaml` 遺漏 `assemble_copy_to_cleanup` 欄位，`config.get("assemble_copy_to_cleanup", False)` 預設為 `False`，避免誤寫入 Obsidian 待整理區。

---

## 三、修改項目清單

### 1. [requirements.txt](file:///g:/我的雲端硬碟/Project/Notebooklm/requirements.txt)
- 新增 `opencc-python-reimplemented>=0.1.7`。

### 2. [scripts/04_qc_check.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/04_qc_check.py)
- 安全匯入 OpenCC 並初始化 `s2t` 轉換器。
- `_normalize()` 函式加入簡繁轉換與全形彎引號支援（涵蓋 B1、B3）。

### 3. [scripts/01_init_notebook.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/01_init_notebook.py)
- 定義 `FRONTMATTER_KEYWORDS`、`_is_frontmatter()` 與 `_is_chapter_candidate()`。
- XML 解析路徑與 fallback candidates 迴圈全面套用 `_is_chapter_candidate()`（涵蓋 B2）。

### 4. [config/book_config.yaml.template](file:///g:/我的雲端硬碟/Project/Notebooklm/config/book_config.yaml.template)
- 新增 `assemble_copy_to_cleanup: false` 設定註解與預設值（涵蓋 B4）。

### 5. [scripts/03_assemble_report.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/03_assemble_report.py)
- 讀取 `assemble_copy_to_cleanup` 設定值，當且僅當為 `True` 時才執行複製至 `raw/__cleanup_pending__/`（涵蓋 B4）。

### 6. [tests/test_epub_toc_and_assemble.py](file:///g:/我的雲端硬碟/Project/Notebooklm/tests/test_epub_toc_and_assemble.py)
- 新增 `test_extract_epub_toc_filters_frontmatter_xml` 與 `test_extract_epub_toc_filters_frontmatter_malformed_fallback`。
- 新增 `test_normalize_with_opencc_and_fallback`（測試繁簡同化、彎引號與無 opencc 模擬）。

---

## 四、驗收標準 (Acceptance Criteria)
1. 執行單元測試全數通過（含新舊共 11+ 項測試）。
2. 在無 opencc 模擬環境下，`04_qc_check.py` 正常啟動不拋出 Exception。
3. EPUB GT TOC 解析排除所有前言/推薦序等非正文章節。
4. 03 組裝報告在預設配置下不會複製至 Obsidian 待整理區。

以上規劃是否正確？確認後將進入 Phase 2 依序實作與驗證。

---

## 五、Claude 審核結果（2026-08-15）

**結論：✅ 有條件核准，可進入 Phase 2。**

本規劃正確吸收了 `book-reader-v5.0.2-fix-plan.md` 第十三節的全部四項修正意見：B1 安全匯入機制、B2 雙路徑（XML 成功路徑＋fallback）同步套用 `_is_chapter_candidate()` 且改子字串比對、B3 併入 B1 一併處理彎引號、B4 預設關閉的開關設計，架構質疑三點（環境相依性、Fallback 一致性、設定預設值安全性）也切中要害，方向正確。

核准通過，但實作時請一併納入以下 3 點，避免 Phase 2 出現新的疏漏：

1. **OpenCC 轉換器須在模組層級初始化一次，不可放在 `run_single_qc_pass()` 內部。**
   現有 `_normalize()` 目前是定義在 `run_single_qc_pass()` 函式內的 nested function，而該函式在 `--auto-backfill` 模式下最多會被呼叫 `MAX_RETRY_BATCH + 1`（即 4）次。若 `opencc.OpenCC('s2t')` 的初始化也跟著放在這個內部作用域內，會導致每次重試都重新載入一次 OpenCC 字典表，造成不必要的效能浪費。請確保 `try: import opencc; _CC = opencc.OpenCC('s2t')` 這段放在檔案最頂部（import 區塊），全域只初始化一次。

2. **新增回歸測試：確認 OpenCC 轉換不會破壞既有已通過的正體中文書籍。**
   B1 的 `_normalize()` 修改會影響**所有**書籍的 QC 比對（不分簡繁），而不僅是本次測試用的簡體書。目前四、驗收標準只涵蓋「無 opencc」與「排除前導詞」兩類情境，建議補上第 5 項驗收標準：**以先前已驗證 100% 通過的正體中文書籍（即先前已驗證過的那本測試用書）重新執行一次 `04_qc_check.py`，確認加入 OpenCC s2t 轉換後 QC 結果仍維持 100% 通過、無新增缺漏章節**。這是為了排除 OpenCC 詞典轉換在處理已是繁體的文字時，因異體字或詞彙轉換表而產生非預期改動的風險（機率低，但屬於全域性修改，值得一次性驗證清楚）。

3. **`book_config.yaml.template` 的新欄位請附簡短註解。**
   `assemble_copy_to_cleanup: false` 建議附一行 YAML 註解說明用途（例如 `# 是否自動複製報告至 Obsidian raw/__cleanup_pending__/，v5.0 雙檔分流架構下建議維持 false`），方便日後其他人閱讀設定檔時無需回頭查文件。

以上 3 點均為小幅補強，不影響整體方向，**可直接進入 Phase 2 實作**，實作完成後請一併附上第 2 點的回歸測試結果供覆核。
