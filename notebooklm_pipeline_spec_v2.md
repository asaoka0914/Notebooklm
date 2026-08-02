# NotebookLM 長篇讀書報告自動化 Pipeline 實作計畫 (v2)

本文件整合近期所有實驗數據、技術驗證與架構決策，作為開發團隊/Subagent 進行程式碼實作的單一真實來源規格書 (SSOT Spec)。

**v2 修訂說明**：本版針對 v1 規格書進行技術細節補強，修正標題階層不一致、腳註範圍格式解析、JSON 有效性驗證、API 節流、上下文擷取容錯等五項問題，避免全書批次生成到一半才發現架構缺陷。

---

## 一、背景與關鍵技術驗證成果

### 突破 1：指令轉來源檔案 (Instruction as Source)
將 `讀書報告核心概念.md` 透過 `source add` 直接上傳為 NotebookLM 的 Source。
效果：後續所有 Query 僅需傳送約 50 字的極簡 Prompt，完全解決 Windows PowerShell 長字串編碼、符號與換行溢位的問題。

### 突破 2：小範圍分批對話生成 (Chunked Batch Generation)
實測證明：一次生成全書（16 章）字數約 4,694 字元（每章僅配額 ~290 字元）；小範圍（2 章）一次輸出達 2,823 字元（每章配額升至 ~1,400 字元）。
效果：章節篇幅密度提升近 5 倍，且完全忠實遵循 Markdown 結構與腳註規範。

### 突破 3：結構化腳註與引用 (Citations & References)
NotebookLM 返回的 JSON 包含完整的 `citations` 與 `references` 字典，含原文引述 (`cited_text`)。
效果：腳註重新編號可基於結構化 JSON 處理，無需正則表達式猜測「內容」，但**內文中的編號標記仍需正則辨識位置**（見四-3）。

### 問題 4（v2 新增）：標題階層不一致
比對兩次實測輸出：
- 第一次全書生成：章節標題為 `##`，子結構為 `###`
- 本次 Ch5-6 生成：章節標題為 `####`，子結構為 `#####`

同一份規則文件、不同批次的輸出，標題階層深淺不一致。這代表 NotebookLM 的輸出格式**不可完全信任其階層深度**，組裝模組必須做正規化，否則最終文件的 Markdown 結構會混亂（詳見四-2）。

---

## 二、決策拍板與規格定案

| 決策項目 | 拍板定案內容 | 評估與設計考量 |
|---|---|---|
| 1. 跨書籍分批策略 | 預設 2 章一組，透過 `book_config.yaml` 彈性配置 | 若處理新書，先透過 Python 讀取總字數，自動決定分批數量 |
| 2. 上下文銜接 (Context Bridge) | 擷取上一批輸出的【核心論點摘要】第一段（約 100-150 字），**擷取失敗則 fallback 為空字串，不中斷 pipeline** | 0 額外 Token 消耗、低延遲；容錯設計避免格式異常拖垮整條流程 |
| 3. 錯誤重試與續傳 | 指數退避重試（3 次，2s→4s→8s）+ Checkpointing + 單批補跑 + **Schema 有效性檢查** | 「非空但不合格」的回應（無 references、無標題結構）視同失敗，觸發重試 |
| 4. 測試規模 | 先執行 Chapter 1-4（2 批）小規模驗證 | 低成本驗證組裝、腳註重編號與 QC 模組 |
| 5.（v2 新增）標題階層正規化 | 組裝時統一重映射為：書名 H1 → 章節 H2 → 子結構 H3，不採用 NotebookLM 原始階層 | 避免不同批次階層深淺不一造成最終 TOC/轉檔錯亂 |
| 6.（v2 新增）API 呼叫節流 | 每批次之間固定延遲 8 秒 | 避免連續呼叫觸發帳號驗證或頻率限制 |

---

## 三、Pipeline 目錄與架構規劃

