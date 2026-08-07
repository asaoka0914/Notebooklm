# book-reader 技能修正計畫 v3

> 產生日期：2026-08-07
> 依據：對 v2 計畫執行結果的複查，比對 `scripts/01~04`、`README.md`、`handoff.md`、`changelog_index.json` 後發現的落實落差與新問題。
> 適用對象：後續處理此計畫的 Agent（會直接修改程式碼）。

---

## 前情提要：v2 計畫執行結果複查

| v2 問題 | 狀態 | 備註 |
|---|---|---|
| 問題1 認證失敗恢復 | ✅ 已做（但範圍不足，見本文問題 A） | `ensure_auth()` 已寫入 `01_init_notebook.py` |
| 問題2 Obsidian 路徑動態化 | ✅ 已做 | `find_obsidian_raw_dir()` 已生效 |
| 問題3 SKILL.md 三處同步 | ⚠️ 未確認完成 | 8/7 這次 commit 只改了本機這份，`~/.gemini/...` 與 chezmoi 路徑未見於 changelog |
| 問題4 禁止詞過濾 | ✅ 已做 | `clean_forbidden_phrases()` 已生效 |
| 問題5 每批 2 章 | ✅ 已做 | `book_config.yaml` 已改 |
| 問題6 規則檔強化 | ❌ 未做 | 見本文問題 D |

---

## 問題 A：認證過期恢復機制只覆蓋「執行前」，未覆蓋「執行中」🔴 P0

**根本原因**

`ensure_auth()`（自動偵測過期→啟動 Chrome CDP→重新取得 token）**只在 `01_init_notebook.py` 的 `init_notebook()` 開頭被呼叫一次**。真正會長時間執行、跨多個批次呼叫 API 的是 `02_batch_generate.py`，但它的 `run_query_via_cli()`：

```python
for attempt in range(1, max_retries + 1):
    auth = AuthManager()
    profile = auth.load_profile()   # 只是重讀快取的 profile，不會刷新
    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
    try:
        res = client.query(notebook_id, prompt)
        ...
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e):
            ...
        else:
            print(f"    [SDK Error]: {err_msg[:300]}")  # 認證過期通常會落在這裡，僅印出錯誤後重試同一組壞憑證
```

**症狀**：7 個批次的執行過程中（含批次間 8 秒延遲 + NotebookLM 回應時間，實測可能超過 10-20 分鐘），若 CSRF Token 在中途被 Google rotate，`01` 開頭做的認證檢查完全幫不上忙——`02` 會用同一組已失效的憑證重試 3 次、全部失敗，該批次直接進 `failed_batches.json`，且**後續所有批次也會用同一組壞憑證繼續嘗試，大概率連環失敗**。

**修正方案**

在 `02_batch_generate.py` 的 `run_query_via_cli()` 中：
1. 每次 `client.query()` 拋出例外時，先判斷是否為認證類錯誤（`ClientAuthenticationError`、`401`、`UNAUTHENTICATED`、或訊息含「auth」「token」等關鍵字），若是，**呼叫 `01_init_notebook.py` 中已寫好的 `ensure_auth()`**（可考慮把 `ensure_auth()` 抽到共用模組，例如 `scripts/_auth_utils.py`，供 01、02 共同 import，避免重複定義）成功後才進行下一次重試。
2. `run_batch_generation()` 主迴圈中，每處理完一個批次、或每隔 N 個批次，主動呼叫一次 `check_auth(profile='default', live=True)` 做輕量健康檢查，過期就提前觸發恢復，而不是等到 API 呼叫失敗才處理。

```python
def ensure_auth_inline():
    """批次執行中途的輕量認證檢查與恢復，複用 01_init_notebook.py 的 ensure_auth 邏輯。"""
    from scripts._auth_utils import ensure_auth  # 建議抽成共用模組
    return ensure_auth()
```

---

## 問題 B：配額耗盡（RESOURCE_EXHAUSTED）帳號切換流程非全自動，無等待與自動接續 🔴 P0

**根本原因**

目前偵測到 `RESOURCE_EXHAUSTED` 後的處理：

```python
if "RESOURCE_EXHAUSTED" in err_msg or "error code 8" in err_msg:
    print("⚠️ [Quota Limit Alert] ...")
    print("👉 請在您的 Terminal 貼上並執行以下指令彈出 Chrome 切換 Google 帳號：")
    print("   python -c \"from notebooklm_tools.cli.main import app; app(['login', '--clear', '--force'])\"")
    return None
```

