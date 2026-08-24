# Implementation Plan - QC 檢查流程擴充書籍封面 (Book Cover) 完整性比對

在書籍報告組裝與品質檢驗階段，為解決「原始檔案或本地暫存有封面，但合成報告後被漏掉」的問題，於 `04_qc_check.py` 新增封面完整性檢查，並修復 `cleanup_temp_files()` 會誤刪 `cover.jpg` 的既有缺陷。

## Phase 1 需求與邊界分析

### 1-A: 歷史避坑檢視
- 嚴格遵守 `replace_file_content` 唯一字串匹配與 Windows `.bat`/`.ps1` 純 ASCII 規範。
- 不破壞既有單元測試（目前 10 項）。
- `run_single_qc_pass()` 回傳值變更時，必須同步修改 `05_backfill.py` 中解構該回傳值的地方。

### 1-B: Functional Scope & 驗收標準 (Acceptance Criteria)

1. **封面存在性核對 (Cover Integrity Check)**：
   - 以 `os.path.dirname(report_path)` 取得 `cover_jpg_path`（統一路徑來源，避免 `final/full_report.md` 舊路徑格式下 dirname 與 `final/{book_title}/` 不一致的歧義）。
   - 若 `cover.jpg` 存在，檢驗報告 `content` 是否同時包含 `<img` 與 `alt="書籍封面"`。
   - 若存在圖片檔但報告未內嵌：判定為 **`❌ [FAIL]`（Hard-Fail）**，設 `passed_all = False`，並記錄 `cover_status = "FAIL"`。
   - 若存在圖片檔且報告已內嵌：`cover_status = "PASS"`。

2. **無封面書籍正常放行**：
   - 若 `cover.jpg` 不存在，顯示 `ℹ️ [INFO] 本書無封面圖片，已略過。`，設 `cover_status = "SKIPPED"`，不影響 `passed_all`。

3. **EPUB 來源一致性 WARN（在 `qc_check()` 層級執行）**：
   - 在 `run_single_qc_pass()` 回傳後、寫入 `qc_status.json` 之前，若 `cover.jpg` 不存在，從 config 取 `book_local_path`。
   - 若 `book_local_path` 為 `.epub`，用 `zipfile` 開啟 EPUB 檢查 manifest 中是否有 `cover-image` properties 或 id 含 `cover` 的圖片項目。
   - 若 EPUB 內有封面但本地未提取：輸出 `⚠️ [WARN] 原始 EPUB 含有封面圖片，但 final/cover.jpg 未提取`。
   - 若 config 無 `book_local_path` 或檔案不存在或非 EPUB：靜默略過。

4. **修復 `cleanup_temp_files()` 誤刪 `cover.jpg` 的缺陷**：
   - 在 final 目錄清理迴圈中，`cover.jpg` 與 `.md` 檔案同級白名單，跳過不刪。

5. **`qc_status.json` 擴充 `cover_check` 欄位**：
   - 新增 `"cover_check"` 欄位，值為 `"PASS"` / `"FAIL"` / `"SKIPPED"`。

### 1-C: 邊界條件與異常處理
- **邊界 1**：`report_path` 指向 `final/full_report.md`（無書名子目錄）→ `dirname` 為 `final/`，`cover.jpg` 查找路徑正確。
- **邊界 2**：`clean_temp` 啟動時不可刪除 `cover.jpg`（已在變更 C 中修復）。
- **邊界 3**：`run_single_qc_pass()` 回傳值由 `(passed_all, missing_chapters)` 變為 `(passed_all, missing_chapters, cover_status)` → 必須同步修改 `05_backfill.py` 和 `qc_check()` 中所有解構此回傳值的地方。

---

## Proposed Changes

### 1. `scripts/04_qc_check.py`
#### [MODIFY] [04_qc_check.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/04_qc_check.py)

**變更 A — `run_single_qc_pass()` 新增封面內嵌檢查**：

在「1. 失敗批次檢查」（L43-54）之後、「2. 標題與章節密度檢查」（L56）之前，插入：

```python
    # 0.5 封面圖片完整性檢查
    print("\n--- 0.5 Book Cover Image Integrity Check ---")
    cover_jpg_path = os.path.join(os.path.dirname(report_path), "cover.jpg")
    cover_status = "SKIPPED"
    if os.path.exists(cover_jpg_path):
        if '<img' in content and 'alt="書籍封面"' in content:
            print("✅ [PASS] 封面圖片已正確內嵌於報告中。")
            cover_status = "PASS"
        else:
            print(f"❌ [FAIL] 封面圖片存在於 {cover_jpg_path}，但報告中未偵測到內嵌的封面 img 標籤。")
            passed_all = False
            cover_status = "FAIL"
    else:
        print("ℹ️ [INFO] 本書無封面圖片 (cover.jpg)，已略過封面檢查。")
```

修改函式回傳值：

```python
    # 原本：return passed_all, missing_chapters
    return passed_all, missing_chapters, cover_status
```

**變更 B — `qc_check()` 同步接收三個回傳值，並增加 EPUB fallback WARN**：

修改 `qc_check()` 中所有呼叫 `run_single_qc_pass()` 的地方，從：
```python
passed_all, missing_chapters = run_single_qc_pass(report_path)
```
改為：
```python
passed_all, missing_chapters, cover_status = run_single_qc_pass(report_path)
```

