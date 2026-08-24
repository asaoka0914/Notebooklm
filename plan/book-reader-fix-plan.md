# book-reader 修正計畫：華爾街操盤手書籍匯入故障分析

> 產生日期：2026-08-20
> 情境：使用 book-reader v5.0 技能整理《華爾街操盤手給年輕人的15堂理財課.epub》時，遭遇 01 → 02 → 03 流程中斷與錯誤修正。

---

## 一、問題發生經過（時間線）

### 步驟 1：認證遷移（非預期）
- 原本 `book_config.yaml` 裡的 `notebook_id` 是 `gwa20080808@gmail.com` 帳號的筆記本
- 當前 Chrome Default Profile 對應的是 `asaoka0914@gmail.com`
- 01 上傳規則檔時出現 `PERMISSION_DENIED`
- **處理方式**：用 `nlm create notebook` 建立新筆記本，手動更新 `book_config.yaml` 裡的 `notebook_id`
- **建議**：在 SKILL.md 中補一句「若 `nlm notebook list` 列出結果為空或來源數不符，需確認當前 Google 帳號是否具備該筆記本權限，必要時建立新筆記本」

### 步驟 2：EPUB 目錄解析失敗（根本原因）
- `01_init_notebook.py` 用 `extract_epub_toc()` 解析 NCX（`toc.ncx`）
- 這本 EPUB 的 NCX 中文為亂碼（Calibre 轉換時的編碼問題），只抓到 1 個無意義條目
- `toc.xhtml` 裡有完整的 15 章目錄，但 `01` 的 `_is_chapter_candidate()` 正則沒有匹配到
- **結果**：`ground_truth_toc.json` 被寫成只有 1 章，後續 `02` 雖然成功（因為 config 另有 `batch_strategy.batches` 預填），但 `03` 組裝報告後 QC 發現 15 章全缺（H2 層級只有 H4）

### 步驟 3：03 normalize_headings 未涵蓋新格式
- `03_assemble_report.py` 的 `normalize_headings()` 只處理：
  - `第 X 章...`
  - `CHAPTER X...`
  - `前言/總結/附錄`
  - `洞察市場真實面`
- **漏掉**：`#### 1 理財要分身有術` 這種「數字 + 空格 + 中文」格式
- 同時漏掉 `#### 14 「愛」是所有財富的種子` 這種數字後面跟引號的格式
- **結果**：組裝出的報告所有章節標題都是 `####`（H4），QC 判定為 HARD-FAIL

### 步驟 4：batch_strategy.batches 為空
- `book_config.yaml` 裡的 `batch_strategy` 只有 `batch_delay_seconds: 8`，沒有 `batches` 陣列
- `02_batch_generate.py` 讀到空陣列，直接跳過全部批次，但仍印出 `[Complete] All batches generated successfully!`（這是一個偽成功訊息）
- **處理方式**：手動寫 Python 根據 `ground_truth_toc.json` 重新生成批次配置
- **建議**：`01_init_notebook.py` 應在成功解析 TOC 後，自動將 chapters 分段寫入 `batch_strategy.batches`

---

## 二、實際修復方式（供另一 Agent 參考）

### 修復 1：手動寫入正確 ground_truth_toc.json
```python
# 直接從 toc.xhtml 提取章节列表，而非依賴 NCX
# 15 章已手動寫入 config/ground_truth_toc.json
```
**但更好的解法是修復 `01_init_notebook.py` 的 TOC 解析邏輯**（見下方建議）。

### 修復 2：`03_assemble_report.py` 新增兩種正則匹配
在 `normalize_headings()` 裡補上兩條規則（約第 30 行）：
```python
# 匹配 "數字 + 空格 + 中文標題" 格式（如：#### 1 理財要分身有術）
elif re.match(r'^(?:#{1,6}\s*)?\d+\s*(?:[「『「」』」])?\s*[一-龥]', stripped):
    clean_title = re.sub(r'^#{1,6}\s*', '', stripped)
    norm_lines.append(f"\n## {clean_title}\n")
```
這同時解決了「數字開頭」和「數字後跟引號」（如 `14 「愛」...`）兩種格式。

