# 修正計畫：02_batch_generate.py 全域中斷保護（Circuit Breaker）漏洞

> 產生日期：2026-08-23
> 審核者：Claude（程式碼審核角色）
> 狀態：**待實作**
> 對照：本計畫修正另一 Agent 於 2026-08-23 提出的診斷（見下方「審核結論」），已用 Filesystem 工具實際讀取程式碼逐項核實。

---

## 一、審核結論（重要：另一 Agent 的診斷有 1 項失準，2 項確認屬實）

| # | 另一 Agent 的診斷 | 核實結果 | 說明 |
|---|---|---|---|
| 1 | 非互動終端會觸發 `input()` 的 `EOFError`，導致選單被取消 | ❌ **不準確** | 實際讀取 `_auth_utils.py` 後發現，`switch_google_account_interactive()` 與 `_select_chrome_profile_interactive()` **都已經有 `sys.stdin.isatty()` 防護**，非互動環境會直接印出警告並 `return False`，並不會真的丟出 `EOFError`。這部分**不需要修改**，另一 Agent 的猜測與現有原始碼不符（可能記錯了舊版行為）。 |
| 2 | 缺少全域致命中斷機制，導致每個 Batch 都重複狂試 | ✅ **確認屬實，為真正根因** | 已讀取 `02_batch_generate.py` 完整邏輯，確認即使 `wait_for_account_switch()` 失敗，也只會讓當下這個 Batch 標記失敗，外層 `for b in batches` 迴圈**完全沒有中止機制**，會繼續跑下一個 Batch。詳見第二節。 |
| 3 | 帳號池目前所有帳號皆在冷卻中 | ⚠️ **目前狀態不成立** | 已讀取 `auth_pool/pool_status.json`，目前兩個帳號 `cooldown_until` 皆為 `null`、`status` 皆為 `active`（`last_rotated` 為 2026-08-22 09:30，冷卻期 30 分鐘早已過期）。**目前不需要手動重置冷卻狀態**；建議修正計畫改為「執行前先檢查現況，非必要不要盲目清空」。 |
| 4（可選） | 將 `jessie3408h@gmail.com` 加入 `pool_config.yaml` 擴充為 3 帳號池 | ✅ 確認可行 | `pool_config.yaml` 目前僅有 `asaoka0914_gmail`、`gwa20080808_gmail` 兩組，此為單純擴充設定，風險低，可一併處理。 |

**結論：另一 Agent 的核心根因判斷（第 2 點）正確，且與過往稽核中已知的原則相符 —— 這正是「只治標（重試/退避）沒有治本（全域 Circuit Breaker / Checkpoint）」的典型案例。但第 1 點與第 3 點的細節描述有誤，請依本計畫的修正內容為準，不要照另一 Agent 原始訊息逐字實作。**

---

## 二、根因詳細分析（逐行核對 `scripts/02_batch_generate.py`）

### 漏洞位置 A：`run_query_via_cli()` 中 RESOURCE_EXHAUSTED 分支

```python
if "RESOURCE_EXHAUSTED" in err_msg or "error code 8" in err_msg:
    if wait_for_account_switch(notebook_id=notebook_id, timeout_sec=300):
        ...
        continue
    return None   # ← 問題：帳號切換徹底失敗時，只是默默回傳 None
```

`wait_for_account_switch()` 失敗（帳號池全冷卻 + 互動式選單也不可用）時，僅 `return None`，被上層當成「這次請求普通失敗」處理，會繼續耗用剩餘的 `max_retries`（3 次）逐一重試 —— 但配額耗盡的情況下重試毫無意義，純粹浪費時間。

### 漏洞位置 B：`run_batch_generation()` 外層迴圈完全沒有中止路徑

```python
for attempt in range(1, max_retries + 1):
    try:
        data = run_query_via_cli(...)
        ...
    except RateLimitExhaustedError as rle:
        last_err = str(rle)
        print(f"  🛑 [Circuit Breaker] {last_err}")
        failed_batches.append({...})
        break              # ← 只跳出「重試迴圈」，不影響外層 Batch 迴圈！
    except Exception as e:
        last_err = str(e)
    ...

if not success:
    ...                    # 記錄失敗
print(f"  Throttling: waiting {delay_sec}s before next query...")
time.sleep(delay_sec)
# ← 外層 for b in batches 迴圈會直接繼續跑下一個 Batch，沒有任何 sys.exit()
```

現有程式中，`RateLimitExhaustedError` **已經存在**（由 `RateLimiter.record_error_and_backoff()` 在連續退避滿 5 輪後拋出），且也有對應的 `except RateLimitExhaustedError` 攔截與印出 `🛑 [Circuit Breaker]` 訊息 —— **但這個攔截只 `break` 掉當前 Batch 的重試迴圈，並沒有終止整個腳本**。這就是為什麼日誌會看到「明明已經印出 Circuit Breaker 警告，卻還是繼續往下一個 Batch 洗」的弔詭現象。

**這正是根本原因**：現有的「Circuit Breaker」名不符實，只是「Retry Breaker」（跳過重試），並非真正的「全域致命中斷」。

---

## 三、修正方案

### 修正 1：`run_query_via_cli()` — 帳號切換徹底失敗時，改為直接拋出致命例外