只是印出訊息後直接 `return None`，該批次寫入 `failed_batches.json`，**主迴圈會繼續嘗試下一批次，但帳號配額仍是耗盡狀態，之後每一批大機率會重複同樣的失敗**，直到跑完所有批次才停下來。整個流程**沒有暫停等待使用者完成帳號切換，也沒有偵測到新帳號登入後自動恢復並重試當下批次**。

**修正方案**

1. 偵測到 `RESOURCE_EXHAUSTED` 時，**不要直接放棄該批次並繼續往下跑**，而是：
   - 印出提示後，呼叫一個阻塞式函式（例如輪詢 `check_auth(live=True)` 或偵測 `notebooklm_tools` 快取的 profile 是否已更新為新帳號的 session），等待使用者完成切換（設定合理逾時，例如 5 分鐘，逾時才真正放棄該批次並繼續）。
   - 或提供 `--pause-on-quota` 參數：偵測到配額耗盡時直接 `sys.exit()` 並保留已完成批次（續傳邏輯已支援），讓使用者手動切帳號後重跑同一指令即可從失敗批次接續，並在 README/SKILL.md 中明確告知這是目前的正確操作方式（而非讓腳本自己在背景繼續空轉失敗）。
2. 兩種方案擇一即可，重點是**避免「配額耗盡後腳本仍笨拙地繼續嘗試並產生一長串失敗批次」**這個現象。

---

## 問題 C：Ground Truth 章節目錄比對機制只存在於文件，程式碼從未真正串接 🔴 P0（本工具核心功能缺失）

**根本原因**

`README.md`、`book-reader_SKILL.md`、`handoff.md`（2026-08-05 紀錄）都聲稱已完成「Ground Truth TOC 解析 + 1 對 1 涵蓋度比對 + 截斷自動補全（`MAX_RETRY_BATCH = 3`）」機制，用來避免 NotebookLM 輸出被截斷（例如全書 14 章只寫到第 11 章）卻被誤判為完成。

但實際檢查程式碼：

- `01_init_notebook.py` 中 `extract_epub_toc()`、`discover_actual_toc()` **兩個函式都已寫好，但 `init_notebook()` 主流程完全沒有呼叫它們**，是未串接的死程式碼。
- `04_qc_check.py` 目前只做三件事：① 檢查 `failed_batches.json`、② 檢查每章字數（≥1000 字）與結構元素（📌核心概念/💡重點擷取）、③ 檢查腳註前後一致性。**完全沒有任何拿 EPUB 真實章節數與報告實際章節數做比對的邏輯，也沒有 `MAX_RETRY_BATCH` 補全觸發機制。**

`changelog_index.json` 也印證了這點：2026-08-05 17:30 那筆「重構防截斷流程與 Ground Truth TOC 檢核機制」修改的檔案只有 `book-reader_SKILL.md` 與外部 gemini config，**沒有觸及 `scripts/` 底下任何 `.py`**。

**症狀**：目前若 NotebookLM 又發生截斷，QC 只看字數與結構夠不夠，**抓不出漏章**，等於這個工具存在的核心防呆功能形同虛設。

**修正方案**

1. 在 `01_init_notebook.py` 的 `init_notebook()` 中，於解析 `book_local_path` 後實際呼叫 `extract_epub_toc(book_local_path)`，取得章節清單，寫入例如 `config/ground_truth_toc.json`：
   ```json
   {"total_chapters": 14, "chapters": ["第 1 章 ...", "第 2 章 ...", ...]}
   ```
2. 在 `04_qc_check.py` 新增一個檢查段落，讀取 `ground_truth_toc.json`，用正則從最終 Markdown 抓出所有 `## ` 開頭的章節標題，與 Ground Truth 清單做 1 對 1 比對：
   - 若報告涵蓋章節數 < Ground Truth 總數，視為 **Hard-Fail**（`passed_all = False`，且需明確印出缺漏的章節名稱清單）。
