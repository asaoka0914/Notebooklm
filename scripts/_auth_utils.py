import os
import sys
import time
import subprocess
import shutil

def _find_chrome_path():
    """在 Windows 上尋找 Chrome 可執行檔。"""
    import glob
    candidates = glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    candidates += glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
    return candidates[0] if candidates else None

def _get_chrome_user_data_root():
    """取得 Chrome User Data 根目錄路徑（Default / Profile 1 / Profile 2 ... 的共同上層）。"""
    return os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data')

def list_chrome_profiles_with_email():
    """
    讀取 Chrome 的 Local State 設定檔，取得每個 Profile 資料夾對應的登入 Email。
    回傳格式：[{'dir': 'Default', 'email': 'xxx@gmail.com', 'name': '顯示名稱'}, ...]
    """
    import json
    root = _get_chrome_user_data_root()
    local_state_path = os.path.join(root, 'Local State')
    profiles = []
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        info_cache = data.get('profile', {}).get('info_cache', {})
        for profile_dir, info in info_cache.items():
            email = info.get('user_name') or info.get('gaia_name') or '(未登入或無法讀取)'
            display_name = info.get('name', profile_dir)
            profiles.append({'dir': profile_dir, 'email': email, 'name': display_name})
    except Exception as e:
        print(f"⚠️  無法讀取 Chrome Profile 清單 ({e})，將使用預設 Default。")
    return profiles

