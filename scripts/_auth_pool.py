import os
import sys
import json
import yaml
import time
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
# 確保 stdout 為 UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout.reconfigure(encoding='utf-8')

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

def rotate_account(pool_status: dict, config: dict, set_cooldown: bool = True) -> dict | None:
    """
    切換至下一個可用帳號並更新 pool_status.json。
    僅在 set_cooldown=True (如配額耗盡) 時才設定 cooldown_until。
    """
    current_id = pool_status.get("current_account")
    cooldown_minutes = config.get("cooldown_minutes", 30)
    cooldown_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()

    status_accounts = pool_status.setdefault("accounts", {})
    if set_cooldown and current_id and current_id in status_accounts:
        status_accounts[current_id]["cooldown_until"] = cooldown_until
        status_accounts[current_id]["status"] = "cooldown"
        print(f"⏸️ 帳號 [{current_id}] 進入冷卻狀態，冷卻至: {cooldown_until}")

    next_acc = select_next_account(pool_status, config, exclude_current=True)
    if next_acc:
        pool_status["current_account"] = next_acc["id"]
        pool_status["last_rotated"] = datetime.now().isoformat()
        if status_accounts.get(next_acc["id"], {}).get("status") != "cooldown":
            status_accounts[next_acc["id"]]["status"] = "active"
        save_pool_status(pool_status)
        print(f"🔀 已輪換切換至帳號: [{next_acc['id']}] ({next_acc.get('email')})")
        return next_acc
    else:
        save_pool_status(pool_status)
        print("⚠️ 帳號池中所有帳號均在冷卻中或無可用帳號。")
        return None

def is_current_token_valid(expected_email: str = None) -> bool:
    """
    檢查當前本地快取的 Token 是否依然有效，
    若指定 expected_email 則一併比對快取中的帳號 Email 是否相符。
    """
    try:
        from notebooklm_tools.core.auth import check_auth
        from notebooklm_tools.services.auth import AuthManager

        result = check_auth(profile='default', live=True)
        if not getattr(result, 'valid', False):
            return False

        if expected_email:
            auth = AuthManager('default')
            profile = auth.load_profile()
            cached_email = getattr(profile, "email", "") or ""
            if cached_email.strip().lower() != expected_email.strip().lower():
                print(f"ℹ️ 當前快取 Token 身分 ({cached_email}) 與目標帳號 ({expected_email}) 不符，需重新提取。")
                return False

        return True
    except Exception:
        return False

def fetch_token_headless(account: dict, timeout_sec: int = 60) -> bool:
    """
    優先使用獨立資料夾隔離法 (~/.notebooklm/chrome_profiles/<account_id>)，
    若不存在則動態比對本機 Chrome Profile 目錄，啟動 headless Chrome 並透過 CDP 快取新 Token。
    """
    from _auth_utils import _launch_chrome_and_authenticate
    email = account.get("email")
    acc_id = account.get("id")
    if not email:
        print(f"❌ 帳號設定缺少 email: {account}")
        return False

    # 1. 優先檢查是否具有獨立隔離 Profile 目錄
    isolated_profile_dir = Path.home() / ".notebooklm" / "chrome_profiles" / acc_id
    if isolated_profile_dir.exists():
        print(f"🔑 正在為帳號 [{acc_id}] 使用獨立隔離目錄 ({isolated_profile_dir}) 取得認證 Token...")
        return _launch_chrome_and_authenticate(profile_dir=None, timeout_sec=timeout_sec, custom_user_data_dir=str(isolated_profile_dir))

    # 2. 次選本機 Chrome Profile 目錄比對
    profile_dir = find_chrome_profile_by_email(email)
    if not profile_dir:
        print(f"⚠️ 本機 Chrome 尚未登入帳號 [{email}] 或無法比對 Profile，跳過此帳號。")
        return False

    print(f"🔑 正在為帳號 [{acc_id}] ({email} -> Profile: {profile_dir}) 取得認證 Token...")
    success = _launch_chrome_and_authenticate(profile_dir=profile_dir, timeout_sec=timeout_sec)
    return success

def get_shortest_cooldown_wait_seconds(pool_status: dict, config: dict) -> int | None:
    """
    計算帳號池中『最快解鎖』的帳號還需等待的秒數。
    若無帳號在冷卻或無設定則回傳 None。
    """
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    if not accounts:
        return None
    
    status_accounts = pool_status.get("accounts", {})
    min_wait_seconds = None

    for acc in accounts:
        acc_stat = status_accounts.get(acc["id"], {})
        cooldown_until_str = acc_stat.get("cooldown_until")
        if cooldown_until_str:
            try:
                cooldown_until = datetime.fromisoformat(cooldown_until_str)
                diff = (cooldown_until - datetime.now()).total_seconds()
                if diff > 0:
                    if min_wait_seconds is None or diff < min_wait_seconds:
                        min_wait_seconds = diff
                else:
                    # 已經過期，代表有帳號可以立即解鎖
                    return 0
            except Exception:
                pass
    return int(min_wait_seconds) if min_wait_seconds is not None else None