3. 在 `02_batch_generate.py` 或一個新的 `05_backfill.py` 中，讀取 QC 檢查回傳的缺漏章節清單，針對缺漏章節重新組 prompt 補跑（上限 `MAX_RETRY_BATCH = 3` 次），跑完後重新組裝、重新 QC，直到涵蓋完整或達重試上限為止。
4. 若 EPUB 本機檔案不存在（例如使用者只給了 NotebookLM 筆記本 ID 沒有本機書檔），退回使用 `discover_actual_toc()`（呼叫 NotebookLM 詢問全書目錄）作為 Ground Truth 的備援來源。

---

## 問題 D：`讀書報告核心概念.md` 禁止詞清單未依 v2 計畫強化 🟡 P2

**現況**

`source/讀書報告核心概念.md` 目前第 1 條仍只是：

```
1. **完全忠實**：僅能擷取原文明確記載的事實、數據與觀點，嚴禁加入個人推論、延伸解釋或主觀評論（如「這顯示」、「這意味著」）。
```

v2 計畫要求的完整 8 詞清單（這顯示、這意味著、這說明、這反映了、這代表、值得注意的是、可以發現、由此可見）**沒有寫進規則檔**，目前完全依賴 `03_assemble_report.py` 的 `clean_forbidden_phrases()` 事後清洗，屬於治標不治本（NotebookLM 產出時仍會用這些詞，只是輸出後被字串替換掉，可能造成語意不順）。

**修正方案**

依 v2 計畫原案，將規則檔第 1 條改為：

```markdown
1. **完全忠實**：僅能擷取原文明確記載的事實、數據與觀點，嚴禁加入個人推論、延伸解釋或主觀評論。
   - 禁止詞：不得出現「這顯示」「這意味著」「這說明」「這反映了」「這代表」「值得注意的是」「可以發現」「由此可見」等詞。
   - 若原文有「這顯示」之類的表述，必須改為直接陳述事實（如「數據表明」或改為數據本身）。
```

並建議 `clean_forbidden_phrases()` 中的字典與此處清單保持同步維護（未來新增禁止詞時兩處要一起改）。

---

## 問題 E：SKILL.md 三處同步狀態未確認完成 🟡 P2

`changelog_index.json` 顯示 2026-08-07 14:03 這次修正只更動了本機 `book-reader_SKILL.md`，並未見到對應更新 `~/.gemini/config/skills/book-reader/SKILL.md` 與 chezmoi 路徑的紀錄（v2 計畫問題 3 的修正步驟）。建議比對三處檔案的最後修改時間與內容雜湊，確認是否仍不同步，若是則依 v2 計畫的 `cp` + `chezmoi add/commit` 步驟重新執行一次。

---

## 執行順序建議

| 順序 | 問題 | 優先級 | 原因 |
|---|---|---|---|
| 1 | 問題 C：Ground Truth 比對機制真正串接 | P0 | 工具核心防呆功能，目前完全沒作用 |
| 2 | 問題 A：批次執行中途認證恢復 | P0 | 直接對應使用者反映「一直認證過期」的實測問題 |
| 3 | 問題 B：配額耗盡後暫停等待/明確重跑指引 | P0 | 避免帳號切換後腳本仍空轉出一堆失敗批次 |
| 4 | 問題 D：規則檔禁止詞清單補完整 | P2 | 治標已生效，此為治本 |
| 5 | 問題 E：SKILL.md 三處同步確認 | P2 | 影響跨裝置一致性，非功能性錯誤 |

---

## 驗證方式

1. 人為將某本書的 EPUB 目錄準備好（已知總章數 N），故意讓 NotebookLM 只回應到第 N-3 章，確認 `04_qc_check.py` 能明確 Hard-Fail 並列出缺漏章節，且觸發補全流程直到涵蓋完整。
2. 執行 `02_batch_generate.py` 過程中，人為讓 CSRF Token 失效（或等待自然過期時機），確認腳本能在批次執行「中途」自動偵測並恢復認證，不需要重新從頭啟動整個 pipeline。
3. 模擬 `RESOURCE_EXHAUSTED` 錯誤，確認腳本會明確暫停/中止並給出可執行的接續指引，且使用者切換帳號後重跑指令能從失敗批次正確接續，不會產生連環失敗的批次清單。
4. 確認 `讀書報告核心概念.md` 與 `clean_forbidden_phrases()` 的禁止詞清單一致。
5. 比對三處 SKILL.md 內容雜湊值一致。