def _select_chrome_profile_interactive(target_email: str = None):
    """
    列出所有偵測到的 Chrome 帳號身分（Profile 資料夾 + 登入 Email），
    互動式讓使用者輸入編號選擇要用哪個身分認證。
    支援 target_email 自動比對、環境變數 NOTEBOOKLM_CHROME_PROFILE 直接指定。
    """
    env_override = os.environ.get('NOTEBOOKLM_CHROME_PROFILE')
    if env_override:
        print(f"ℹ️  偵測到環境變數 NOTEBOOKLM_CHROME_PROFILE，直接使用指定身分：{env_override}")
        return env_override

    profiles = list_chrome_profiles_with_email()
    if not profiles:
        return 'Default'

    if target_email:
        target_email_clean = target_email.strip().lower()
        for p in profiles:
            if p.get('email', '').strip().lower() == target_email_clean:
                return p['dir']

    if len(profiles) == 1:
        return profiles[0]['dir']

    print("\n" + "="*70)
    print("🔀 偵測到多個 Chrome 帳號身分，請選擇要用哪一個登入 NotebookLM：")
    for i, p in enumerate(profiles, 1):
        print(f"  [{i}] {p['email']}   (Profile 資料夾: {p['dir']} / {p['name']})")
    print("="*70)

    if not sys.stdin.isatty():
        fallback_profile = profiles[0]['dir']
        print(f"⚠️ 偵測到非互動式終端環境 (non-interactive)，自動採用預設身分：{fallback_profile}")
        return fallback_profile

    while True:
        try:
            choice = input(f"請輸入編號 (1-{len(profiles)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            fallback_profile = profiles[0]['dir']
            print(f"\n⚠️ 無法取得使用者輸入 (EOF)，自動採用預設身分：{fallback_profile}")
            return fallback_profile
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            selected = profiles[int(choice) - 1]
            print(f"✅ 已選擇身分：{selected['email']} ({selected['dir']})")
            return selected['dir']
        print("輸入無效，請重新輸入。")

def _launch_chrome_and_authenticate(profile_dir, timeout_sec=60):
    """
    強制啟動指定 Chrome Profile 身分的偵錯模式，透過 CDP 取得並快取新的認證 Token。
    共用於 ensure_auth() 自動恢復與 switch_google_account_interactive() 主動切換帳號兩處。
    """
    try:
        from notebooklm_tools.services.auth import AuthManager
        from notebooklm_tools.utils.cdp import extract_cookies_via_existing_cdp
    except ImportError:
        print("Notice: notebooklm_tools inner auth modules not available.")
        return False

    chrome_path = shutil.which('chrome') or _find_chrome_path()
    if not chrome_path:
        print("❌ 無法找到 Chrome。")
        return False

    print(f"🚀 啟動 Chrome 偵錯模式 (Port 9223)，使用身分: {profile_dir} ...")
    user_data_root = _get_chrome_user_data_root()
    import urllib.request
    
    # 優先檢查 Port 9223 是否已經有開好的 Chrome 偵錯埠
    cdp_ready = False
    try:
        urllib.request.urlopen('http://127.0.0.1:9223/json', timeout=1)
        cdp_ready = True
        chrome_proc = None
        print("ℹ️ 偵測到現有 Chrome 偵錯連線已就緒 (Port 9223)，直接進行 Token 提取...")
    except Exception:
        print(f"🚀 啟動 Chrome 偵錯模式 (Port 9223)，使用身分: {profile_dir} ...")
        chrome_proc = subprocess.Popen([
            chrome_path,
            '--remote-debugging-port=9223',
            '--no-first-run',
            '--no-default-browser-check',
            f'--user-data-dir={user_data_root}',
            f'--profile-directory={profile_dir}',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        for i in range(15):
            time.sleep(1)
            try:
                urllib.request.urlopen('http://127.0.0.1:9223/json', timeout=2)
                cdp_ready = True
                break
            except Exception:
                pass

    if not cdp_ready:
        if chrome_proc:
            chrome_proc.terminate()
        print("❌ Chrome CDP 無法就緒（若目前已有一般 Chrome 視窗開著，請先關閉所有 Chrome 視窗後再重試）")
        return False

    auth_data = None
    try:
        auth_data = extract_cookies_via_existing_cdp(
            cdp_url="http://127.0.0.1:9223",
            wait_for_login=True,
            login_timeout=timeout_sec
        )
    except Exception as e:
        print(f"CDP auth extraction failed: {e}")

    chrome_proc.terminate()

    if auth_data and auth_data.get("cookies"):
        try:
            auth_manager = AuthManager("default")
            auth_manager.save_profile(
                cookies=auth_data["cookies"],
                csrf_token=auth_data.get("csrf_token"),
                session_id=auth_data.get("session_id"),
                email=auth_data.get("email"),
                build_label=auth_data.get("build_label"),
                base_host=auth_data.get("base_host"),
                force=True,
            )
            extracted_email = auth_data.get("email") or profile_dir
            print(f"✅ 已成功切換並快取新身分的認證 Token（Profile: {profile_dir}, Email: {extracted_email}）")
            return True
        except Exception as e:
            print(f"❌ 儲存 Profile 失敗: {e}")
    return False

def switch_google_account_interactive(timeout_sec=60):
    """
    主動彈出 Chrome 帳號身分選單，讓使用者選擇要切換到哪一個 Google 帳號，
    選定後立即啟動對應 Chrome 身分完成重新認證。
    適用於配額用盡 (RESOURCE_EXHAUSTED) 需要改用另一個帳號的情境。
    """
    profiles = list_chrome_profiles_with_email()
    if not profiles:
        print("⚠️ 找不到任何 Chrome 帳號身分，請確認 Chrome 已安裝且曾登入過帳號。")
        return False

    print("\n" + "="*70)
    print("🔀 請選擇要切換使用的 Google 帳號（建議選與目前不同的身分）：")
    for i, p in enumerate(profiles, 1):
        print(f"  [{i}] {p['email']}   (Profile 資料夾: {p['dir']} / {p['name']})")
    print("="*70)

    if not sys.stdin.isatty():
        print("⚠️ 偵測到非互動式終端環境，無法進行互動式帳號切換。")
        return False

    while True:
        try:
            choice = input(f"請輸入編號 (1-{len(profiles)})，或輸入 q 取消: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n⚠️ 無法取得使用者輸入 (EOF)，已取消切換。")
            return False
        if choice.lower() == 'q':
            print("已取消切換。")
            return False
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            selected = profiles[int(choice) - 1]
            print(f"✅ 已選擇：{selected['email']} ({selected['dir']})")
            return _launch_chrome_and_authenticate(selected['dir'], timeout_sec=timeout_sec)
        print("輸入無效，請重新輸入。")

def ensure_auth():
    """檢查認證有效性，過期時自動啟動 Chrome headless 重認證。"""
    try:
        from notebooklm_tools.core.auth import check_auth
    except ImportError:
        print("Notice: notebooklm_tools inner auth modules not available for auto-recovery check.")
        return True

    result = check_auth(profile='default', live=True)
    if getattr(result, 'valid', False):
        return True

    print("⚠️  認證過期或 Token 需要旋轉刷新，嘗試自動恢復...")

    # 選擇要使用哪一個 Chrome 帳號身分，並啟動 Chrome 重新認證
    profile_dir = _select_chrome_profile_interactive()
    if _launch_chrome_and_authenticate(profile_dir, timeout_sec=60):
        return True

    print("❌ 自動認證恢復失敗，請手動執行: python -c \"from notebooklm_tools.cli.main import app; app(['login', '--clear', '--force'])\"")
    return False

def is_auth_error(e):
    """判斷例外是否為認證失效相關。"""
    err_str = str(e).lower()
    auth_keywords = [
        "clientauthenticationerror", "unauthenticated", "401", 
        "invalid_grant", "token expired", "auth failed", "snlm0e", "csrf"
    ]
    return any(kw in err_str for kw in auth_keywords)

def get_profile_metadata():
    """取得當前 Token Profile 的 session_id 與檔案 mtime，作為帳號切換與 Token 變更的具體監控指標。"""
    try:
        from notebooklm_tools.services.auth import AuthManager
        auth = AuthManager('default')
        profile = auth.load_profile()
        session_id = getattr(profile, "session_id", "")
        
        # 取得 metadata 快取檔路徑與 mtime
        metadata_file = auth.metadata_file
        mtime = os.path.getmtime(metadata_file) if metadata_file.exists() else 0
        return session_id, mtime
    except Exception:
        return "", 0

def ensure_auth_with_pool() -> bool:
    """
    優先嘗試使用帳號池 (_auth_pool.ensure_auth_pool())，
    若 auth_pool/pool_config.yaml 不存在或執行失敗，自動 fallback 至原本的 ensure_auth()。
    """
    from pathlib import Path
    pool_config = Path(__file__).resolve().parent.parent / "auth_pool" / "pool_config.yaml"
    if pool_config.exists():
        try:
            from _auth_pool import ensure_auth_pool
            return ensure_auth_pool()
        except Exception as e:
            print(f"⚠️ auth_pool 啟動失敗 ({e})，切回單帳號模式...")
    return ensure_auth()
