# Multi-Profile Auth Pool 缺陷修復計畫 (Fix Plan)

本文件專為接手/協作 Agent 撰寫，提供明確的修復指引、程式碼範本與驗收標準。

---

## 一、問題描述 (Problem Statement)

### 規格 vs 實作落差
對照原計畫書 `multi-profile-auth-pool-plan.md` 第十節規劃之主流程：
```python
def ensure_auth_pool() -> bool:
    # 1. get_or_init_status() → 取當前帳號
    # 2. fetch_token_headless() → 取 Token
    # 3. 成功 → True
    # 4. 失敗 → rotate_account() → 重試（最多輪換一圈）
    # 5. 全部失敗 → fallback 到 _auth_utils.ensure_auth()
```

### 實際程式碼現況
在 `scripts/_auth_pool.py` 中，`ensure_auth_pool()` 函式跑完 `for` 迴圈（所有帳號均認證失敗、冷卻或找不到 Profile）後，直接執行 `return False`：

```python
        else:
            print(f"❌ 帳號 [{current_acc['id']}] 認證或 Profile 比對失敗，嘗試切換下一個帳號...")
            current_acc = rotate_account(pool_status, config)
            if not current_acc:
                break

    return False  # ⚠️ 缺少計畫書規定的 fallback 步驟 5
```

### 實務影響
在外層 `_auth_utils.py` 的 `ensure_auth_with_pool()` 中：
```python
if pool_config.exists():
    try:
        return ensure_auth_pool()  # 回傳 False 時直接返回，不會走到 ensure_auth()
    except Exception as e:
        ...
return ensure_auth()
```
當在一台未登入池內個人帳號的全新環境（如公司筆電）執行時，`ensure_auth_pool()` 因比對不到 Profile 直接回傳 `False` 導致主程式中斷退出，無法進入原本 `ensure_auth()` 貼心的互動式選單（供使用者手動選擇本機既有的其他 Chrome Profile）。

---

## 二、修正範圍 (Scope of Changes)

> [!IMPORTANT]
> **嚴格限制修改範圍**：
> - **唯一允許修改檔案**：`scripts/_auth_pool.py`
> - **其餘檔案請勿改動**（包含 `scripts/_auth_utils.py`, `scripts/01_init_notebook.py`, `scripts/02_batch_generate.py`, `auth_pool/pool_config.yaml` 等），皆已核對無誤，請保持原樣。

---

## 三、修正內容 (Implementation Details)

請將 `scripts/_auth_pool.py` 中的 `ensure_auth_pool()` 函式替換為以下實作：
- 更新 docstring 補上步驟 5。
- **內部迴圈邏輯完全不變**（保持防呆與輪換流程）。
- 於迴圈結束時加入 `print` 提示並使用延遲匯入（Lazy Import）呼叫 `from _auth_utils import ensure_auth` 作為最終 fallback。

```python
def ensure_auth_pool() -> bool:
    """
    帳號池主入口：
    1. 載入設定與狀態檔。
    2. 取當前帳號並檢查是否冷卻；若冷卻則自動切換。
    3. 嘗試取 Token，若失敗或 Chrome 找不到 profile 則輪換嘗試下一個帳號（最多輪換一圈）。
    4. 若所有帳號皆失敗，自動 Fallback 回退至單帳號互動式 ensure_auth()。
    """
    config = load_pool_config()
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    if not accounts:
        print("⚠️ pool_config.yaml 中未設定任何可用帳號，切回單帳號模式...")
        from _auth_utils import ensure_auth
        return ensure_auth()

    pool_status = get_or_init_status()
    total_accounts = len(accounts)

    # 嘗試最多 total_accounts 次（內部邏輯完全不變）
    for attempt in range(total_accounts):
        current_id = pool_status.get("current_account")
        current_acc = next((acc for acc in accounts if acc["id"] == current_id), None)

        if not current_acc:
            current_acc = select_next_account(pool_status, config, exclude_current=False)
            if not current_acc:
                print("❌ 帳號池無可用帳號。")
                break
            pool_status["current_account"] = current_acc["id"]
            save_pool_status(pool_status)

        # 檢查當前帳號是否在冷卻
        acc_stat = pool_status.setdefault("accounts", {}).setdefault(current_acc["id"], {})
        if is_account_in_cooldown(acc_stat):
            print(f"⏳ 當前帳號 [{current_acc['id']}] 冷卻中，尋找下一個帳號...")
            current_acc = rotate_account(pool_status, config)
            if not current_acc:
                break

        # 執行 headless 取得 Token
        if fetch_token_headless(current_acc):
            # 更新成功使用狀態
            status_accounts = pool_status.setdefault("accounts", {})
            status_accounts[current_acc["id"]]["last_used"] = datetime.now().isoformat()
            status_accounts[current_acc["id"]]["total_requests"] = status_accounts[current_acc["id"]].get("total_requests", 0) + 1
            status_accounts[current_acc["id"]]["status"] = "active"
            save_pool_status(pool_status)
            print(f"✅ 帳號池認證成功！當前帳號：[{current_acc['id']}] ({current_acc.get('email')})")
            return True
        else:
            print(f"❌ 帳號 [{current_acc['id']}] 認證或 Profile 比對失敗，嘗試切換下一個帳號...")
            current_acc = rotate_account(pool_status, config)
            if not current_acc:
                break

    # 5. 全部失敗 → fallback 到 _auth_utils.ensure_auth()
    print("⚠️ 帳號池所有帳號均認證失敗或冷卻中，啟動優雅降級 (Fallback 至單帳號互動選單)...")
    from _auth_utils import ensure_auth
    return ensure_auth()
```

---

## 四、驗收標準與驗證要求 (Verification & Acceptance Criteria)

為確保修改確實生效並避免「口頭完成但實體檔案未變動」的情況，請執行 Agent 務必達成並回報以下項目：

1. **實體檔案修改檢查**：
   - 檢查 `scripts/_auth_pool.py` 的檔案修改時間（mtime）確實更新。
   - 使用 `git diff scripts/_auth_pool.py` 確認僅有 `ensure_auth_pool` 包含上述 diff，且無其他無關檔案改動。
2. **語法與匯入檢查**：
   - 執行 `python -m py_compile scripts/_auth_pool.py` 確認語法 100% 正確無報錯。
3. **單元測試回歸**：
   - 執行測試：`$env:PYTHONIOENCODING="utf-8"; python -m unittest tests/test_auth_pool.py`
   - 確認全套單元測試依然維持全數通過（OK）。
4. **具體回報要求**：
   - 回報時**必須附上實際的 `git diff` 程式碼片段**，禁止僅用「已修正」帶過。
