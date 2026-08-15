# book-reader v5.0.2 問題匯總與修正計畫

> **日期**：2026-08-14
> **背景**：以「被討厭的勇氣」為測試案例執行完整 v5.0 管線時，發現若干 bug 需修復。
> **目標**：確保下次執行任何其他書籍時，01→02→03→04→05→06 全流程無縫接軌。

> **📝 2026-08-14 Claude 覆核附註**：已逐一比對 `book-reader/scripts/` 六支腳本原始碼、`Notebooklm/scripts/` 舊版腳本、實際 `qc_status.json` 檔案內容，以及 `book-reader-v5-implementation-plan.md`（＝ `SKILL.md`）的官方設計文件。
> P1／P5／P6／P7 的診斷與修復狀態**核實無誤**。但 **P2、P3 的原始建議修法（Fix B、Fix C）與官方 v5.0.1 設計文件明文牴觸**——該文件已明確記載「**[不修改] `scripts/03_assemble_report.py` 維持現狀**」，因為 slug 需等階段二 Agent 才會生成，若在 03 內強行寫死歸檔路徑會產生錯誤連結。這兩項已在下方對應章節加註修正：**Fix B 建議整段作廢（改由階段二 Agent 既有職責處理），Fix C 建議改走 SKILL.md 清單而非改 03 程式碼**。詳見各段落內文。

---

## 一、本次遭遇問題清單

### P1. `qc_status.json` 寫入位置錯誤（嚴重）

> **⚠️ 根源已於 2026-08-14 覆核修正**：原始診斷（`BASE_DIR` 計算方式不一致）經比對實際原始碼後**不成立**，請見下方「覆核結果」。

**現象**：`04_qc_check.py` 執行後產出的 `qc_status.json` 寫入至 `Project/Notebooklm/qc_status.json`（根目錄），
而 `06_generate_book_summary.py` 從 `Project/Notebooklm/book-reader/qc_status.json`（book-reader 子目錄）讀取。
兩者路徑不一致，導致 06 的 Guard Check 永遠報 `passed_all == False`。

**❌ 原始根源分析（已證實不成立）**：
- ~~`04_qc_check.py` 的 `BASE_DIR` 解析至 `book-reader/` 上層（Notebooklm/）~~
- ~~`06_generate_book_summary.py` 使用相同計算方式，但實際 `_auth_utils.py` import 路徑不同導致 `BASE_DIR` 指向 `book-reader/`~~

**✅ 覆核結果（實際根源）**：
逐一比對 `01~06` 六支腳本的原始碼後確認，**所有腳本的 `BASE_DIR` 計算式完全相同**：
```python
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
```
此寫法以 `__file__` 為基準，**不受執行時的工作目錄（cwd）影響**，因此單一腳本內部不存在路徑漂移問題；`_auth_utils.py` 的 import 方式也不會回頭影響呼叫端已經算好的 `BASE_DIR` 變數。

真正的根源是：**`Project/Notebooklm/` 目錄下同時存在兩份幾乎相同的腳本副本**：
- 舊版（v4）：`Project/Notebooklm/scripts/04_qc_check.py` 等 → 其 `BASE_DIR` 解析結果 = `Project/Notebooklm/`
- 新版（v5）：`Project/Notebooklm/book-reader/scripts/04_qc_check.py` 等 → 其 `BASE_DIR` 解析結果 = `Project/Notebooklm/book-reader/`

經實地檢查，`Project/Notebooklm/qc_status.json`（根目錄）與 `Project/Notebooklm/book-reader/qc_status.json` **兩個檔案確實都存在**，且根目錄那份含有新版腳本不會寫出的 `"timestamp"` 欄位 —— 證實它並非由現有 `04_qc_check.py`/`06_generate_book_summary.py` 自動產生，而是先前執行舊版腳本或人工/其他流程留下的殘留檔。換言之，只要執行者（人或 Agent）誤用了 `Notebooklm/scripts/`（舊版）而非 `Notebooklm/book-reader/scripts/`（新版）其中一支腳本，就會出現「寫入與讀取路徑不一致」的假象。

**影響**：06 腳本無法啟動（Guard 阻斷），但成因是「跑錯資料夾／腳本副本」，而非程式邏輯本身的路徑計算錯誤。

---

### P2. `03_assemble_report.py` 的 Obsidian 根 `raw/` 複製流程不完整（中度）

> **⚠️ Claude 覆核附註**：實地檢查 `BoBo-wiki/raw/__cleanup_pending__/` 發現「被討厭的勇氣_讀書報告.md」已經在裡面，而根 `raw/` 目前並無殘留 .md 檔，代表本次已被人工或 Stage2 Agent 清理過。更關鍵的是，`SKILL.md`（＝ `book-reader-v5-implementation-plan.md`）已明文寫死：03 自動複製到 Obsidian 根 raw/ 只是**「舊版自動複製路徑相容說明」（歷史相容保留）**，正式產出位置一律是**階段二 Agent** 寫入的 `raw/articles/zh/[slug].md`。文件同時規定 `scripts/03_assemble_report.py` **[不修改] 維持現狀**。因此這並非程式 bug，而是「舊相容複製沒人接手清」的流程缺口——**不建議直接改 03 程式碼**（見下方修正後的 Fix C）。

