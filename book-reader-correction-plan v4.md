# book-reader 技能修正計畫 v4 — Ground Truth TOC 純筆記本情境優化

> 產生日期：2026-08-07
> 依據：使用者提問「純筆記本（無本機 EPUB 檔）情境下，能否直接請 NotebookLM 列出章節清單再解析」，複查後確認此機制已存在（`discover_actual_toc()`），但目前是靠關鍵字逐行過濾自由文字回覆，建議改為直接要求 JSON 輸出以提高穩定性。
> 適用對象：後續處理此計畫的 Agent（會直接修改程式碼）。

---

## 背景

`01_init_notebook.py` 目前的 Ground Truth TOC 取得邏輯：

```python
gt_chapters = []
if book_local_path and os.path.exists(book_local_path):
    gt_chapters = extract_epub_toc(book_local_path)   # 優先：本機 EPUB 直接解析 .ncx/nav.xhtml

if not gt_chapters:
    raw_gt = discover_actual_toc(notebook_id)          # Fallback：問 NotebookLM
    if raw_gt:
        for line in raw_gt.split('\n'):
            line_str = line.strip()
            if line_str and ("章" in line_str or "Chapter" in line_str or "法則" in line_str):
                gt_chapters.append(line_str)
```

`discover_actual_toc()` 送給 NotebookLM 的 prompt 要求「列出這本書『正文』的完整章節目錄清單」，但沒有要求固定輸出格式，回傳的是自由文字。目前解析方式是**逐行關鍵字比對**（只認「章」「Chapter」「法則」三個關鍵字），有兩個已知風險：

1. **命名慣例不符時會漏抓**：若書籍章節是「Part 1」「Unit 1」「Lesson 1」或純數字標題（無「章」字），關鍵字過濾會直接漏掉，導致 Ground Truth 清單不完整，QC 比對基準本身就是錯的。
2. **NotebookLM 附帶的說明句可能被誤判為章節**：例如回覆開頭「以下是本書的章節清單：」這類句子若含目標關鍵字，可能被誤抓進 `gt_chapters`，污染基準清單。

---

## 修正方案

### 元件：`scripts/01_init_notebook.py` 的 `discover_actual_toc()`

**1. 修改 prompt，明確要求純 JSON 輸出**

```python
def discover_actual_toc(notebook_id):
    """Query NotebookLM with a fresh isolated UUID to discover real chapter list, requesting strict JSON output."""
    import uuid
    from notebooklm_tools.services.auth import AuthManager
    from notebooklm_tools.core.client import NotebookLMClient

    auth = AuthManager()
    profile = auth.load_profile()
    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
    fresh_conv_id = str(uuid.uuid4())
    prompt = (
        "請僅依據來源書籍本身的實際內容（不要包含附錄、注釋、參考書目、推薦序等非正文部分），"
        "列出這本書「正文」的完整章節目錄清單。\n"
        "請「只」輸出一個合法 JSON 陣列，不要有任何前言、說明文字、Markdown code fence 或其他內容，"
        "格式範例：[\"第1章 xxx\", \"第2章 xxx\", \"Part 1: xxx\"]\n"
        "請保留書中原本的章節命名方式（可能是「第X章」「Chapter X」「Part X」「Unit X」或純標題），"
        "不要自行套用固定格式硬改章節名稱。"
        "請勿自行推測或延伸不存在的章節，如果全書只到第 N 章，請明確只列出 N 個項目。"
    )
    res = client.query(notebook_id, prompt, conversation_id=fresh_conv_id)
    return res.get("answer", "") if res else ""
```

**2. 修改呼叫端解析邏輯，優先嘗試 JSON 解析，失敗才退回關鍵字過濾（雙保險，不降級）**

```python
if not gt_chapters:
    raw_gt = discover_actual_toc(notebook_id)
    if raw_gt:
        gt_chapters = _parse_toc_response(raw_gt)

def _parse_toc_response(raw_gt):
    """優先嘗試解析 JSON 陣列，失敗則退回關鍵字逐行過濾（保留原本的相容性）。"""
    import json, re

    # 1. 嘗試直接解析（可能夾雜 code fence，先剝除）
    cleaned = raw_gt.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return [x.strip() for x in parsed if x.strip()]
    except Exception:
        pass

    # 2. JSON 解析失敗，退回原本的關鍵字過濾（相容非章/Chapter/法則以外的情況也擴充關鍵字）
    chapters = []
    keywords = ("章", "Chapter", "chapter", "法則", "Part", "PART", "Unit", "Lesson")
    for line in raw_gt.split('\n'):
        line_str = line.strip()
        if line_str and any(kw in line_str for kw in keywords):
            chapters.append(line_str)
    return chapters
```

**3. `04_qc_check.py` 不需修改**——它讀取的是已經解析好的 `ground_truth_toc.json`，跟來源是 JSON 解析還是關鍵字過濾無關，維持現有比對邏輯即可。

---

## 為什麼是「雙保險」而不是直接取代

NotebookLM 偶爾仍可能不遵守「只輸出 JSON」的指令（例如附加一句客套話），若直接假設一定拿得到合法 JSON、拿不到就整個失敗，反而讓純筆記本情境的 Ground Truth 機制比現在更脆弱。因此設計上是「JSON 解析優先，失敗才退回關鍵字過濾」，兩層機制疊加，確保不會比現有行為更差，同時擴充了關鍵字清單（新增 Part/Unit/Lesson）讓退回機制也比原本更寬容。

---

## 驗證方式

1. 對一個純筆記本（無本機 EPUB、章節命名為「第X章」）測試，確認 JSON 解析路徑正確取得完整章節清單，數量與人工目視核對書本章節數一致。
2. 對一個章節命名非制式格式的筆記本（若有測試素材，例如章節只寫「Part 1」）測試，確認 JSON 解析仍能正確取得（因為 JSON 陣列本身不依賴關鍵字，只要 NotebookLM 有把該行放進陣列即可）。
3. 人為模擬 NotebookLM 回覆非合法 JSON（例如夾雜說明文字）的情況，確認能正確退回關鍵字過濾且不會整個流程中斷。
4. 確認 `ground_truth_toc.json` 寫入內容與 `04_qc_check.py` 的比對結果符合預期，QC Hard-Fail 邏輯不受影響。
