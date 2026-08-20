# 多 Profile 預認證帳號池（Multi-Profile Auth Pool）實作計畫

> **版本**：v1.2（GDrive 非必要版）| **建立日期**：2026-08-20
> **目標**：解決每次使用後 Token 立即失效、反覆手動認證的問題

---

## 一、問題確認

| 確認項目 | 結論 |
|----------|------|
| 使用帳號範圍 | ✅ 僅個人帳號（不含公司帳號） |
| Token 失效週期 | ⚠️ 每次使用完畢後，下一次啟動就失效（Session 型，一次性） |
| GDrive 同步延遲 | ✅ 可接受幾秒延遲（但 GDrive 非必要條件） |

---

## 二、依賴鏈分析（跨電腦核心問題）

### Token 不需跨電腦同步

由於 Token 每次使用完即失效，每台電腦執行時都必須重新 headless 取得新 Token。
因此 Token 本身是「純本機暫存」，**不需要同步到任何地方**。

### 真正需要跨電腦的只有「設定檔」

| 需要 | 同步方式 | GDrive 必要？ |
|------|----------|--------------|
| 程式碼（_auth_pool.py 等） | git pull | ❌ 不需要 |
| pool_config.yaml（帳號清單） | git pull（已規劃 git push） | ❌ 不需要 |
| Token（一次性）| 本機自動取得 | ❌ 完全不需要 |
| pool_status.json（輪換狀態） | 本機重置即可 | ❌ 不需要 |

> **結論：整套方案完全不依賴 GDrive，git pull 後即可在任何電腦使用。**

---

## 三、唯一真正的跨電腦挑戰：Chrome Profile 對應

`chrome_profile` 資料夾名稱在不同電腦可能不一樣：

| 電腦 | Chrome Profile 目錄 | 對應帳號 |
|------|---------------------|---------|
| 家用筆電 | `Default` | asaoka0914@gmail.com |
| 公司筆電 | `Default` | 可能是公司帳號！ |

若 `pool_config.yaml` 硬編碼 `chrome_profile: Default`，在公司筆電上可能認錯人。

### 解法：以 Email 為主鍵，動態查找 Chrome Profile

不在設定檔存 Profile 目錄名稱，改以 **email 為主鍵**，執行時呼叫已有的
`list_chrome_profiles_with_email()` 動態比對，自動找到正確的 Profile 目錄。

```
pool_config.yaml 指定 email: asaoka0914@gmail.com
  ↓
_auth_pool.py 呼叫 list_chrome_profiles_with_email()（已有函式）
  ↓
自動在本機 Chrome 找到 email 對應的 Profile 目錄（無論叫 Default 還是 Profile 3）
  ↓
啟動 headless 認證
```

---

## 四、修訂後的 pool_config.yaml 格式（email 主鍵版）

```yaml
version: 1
strategy: round_robin       # 輪換策略：round_robin | least_used | cooldown_first
cooldown_minutes: 30
accounts:
  - id: asaoka0914_gmail
    email: asaoka0914@gmail.com   # ← 主鍵，不依賴 Profile 目錄名稱
    token_file: tokens/asaoka0914_gmail.json
    enabled: true
    note: "個人主帳號"
  - id: gwa20080808_gmail
    email: gwa20080808@gmail.com
    token_file: tokens/gwa20080808_gmail.json
    enabled: true
    note: "個人備用帳號"
```

不再有 `chrome_profile` 欄位，由 `list_chrome_profiles_with_email()` 動態查找。

---

## 五、架構設計（修訂版）

```
G:\我的雲端硬碟\Project\Notebooklm\   （或任何電腦上的 git clone 路徑）
├── auth_pool\
│   ├── pool_config.yaml              ← ✅ git push（帳號清單，無 Token）
│   ├── tokens\                       ← 🔒 .gitignore（本機暫存，每次重新取得）
│   │   └── asaoka0914_gmail.json
│   └── pool_status.json             ← 🔒 .gitignore（本機狀態，跨電腦重置）
│
└── scripts\
    ├── _auth_utils.py               ← 已有（加入橋接函式）
    └── _auth_pool.py                ← 新增：帳號池管理核心
```

---

## 六、Token 輪換流程

```
執行 book-reader 腳本
  ↓
ensure_auth_pool()
  ├─ 讀 pool_config.yaml，取帳號清單
  ├─ 讀 pool_status.json，取 current_account（若不存在則用第一個帳號）
  ├─ list_chrome_profiles_with_email() → 動態找到對應 Chrome Profile 目錄
  ├─ headless 啟動 Chrome → 取新 Token → 存到 tokens/xxx.json（本機暫存）
  ├─ 注入 Token → 執行成功 → 完成
  └─ 失敗（RESOURCE_EXHAUSTED / headless 取 Token 失敗）
       └─ rotate_account()
            ├─ 標記當前帳號冷卻 30 分鐘
            └─ 切換下一個個人帳號 → 重試（最多輪換一圈）
```

---

## 七、跨電腦使用流程（無需 GDrive）

```
任何電腦（有網路 + Chrome + git 即可）
  ├─ 1. git pull  →  取得最新程式碼 + pool_config.yaml
  ├─ 2. 確認 Chrome 已登入個人帳號（一次性人工確認）
  └─ 3. 執行 book-reader → ensure_auth_pool() 自動：
         ● 動態比對 email → Chrome Profile 目錄
         ● headless 取新 Token
         ● 注入並執行
         → 全程無需人工介入
```

---

## 八、.gitignore 更新