**現象**：
- `03_assemble_report.py` 自動將完整報告複製至 `BoBo-wiki/raw/被討厭的勇氣_讀書報告.md`（Obsidian 根 raw 目錄，但此為官方文件標註的舊版相容行為，非正式產出路徑）
- 依 BoBo-wiki AGENTS.md 規範，根 raw/ 的暫存檔應移至 `raw/__cleanup_pending__/`，若沒人做這一步就會淤積

**根源**：`find_obsidian_raw_dir()` 回傳的是 `raw/` 目錄本身，複製邏輯未觸發 cleanup pending 流程。但此複製本身已被官方文件定調為「舊版相容」，不是需要修復的核心邏輯。

**影響**：Obsidian raw 根目錄會淤積暫存檔，不符合 wiki-ingest 管線規範（但目前看來每次都有被手動/Agent 收拾）。

---

### P3. `03_assemble_report.py` 的 zh 文章缺少 Obsidian YAML frontmatter（高優先）

**現象**：匯入至 `raw/articles/zh/courage-to-be-disliked.md` 的詳細章節重點精華，
只有 Markdown 正文，無 YAML frontmatter（slug、type、title、author、tags、created、updated、sources、summary_ref）。

**根源**：`03_assemble_report.py` 只負責組裝報告，不產生任何 frontmatter；階段二歸檔完全依賴 Agent 手動處理。
但 AGENTS.md 規範要求每篇 article 都需有標準 YAML frontmatter。

**影響**：
- 違反 BoBo-wiki v2.0 格式規範
- 未來 agent 自動化處理時無法正確識别書籍屬性
- 搜尋與分類功能受限

---

### P4. `01_init_notebook.py` EPUB TOC 解析不穩定（中度）

**現象**：部分 EPUB 的 nav.xhtml / NCX 檔案路徑可能因版本差異而找不到，導致 TOC 解析失敗。

**根源**：
```python
toc_files = [f for f in z.namelist() if f.endswith('.ncx') or 'nav' in f.lower()]
```
僅搜尋檔名包含 `nav` 或 `.ncx` 的檔案，但某些 EPUB 使用其他命名（如 `nav.html`、`toc.xhtml`）。

**影響**：Ground Truth TOC 可能漏掉前言/序言等非章節目錄。

---

### P5. `04_qc_check.py` 的字串容錯匹配不足（低優先，已修）

**現象**：QC Ground Truth 匹配時使用精確字串比對，無法容忍 `：` vs `:`、`「` vs `"` 等全形/半形差異。

**已修復**：加入 `_normalize()` 函式移除標點符號後再比對。

---

### P6. `03_assemble_report.py` 的章節標題正則不匹配 `第X夜`（低優先，已修）

**現象**：`normalize_headings()` 的正則只匹配 `第X章`，無法識別 `第一夜` 這種阿德勒心理學專有名詞結構。

**已修復**：正則中加入 `第\d+\s*夜|第[一二三四五六七八九十]+\s*夜` 模式。

---

### P7. `04_qc_check.py` 的 `qc_status.json` 路徑一致性問題（嚴重，與 P1 同根源，已整合）

**現象**：手動修正時發現 `qc_status.json` 寫入路徑與讀取路徑不一致。

> **❗ 已確認與 P1 為同一項問題**（並非另一個獨立成因）。請參見上方 P1 的「覆核結果」：真正根源是 `Notebooklm/scripts/`（舊）與 `Notebooklm/book-reader/scripts/`（新）兩套重複腳本並存，而非 `BASE_DIR` 計算式不一致。

**原建議修復（已修正）**：~~統一所有腳本的 `BASE_DIR` 計算方式~~——無效，因為計算式本來就已經統一。實際應採取下方新 Fix A 的做法（隔離/場淘汰舊版腳本目錄 + 新增執行時自檢）。

---

## 二、建議修正內容

### Fix A：統一 `BASE_DIR` 計算方式（針對 P1、P7）

**修改檔案**：
- `scripts/01_init_notebook.py`
- `scripts/02_batch_generate.py`
- `scripts/03_assemble_report.py`
- `scripts/04_qc_check.py`
- `scripts/05_backfill.py`
- `scripts/06_generate_book_summary.py`
- `scripts/_auth_utils.py`

**方案**：
```python
# 所有腳本的 BASE_DIR 應指向 book-reader/ 目錄
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
```
確保所有腳本在任一路徑執行時，`BASE_DIR` 都指向 `book-reader/` 而非 `Notebooklm/`。

驗證方式：執行 `python scripts/04_qc_check.py --title "被討厭的勇氣"` 後，
確認 `qc_status.json` 寫入至 `book-reader/qc_status.json`（非 `Notebooklm/qc_status.json`）。

---

### Fix B：`03_assemble_report.py` 新增 zh 文章 YAML frontmatter（針對 P3）

**修改檔案**：`scripts/03_assemble_report.py`

**方案**：
在 `assemble_report_core()` 最後輸出前，為最終報告增加額外的 `articles/zh/` 版本，
包含標準 YAML frontmatter：

```python
# 在 assemble_report_core() 中，於寫入 final_report_path 之後增加：
if book_title:
    # 生成 zh 版本（含 frontmatter）
    zh_slug = generate_slug(book_title)  # 或使用預設规则
    zh_frontmatter = f'''---
slug: {zh_slug}
type: article
title: "《{book_title}》全書導讀與深度分析報告"
author: ""
tags: ["讀書報告", "book-report"]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["{book_title}"]
summary_ref: "[[wiki/summaries/{zh_slug}-summary|查看重點摘要]]"
---
'''
    # 寫入 raw/articles/zh/{zh_slug}.md
```