def wait_for_cooldown_recovery(pool_status: dict, config: dict, max_wait_seconds: int = 2400) -> bool:
    """
    當所有帳號都在冷卻期時，自動倒數等待最快解鎖的帳號，直到解鎖後自動 Resume。
    """
    import time
    wait_sec = get_shortest_cooldown_wait_seconds(pool_status, config)
    if wait_sec is None:
        return False
    
    if wait_sec <= 0:
        print("⏰ 偵測到已有帳號冷卻時間屆滿，自動解除鎖定並重試...")
        return True

    if wait_sec > max_wait_seconds:
        print(f"⚠️ 最短冷卻等待時間過長 ({wait_sec // 60} 分鐘 > 最大等待 {max_wait_seconds // 60} 分鐘)，放棄自動等待。")
        return False

    print("\n" + "=" * 70)
    print(f"⏳ [Auto-Cooldown Wait] 帳號池所有帳號均在冷卻中。")
    print(f"🔄 系統啟動自動等待機制，將在 {wait_sec + 5} 秒後（約 {(wait_sec + 5) // 60 + 1} 分鐘）自動喚醒並重試...")
    print("=" * 70 + "\n")

    # 每 10 秒印一次進度，防止終端被當作死當
    total_wait = wait_sec + 5
    elapsed = 0
    while elapsed < total_wait:
        sleep_step = min(10, total_wait - elapsed)
        time.sleep(sleep_step)
        elapsed += sleep_step
        remaining = total_wait - elapsed
        if remaining > 0 and elapsed % 30 == 0:
            print(f"⏳ 正在等待冷卻恢復... 剩餘約 {remaining} 秒")

    print("🎉 冷卻時間已過！正在自動喚醒並切換帳號重試...")
    return True

def ensure_auth_pool() -> bool:
    """
    帳號池主入口：
    1. 載入設定與狀態檔。
    2. 若當前已有有效 Token，直接使用（避免已開 Chrome 造成 CDP 衝突）。
    3. 若無有效 Token 或帳號在冷卻中，依序嘗試 headless 取 Token（最多輪換一圈）。
    4. 若所有帳號皆冷卻，自動進入等待倒數（Auto-Cooldown Wait），時間到自動重試！
    5. 若所有帳號皆失敗，自動 Fallback 回退至單帳號互動式 ensure_auth()。
    """
    config = load_pool_config()
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    if not accounts:
        print("⚠️ pool_config.yaml 中未設定任何可用帳號，切回單帳號模式...")
        from _auth_utils import ensure_auth
        return ensure_auth()

    pool_status = get_or_init_status()
    current_id = pool_status.get("current_account")
    current_acc = next((acc for acc in accounts if acc["id"] == current_id), None)
    if not current_acc and accounts:
        current_acc = accounts[0]
        pool_status["current_account"] = current_acc["id"]
        save_pool_status(pool_status)

    # 1. 優先檢查現有快取 Token：若當前帳號未冷卻且 Token 有效且 Email 符合，直接使用無需重啟 Chrome
    if current_acc:
        acc_stat = pool_status.setdefault("accounts", {}).setdefault(current_acc["id"], {})
        if not is_account_in_cooldown(acc_stat):
            if is_current_token_valid(expected_email=current_acc.get("email")):
                print(f"✅ 當前帳號 [{current_acc['id']}] ({current_acc.get('email')}) Token 依然有效，直接使用（無需啟動 Chrome）。")
                return True

    total_accounts = len(accounts)

    # 2. 當前 Token 無效或需切換時，嘗試透過 Chrome CDP 取得新 Token
    for attempt in range(total_accounts):
        current_id = pool_status.get("current_account")
        current_acc = next((acc for acc in accounts if acc["id"] == current_id), None)

        if not current_acc:
            current_acc = select_next_account(pool_status, config, exclude_current=False)
            if not current_acc:
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
            current_acc = rotate_account(pool_status, config, set_cooldown=False)
            if not current_acc:
                break

    # 2.5 檢查是否所有帳號都在冷卻期中，若是則啟動自動等待機制（Auto-Cooldown Wait）
    if wait_for_cooldown_recovery(pool_status, config):
        # 重新遞迴呼叫自身一次（此時已有帳號過期解鎖）
        return ensure_auth_pool()

    # 3. 全部失敗 → fallback 到 _auth_utils.ensure_auth()
    print("⚠️ 帳號池所有帳號均認證失敗或冷卻中，啟動優雅降級 (Fallback 至單帳號互動選單)...")
    from _auth_utils import ensure_auth
    return ensure_auth()

