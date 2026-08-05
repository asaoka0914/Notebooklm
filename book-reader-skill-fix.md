# book-reader 技能補強實作文件

> 作者：Agnes / Claude
> 日期：2026-08-05
> 背景：《持續買進》EPUB 報告只產出 11 章，實際書中有 21 章，因 SKILL.md 缺少「前置目錄檢索」步驟導致漏章。

---

## 一、問題診斷

### 1.1 現有 SKILL.md 流程缺口

| 步驟 | 內容 | 問題 |
|------|------|------|
| 步驟 1-3 | 解析名稱 → 確認授權 → 比對 Notebook ID | ✅ OK |
| 步驟 4 | 載入 `讀書報告核心概念.md` 作為 Prompt | ✅ OK |
| **步驟 4.5（缺）** | **擷取來源目錄、建立章節基準（Ground Truth）** | ❌ 不存在 |
| 步驟 5 | 呼叫 NotebookLM 生成報告 | ⚠️ 盲生，不知總章數 |
| 步驟 6 | 核對報告是否涵蓋所有章节 | ⚠️ 無基準可對照，漏章時誤判為通過 |
| 步驟 7 | 交付結果 | — |

### 1.2 實際驗證結果

**來源：** `C:\Users\asaoka.zhong\Documents\電子書\Calibre Portable\持續買進.epub`

透過 NCX（`.ncx` 目錄檔）解析，本書結構如下：

| 分類 | 數量 |
|------|------|
| 主體章節（第 1-21 章） | 21 |
| 前言 | 1 |
| 分部標題（第1部｜儲蓄、第2部｜投資） | 2 |
| 結語 | 1 |
| 附錄（致謝、註釋、版權頁） | 3 |
| **主要內容章節目錄** | **約 25 項** |

**報告實際產出：** 只到第 11 章 → 漏掉第 12-21 章（共 10 章，佔內容近半）

### 1.3 根本原因

步驟 6 的核對邏輯：「將來源章節目錄逐一對照報告內文」——但**步驟 3 和 4 從來沒有做過「將來源章節目錄提取並紀錄」**。Agent 拿到報告時沒有基準， NotebookLM 截斷到第 11 章時，Agent 以為就是這麼多，核對步驟形同虛設。

---

## 二、實作方案

### 2.1 新增步驟 3.5：建立 Ground Truth 基準

**位置：** 插入於現有步驟 3（比對 Notebook ID）之後、步驟 4（載入規則）之前。

**執行邏輯：**

```
### 3.5 擷取來源目錄並建立章節基準（Ground Truth Baseline）

在呼叫 NotebookLM 生成報告之前，必須先取得來源文件的完整目錄，
作為後續核對的唯一基準。

#### 取決於來源文件類型：

**類型 A：本地 EPUB / PDF 檔案**
- 執行章節解析，取得完整章節目錄。
- EPUB 優先：用 python + zipfile 讀取 .ncx 或 nav.xhtml，
  以 XML 解析（ElementTree）或正規表達式萃取所有 `navLabel/text`。
- PDF：用 `pydantic` 或其他工具讀取 TOC，或直接請使用者提供目錄。
- 只保留「主要章節」（第 X 章 / 前言 / 結語），
  排除封面、書名頁、版權頁等前導/尾注項目。

**類型 B：已有 NotebookLM 筆記本中的來源**
- 執行 `nlm source list <notebook_id>` 列出來源。
- 若來源是 EPUB/PDF，仍優先用類型 A 的方式解析本地檔案。
- 若無本地檔案，可改為用 `nlm notebook describe <notebook_id>`
  取得 NotebookLM 自己產生的 AI 摘要（作為次級基準）。

#### 輸出格式（必須記錄下來）：
```
Ground Truth 目錄：
  N = 25 個主要章節
  [1] 前言
  [2] 第1章｜你該從何處開始？
  [3] 第2章｜你應該存多少錢？
  ...
  [23] 第21章｜最重要的資產
  [24] 結語 持續買進法則
  [25] 致謝
```

#### 失敗處理：
- 若解析失敗或無法取得目錄，**不得跳過**。
- 改為用 `nlm notebook query <notebook_id> "請列出這份來源文件的所有章節與段落結構"` 向 NotebookLM 反向詢問。
- 再次失敗時，標 `UNVERIFIED: 無法取得來源目錄，後續核對步驟可能失效` 並告知使用者。
```

### 2.2 修改步驟 6：使用 Ground Truth 基準核對

**位置：** 替換現有步驟 6 的「章節涵蓋度核對」段落。