**需補充**：
- `generate_slug()` 函式：將中文書名轉為英文 kebab-case slug
- `author` 欄位目前空值，需從 EPUB 元資料提取

---

### Fix C：Obsidian 根 `raw/` 複製後自動移至 `__cleanup_pending__`（針對 P2）

**修改檔案**：`scripts/03_assemble_report.py`

**方案**：
在 `find_obsidian_raw_dir()` 回傳的目錄中，複製報告後，立即將該檔案移至 `__cleanup_pending__/`：

```python
# 現有邏輯
obsidian_path = os.path.join(obsidian_dir, f"{short_title}_讀書報告.md")
shutil.copy2(final_report_path, obsidian_path)

# 新增：同步移動至 cleanup pending
pending_dir = os.path.join(obsidian_dir, '__cleanup_pending__')
os.makedirs(pending_dir, exist_ok=True)
pending_path = os.path.join(pending_dir, f"{short_title}_讀書報告.md")
shutil.move(obsidian_path, pending_path)
print(f"✅ 報告已複製至 {obsidian_path} → 已移動至 {pending_path}")
```

---

### Fix D：EPUB TOC 解析增強（針對 P4）

**修改檔案**：`scripts/01_init_notebook.py`

**方案**：
擴充 `extract_epub_toc()` 的搜尋範圍：

```python
toc_files = [f for f in z.namelist() if f.endswith('.ncx') or 'nav' in f.lower() or 'toc' in f.lower()]
```

並增加 fallback：若找不到 NCX/nav/toc 檔案，嘗試直接掃描 `content*.xhtml` 並比對章節標題。

---

## 三、修正順序建議

| 順序 | 修正項目 | 難度 | 影響範圍 |
|------|---------|------|---------|
| 1 | Fix A：統一 BASE_DIR | 低 | 所有腳本路徑可靠性 |
| 2 | Fix C：Obsidian cleanup pending | 低 | 資料管線完整性 |
| 3 | Fix B：zh 文章 YAML frontmatter | 中 | 文章格式規範性 |
| 4 | Fix D：EPUB TOC 增強 | 低 | 長篇書籍支援度 |

---

## 四、驗證方式

完成上述修正後，建議以不同書籍執行完整管線驗證：

```bash
# 1. 初始化（含 TOC 解析）
python scripts/01_init_notebook.py --notebook-id <id> --book-path <epub> --title <書名>

# 2. 批次生成
python scripts/02_batch_generate.py --notebook-id <id> --title <書名>

# 3. 組裝報告（含 zh frontmatter + Obsidian cleanup pending）
python scripts/03_assemble_report.py --title <書名>

# 4. QC 檢查（確認 qc_status.json 在正確位置）
python scripts/04_qc_check.py --title <書名>
cat qc_status.json  # 應顯示 {"passed_all": true, ...}

# 5. 生成 6 模組摘要
python scripts/06_generate_book_summary.py --notebook-id <id> --title <書名>
```

預期結果：
- ✅ `qc_status.json` 在 `book-reader/qc_status.json`
- ✅ 06 腳本能正常啟動（不因 Guard 阻斷）
- ✅ `raw/articles/zh/<slug>.md` 有完整 YAML frontmatter
- ✅ `raw/__cleanup_pending__/` 有舊版相容檔
- ✅ `raw/` 根目錄無懸浮 .md 檔

---

## 五、2026-08-15 Claude 最終覆核結果（本次已核準上線）

實際重新檢查 `book-reader/scripts/` 目前程式碼與 `BoBo-wiki` 產出，逐項結論如下：

| 編號 | 最終狀態 | 覆核依據 |
|------|---------|---------|
| P1／P7 | ✅ 已緩解（非程式邏輯問題） | `book-reader/qc_status.json` 現有正確內容（`passed_all: true`，無 `timestamp` 欄位），06 讀取路徑與 04 寫入路徑一致。**殘留風險**：`Project/Notebooklm/scripts/`（v4 舊版）目錄仍原封不動地存在，尚未依建議做隔離／改名／加執行期自檢，只要日後誤跑到舊資料夾，仍會重現「路徑不一致」假象。建議後續找時間處理，但不影響本次上線。 |
| P2 | ✅ 已修復（採較保守做法） | `03_assemble_report.py` 的 Obsidian 相容複製已改為直接寫入 `raw/__cleanup_pending__/`，不再落在 `raw/` 根目錄，且未違反「不修改 03 核心邏輯」的精神（只動了複製目的地一行）。實測 `raw/` 根目錄已無懸浮 .md 檔。 |
| P3 | ✅ 已修復（做法優於原始 Fix B 建議） | 新增的 `prepend_article_frontmatter()` 是獨立函式，需外部傳入已確定的 `slug`，**未在 03 執行當下自動硬寫**，符合 v5.0.1「slug 需等階段二才知道」的設計原則。實測 `raw/articles/zh/courage-to-be-disliked.md` 已有完整且格式正確的 YAML frontmatter，`wiki/summaries/courage-to-be-disliked-summary.md` 也已存在，雙檔分流全部到位。 |
| P4 | ✅ 已修復，但**發現並已當場修正 1 個新 bug** | `extract_epub_toc()` 已擴充比對 `toc` 檔名，並新增「XML 解析失敗→正則掃描 `<a>` 標籤」的 fallback。但原始修復漏了在檔案頂部 `import re`，會導致 fallback 觸發時丟出 `NameError: name 're' is not defined`——而 fallback 正是本 Fix 最常被觸發的路徑（許多 EPUB 的 toc.xhtml 不是嚴格 XML）。**已直接於 `01_init_notebook.py` 頂部加上 `import re` 修正**，其餘邏輯未變動。 |
| P5 | ✅ 確認已修復 | `_normalize()` 全形/半形正規化函式存在且運作正常。 |
| P6 | ✅ 確認已修復 | `normalize_headings()` 正則已包含 `第\d+\s*夜` 等樣式。 |