### 修復 3：02 偽成功訊息
`02_batch_generate.py` 在 `batches` 為空時仍印出 `[Complete] All batches generated successfully!`，應改為：
```python
if not batches:
    print("❌ [Error] batch_strategy.batches 為空，請先執行 01 以產生批次配置")
    sys.exit(1)
```

---

## 三、建議修復的 3 個程式改動

### 【優先高】修復 `01_init_notebook.py` — EPUB TOC 解析容錯

**位置**：`scripts/01_init_notebook.py`，`extract_epub_toc()` 函式

**問題**：只讀 NCX（`toc.ncx`），NCX 編碼損壞時無 fallback，且無法解析 `toc.xhtml`。

**建議改法**：
```python
def extract_epub_toc(book_path):
    """解析 EPUB 目錄，優先讀 toc.xhtml，fallback 到 toc.ncx"""
    chapters = []
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            names = z.namelist()
            # 優先讀 toc.xhtml
            xhtml_candidates = [f for f in names if f.endswith('.xhtml') and
                               ('toc' in f.lower() or 'nav' in f.lower())]
            ncx_candidates = [f for f in names if f.endswith('.ncx')]
            candidates = xhtml_candidates + ncx_candidates

            for tf in candidates:
                data = z.read(tf).decode('utf-8', errors='replace')
                # xhtml 格式：解析 <a> 標籤內的文字
                if tf.endswith('.xhtml'):
                    links = re.findall(r'<a[^>]*>([^<]+)</a>', data)
                    for link_text in links:
                        clean = link_text.strip()
                        if _is_chapter_candidate(clean) and clean not in chapters:
                            chapters.append(clean)
                # ncx 格式：原有邏輯
                elif tf.endswith('.ncx'):
                    # ...原有 NCX 解析邏輯...
                    pass
    except Exception as e:
        print(f"⚠️ TOC 解析失敗 ({e})，嘗試從 content.opf 解析...")
        # content.opf fallback 原有邏輯不變
    return chapters
```

**額外建議**：在 `extract_epub_toc` 結尾加驗證：
```python
if len(chapters) < 3:
    print(f"⚠️ 僅解析到 {len(chapters)} 章，疑似 NCX 編碼問題，請檢查 EPUB 格式")
```

---

### 【優先高】修復 `01_init_notebook.py` — 新書初始化時清空舊狀態

**位置**：`scripts/01_init_notebook.py`，`init_notebook()` 函式開頭

**問題**：切換新書時，`ground_truth_toc.json`、`raw_outputs/`、`final/` 下舊書資料夾仍殘留。

**建議改法**（在 config 讀取後、TOC 解析前）：
```python
# 檢查是否需要清空舊狀態
config_title = config.get('book_title', '')
cli_title = args.title or ''
current_title = cli_title or config_title

if current_title and current_title != config_title and config_title:
    print(f"🔄 檢測到新書籍（《{current_title}》），清空舊狀態...")
    # 清空 ground_truth_toc.json
    gt_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
    if os.path.exists(gt_path):
        os.remove(gt_path)
        print(f"  ✅ 已清除 {gt_path}")
    # 清空 raw_outputs 下舊書目錄
    raw_dir = os.path.join(BASE_DIR, "raw_outputs")
    if os.path.exists(raw_dir):
        for d in os.listdir(raw_dir):
            if d != current_title:
                old_path = os.path.join(raw_dir, d)
                if os.path.isdir(old_path):
                    shutil.rmtree(old_path)
                    print(f"  ✅ 已清除 {old_path}")
    # 清空 final 下舊書目錄（保留 cover.jpg）
    final_dir = os.path.join(BASE_DIR, "final")
    if os.path.exists(final_dir):
        for d in os.listdir(final_dir):
            if d != current_title:
                old_path = os.path.join(final_dir, d)
                if os.path.isdir(old_path):
                    shutil.rmtree(old_path)
                    print(f"  ✅ 已清除 {old_path}")
```

---

### 【優先中】修復 `01_init_notebook.py` — 自動產生 batch_strategy.batches

