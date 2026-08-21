import os
import sys
import json
import yaml
import time
from datetime import datetime, timedelta
from pathlib import Path

# 定義目錄與檔案路徑
POOL_DIR = Path(__file__).resolve().parent.parent / "auth_pool"
POOL_CONFIG = POOL_DIR / "pool_config.yaml"
POOL_STATUS = POOL_DIR / "pool_status.json"

def load_pool_config() -> dict:
    """讀取 pool_config.yaml，回傳帳號清單與策略設定。"""
    if not POOL_CONFIG.exists():
        return {}
    try:
        with open(POOL_CONFIG, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data or {}
    except Exception as e:
        print(f"⚠️ 無法讀取 pool_config.yaml: {e}")
        return {}

def save_pool_status(status_data: dict) -> bool:
    """將狀態存入 pool_status.json。"""
    try:
        POOL_DIR.mkdir(parents=True, exist_ok=True)
        with open(POOL_STATUS, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"⚠️ 無法儲存 pool_status.json: {e}")
        return False

def get_or_init_status() -> dict:
    """讀取 pool_status.json；若不存在則以 pool_config.yaml 第一個可用帳號初始化。"""
    config = load_pool_config()
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    
    if POOL_STATUS.exists():
        try:
            with open(POOL_STATUS, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data and isinstance(data, dict):
                    # 同步補齊新加入 config 的帳號
                    status_accounts = data.setdefault("accounts", {})
                    for acc in accounts:
                        acc_id = acc["id"]
                        if acc_id not in status_accounts:
                            status_accounts[acc_id] = {
                                "total_requests": 0,
                                "last_used": None,
                                "cooldown_until": None,
                                "status": "active"
                            }
                    return data
        except Exception as e:
            print(f"⚠️ 讀取 pool_status.json 失敗 ({e})，重新初始化...")

    first_account_id = accounts[0]["id"] if accounts else None
    status_data = {
        "current_account": first_account_id,
        "last_rotated": datetime.now().isoformat(),
        "accounts": {}
    }
    for acc in accounts:
        status_data["accounts"][acc["id"]] = {
            "total_requests": 0,
            "last_used": None,
            "cooldown_until": None,
            "status": "active"
        }
    save_pool_status(status_data)
    return status_data

def find_chrome_profile_by_email(email: str) -> str | None:
    """
    呼叫 _auth_utils.list_chrome_profiles_with_email()，
    依 email 比對本機 Chrome Profile，回傳 Profile 目錄名稱（如 'Default'、'Profile 1'）。
    若找不到或未登入則回傳 None。
    """
    try:
        from _auth_utils import list_chrome_profiles_with_email
        profiles = list_chrome_profiles_with_email()
        target_email = email.strip().lower()
        for p in profiles:
            p_email = p.get('email', '').strip().lower()
            if p_email == target_email:
                return p.get('dir')
    except Exception as e:
        print(f"⚠️ 比對 Chrome Profile 失敗 ({e})")
    return None

def is_account_in_cooldown(acc_status: dict) -> bool:
    """檢查指定帳號是否在冷卻期內。"""
    cooldown_until_str = acc_status.get("cooldown_until")
    if not cooldown_until_str:
        return False
    try:
        cooldown_until = datetime.fromisoformat(cooldown_until_str)
        if datetime.now() < cooldown_until:
            return True
    except Exception:
        pass
    return False

def select_next_account(pool_status: dict, config: dict, exclude_current: bool = True) -> dict | None:
    """
    依策略選取下一個可用（未在冷卻期且本機 Chrome 找得到 Profile）的帳號。
    """
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    if not accounts:
        return None

    current_id = pool_status.get("current_account")
    status_accounts = pool_status.setdefault("accounts", {})
    strategy = config.get("strategy", "round_robin")

    # 候選過濾：必須未在冷卻中
    available_accounts = []
    for acc in accounts:
        acc_id = acc["id"]
        acc_stat = status_accounts.setdefault(acc_id, {
            "total_requests": 0,
            "last_used": None,
            "cooldown_until": None,
            "status": "active"
        })
        if not is_account_in_cooldown(acc_stat):
            available_accounts.append(acc)

    if not available_accounts:
        return None

    if strategy == "round_robin":
        acc_ids = [acc["id"] for acc in accounts]
        if current_id in acc_ids:
            cur_idx = acc_ids.index(current_id)
            # 從當前位置的下一個開始依序找第一個可用的
            n = len(accounts)
            start_offset = 1 if exclude_current else 0
            for i in range(start_offset, n):
                candidate = accounts[(cur_idx + i) % n]
                if candidate in available_accounts:
                    return candidate
            if not exclude_current and accounts[cur_idx] in available_accounts:
                return accounts[cur_idx]
        return available_accounts[0]

    elif strategy == "least_used":
        # 依 total_requests 排序
        available_accounts.sort(
            key=lambda x: status_accounts.get(x["id"], {}).get("total_requests", 0)
        )
        return available_accounts[0]

    return available_accounts[0]

def rotate_account(pool_status: dict, config: dict) -> dict | None:
    """
    標記當前帳號冷卻（預設 cooldown_minutes 分鐘），切換至下一個可用帳號並更新 pool_status.json。
    """
    current_id = pool_status.get("current_account")
    cooldown_minutes = config.get("cooldown_minutes", 30)
    cooldown_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()

    status_accounts = pool_status.setdefault("accounts", {})
    if current_id and current_id in status_accounts:
        status_accounts[current_id]["cooldown_until"] = cooldown_until
        status_accounts[current_id]["status"] = "cooldown"
        print(f"⏸️ 帳號 [{current_id}] 進入冷卻狀態，冷卻至: {cooldown_until}")

    next_acc = select_next_account(pool_status, config, exclude_current=True)
    if next_acc:
        pool_status["current_account"] = next_acc["id"]
        pool_status["last_rotated"] = datetime.now().isoformat()
        status_accounts[next_acc["id"]]["status"] = "active"
        save_pool_status(pool_status)
        print(f"🔀 已輪換切換至帳號: [{next_acc['id']}] ({next_acc.get('email')})")
        return next_acc
    else:
        save_pool_status(pool_status)
        print("⚠️ 帳號池中所有帳號均在冷卻中或無可用帳號。")
        return None

def fetch_token_headless(account: dict, timeout_sec: int = 60) -> bool:
    """
    以 email 動態查找 Chrome Profile 目錄，啟動 headless Chrome 並透過 CDP 快取新 Token。
    """
    from _auth_utils import _launch_chrome_and_authenticate
    email = account.get("email")
    if not email:
        print(f"❌ 帳號設定缺少 email: {account}")
        return False

    profile_dir = find_chrome_profile_by_email(email)
    if not profile_dir:
        print(f"⚠️ 本機 Chrome 尚未登入帳號 [{email}] 或無法比對 Profile，跳過此帳號。")
        return False

    print(f"🔑 正在為帳號 [{account['id']}] ({email} -> Profile: {profile_dir}) 取得認證 Token...")
    success = _launch_chrome_and_authenticate(profile_dir, timeout_sec=timeout_sec)
    return success

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

    # 嘗試最多 total_accounts 次
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

def pool_status_report():
    """印出帳號池目前狀態（CLI 輔助檢視）。"""
    config = load_pool_config()
    pool_status = get_or_init_status()
    current_id = pool_status.get("current_account")

    print("\n" + "="*70)
    print("📊 NotebookLM 多 Profile 帳號池狀態")
    print("="*70)
    print(f"策略: {config.get('strategy', 'round_robin')} | 冷卻設定: {config.get('cooldown_minutes', 30)} 分鐘")
    print(f"當前指定帳號: {current_id}\n")

    accounts = config.get("accounts", [])
    status_accounts = pool_status.get("accounts", {})

    print(f"{'ID':<20} {'Email':<28} {'狀態':<10} {'呼叫次數':<10} {'冷卻至'}")
    print("-" * 85)
    for acc in accounts:
        acc_id = acc["id"]
        email = acc.get("email", "")
        stat = status_accounts.get(acc_id, {})
        cooldown = stat.get("cooldown_until") or "無"
        status_label = stat.get("status", "active")
        if is_account_in_cooldown(stat):
            status_label = "⏳冷卻中"
        elif acc_id == current_id:
            status_label = "⭐使用中"

        print(f"{acc_id:<20} {email:<28} {status_label:<10} {stat.get('total_requests', 0):<10} {cooldown}")
    print("="*70 + "\n")

if __name__ == "__main__":
    pool_status_report()