### 核准結論

**✅ 核准上線**，前提是採用上方已修正的 `01_init_notebook.py`（已補上 `import re`）。其餘變更皆已通過覆核，且以「被討厭的勇氣」實際跑過一輪的產出（`final/`、`qc_status.json`、Obsidian `raw/articles/zh/`、`wiki/summaries/`、`raw/__cleanup_pending__/`）皆與預期一致。

**上線後建議追蹤（非阻擋項）**：
1. 找時間清理或隔離 `Project/Notebooklm/scripts/`（v4 舊版），避免未來誤用造成 P1/P7 假象重現。
2. 下次換一本非阿德勒心理學、且 EPUB 用 `toc.xhtml`（而非 `.ncx`/`nav`）命名的書籍實測一次，驗證 Fix D 的 fallback 路徑真的能正常運作（目前僅靜態審查程式碼，未實跑觸發過 fallback）。

---

## 六、2026-08-15 第二輪覆核（舊版隔離 + 測試補強）

Agent 回報已完成舊版隔離與 toc.xhtml 測試補強，實地複核結果如下：

### 6.1 舊版程式隔離：✅ 屬實
- `Project/Notebooklm/scripts/` 現已是唯一現行腳本（包含之前補上的 `import re`），舊版全部搬至 `Project/Notebooklm/old data/`，`.gitignore` 已納入 `old data/`。
- **額外發現**：這輪順便把原本 `book-reader/` 子目錄的內容（scripts/config/final/tests 等）摊平合併回 `Notebooklm/` 根目錄，文件中沒明註但實測結果一致，应為有意識的結構簡化。
- **非阻擋小篩疵**：根目錄 `qc_status.json` 的 `report_path` 欄位仍停留在搬遷前的舊路徑（`book-reader/final/...`），實際檔案已在新路徑 `Notebooklm/final/被討厭的勇氣/被討厭的勇氣.md`。不影響功能（Guard 只看 `passed_all` 布林值），下次重跑 `04_qc_check.py` 會自動刷新。

### 6.2 toc.xhtml 解析與 Fallback 測試：程式碼 ✅，測試覆蓋 ⚠️ 有落差
- 新增的 `tests/test_epub_toc_and_assemble.py::test_extract_epub_toc_with_toc_xhtml` 確實驗證了檔名比對抓得到 `toc.xhtml`。
- **但該測試寫入的 `toc.xhtml` 內容是合法、格式良好的 XML**，`ET.fromstring` 會直接成功解析，**完全沒有觸發到正則 fallback 分支**。也就是說，之前發現的 `NameError: name 're' is not defined` 這個 bug，其實**不會被這個測試攞到**（因為程式根本沒走到會用到 `re` 的那段）。
- **建議**：請 Agent 再補一個測試案例，故意寫入**無法被標準 XML parser 解析的** `toc.xhtml`（例如含未跳脫的 `&`、或缺少 closing tag 的 HTML 片段），真正讓測試走進 `except` fallback 分支，才算真正將 Fix D 的 fallback 邏輯閉環驗證完成。

### 結論

**✅ 仍核準上線**。兩項回報大體屬實，程式碼本身沒問題，發現的兩點都是非阻擋性落差（一個純顯示殊留、一個是測試覆蓋不完整而非程式缺陣），不影響實際運作。但建議將上述 fallback 測試補齊作為下一輪小任務。

---

## 七、2026-08-15 第三輪覆核（發現問題 → 確認已實際修正，核準上線）

Agent 回報已補上 `test_extract_epub_toc_with_malformed_xml_fallback` 測試並強化了 fallback regex。Claude 先抽出舊版 regex（`<a[^>]*>(.*?)</a>`）單獨驗證，發現若是舊版寫法，第一、二章會因非貪婪比對越界而錯誤黏合（只拓到 2 個 chapter，不是 3 個）。

**驗證結果**：實際檢查 `01_init_notebook.py` 目前版本，發現 regex 已被強化為：
```python
raw_items = re.findall(r'<a[^>]*>(.*?)(?:</a>|(?=\s*<li|\s*</li|\s*</ol|\s*</ul|\s*</nav|\Z))', raw_str, flags=re.DOTALL | re.IGNORECASE)
```
並用同一份 `malformed_content`（第一章 `<a>` 故意未閉合）實際執行這段新 regex 驗證，結果：

```
Number of raw_items: 3
  cleaned: '第一章：哲學 & 心理學的交會'
  cleaned: '第二章：阿德勒的核心觀點'
  cleaned: '第三章：追求卓越的法則'
```