**位置**：`scripts/01_init_notebook.py`，在寫入 `ground_truth_toc.json` 之後

**問題**：02 需要 `batch_strategy.batches` 陣列，但目前需手動填寫。

**建議改法**：
```python
# 自動產生 batch_strategy.batches（每 2 章一批）
if 'batch_strategy' not in config or not config['batch_strategy'].get('batches'):
    batches = []
    batch_size = 2  # 預設每批 2 章
    for i in range(0, len(gt_chapters), batch_size):
        batch_num = len(batches) + 1
        batch_chapters = gt_chapters[i:i+batch_size]
        batches.append({'batch': batch_num, 'chapters': batch_chapters})
    config['batch_strategy']['batches'] = batches
    config['batch_strategy']['batch_delay_seconds'] = config['batch_strategy'].get('batch_delay_seconds', 8)

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"✅ 自動產生 {len(batches)} 個批次配置至 {config_path}")
```

---

### 【優先中】修復 `02_batch_generate.py` — 防止偽成功

**位置**：`scripts/02_batch_generate.py`，讀取 `batches` 之後

**建議改法**：
```python
batches = batch_strategy.get("batches", [])
if not batches:
    print("❌ [Error] batch_strategy.batches 為空！")
    print("   請先執行 01_init_notebook.py 以產生批次配置。")
    sys.exit(1)
```

---

### 【優先低】修復 `03_assemble_report.py` — normalize_headings 正則強化

**位置**：`scripts/03_assemble_report.py`，`normalize_headings()` 函式

**已有改動**（本次會話已修復）：
```python
# 在 CHAPTER 匹配之後、子結構匹配之前，新增：
elif re.match(r'^(?:#{1,6}\s*)?\d+\s*(?:[「『「」』」])?\s*[一-龥]', stripped):
    clean_title = re.sub(r'^#{1,6}\s*', '', stripped)
    norm_lines.append(f"\n## {clean_title}\n")
```

**建議同步更新** SKILL.md 或 CHANGELOG 記錄此修補。

---

## 四、建議同步更新的文件

| 文件 | 建議修改內容 |
|------|-------------|
| `SKILL.md` Step 0 | 增加「建立筆記本後，確認 NotebookLM 網頁上來源清單包含本書 EPUB」 |
| `SKILL.md` Step 1 | 增加「若 `book_config.yaml` 的 `book_title` 與本次不同，01 會自動清空舊狀態」 |
| `scripts/01_init_notebook.py` | 修復 NCX 容錯 + 自動產生 batches + 舊狀態清空 |
| `scripts/02_batch_generate.py` | 空 batches 時 exit(1) 而非偽成功 |
| `scripts/03_assemble_report.py` | normalize_headings 補上數字+中文標題格式（已修復） |

---

## 五、驗證方式

修復後執行以下檢查：

```bash
# 1. 測試 NCX 容錯（用這本已知有問題的 EPUB）
cd ~/.claude/skills/book-reader
python scripts/01_init_notebook.py --book-path "C:/Users/asaoka.zhong/Downloads/華爾街操盤手給年輕人的15堂理財課.epub" --title "華爾街操盤手給年輕人的15堂理財課"
# 應看到：✅ Ground Truth TOC saved with 15 chapters（而非 1）
# 應看到：✅ 自動產生 8 個批次配置

# 2. 測試 02 不被偽成功騙過
python scripts/02_batch_generate.py --title "華爾街操盤手給年輕人的15堂理財課"
# 應看到 8 個批次的進度訊息，最後 [Complete]

# 3. 測試 03 修正後的 normalize_headings
python scripts/03_assemble_report.py --title "華爾街操盤手給年輕人的15堂理財課"
# 報告中應有 15 個 ## 標題（而非 ####）

# 4. 測試 04 QC
python scripts/04_qc_check.py --title "華爾街操盤手給年輕人的15堂理財課"
# 應看到 15 chapters found，passed_all = true
```

---

*本文檔由 Claude 在 2026-08-20 下午整理，基於實際執行日誌與程式碼比對。*
