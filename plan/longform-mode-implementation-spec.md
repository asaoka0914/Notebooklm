# NotebookLM 自動化系統擴充規格 v3：新增 Longform（無章節逐字稿）模式

## 重要說明：本版已對照真實原始碼校正，取代 v1 / v2

前兩版規格（v1、v2）在撰寫時對 NotebookLM 管線的實際運作方式做了錯誤假設。本版已實際讀取
`scripts/01_init_notebook.py`、`02_batch_generate.py`、`03_assemble_report.py`、`04_qc_check.py`、
`06_generate_book_summary.py`、`SKILL.md`、`config/book_config.yaml`、`plan/讀書報告核心概念.md`
八份真實檔案後重新設計，**修正幅度極大**，請完全以本版為準，v1/v2 僅供對照歷史演進。

### 四個推翻前兩版設計的關鍵事實

1. **步驟 0（`_is_chapter_candidate` 關鍵字表不一致）已經修好了，不需要再處理。**
   目前 `01_init_notebook.py` 的 `CHAPTER_MARKERS` 已是
   `("章","Chapter","chapter","篇","Part","part","PART","Unit","unit","Lesson","lesson","法則","夜","卷","節","讲","講","堂","課","课","Letters","Letter")`
   的完整集合，且 `_is_chapter_candidate()` 與 `_parse_toc_response()` 已共用同一份常數。

2. **批次機制不是「切原文字元/貼原文內容」，而是「傳遞真實存在於原文中的標題字串」給 NotebookLM 做 RAG 檢索。**
   `book_config.yaml` 的 `batch_strategy.batches` 長這樣：
   ```yaml
   batches:
     - batch: 1
       chapters: ["第1章　投資理財的威脅", "1-1　下次黑天鵝什麼時候還會再來？"]
   ```
   `02_batch_generate.py` 直接把 `chapters` 陣列 join 成 `ch_range_str`，塞進 Prompt：
   `"針對原書 {ch_range_str} 進行極度詳細、深度且不遺漏細節的繁體中文導讀報告撰寫。"`
   完全依賴 NotebookLM 的 RAG 架構去比對這些**逐字存在於已上傳來源文件中**的標題文字。
   **字元 offset 或整段貼原文都不是這個管線的運作模式，v1/v2 的相關設計全部作廢。**

3. **QC（`04_qc_check.py`）用 `config/ground_truth_toc.json` 做 1:1 覆蓋度 Hard-Fail 比對，此機制可直接沿用。**
   只要把逐字稿的錨點清單，用同一種 JSON 結構（`{"total_chapters": N, "chapters": [...]}`）寫進
   `ground_truth_toc.json`，現有比對邏輯（含繁簡同化、標點忽略、子字串比對）完全不需要修改就能運作。

4. **規範檔 `plan/讀書報告核心概念.md` 本來就是通用的**，其輸出模板用的是 `## [章節/段落名稱]` 這種
   泛用占位符，並非綁死「章節」兩字。**這份檔案完全不需要修改、也不需要拆成兩份。**

### 結論：真正需要改動的範圍比 v1/v2 想像的小得多

只需要：
- `01_init_notebook.py`：新增一個 `--source-type` 參數與一個新函式，讓逐字稿也能產出一份「章節標題」清單（只是這份清單的內容是從逐字稿本身抽出的錨點文字，而非 EPUB 目錄）。
- `02_batch_generate.py`：Prompt 組裝的地方依 `source_type` 做極小幅的文字分支（換幾句措辭），其餘（RateLimiter、重試、驗證 schema、帳號輪換）完全不動。
- `03_assemble_report.py`、`04_qc_check.py`、`06_generate_book_summary.py`：**預期不需要修改**（詳見下方逐一驗證）。

---

## 步驟 1：`01_init_notebook.py` 新增 `source_type` 支援

### 1.1 CLI 參數與 config 欄位

```python
parser.add_argument("--source-type", choices=["book", "transcript"], default=None,
                     help="來源類型，預設沿用 config 既有值或 book")
```

`config` 讀寫處新增：
```python
source_type = args.source_type or config.get("source_type", "book")
config["source_type"] = source_type  # 回寫，維持既有「回寫最新設定」慣例
```