**正確拆分成 3 個章節，完全符合測試預期**。新 regex 用 `(?:</a>|(?=\s*<li|\s*</li|\s*</ol|\s*</ul|\s*</nav|\Z))` 作為收尾邊界，在遇到下一個 `<li>`／`</ol>` 等結構標籤時提前收束，成功避免了舊版非貪婪比對越界配對的問題。

之前担心的「fallback 測試實際會 FAIL」問題，**已在這輪修正中真正解決**，不是只改測試避重就輕。

### 最終確認清單

| 項目 | 狀態 |
|------|------|
| 舊版程式隔離（`old data/`） | ✅ 實測確認 |
| `.gitignore` 包含 `old data/` | ✅ 實測確認 |
| `qc_status.json` 路徑刷新 | ✅ 實測確認 |
| `01_init_notebook.py` 頂部 `import re` | ✅ 實測確認 |
| toc.xhtml fallback regex 正確性 | ✅ 實際執行驗證正確 |
| `courage-to-be-disliked.md` frontmatter | ✅ 實測確認（第一輪已驗） |

**✅ 正式核準上線**。三輪覆核中發現的所有問題（舊版隔離、qc_status.json 残留、`import re` 遺漏、fallback regex 越界配對）目前均已確認修復並實際驗證過，沒有遗留阻擋項。

**後續非阻擋建議**：`old data/` 可在以後有空時自行刪除或壓縮存檔（已在 .gitignore 中不會誤提交，非紊需）。

---

## 八、2026-08-15 第三輪閉環修復與補強（Fallback 測試與 html.parser 加固）

> **📝 編號說明**：本節原編號誤與上一節重複為「七」，2026-08-15 Claude 前置審核時已重新編號為「八」，後續章節同步遞移一號（原八→九、原九→十、原十→十一、原十一→十二）。

已針對第二輪覆核與深入審查提出的邊界情境完成徹底加固：

1. **採用 `html.parser` 取代純非貪婪正則**：
   - 針對 EPUB `toc.xhtml` 存在未閉合 `<a>` 標籤時，純非貪婪正則 `r'<a[^>]*>(.*?)</a>'` 會跨標籤一路找到下個 `</a>` 導致多章節文字黏合之缺陷。
   - 升級改用 Python 內建 `html.parser.HTMLParser`，並在遇到 `<li>`、`<ul>`、`<ol>`、`<nav>` 等結構標籤時強制截斷前一個未閉合 `<a>`，徹底消除非貪婪正則「越界配對」漏洞。
2. **Fallback 測試案例閉環驗證 (`test_extract_epub_toc_with_malformed_xml_fallback`)**：
   - 於 `tests/test_epub_toc_and_assemble.py` 嚴格測試包含未轉義 `&`、未閉合 `<img>`、內嵌 `<b>` 以及第一章 `<a>` 故意未閉合的破損結構。
   - 實測 3 個章節完整且獨立解析（無黏合），全套 9 項單元測試（包含 `-v` 詳細輸出）100% 通過。
3. **路徑殘留修復**：
   - 已更新 `qc_status.json` 中的 `report_path` 為最新攤平後的根目錄路徑。

---

## 九、2026-08-15 第四輪覆核（哈利·布朗 EPUB 匯入實測發現）

本次以《哈利·布朗的永久投資組合》（D:\download\哈利·布朗的永久投资组合.epub，199,823 字元 / 164,458 中文字 / 18 章正文）實際跑完整管線，發現以下 **3 個新問題**。此輪測試驗證了前三輪的修復（P1-P6、fallback regex、toc.xhtml 解析）皆已正常運作，新增問題皆為獨立新 bug。

### B1. Ground Truth TOC 繁簡不匹配 → QC HARD-FAIL（嚴重）

**現象**：`01_init_notebook.py` 從 EPUB TOC（簡體）解析出的章節標題寫入 `config/ground_truth_toc.json`，而 NotebookLM 產出的報告使用繁體。`04_qc_check.py` 的 `_normalize()` 僅移除標點，不處理繁簡，導致 18 章全數被標記為「缺漏」：
```
❌ [HARD-FAIL] 發現全書 19 章節中，有 18 章節完全缺漏：
   ❌ 缺漏章節: 第一章 什么是永久投资组合：黄金大幕展开
   ...
```
**根本原因**：`_normalize()` 缺少繁簡同化步驟。EPUB TOC 來源（簡體）與報告正文（繁體）無法比對。

**修正方案**：在 `_normalize()` 中加入 OpenCC 簡→繁轉換（或雙向同化），並提供 fallback：
```python
import opencc

_CC = opencc.OpenCC('s2t')  # 簡→繁

def _normalize(s):
    try:
        s = _CC.convert(s)    # 先同化為繁體
    except NameError:
        pass                   # fallback：opencc 未安裝時跳過
    return re.sub(r'[\s:：""\'\.,;!?、《》【】「」()\(\)]', '', s)
```

> **備註**：此修正同時影響所有簡體 EPUB 的書籍匯入，不單限本次案例。

---

### B2. extract_epub_toc() 將前導章節誤納入 GT TOC（中度）