def sync_notebook_collaborators(notebook_id: str) -> bool:
    """
    自動將 pool_config.yaml 中所有已啟用的帳號（email）共用為該筆記本的 Editor。
    確保在主帳號配額用盡輪換至備用帳號時，備用帳號可以直接存取該筆記本。
    """
    if not notebook_id:
        return False
    try:
        config = load_pool_config()
        accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
        if not accounts:
            return False

        from notebooklm_tools.services.auth import AuthManager
        from notebooklm_tools.core.client import NotebookLMClient

        auth = AuthManager()
        profile = auth.load_profile()
        client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)

        # 取得現有協作者名單
        share_status = client.get_share_status(notebook_id)
        existing_emails = set()
        if share_status and hasattr(share_status, "collaborators"):
            for c in share_status.collaborators:
                if getattr(c, "email", None):
                    existing_emails.add(c.email.strip().lower())

        synced_any = False
        for acc in accounts:
            email = acc.get("email", "").strip().lower()
            if not email:
                continue
            if email not in existing_emails:
                print(f"🤝 [Auto-Share] 正在自動將筆記本共用給帳號池成員: {email} (editor)...")
                try:
                    success = client.add_collaborator(notebook_id, email, role="editor", notify=False)
                    if success:
                        print(f"  ✅ 成功將筆記本共用給: {email}")
                        existing_emails.add(email)
                        synced_any = True
                    else:
                        print(f"  ⚠️ 共用至 {email} 回傳非 True")
                except Exception as share_err:
                    print(f"  ⚠️ 共用至 {email} 失敗: {share_err}")
            else:
                pass

        return True
    except Exception as e:
        print(f"⚠️ [Auto-Share] 自動同步筆記本協作者失敗 ({e})，略過此步驟。")
        return False

def switch_account_by_id(account_id: str) -> bool:
    """
    指定帳號 ID 進行強制切換並提取該帳號之 Token。
    """
    config = load_pool_config()
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    target_acc = next((acc for acc in accounts if acc["id"] == account_id), None)
    if not target_acc:
        print(f"❌ 帳號池中找不到 ID 為 [{account_id}] 的帳號。")
        return False

    pool_status = get_or_init_status()
    pool_status["current_account"] = target_acc["id"]
    save_pool_status(pool_status)

    print(f"🔄 正在為指定帳號 [{target_acc['id']}] ({target_acc.get('email')}) 提取認證 Token...")
    if fetch_token_headless(target_acc):
        status_accounts = pool_status.setdefault("accounts", {})
        status_accounts[target_acc["id"]]["last_used"] = datetime.now().isoformat()
        status_accounts[target_acc["id"]]["status"] = "active"
        save_pool_status(pool_status)
        print(f"✅ 成功切換至帳號 [{target_acc['id']}]！")
        return True
    else:
        print(f"❌ 切換至帳號 [{target_acc['id']}] 失敗。")
        return False

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

def login_isolated_account(account_id: str) -> bool:
    """
    為指定帳號啟動獨立隔離目錄的 Chrome 視窗供使用者登入一次。
    """
    config = load_pool_config()
    accounts = [acc for acc in config.get("accounts", []) if acc.get("enabled", True)]
    target_acc = next((acc for acc in accounts if acc["id"] == account_id), None)
    if not target_acc:
        print(f"❌ 帳號池中找不到 ID 為 [{account_id}] 的帳號。")
        return False

    isolated_profile_dir = Path.home() / ".notebooklm" / "chrome_profiles" / account_id
    isolated_profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"🚀 正在為帳號 [{account_id}] ({target_acc.get('email')}) 開啟獨立登入視窗...")
    print(f"   目錄：{isolated_profile_dir}")
    print("   請在彈出的 Chrome 瀏覽器中登入該 Google 帳號並進入 NotebookLM 首頁，登入完成後關閉視窗即可。")

    from _auth_utils import _find_chrome_path
    chrome_path = shutil.which('chrome') or _find_chrome_path()
    if not chrome_path:
        print("❌ 無法找到 Chrome。")
        return False

    cmd = [
        chrome_path,
        '--no-first-run',
        '--no-default-browser-check',
        f'--user-data-dir={isolated_profile_dir}',
        'https://notebooklm.google.com'
    ]
    proc = subprocess.Popen(cmd)
    proc.wait()
    print(f"✅ 帳號 [{account_id}] 獨立 Profile 設定完畢！未來可 100% 背景無痕提取 Token。")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NotebookLM Auth Pool Manager")
    parser.add_argument("--status", action="store_true", help="Show pool status report")
    parser.add_argument("--login", type=str, help="Login an account into its isolated profile directory (e.g. --login gwa20080808_gmail)")
    parser.add_argument("--switch", type=str, help="Switch active account by ID")
    args = parser.parse_args()

    if args.login:
        login_isolated_account(args.login)
    elif args.switch:
        switch_account_by_id(args.switch)
    else:
        pool_status_report()