```gitignore
# Auth Pool Token（一次性 Session Token，本機暫存，不推送）
auth_pool/tokens/
auth_pool/pool_status.json
```

`auth_pool/pool_config.yaml` 推送 GitHub（只含 email 設定，無 Token）。

---

## 九、pool_status.json 格式

```json
{
  "current_account": "asaoka0914_gmail",
  "last_rotated": "2026-08-20T10:30:00",
  "accounts": {
    "asaoka0914_gmail": {
      "total_requests": 142,
      "last_used": "2026-08-20T10:29:55",
      "cooldown_until": null,
      "status": "active"
    }
  }
}
```

此檔案在新電腦首次執行時若不存在，自動從 pool_config.yaml 第一個帳號初始化。

---

## 十、_auth_pool.py 核心介面（給實作 Agent 參考）

```python
# scripts/_auth_pool.py
from pathlib import Path

POOL_DIR = Path(__file__).parent.parent / "auth_pool"
POOL_CONFIG = POOL_DIR / "pool_config.yaml"
POOL_STATUS = POOL_DIR / "pool_status.json"

def load_pool_config() -> dict
    # 讀取 pool_config.yaml，回傳帳號清單與策略設定

def get_or_init_status() -> dict
    # 讀取 pool_status.json；若不存在則以 pool_config.yaml 第一個帳號初始化

def find_chrome_profile_by_email(email: str) -> str | None
    # 呼叫 _auth_utils.list_chrome_profiles_with_email()
    # 依 email 比對，回傳對應的 Chrome Profile 目錄名稱（如 "Default"）
    # 若找不到回傳 None（表示此電腦未登入該帳號）

def fetch_token_headless(account: dict) -> bool
    # 以 find_chrome_profile_by_email() 找 Profile 目錄
    # 呼叫 _auth_utils._launch_chrome_and_authenticate() 取新 Token
    # 成功後存到 account['token_file']（本機暫存）

def rotate_account(pool_status: dict, config: dict) -> dict | None
    # 標記當前帳號冷卻（cooldown_until = now + cooldown_minutes）
    # 依策略選下一個未冷卻且在本機 Chrome 找得到的帳號
    # 回傳新帳號 dict，或 None（所有帳號均冷卻中）

def ensure_auth_pool() -> bool
    # 主入口：
    # 1. get_or_init_status() → 取當前帳號
    # 2. fetch_token_headless() → 取 Token
    # 3. 成功 → True
    # 4. 失敗 → rotate_account() → 重試（最多輪換一圈）
    # 5. 全部失敗 → fallback 到 _auth_utils.ensure_auth()

def pool_status_report() -> None
    # 印出帳號池狀態表格（給 CLI 用）
```

---

## 十一、_auth_utils.py 需新增橋接函式（給實作 Agent 參考）

在現有 `_auth_utils.py` 末尾新增：

```python
def ensure_auth_with_pool() -> bool:
    """
    優先嘗試使用帳號池（_auth_pool.ensure_auth_pool()），
    若 auth_pool/pool_config.yaml 不存在，fallback 到原本的 ensure_auth()。
    """
    pool_config = Path(__file__).parent.parent / "auth_pool" / "pool_config.yaml"
    if pool_config.exists():
        try:
            from _auth_pool import ensure_auth_pool
            return ensure_auth_pool()
        except Exception as e:
            print(f"⚠️ auth_pool 啟動失敗 ({e})，切回單帳號模式...")
    return ensure_auth()
```

---

## 十二、現有腳本修改清單（給實作 Agent 參考）

下列腳本將 `ensure_auth()` 改為 `ensure_auth_with_pool()`：

| 檔案 | 修改位置 |
|------|----------|
| `scripts/01_init_notebook.py` | import + 呼叫處 |
| `scripts/02_batch_generate.py` | import + 呼叫處 |
| `scripts/03_assemble_report.py` | import + 呼叫處（若有） |
| `scripts/04_qc_check.py` | import + 呼叫處（若有） |
| `scripts/06_generate_book_summary.py` | import + 呼叫處（若有） |

---

## 十三、開發優先順序

| 優先度 | 項目 | 說明 |
|--------|------|------|
| P0 | 建立 auth_pool/ 目錄結構 | pool_config.yaml + tokens/ + .gitignore |
| P0 | _auth_pool.py 核心實作 | 依第十節介面清單實作 |
| P0 | _auth_utils.py 新增 ensure_auth_with_pool() | 橋接函式 |
| P1 | 現有 5 個腳本換呼叫 | 01~06 的 ensure_auth → ensure_auth_with_pool |
| P1 | tests/test_auth_pool.py | mock headless，測試輪換與冷卻邏輯 |
| P2 | CLI：pool status / rotate / revoke | 方便手動管理 |

---

## 十四、注意事項（給實作 Agent 的 Guardrails）

1. **不動非目標檔案**：只動 `_auth_pool.py`（新增）、`_auth_utils.py`（加橋接函式）、5 個腳本（換一行 import + 一行呼叫）
2. **向後相容優先**：`ensure_auth()` 原有邏輯完全不改動
3. **auth_pool/tokens/ 必須加 .gitignore**：實作完成前確認
4. **Windows 路徑**：一律用 `Path(__file__)` 相對取路徑，避免硬編碼
5. **Chrome Profile 動態查找**：不依賴設定檔的 Profile 目錄名稱，一律呼叫 `find_chrome_profile_by_email()`
6. **Chrome 未登入的 graceful 處理**：`find_chrome_profile_by_email()` 回傳 None 時，跳過該帳號並嘗試下一個，不 crash