**現象**：`01_init_notebook.py` 的 `extract_epub_toc()` 過濾條件包含：
```python
if text and ("章" in text or "Chapter" in text or "法則" in text or "夜" in text or text in ("前言", "序言", "結語", "後記", "緒論")):
```
其中 `"前言"` 等前導詞被當成正文章節列入 GT TOC（Order 3-4：前言、致谢），但批次生成時這些章節並不會被單獨處理（batch_strategy 只列 18 章），導致 QC 報告「前言缺漏」。

**修正方案**：在過濾條件中**排除**前導詞彙：
```python
FRONTMATTER = {
    "封面", "推荐序", "推薦序", "前言", "致謝", "致谢",
    "序言", "緒論", "後記", "結語", "目錄", "Table of Contents"
}

if text and ("章" in text or "Chapter" in text or "法則" in text or "夜" in text):
    if text not in FRONTMATTER and text not in chapters:
        chapters.append(text)
```

> **備註**：修正後 GT TOC 只保留 18 章正文，排除封面/推薦序/前言/致謝等非正文項目。

---

### B3. `_normalize()` 中正則 escape 警告 + character class 內多餘轉義（低度）

**現象**：`04_qc_check.py` line 77：
```python
return re.sub(r'[\s:：""''""\'\'\.,;!?、《》【】「」()\(\)]', '', s)
```
Python 3.12+ 在 character class 內對 `\.` 發出 SyntaxWarning（雖然 raw string 中合法，但部分 build 仍報警）。同時 `\"`、`\'` 在 `[]` 內不需轉義。

**修正方案**：移除多餘的 escape，使用明確字元集：
```python
def _normalize(s):
    # ...繁簡轉換...
    return re.sub(r'[\s:：""\'\.,;!?、《》【】「」()\(\)]', '', s)
```

---

### B4. 03_assemble_report.py 自動複製至 Obsidian cleanup_pending（流程衝突）

**現象**：`03_assemble_report.py` line 238–246 會自動將組裝好的報告複製到：
```
Obsidian/raw/__cleanup_pending__/{short_title}_讀書報告.md
```
這是 v4 時代的歷史相容行為。v5.0 的新流程要求詳細報告由**階段二 Agent** 寫入 `raw/articles/zh/[slug].md`，03 的自動複製產生了額外的 `_讀書報告.md` 檔案，與雙檔分流架構不符。

**修正方案**：在 `book_config.yaml` 中新增開關，預設為 `false`：
```yaml
assemble_copy_to_cleanup: false   # 關閉舊版自動複製，避免與階段二流程衝突
```

在 `03_assemble_report.py` 中讀取此開關：
```python
copy_to_cleanup = config.get("assemble_copy_to_cleanup", False)
if copy_to_cleanup:
    # 原有複製邏輯
    ...
else:
    print("[Info] assemble_copy_to_cleanup is disabled; skipping auto-copy.")
```

---

## 十、修正檔案清單（本次新增）

| 檔案 | 修改內容 | 對應 Issue |
|------|---------|-----------|
| `scripts/04_qc_check.py` | `_normalize()` 加入 OpenCC 繁簡轉換 + 移除多餘 escape | B1, B3 |
| `scripts/01_init_notebook.py` | `extract_epub_toc()` 加入 FRONTMATTER 排除集合 | B2 |
| `config/book_config.yaml.template` | 新增 `assemble_copy_to_cleanup: false` 預設值 | B4 |
| `scripts/03_assemble_report.py` | 讀取 `assemble_copy_to_cleanup` 開關 | B4 |

---

## 十一、驗證方式

完成上述修正後，建議以簡體 EPUB 執行完整管線驗證：

```bash
# 1. 確認 GT TOC 不含前導詞
python -c "import json; toc=json.load(open('config/ground_truth_toc.json')); print([c for c in toc['chapters'] if any(x in c for x in ['前言','推荐序','致谢'])])"
# 預期：[] （空列表）

# 2. 執行 QC 確認 18 章全通過
python scripts/04_qc_check.py
# 預期：✅ [PASS] 報告完整涵蓋全書 Ground Truth 18 章節，無任何遺漏！

# 3. 確認無 SyntaxWarning
python -W error::SyntaxWarning scripts/04_qc_check.py
# 預期：無輸出錯誤

# 4. 確認 03 不再自動複製到 cleanup_pending
ls raw/__cleanup_pending__/ | grep "_讀書報告"
# 預期：空列表（除非 config 中 assemble_copy_to_cleanup: true）
```

---

## 十二、最終確認清單