不做 `auto` 自動偵測模式（v1/v2 都設計了 `auto`）。理由：現有 EPUB 解析與 NotebookLM TOC 詢問（`discover_actual_toc`）皆是針對書籍設計，逐字稿與書籍的輸入路徑（本地文字檔 vs. EPUB/PDF）本來就不同，由使用者明確指定 `--source-type transcript` 比嘗試自動判斷更可靠，也更符合「先求精簡」原則。

### 1.2 新增 `build_transcript_anchors()` 函式，取代 `extract_epub_toc()` / `discover_actual_toc()`

```python
def _split_paragraph_aligned(text: str, target_size: int) -> list:
    """依段落邊界（\n\n）切成接近 target_size 字元的大區塊，不重疊。"""
    paragraphs = text.split('\n\n')
    chunks, current, current_len = [], [], 0
    for p in paragraphs:
        current.append(p)
        current_len += len(p)
        if current_len >= target_size:
            chunks.append('\n\n'.join(current))
            current, current_len = [], 0
    if current:
        chunks.append('\n\n'.join(current))
    return chunks

def build_transcript_anchors(text_path: str, target_chunk_chars: int = 25000) -> list:
    """
    為逐字稿生成一份「章節標題」等效清單：每個元素都是逐字存在於原文中的錨點文字，
    可直接餵給既有的 chapters 陣列與 ground_truth_toc.json，不需另建新的資料結構。
    """
    with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    ts_pattern = re.compile(r'\d{1,2}:\d{2}:\d{2}')
    chunks = _split_paragraph_aligned(text, target_chunk_chars)
    anchors = []

    has_timestamps = len(ts_pattern.findall(text)) >= 5
    for chunk in chunks:
        if has_timestamps:
            m = ts_pattern.search(chunk)
            anchor = m.group(0) if m else chunk.strip().split('\n', 1)[0][:20]
        else:
            first_line = chunk.strip().split('\n', 1)[0].strip()
            anchor = first_line[:20] if len(first_line) > 20 else first_line
        anchors.append(anchor)

    return anchors
```

**設計原則說明**：
- 每個 anchor 必須是**逐字存在於原文中的文字**（時間戳字串，或段落開頭的原文短句），這樣 NotebookLM 的 RAG 才能實際定位，功能上等同於書籍模式的章節標題。
- 切批策略採「大區塊、不重疊」，`target_chunk_chars` 預設 25000 字元（22 萬字約產生 8～9 個 anchor），對應另一位 agent 提出的「批次數從 25 砍到 7～8」的修正建議，且不重疊，從根本避免去重問題。
- 這個函式故意做得很簡單（只有段落邊界切分 + 抓時間戳/開頭短句），沒有做講者偵測、沒有貪婪打包演算法——這些複雜度在 v1/v2 中被另一位 agent 正確指出是不必要的過度工程。

### 1.3 在 `init_notebook()` 中插入分支

在原本 `gt_chapters = extract_epub_toc(book_local_path)` 與 `discover_actual_toc()` 的呼叫之前插入：

```python
if source_type == "transcript":
    if not (book_local_path and os.path.exists(book_local_path)):
        print("❌ [Error] transcript 模式需要 --book-path 指向本機逐字稿文字檔（.txt）。")
        sys.exit(1)
    chunk_chars = config.get("transcript_chunk_chars", 25000)
    gt_chapters = build_transcript_anchors(book_local_path, target_chunk_chars=chunk_chars)
    default_batch_size = 1   # 每個 anchor 已代表一個完整大區塊，一批一個 anchor 即可
else:
    gt_chapters = []
    if book_local_path and os.path.exists(book_local_path):
        # ...原本 EPUB 封面/TOC 解析邏輯，完全不動...
    if not gt_chapters:
        # ...原本 discover_actual_toc 呼叫，完全不動...
    default_batch_size = 2
```

原本寫死的 `plan_batches(gt_chapters, batch_size=2)` 改為：
```python
auto_batches = plan_batches(gt_chapters, batch_size=default_batch_size)
```

**`plan_batches()` 函式本身完全不需要修改**——它只是把一份字串清單依數量分組，本來就與內容類型無關。

### 1.4 逐字稿的「來源上傳」

`init_notebook()` 現有的「上傳電子書來源檔案」區塊（`app(["source", "add", notebook_id, "--file", book_local_path, "--wait"])`）不區分副檔名，`.txt` 檔案應可直接沿用同一段程式碼上傳。**執行前請先手動測試 `nlm source add` 對 `.txt` 檔案的相容性**，若 NotebookLM 來源上傳不支援 `.txt`，需先將逐字稿轉存為 `.pdf` 或其他支援格式再上傳（轉檔本身不在此規格範圍內，屬於前置資料準備）。