在 backfill 迴圈內的呼叫也同步修改（約 L201）。

在寫入 `qc_status.json` 之前（約 L208），新增 EPUB fallback WARN：

```python
    # EPUB 來源一致性 WARN
    if cover_status == "SKIPPED":
        book_local_path = config.get("book_local_path", "")
        if book_local_path and book_local_path.lower().endswith(".epub") and os.path.exists(book_local_path):
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(book_local_path, 'r') as z:
                    try:
                        container_data = z.read('META-INF/container.xml')
                        root = ET.fromstring(container_data)
                        rootfile_path = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile').attrib['full-path']
                    except Exception:
                        rootfile_path = 'OEBPS/content.opf'
                    opf_data = z.read(rootfile_path)
                    opf_root = ET.fromstring(opf_data)
                    manifest = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')
                    if manifest is not None:
                        for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                            props = item.attrib.get('properties', '').lower()
                            item_id = item.attrib.get('id', '').lower()
                            href = item.attrib.get('href', '').lower()
                            if ('cover-image' in props or 'cover' in item_id) and any(href.endswith(ext) for ext in ('.jpg', '.jpeg', '.png')):
                                print(f"⚠️ [WARN] 原始 EPUB 含有封面圖片，但 final/cover.jpg 未提取。建議重新執行 01_init_notebook.py 提取封面。")
                                break
            except Exception:
                pass
```

**變更 C — `cleanup_temp_files()` 保護 `cover.jpg`**：

修改 final 目錄清理迴圈（約 L248-254），將 `cover.jpg` 加入白名單：

```python
                    for fname in os.listdir(target_final):
                        if fname.endswith(".md") or fname == "cover.jpg":
                            continue
                        fpath = os.path.join(target_final, fname)
                        # ...原有刪除邏輯不變
```

**變更 D — `qc_status.json` 新增 `cover_check` 欄位**：

```python
    json.dump({
        "passed_all": bool(passed_all and not missing_chapters),
        "book_title": book_title,
        "report_path": report_path,
        "cover_check": cover_status  # 新增
    }, qf, ensure_ascii=False, indent=2)
```

---

### 2. `scripts/05_backfill.py`
#### [MODIFY] [05_backfill.py](file:///g:/我的雲端硬碟/Project/Notebooklm/scripts/05_backfill.py)

同步修改解構 `run_single_qc_pass()` 回傳值的地方（若有直接呼叫），從二元組改為三元組：

```python
# 原本：passed_all, missing_chapters = run_single_qc_pass(...)
passed_all, missing_chapters, _cover_status = run_single_qc_pass(...)
```

---

### 3. `tests/test_epub_toc_and_assemble.py`
#### [MODIFY] [test_epub_toc_and_assemble.py](file:///g:/我的雲端硬碟/Project/Notebooklm/tests/test_epub_toc_and_assemble.py)

新增 4 個測試案例（全部使用 `tempfile.mkdtemp()` 建立隔離環境）：

#### test_qc_cover_present_and_embedded_passes
- 在暫存目錄建立 `cover.jpg`（隨意小圖即可）和包含 `<img src="data:image/jpeg;base64,..." alt="書籍封面" width="300" />` 的報告 `.md`。
- 同時建立最小化的 `batch_01.json`（含至少一個 H2 章節 + 核心概念 + 重點擷取，長度 > 1000 字元）避免觸發章節密度 FAIL。
- 呼叫 `run_single_qc_pass(report_path)` 取得 `(passed_all, missing_chapters, cover_status)`。
- 斷言 `cover_status == "PASS"`。

#### test_qc_cover_present_but_not_embedded_fails
- 在暫存目錄建立 `cover.jpg` 和**不含** img 標籤的報告 `.md`。
- 呼叫 `run_single_qc_pass(report_path)`。
- 斷言 `cover_status == "FAIL"` 且 `passed_all == False`。

#### test_qc_no_cover_skipped
- 在暫存目錄只建立報告 `.md`，不建立 `cover.jpg`。
- 呼叫 `run_single_qc_pass(report_path)`。
- 斷言 `cover_status == "SKIPPED"`，且封面檢查不影響 `passed_all` 結果。

#### test_cleanup_preserves_cover_jpg
- 在暫存目錄模擬 `final/{book_title}/` 結構，放入 `cover.jpg`、`report.md`、`temp_file.tmp`。
- 呼叫 `cleanup_temp_files()` 邏輯（或直接測試清理行為）。
- 斷言 `cover.jpg` 仍存在、`temp_file.tmp` 已被刪除。

---

### 4. 不修改的檔案
- `03_assemble_report.py` — 組裝邏輯不變。
- `01_init_notebook.py` — 封面提取邏輯不變。

---

## Verification Plan

### Automated Tests
```bash
python -m unittest discover tests
```
確保新增 4 項 + 既有全部測試 100% 通過。

### Manual Verification
- 對一本已有 `cover.jpg` 的書籍執行 `python scripts/04_qc_check.py --title "書名"` 驗證 PASS 輸出。
- 手動刪除報告中的 img 標籤後重跑，驗證 FAIL 輸出。
- 使用 `--clean-temp` 執行後確認 `cover.jpg` 未被刪除。