```
Project/Notebooklm/
├── config/
│   └── book_config.yaml          # 書籍設定、notebook_id、動態分批規則
├── source/
│   └── 讀書報告核心概念.md         # 規則文件（一次性 source add）
├── scripts/
│   ├── 01_init_notebook.py       # 初始化：確認/上傳 Source、估算字數與生成配置
│   ├── 02_batch_generate.py      # 主迴圈：發送分批 Query、支援節流/重試/續傳
│   ├── 03_assemble_report.py     # 拼裝：標題正規化、腳註全域重編號、合成 Markdown
│   └── 04_qc_check.py            # 品質審查：密度、標題結構、腳註一致性
├── raw_outputs/
│   ├── batch_01_ch1-2.json       # 每批次原始 JSON 備份
│   └── batch_02_ch3-4.json
├── failed_batches.json           # 重試 3 次仍失敗的批次清單
└── final/
    └── full_report.md            # 最終產出之長篇導讀報告
```

---

## 四、關鍵模組實作規格

### 1. 配置與初始化模組 (`config/book_config.yaml` & `01_init_notebook.py`)

功能：讀取書籍資訊與本地字數/章節，檢查目標 Notebook 是否已包含 `讀書報告核心概念.md`，避免重複 `source add`。

```yaml
book_title: "A Richer Retirement"
notebook_id: "d7ec78f8-4df3-44ea-95ff-ea6939058106"
batch_strategy:
  default_batch_size: 2
  batch_delay_seconds: 8   # v2 新增：批次間節流延遲
  batches:
    - batch: 1
      chapters: ["Chapter 1", "Chapter 2"]
    - batch: 2
      chapters: ["Chapter 3", "Chapter 4"]
```

---

### 2. 分批生成模組 (`02_batch_generate.py`)

**Prompt 模板：**
```
請嚴格依據來源檔案《讀書報告核心概念.md》中的撰寫規範與原則，
針對原書 {chapter_range} 進行詳細、深度且不遺漏細節的報告撰寫。

【前情提要】：
{previous_batch_summary}

請確保本批內容與前述章節在概念上連貫，避免重複解釋已提及的核心概念。
```

**續傳邏輯**：檢查 `raw_outputs/batch_XX.json` 是否已存在且非空，若存在則跳過。

**Schema 有效性檢查（v2 新增，重試觸發條件）**：
回應需同時滿足以下條件才視為有效，否則視同失敗、進入重試：
- HTTP/回應狀態正常且 `content` 欄位非空
- `content` 中包含至少一個章節子結構標記（無論階層為何，正則需寬鬆匹配 `#{2,5}\s*(核心論點摘要|Ⅰ)`）
- `references` 或 `citations` 欄位存在（允許為空陣列，但欄位本身必須存在）

**異常處理**：遇到 Exception、空回應、或 Schema 檢查未通過時，等待 2s → 4s → 8s 重試最多 3 次。3 次皆失敗則寫入 `failed_batches.json`（記錄 batch 編號、章節範圍、最後一次錯誤訊息），不中斷整體流程，繼續處理下一批。

**節流**：每批次成功處理完畢後，無論是否重試，固定延遲 `batch_delay_seconds`（預設 8 秒）再發送下一批請求。

**上下文擷取容錯**：
```python
def extract_summary(previous_batch_json):
    try:
        content = previous_batch_json["content"]
        # 尋找「核心論點摘要」段落並取第一段（約100-150字）
        summary = parse_first_paragraph_after_heading(content, "核心論點摘要")
        return summary if summary else ""
    except (KeyError, IndexError, TypeError):
        return ""  # fallback：不中斷 pipeline，本批 prompt 不含前情提要
```

---

### 3. 組裝與腳註重編號模組 (`03_assemble_report.py`)