---

## 步驟 2：`02_batch_generate.py` 的 Prompt 分支（唯一需要修改的地方）

在 `run_batch_generation()` 組 Prompt 的地方，新增 `source_type` 讀取與分支：

```python
source_type = config.get("source_type", "book")
...
for b in batches:
    ...
    if source_type == "transcript":
        prompt = (
            f"請嚴格依據來源檔案《讀書報告核心概念.md》中的撰寫規範與原則，"
            f"針對這份英文對話訪談逐字稿中，對應以下錨點段落：{ch_range_str}，"
            f"進行極度詳細、深度且不遺漏細節的繁體中文導讀報告撰寫。\n"
            f"【逐字稿專屬要求】：\n"
            f"1. 小節標題請逐字使用上述錨點文字本身（不要意譯、改寫或翻譯錨點文字），以利後續章節涵蓋度比對。\n"
            f"2. 請額外保留重要對話情境與金句，並附上金句的中文翻譯（原文以括號附註）。\n"
            f"3. 若原文有標示發言者，請在對應重點旁標明。\n"
            f"【重要輸出限制】：請將所有輸出配額完全集中於豐富、詳盡的段落細節與洞見，"
            f"嚴禁在文中插入任何腳註引用標號（例如切勿出現 [1]、[2] 或 [1-3] 等數字標籤），"
            f"亦切勿產生任何原文引用附錄。\n\n"
        )
    else:
        prompt = (
            f"請嚴格依據來源檔案《讀書報告核心概念.md》中的撰寫規範與原則，"
            f"針對原書 {ch_range_str} 進行極度詳細、深度且不遺漏細節的繁體中文導讀報告撰寫。\n"
            f"【重要輸出限制】：請將所有輸出配額完全集中於豐富、詳盡的章節細節與數據分析。"
            f"嚴禁在文中插入任何腳註引用標號（例如切勿出現 [1]、[2] 或 [1-3] 等數字標籤），亦切勿產生任何原文引用附錄。\n\n"
        )
    if previous_summary:
        prompt += ( ... 原本的前情提要邏輯，不分流，完全不動 ... )
```

**其餘所有邏輯（`RateLimiter`、`run_query_via_cli` 的中途認證恢復/限流退避/帳號輪換、`validate_schema`、`extract_summary`、中斷續傳、`failed_batches.json` 寫入）完全不需要修改**，因為這些都與內容類型無關，本來就是通用機制。

**重點提醒（步驟 2.1 明確要求）**：Prompt 裡明確要求「小節標題請逐字使用錨點文字本身」，這是為了讓步驟 3 的 QC 覆蓋度比對能夠成立——如果 NotebookLM 自行意譯或重新命名小節標題，`ground_truth_toc.json` 的 1:1 比對會產生大量假性缺漏（False Missing）。

---

## 步驟 3：`03_assemble_report.py`、`04_qc_check.py`、`06_generate_book_summary.py` —— 預期不需修改，但需驗證

逐一比對現有程式碼與 transcript 模式的相容性：

| 腳本 | 相關邏輯 | 對 transcript 模式的影響 | 結論 |
|---|---|---|---|
| `03_assemble_report.py` | `normalize_headings()` 只對特定書籍標題格式（Part/第X章/純數字開頭）做正規化重寫，其餘格式一律原樣通過 | anchor 文字（時間戳或原文短句）不會命中任何規則分支，會被原樣保留，只要 NotebookLM 確實輸出 `## {anchor}` 格式的 H2 標題即可正確被 `re.split(r'\n(?=##\s+)', ...)` 切開 | **不需修改**，但需在真實測試中確認 NotebookLM 有依規範檔模板輸出 `## [段落名稱]` 格式 |
| `04_qc_check.py` | `_normalize()` 對 `第 N 章` 做中文數字轉換屬於加分規則，其餘為通用標點移除；Ground Truth 1:1 比對用子字串雙向比對，容忍度高 | anchor 文字不會命中 `第N章` 特殊轉換，但一般標點正規化仍適用，比對邏輯正常運作 | **不需修改** |
| `04_qc_check.py` | `is_part_header` 判斷（Part/篇/卷/前言/總結/附錄）用於豁免 1000 字長度限制 | anchor 文字不會命中，因此每個 anchor 段落仍會被檢查是否 ≥1000 字——但因為 transcript 每批對應 25000 字原文，產出報告篇幅遠超過 1000 字門檻，不會有問題 | **不需修改** |
| `06_generate_book_summary.py` | `check_qc_prerequisite()` 只檢查 `qc_status.json` 的 `passed_all` 與書名是否相符，`build_book_summary_prompt()` 的措辭用「整本書」 | 邏輯與 `source_type` 無關，直接可用；「整本書」措辭對逐字稿而言語意上稍不精準但不影響功能 | **功能上不需修改**；若想要措辭更精準，可選配（非必要）將 prompt 中「整本書《{book_title}》」改為「這份內容《{book_title}》」，屬於錦上添花，不影響驗收 |