| 項目 | 狀態 | Claude 前置審核意見 |
|------|------|------|
| B1: `_normalize()` 加入 OpenCC 繁簡同化 | 🔲 待修復（**原始程式碼需修正，見十三節**） | ⚠️ 原建議的 `import opencc` 寫在模組頂層且無 try/except，若執行環境未安裝 opencc 會直接 ImportError 導致整支 `04_qc_check.py` 無法啟動；且 `requirements.txt` 目前確認未包含 opencc，必須同步新增依賴 |
| B2: `extract_epub_toc()` 排除 FRONTMATTER | 🔲 待修復（**原始程式碼遺漏一處，見十三節**） | ⚠️ 原建議只修改了 XML 解析成功路徑的過濾條件，但 `extract_epub_toc()` 內部的 fallback（HTMLParser 失敗後的正則備援）有第二份幾乎相同的過濾條件，未同步修改會導致 fallback 觸發時前導章節仍會混入 GT TOC；另建議排除判斷改用子字串比對而非完全相等，以涵蓋「推薦序一」「致謝辭」等變體標題 |
| B3: `_normalize()` 移除多餘 escape | 🔲 待重新定性（**非必要修復，見十三節**） | ⚠️ 實地檢查現有程式碼確認該行已是 `r'...'` raw string，Python 不會對 raw string 內的 `\.` 發出 SyntaxWarning，原診斷之根源不成立；建議降級為「程式碼整潔選配項」，並改為新增真正缺少的全形彎引號（U+2018/2019/201C/201D）以提升穩健度 |
| B4: `03_assemble_report.py` 加入配置開關 | 🔲 待修復 | ✅ 審核通過，邏輯與現有程式碼相容，可依原方案實作 |
| 驗證腳本執行通過 | 🔲 待測試 | — |
| 新增測試：B2 前導詞排除（含 fallback 分支） | 🔲 待新增 | 建議比照 `test_extract_epub_toc_with_malformed_xml_fallback` 手法，另建立一組刻意包含「推薦序」「前言」「致謝」的 malformed TOC 測試，驗證 fallback 分支也不會誤收錄 |
| 新增測試：B1 opencc 未安裝時的 graceful fallback | 🔲 待新增 | 建議以 `unittest.mock.patch` 模擬 `import opencc` 失敗情境，確認 `_normalize()` 仍可運作（僅略過繁簡轉換）而不拋出例外 |

---

## 十三、Claude 專業審核：修正版程式碼與缺失說明（2026-08-15 第五輪前置審核）

> 本節為 Claude 於 Agent 動手實作 B1～B4 之前，針對「九、第四輪覆核」提出的修正方案所做的程式碼層級審核。發現 B1、B2 的原始建議程式碼若照抄實作，會產生**新的執行期錯誤或涵蓋不全**的問題；B3 的診斷前提則有誤。以下為建議 Agent 實際採用的修正版本，請以本節內容為準，取代「九、第四輪覆核」中對應的程式碼片段。

### 13.1 B1 修正版：安全的 OpenCC 匯入方式

**問題**：原方案 `import opencc` 寫在檔案頂層且沒有包 try/except。如果 Agent 實作環境（或未來任何一台執行機器）沒有安裝 opencc，`04_qc_check.py` 會在匯入階段就整支 crash，QC 完全無法執行——這比「繁簡不匹配」本身更嚴重，屬於回歸性風險。原本寫的 `except NameError` 也接不到這種情況，因為程式根本走不到 `_normalize()` 內部。

**另一個實務問題**：`requirements.txt` 目前只有 `PyYAML` 與 `python-dotenv`，需新增 opencc 依賴。由於執行環境是 Windows，建議優先採用純 Python 實作的 `opencc-python-reimplemented`（安裝命令為 `pip install opencc-python-reimplemented`，安裝後仍以 `import opencc` 引用），可避免 `opencc`（cffi 版）在 Windows 上可能需要額外編譯工具鏈的問題。

**修正版程式碼**（取代 `scripts/04_qc_check.py` 中的對應段落）：

```python
# 檔案頂部（import 區塊）：安全匯入 OpenCC，缺套件時自動降級但不中斷程式
try:
    import opencc
    _CC = opencc.OpenCC('s2t')  # 簡→繁
except Exception:
    _CC = None
    print("⚠️ [Notice] 未偵測到 opencc 套件，QC 比對將略過簡繁同化（建議執行 pip install opencc-python-reimplemented）。")

def _normalize(s):
    if _CC is not None:
        try:
            s = _CC.convert(s)   # 先同化為繁體
        except Exception:
            pass
    return re.sub(r'[\s:：""''""\'\'\.,;!?、《》【】「」()\(\)]', '', s)
```

> 注：上述字元類別維持與現行版本完全相同，B1 僅負責修正 opencc 匯入安全性，不變動引號判斷邏輯；若需要新增彎引號支援，請參見 13.3 的選配強化版本。

**`requirements.txt` 新增**：
```
opencc-python-reimplemented>=0.1.7
```

**驗收重點**：Agent 需在「已安裝 opencc」與「刻意移除/未安裝 opencc」兩種情境下都跑一次 `04_qc_check.py`，確認後者僅印出 Notice 訊息並繼續執行（不 crash），前者能正確將簡體 GT 章節同化為繁體後比對成功。

---

### 13.2 B2 修正版：FRONTMATTER 排除須同步套用於 XML 成功路徑與 fallback 路徑

**問題**：`extract_epub_toc()` 內部實際上有**兩處**幾乎相同的章節篩選條件：
1. XML 解析成功時，走 `root.iter()` 逐一檢查 `elem.text`。
2. XML 解析失敗（`except inner_e`）時的 fallback：先試 `HTMLParser`（`TOCHTMLParser`），若 `parser.extracted` 為空才退回正則 `re.findall(...)`，兩者取得的候選字串最終都會經過同一段 `if clean_m and (...)` 判斷式。

原始 B2 建議只示範修改「第 1 處」，若 Agent 只照原方案修改一處，遇到需要觸發 fallback 的破損 TOC（例如第三輪已驗證過的 malformed XML 情境）時，前導詞仍會混入 GT TOC，等於 B2 沒有真正解決問題。

