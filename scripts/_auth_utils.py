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

def ensure_auth():
    """檢查認證有效性，過期時自動啟動 Chrome headless 重認證。"""
    try:
        from notebooklm_tools.core.auth import check_auth, save_tokens_to_cache
        from notebooklm_tools.utils.auth_browser import run_headless_auth
    except ImportError:
        print("Notice: notebooklm_tools inner auth modules not available for auto-recovery check.")
        return True

    result = check_auth(profile='default', live=True)
    if getattr(result, 'valid', False):
        return True

    print("⚠️  認證過期或 Token 需要旋轉刷新，嘗試自動恢復...")

    # 1. 先嘗試 headless auth（需要 Chrome 已以 --remote-debugging-port 啟動）
    try:
        tokens = run_headless_auth(profile_name='default', timeout=30)
        if tokens:
            print("✅ 認證已自動恢復（透過現有 Chrome CDP）")
            return True
    except Exception:
        pass

    # 2. 啟動 Chrome 偵錯模式
    chrome_path = shutil.which('chrome') or _find_chrome_path()
    if not chrome_path:
        print("❌ 無法找到 Chrome，請手動執行: python -c \"from notebooklm_tools.cli.main import app; app(['login', '--clear', '--force'])\"")
        return False

    print("🚀 啟動 Chrome 偵錯模式 (Port 9223)...")
    user_data_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data\Default')
    chrome_proc = subprocess.Popen([
        chrome_path,
        '--remote-debugging-port=9223',
        '--no-first-run',
        '--no-default-browser-check',
        f'--user-data-dir={user_data_dir}',
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 等待 CDP 就緒
    cdp_ready = False
    for i in range(15):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen('http://127.0.0.1:9223/json', timeout=2)
            cdp_ready = True
            break
        except Exception:
            pass

    if not cdp_ready:
        chrome_proc.terminate()
        print("❌ Chrome CDP 無法就緒")
        return False

    # 3. 再次嘗試 headless auth
    tokens = None
    try:
        tokens = run_headless_auth(port=9223, profile_name='default', timeout=60)
    except Exception as e:
        print(f"Headless auth execution failed: {e}")

    chrome_proc.terminate()

    if tokens:
        try:
            save_tokens_to_cache(tokens)
            print("✅ 認證已自動恢復（透過自動啟動 Chrome）")
            return True
        except Exception:
            pass

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
        auth = AuthManager()
        profile = auth.load_profile()
        session_id = getattr(profile, "session_id", "")
        
        # 取得 profile 快取檔路徑與 mtime
        profile_path = os.path.expanduser("~/.notebooklm_tools/profiles/default.json")
        if not os.path.exists(profile_path):
            profile_path = os.path.expanduser("~/.notebooklm_tools/auth.yaml")
        
        mtime = os.path.getmtime(profile_path) if os.path.exists(profile_path) else 0
        return session_id, mtime
    except Exception:
        return "", 0