**標題階層正規化（v2 新增，必須在合併前執行）**：
NotebookLM 回傳的標題階層深度不可信任，一律按「語意角色」而非原始 `#` 數量重新映射：
- 全書標題 → H1（`#`）
- 各章節標題（如「第五章：...」）→ H2（`##`）
- 章節內子結構（核心論點摘要、章節細節與分析等）→ H3（`###`）

實作方式：不直接搬移原始 Markdown 的 `#` 符號，而是用正則辨識語意關鍵字（章節標題模式如 `第[一二三四五六七八九十百]+章|CHAPTER \d+`、子結構關鍵字如「核心論點摘要」「章節細節與分析」），依辨識結果重新賦予階層符號。

**腳註全域重編號演算法**：
- 維持全域計數器 `global_citation_counter = 1`
- 建立全域對照表 `citation_map = {}` 及 `references_list = []`
- 遍歷每個 Batch JSON：
  1. 讀取其 `references` 字典，對每個本機編號將 `cited_text` 映射至新的全域編號
  2. 更新全域計數器、加入 `references_list`

**內文編號替換正則（v2 修正，需處理範圍與複合格式）**：
原始輸出包含 `[1]`、`[1-3]`、`[4, 5]` 等格式，單一數字的正則會漏掉範圍與逗號分隔的情況。修正後的處理流程：

```python
import re

# 匹配 [1] [1-3] [4, 5] [1, 3-5] 等所有複合格式
pattern = r'\[(\d+(?:\s*[-,]\s*\d+)*)\]'

def expand_and_remap(match, citation_map, batch_offset):
    raw = match.group(1)
    numbers = []
    for part in re.split(r',\s*', raw):
        if '-' in part:
            start, end = map(int, part.split('-'))
            numbers.extend(range(start, end + 1))
        else:
            numbers.append(int(part))
    # 依 citation_map 將本機編號轉為全域編號，保持原有的連續/逗號格式風格
    global_numbers = [citation_map[(batch_offset, n)] for n in numbers]
    return format_citation(global_numbers)  # 重組為 [N] 或 [N-M] 或 [N, M]
```

每個 batch 需標記 `batch_offset`，避免不同批次的本機編號 1 互相衝突。

**References 區塊**：組裝完成後，於文末統一輸出，格式：`[N] cited_text（來源：Chapter X）`

---

### 4. 品質審查模組 (`04_qc_check.py`)

檢查指標：
- **密度檢查**：單章字元數是否高於預期下限（< 1,000 字元跳出警告，標記需人工複查）
- **格式檢查**：正規化後每章是否包含 H3 的「核心論點摘要」與「章節細節與分析」結構
- **腳註一致性**：確保內文引用（含展開後的範圍）皆能在文末 References 找到對應 `cited_text`，並反向檢查 References 是否有未被引用的孤兒條目
- **（v2 新增）failed_batches 檢查**：若 `failed_batches.json` 非空，QC 報告需明確列出缺漏章節範圍，提示需人工補跑

---

## 五、開發與驗收步驟

1. **Step 1（測試跑 - 2 批）**：執行 Chapter 1-4 測試（Batch 1 & 2），產出 `raw_outputs/`，驗證 Schema 檢查與節流機制運作正常。
2. **Step 2（驗證組裝邏輯）**：執行 `03_assemble_report.py` 產出草稿，重點確認：
   - 標題階層是否正規化成功（不論原始輸出階層為何，最終應統一為 H1/H2/H3）
   - 腳註號碼連續、複合格式（`[1-3]` 等）正確展開替換
   - 內文未因替換錯誤而斷裂
3. **Step 3（QC 驗證）**：執行 `04_qc_check.py`，確認密度、格式、腳註一致性皆無異常警告。
4. **Step 4（全書開跑 - 8 批）**：Step 1-3 驗證無誤後，正式擴展至 16 章全書生成，產出最終 `final/full_report.md`。

---

本文件已準備就緒，可隨時交由 Subagent 進行代碼實作。