**驗收時務必實際跑一次，確認上表的「預期不需修改」是否成立**，若真實輸出出現以下狀況需回頭修正對應腳本：
- NotebookLM 沒有依規範檔輸出 H2 標題格式 → 需要在步驟 2 的 Prompt 裡加一句更明確的格式範例。
- Ground Truth 比對出現大量假性缺漏 → 檢查是否為 NotebookLM 意譯了 anchor 文字，可能需要放寬 `04_qc_check.py` 的比對容忍度（例如取 anchor 前 8 個字做子字串比對而非全字串）。

---

## 步驟 4：`plan/讀書報告核心概念.md` —— 不修改

此檔案的輸出模板本來就使用泛用占位符 `## [章節/段落名稱]`，`### 📌 核心概念`、`### 💡 重點擷取`、`### 📋 涵蓋度自我檢查清單` 皆與內容類型無關。**不需要新建《訪談報告核心概念.md》，也不需要拆分共用/專屬區塊**——v1/v2 在這點上想得太複雜。

---

## 明確不在本次範圍內（沿用 v2 的判斷，仍然成立）

- 不做語者分離（diarization）音訊辨識，僅處理逐字稿文字檔中既有的講者標籤（若有）。
- 不做批次重疊與去重機制（本版透過不重疊的大區塊切分從根本避免）。
- 不做 `auto` 自動偵測 `source_type`（見步驟 1.1 說明）。
- 不新增獨立 skill 或獨立程式碼庫，不修改 `讀書報告核心概念.md`，不修改 `03_assemble_report.py` / `04_qc_check.py` / `06_generate_book_summary.py`（除非步驟 3 的真實驗收發現需要）。

---

## 驗收測試計畫

1. **回歸測試**：至少一本既有書籍（如 `你沒有學到的資產配置`）重新跑一次 `01_init_notebook.py`（不加 `--source-type` 或明確加 `--source-type book`），確認新增的分支邏輯未破壞既有行為，`gt_chapters`、`batch_strategy.batches`、`ground_truth_toc.json` 內容與修改前一致。
2. **真實資料驗收**：準備一份約 22 萬字的英文 Podcast 逐字稿 `.txt` 檔案，執行：
   ```powershell
   python scripts/01_init_notebook.py --book-path "逐字稿絕對路徑.txt" --title "逐字稿標題" --source-type transcript
   python scripts/02_batch_generate.py
   python scripts/03_assemble_report.py
   python scripts/04_qc_check.py --auto-backfill
   python scripts/06_generate_book_summary.py
   ```
   觀察：
   - `build_transcript_anchors()` 產出的 anchor 數量是否落在 7～9 個左右（對應 25000 字元/批的預期）。
   - 每批輸出是否穩定為繁體中文、有無金句翻譯與發言者標註。
   - `04_qc_check.py` 的 Ground Truth 1:1 比對是否正常通過（沒有大量假性缺漏）。
   - `06_generate_book_summary.py` 是否能正常產出 `scratch/temp_book_summary.md`。
3. **依實測結果校準 `transcript_chunk_chars`**：若 22 萬字產出的單批內容深度不足或 NotebookLM 回應品質下降，調整 `config.get("transcript_chunk_chars", 25000)` 的預設值後重跑，不可跑測前就寫死定案。

---

## 附註：全域技能同步

依 `handoff.md` 記載，本專案的 Python 腳本修改完成後，慣例會同步更新至全域技能目錄
`~/.gemini/config/skills/book-reader/`（Windows 路徑：`C:\Users\AsaokaHTPC\.gemini\config\skills\book-reader\`）。
執行本規格的 agent 完成修改並通過驗收後，請比照慣例同步該目錄，避免下次透過技能觸發時仍載入舊版腳本。