```
### 6. 用真實輸出核對，不接受「看起來完成了」

這一步是整個技能最容易被跳過、但最不該跳過的一步。
生成完成後：

1. **Ground Truth 比對（最重要）**：
   拿步驟 3.5 紀錄的「Ground Truth 目錄」（總章數 N）
   與報告內文的「## 章節標題」逐一比對。
   - 若報告最後一章的序號 M < N → **截斷失敗**，進入補全機制。
   - 若報告有 N 章但內容偏簡 → 標註哪些章節內容較少。
   - **禁止只看 NotebookLM 回報的「涵蓋度自我檢查清單」**，
     該清單是 NotebookLM 自己生成的，可能漏標。
     必須直接翻報告內文，確認每一章都有對應的 `## 標題` 段落。

2. **忠實度抽查**：
   掃過報告內容，看有沒有出現「這顯示」「這意味著」「值得注意的是」
   之類的主觀詮釋語句，或明顯超出原文範圍的背景知識。

3. **完整性檢查**：
   確認報告沒有在句子中間被截斷、沒有明顯的生成錯誤或空白區塊。

4. **語言檢查**：
   如果來源文件不是中文（英文、日文等），確認報告本文仍全程以繁體中文撰寫，
   只有必要的專有名詞才附原文。
```

### 2.3 新增步驟 6.5：截斷補全機制

```
### 6.5 截斷補全機制（M < N 時執行）

若步驟 6 判定報告有截斷（M < N）：

1. 找出報告最後一章的序號 M，以及漏掉的章節 [M+1, ..., N]。
2. 針對漏掉的章節，分批次重新生成：
   - 批次一：生成第 M+1 到第 min(M+5, N) 章。
   - 批次二：若有剩餘，繼續生成。
3. 將各批次結果合併，再次執行步驟 6 的 Ground Truth 比對，
   確認 M_new == N 後再交付。
4. 若分次生成仍無法完整，明確告知使用者：
   「NotebookLM 無法一次處理完整書籍，已分段生成，
   涵蓋了第 X 到第 Y 章，後續章節需要另行處理。」
```

---

## 三、技術實作細節

### 3.1 EPUB 目錄解析（Python 範例）

```python
import zipfile
import re
from xml.etree import ElementTree as ET

def extract_epub_toc(epub_path):
    with zipfile.ZipFile(epub_path, 'r') as z:
        files = z.namelist()
        ncx_files = [f for f in files if f.endswith('.ncx')]
        if not ncx_files:
            return None
        content = z.read(ncx_files[0]).decode('utf-8')
    
    ET.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
    root = ET.fromstring(content)
    ns = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
    
    navmap = root.find('ncx:navMap', ns)
    chapters = []
    for np in navmap.findall('ncx:navPoint', ns):
        label = np.find('ncx:navLabel/ncx:text', ns)
        if label is not None:
            text = label.text.strip()
            order = int(np.get('playOrder', '999'))
            chapters.append((order, text))
    
    chapters.sort(key=lambda x: x[0])
    return chapters
```

### 3.2 過濾前導/尾注項目

```python
SKIP_PREFIXES = ['封面', '書名頁', '版權頁', '各界好評', '目錄']
CHAPTER_PATTERN = re.compile(r'^(第[零一二三四五六七八九十百\d]+章|[前結]言|結語|致謝|註釋)')

def filter_main_chapters(chapters):
    return [c for c in chapters if CHAPTER_PATTERN.match(c[1]) or '｜' in c[1]]
```

### 3.3 所需 Python 套件

- `ebooklib`（pip install ebooklib）— 用於更複雜的 EPUB 解析
- 標準庫 `zipfile` + `xml.etree.ElementTree` — 解析 NCX，無需額外套件

---

## 四、修改檔案清單

| 檔案 | 修改內容 |
|------|----------|
| `~/.claude/skills/book-reader/SKILL.md` | 新增步驟 3.5、修改步驟 6、新增步驟 6.5 |
| `~/.gemini/config/skills/book-reader/SKILL.md` | 同步上述修改 |

**不需要修改**：`讀書報告核心概念.md`（那份是給 NotebookLM 的 prompt，保持原樣即可）

---

## 五、驗證方式

修改完成後，用《持續買進》EPUB 重新執行一次：

1. 確認輸出涵蓋第 1-21 章 + 前言 + 結語
2. 確認無截斷（報告最後一章應該是第 21 章或結語）
3. 確認無主觀詮釋語句（掃過全文）
4. 確認語言全程為繁體中文

---

## 六、備註

- 本次實作驗證中，`notebooklm_tools` Python CLI 出現認證過期（Authentication expired）與 `studio_status` TypeError bug，改以 `nlm` MCP CLI 繞過。建議在 SKILL.md 步驟 2 中補充「若 `notebooklm_tools` 失敗，改用 `nlm` CLI」的備用路徑。
- 本次實作中，測試用筆記本「持續買進 EPUB版」（ID: 86582df0-25bd-41d3-9729-28156e44115c）已刪除，不影響現有筆記本。
- 報告輸出檔案：`C:\Users\asaoka.zhong\Desktop\持續買進_報告2.md`（較完整版本）