另外，原始排除判斷使用**完全相等**（`text not in FRONTMATTER`），但 EPUB 實務上前導章節常有變體寫法，例如「推薦序一」「推薦序二」「致謝辭」「作者序」等，完全相等會漏判。建議改為**子字串比對**。

**修正版程式碼**（取代 `scripts/01_init_notebook.py` 中 `extract_epub_toc()` 的兩處判斷式）：

```python
# 放在 extract_epub_toc() 函式最上方或模組層級均可
FRONTMATTER_KEYWORDS = (
    "封面", "推薦序", "推荐序", "前言", "致謝", "致谢",
    "序言", "緒論", "作者序", "譯者序", "出版序",
    "後記", "结语", "結語", "目錄", "目录", "Table of Contents",
)

def _is_frontmatter(text: str) -> bool:
    return any(kw in text for kw in FRONTMATTER_KEYWORDS)

def _is_chapter_candidate(text: str) -> bool:
    has_marker = ("章" in text or "Chapter" in text or "法則" in text or "夜" in text)
    return bool(text) and has_marker and not _is_frontmatter(text)
```

**第 1 處（XML 解析成功路徑）**改為：
```python
for elem in root.iter():
    text = (elem.text or "").strip()
    if _is_chapter_candidate(text):
        if text not in chapters:
            chapters.append(text)
```

**第 2 處（fallback 路徑，`candidates` 迴圈內）**改為：
```python
for m in candidates:
    clean_m = re.sub(r'<[^>]+>', '', m).strip()
    clean_m = re.sub(r'\s+', ' ', clean_m)
    if _is_chapter_candidate(clean_m):
        if clean_m not in chapters:
            chapters.append(clean_m)
```

> **附註**：`discover_actual_toc()` 之後由 `_parse_toc_response()` 處理的 NotebookLM 回覆解析路徑，其關鍵字清單（`"章", "Chapter", "chapter", "法則", "Part", "PART", "Unit", "Lesson"`）本來就不含「前言」等單一關鍵字，此路徑經覆核**不受影響、無需修改**，僅供記錄避免後續重複調查。

**驗收重點**：新增測試需確保 fallback 分支被實際觸發（沿用第三輪已驗證過的 malformed XML 手法），且刻意在測試資料中混入「推薦序一」「前言」「致謝辭」等變體詞彙，驗證兩處路徑都不會誤收錄。

---

### 13.3 B3 重新定性：非真實 bug，改為選配強化

實地檢查 `scripts/04_qc_check.py` 目前程式碼（第 77 行）確認該正則已經是 `r'[...]'` 型式的 raw string。Python 只會對**非 raw 字串**中無法識別的跳脱序列（如 `"\d"`）發出 `SyntaxWarning`／`DeprecationWarning`，raw string 內的 `\.`、`\(`、`\)` 不會觸發任何警告。因此 B3 原本的診斷（「Python 3.12+ 對 character class 內的 `\.` 發出 SyntaxWarning」）**不成立**，不需要當作 bug 修復。

實際檢查該字元類別的組成後，另外發現一個**原文件未提及、但更值得修的小缺口**：目前的字元類別只涵蓋直角引號（`"` `'`，且重複出現多次）與全形書名號／括號（「」《》【】），但**沒有涵蓋常見的全形彎引號**（U+2018 `'`、U+2019 `'`、U+201C `"`、U+201D `"`）。若 NotebookLM 或 EPUB 原文中出現彎引號而報告 / GT TOC 兩邊只有一邊使用彎引號，仍可能造成比對失敗。

**建議**（優先度：低，屬於強化而非修 bug，可與 B1/B2 同批次一併處理）：
```python
def _normalize(s):
    if _CC is not None:
        try:
            s = _CC.convert(s)
        except Exception:
            pass
    return re.sub(
        r'[\s:："\u2018\u2019\u201c\u201d\'\.,;!?、《》【】「」()\(\)]',
        '', s
    )
```

---

### 13.4 B4：審核通過，可依原方案實作

`03_assemble_report.py` 目前的自動複製邏輯（第 238～246 行左右）沒有任何開關保護，B4 的方案（於 `book_config.yaml.template` 新增 `assemble_copy_to_cleanup: false`，並在 `assemble_report_core()` 中以 `config.get("assemble_copy_to_cleanup", False)` 判斷）與現有程式碼結構相容，未發現需要修正之處，可依「九、B4」原方案直接實作。

---

### 13.5 本輪審核結論

| 項目 | 原方案是否可直接實作 | 說明 |
|------|---------------------|------|
| B1 | ❌ 否，需改用 13.1 修正版 | 原方案有無防護的頂層 import，會造成新的 crash 風險 |
| B2 | ❌ 否，需改用 13.2 修正版 | 原方案遺漏 fallback 路徑的同步修改，且排除判斷過於嚴格 |
| B3 | ⚠️ 診斷有誤，改用 13.3 的定性與選配強化 | 原始「SyntaxWarning」根源不成立，但可以順便補上彎引號 |
| B4 | ✅ 是 | 與現有程式碼相容，無需調整 |

**建議 Agent 實作順序**：B1（13.1）→ B2（13.2）→ B4（原方案）→ B3（13.3，選配）。實作完成後請依「十一、驗證方式」＋本節「驗收重點」逐項驗證，並補齊「十二、最終確認清單」中列出的兩項新增測試後，再交回 Claude 覆核。