**位置**：`scripts/02_batch_generate.py`，`run_query_via_cli()` 函式內，RESOURCE_EXHAUSTED 分支

```python
if "RESOURCE_EXHAUSTED" in err_msg or "error code 8" in err_msg:
    if wait_for_account_switch(notebook_id=notebook_id, timeout_sec=300):
        auth = AuthManager()
        profile = auth.load_profile()
        client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
        continue
    # 修正：帳號池與互動式切換皆失敗 → 判定為全域配額耗盡，立即中止，不再浪費重試次數
    raise RateLimitExhaustedError(
        f"帳號池所有帳號均在冷卻中且無法互動式切換帳號，全域配額耗盡（Batch 層級偵測）"
    )
```

### 修正 2：`run_batch_generation()` — Circuit Breaker 觸發時要真正終止整個程式，而不是跳到下一個 Batch

**位置**：`scripts/02_batch_generate.py`，`run_batch_generation()` 內的 Batch 迴圈

```python
    except RateLimitExhaustedError as rle:
        last_err = str(rle)
        print(f"  🛑 [Circuit Breaker] {last_err}")
        failed_batches.append({
            "batch": b_num,
            "chapters": ch_list,
            "error": last_err
        })
        # 修正：寫出失敗紀錄後，立即終止整個批次生成任務，不再嘗試後續 Batch
        failed_batches_path = os.path.join(BASE_DIR, "failed_batches.json")
        with open(failed_batches_path, "w", encoding="utf-8") as ff:
            json.dump(failed_batches, ff, ensure_ascii=False, indent=2)
        print(f"\n[FATAL] 全域配額耗盡，已中止批次生成。已完成的 Batch 已保留（中斷續傳機制），"
              f"待帳號冷卻結束或新增帳號後，重新執行本腳本即可自動從中斷處繼續。")
        sys.exit(1)
```

> 註：由於 `run_batch_generation()` 開頭已有「檢查中斷續傳」邏輯（跳過已存在且非空的 `batch_XX.json`），`sys.exit(1)` 後重新執行腳本可以安全地從中斷點恢復，不會重複耗用已成功的 Batch 額度。

### 修正 3（可選，風險低）：擴充帳號池至 3 組帳號

**位置**：`auth_pool/pool_config.yaml`

```yaml
  - id: jessie3408h_gmail
    email: jessie3408h@gmail.com
    token_file: tokens/jessie3408h_gmail.json
    enabled: true
    note: "第三備援帳號（Profile 5 / Amy）"
```

**先決條件**：需確認 `jessie3408h@gmail.com` 對目標 NotebookLM 筆記本有存取權限（或依賴 `sync_notebook_collaborators()` 自動共用機制）。

### 不需執行的項目

- ❌ 不需修改 `_auth_utils.py` 的 `input()` / EOFError 處理 — 現有 `isatty()` 防護已正確運作。
- ❌ 不需手動清空 `pool_status.json` 冷卻狀態 — 執行前請先用 `python -c "from _auth_pool import pool_status_report; pool_status_report()"` 確認現況，若仍顯示冷卻中才需要處理，切勿無條件覆寫。

---

## 四、實作步驟（給執行 Agent）

1. 對 `scripts/02_batch_generate.py` 套用「修正 1」與「修正 2」的程式碼變更。
2. （可選）對 `auth_pool/pool_config.yaml` 套用「修正 3」。
3. 執行 `python -c "from _auth_pool import pool_status_report; pool_status_report()"`，確認目前帳號池狀態，記錄下來附在完成報告中。
4. 撰寫最小重現測試：可暫時將 `RateLimiter.max_pause_rounds` 調低（例如改成 1）或直接手動呼叫 `wait_for_account_switch()` 搭配 mock 使其回傳 `False`，驗證：
   - `run_query_via_cli()` 是否正確拋出 `RateLimitExhaustedError`
   - `run_batch_generation()` 是否正確寫出 `failed_batches.json` 並以 `sys.exit(1)` 結束，**且不再繼續處理後續 Batch**
5. 測試完成後將暫時調低的參數改回原值（`max_pause_rounds = 5` 等），並附上修改前後 diff。

---

## 五、驗收標準（Claude 覆核時將檢查）

- [ ] `run_query_via_cli()` 中 `return None` 已改為 `raise RateLimitExhaustedError(...)`（帳號切換失敗分支）
- [ ] `run_batch_generation()` 的 `except RateLimitExhaustedError` 區塊內有 `sys.exit(1)`，且該行確實會終止整個 Process（非僅跳出內層迴圈）
- [ ] 檔案異動時間戳（`get_file_info` 的 `modified` 欄位 + size delta）確實有變化，非空跑
- [ ] 提供一次「全域配額耗盡」情境下的實際執行 log 或測試結果，證明腳本會在偵測到當下立即停止，不會繼續嘗試後續 Batch
- [ ] 若套用修正 3，確認 `pool_config.yaml` 語法正確（`python -c "import yaml; yaml.safe_load(open('auth_pool/pool_config.yaml', encoding='utf-8'))"` 不噴錯）

---

## 六、變更歷史

- 2026-08-23：Claude 初版建立，核實另一 Agent 診斷並修正其中 EOFError 與冷卻狀態兩項失準之處，補上明確程式碼修正與驗收標準。
