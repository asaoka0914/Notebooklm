#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notebooklm / book-reader 環境檢測與動態 Obsidian Vault 路徑配置模組 (env_config.py)
自動偵測本機或雲端 Obsidian Vault (BoBo-wiki / Obsidian)，適應跨電腦路徑。
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Optional, List

def get_obsidian_json_path() -> Optional[Path]:
    """取得 Obsidian 設定檔 obsidian.json 的路徑（跨平台支援）"""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "obsidian" / "obsidian.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    else:
        # Linux / Unix
        return Path.home() / ".config" / "obsidian" / "obsidian.json"
    return None

def find_vaults_from_config() -> List[Path]:
    """從 Obsidian 系統設定檔中解析所有已登記的 Vault 路徑"""
    json_path = get_obsidian_json_path()
    if not json_path or not json_path.exists():
        return []
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            vaults = data.get("vaults", {})
            paths = []
            for vault_id, info in vaults.items():
                v_path = info.get("path")
                if v_path:
                    paths.append(Path(v_path))
            return paths
    except Exception as e:
        print(f"[env_config] 讀取 obsidian.json 失敗: {e}", file=sys.stderr)
        return []

def get_vault_path() -> Path:
    """
    動態尋找 Obsidian Vault 路徑。
    搜尋優先權：
    1. 環境變數 `OBSIDIAN_VAULT_PATH`
    2. Obsidian 系統設定檔中包含 'BoBo-wiki' 或 'Obsidian' 的 Vault 路徑
    3. 專案所在的父目錄（若專案本身就在 Vault 中，或是 Vault 的子目錄）
    4. 本機常用候選路徑（跨電腦 Desktop / Documents / Project / GDrive）
    5. 預設雲端路徑保底 `G:\\我的雲端硬碟\\Obsidian\\BoBo-wiki` 或 `G:\\我的雲端硬碟\\Obsidian`
    """
    # 1. 優先：環境變數
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. 次之：從 Obsidian 系統設定檔中搜尋
    config_vaults = find_vaults_from_config()
    for vault in config_vaults:
        if "bobo-wiki" in vault.name.lower() or "obsidian" in vault.name.lower():
            if vault.exists():
                return vault
            
    # 3. 檢查目前工作目錄 (CWD) 是否為 Vault 或是其子目錄
    cwd = Path.cwd()
    if (cwd / ".obsidian").exists() or (cwd / "raw").exists() or (cwd / "wiki").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".obsidian").exists() or (parent / "raw").exists() or (parent / "wiki").exists():
            return parent

    # 4. 本機常見預設候選路徑（跨電腦相容）
    home = Path.home()
    candidates = [
        # BoBo-wiki 專用 Vault
        home / "Desktop" / "Project" / "Obsidian" / "BoBo-wiki",
        home / "Desktop" / "Project" / "obsidian" / "BoBo-wiki",
        home / "Desktop" / "Project" / "BoBo-wiki",
        home / "Desktop" / "obsidian" / "BoBo-wiki",
        home / "Desktop" / "Obsidian" / "BoBo-wiki",
        home / "Desktop" / "BoBo-wiki",
        home / "Project" / "Obsidian" / "BoBo-wiki",
        home / "Project" / "BoBo-wiki",
        home / "obsidian" / "BoBo-wiki",
        home / "Obsidian" / "BoBo-wiki",
        home / "Documents" / "Obsidian" / "BoBo-wiki",
        home / "Documents" / "BoBo-wiki",
        Path(r"G:\我的雲端硬碟\Obsidian\BoBo-wiki"),
        # 一般 Obsidian 總 Vault
        home / "Desktop" / "Project" / "Obsidian",
        home / "Desktop" / "Project" / "obsidian",
        home / "Desktop" / "obsidian",
        home / "Desktop" / "Obsidian",
        home / "Documents" / "Obsidian",
        Path(r"G:\我的雲端硬碟\Obsidian"),
    ]
    for c in candidates:
        if c.exists() and ((c / ".obsidian").exists() or (c / "raw").exists() or (c / "wiki").exists() or (c / "程式開發").exists()):
            return c

    # 5. Smart search on Desktop/Documents/Project
    for root in [home / "Desktop", home / "Documents", home / "Project"]:
        if not root.exists():
            continue
        try:
            for pat in ["**/BoBo-wiki", "**/bobo-wiki", "**/Obsidian", "**/obsidian"]:
                for cand in root.glob(pat):
                    if cand.is_dir() and ((cand / ".obsidian").exists() or (cand / "raw").exists() or (cand / "wiki").exists()):
                        return cand
        except Exception:
            pass

    # 6. Default GDrive fallback
    default_gdrive = Path(r"G:\我的雲端硬碟\Obsidian\BoBo-wiki")
    if default_gdrive.exists():
        return default_gdrive
    return Path(r"G:\我的雲端硬碟\Obsidian")

def get_obsidian_raw_dir() -> Optional[Path]:
    """取得 Obsidian 內的 raw 目錄路徑"""
    vault = get_vault_path()
    raw_dir = vault / "raw"
    if raw_dir.exists() and raw_dir.is_dir():
        return raw_dir
    # 若 Vault 存在但尚未建立 raw 目錄，自動嘗試建立
    if vault.exists():
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir
    return None

def check_dependencies() -> Dict[str, bool]:
    """檢查 book-reader 所需的依賴套件狀態"""
    status = {
        "yaml": False,
        "dotenv": False,
        "notebooklm_tools": False
    }
    
    try:
        import yaml
        status["yaml"] = True
    except ImportError:
        pass

    try:
        import dotenv
        status["dotenv"] = True
    except ImportError:
        pass

    try:
        from notebooklm_tools.cli.main import app
        status["notebooklm_tools"] = True
    except ImportError:
        pass

    return status

def print_environment_report():
    """輸出當前環境報告"""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
            
    vault = get_vault_path()
    raw_dir = get_obsidian_raw_dir()
    deps = check_dependencies()
    
    print("=" * 60)
    print("  Notebooklm / book-reader 環境檢測報告")
    print("=" * 60)
    print(f"Obsidian Vault 路徑 : {vault} [狀態: {'✅ 存在' if vault.exists() else '❌ 不存在'}]")
    print(f"Obsidian Raw 目錄   : {raw_dir} [狀態: {'✅ 存在' if raw_dir and raw_dir.exists() else '❌ 不存在'}]")
    print("-" * 60)
    print("依賴套件狀態：")
    for dep, ok in deps.items():
        icon = "✅" if ok else "⚠️ (缺)"
        if dep == "yaml" and not ok:
            print(f"  - {dep:<18}: {icon} — YAML 設定解析模組（請安裝 PyYAML）")
        elif dep == "dotenv" and not ok:
            print(f"  - {dep:<18}: {icon} — 環境變數載入模組（請安裝 python-dotenv）")
        elif dep == "notebooklm_tools" and not ok:
            print(f"  - {dep:<18}: {icon} — notebooklm-mcp-cli / notebooklm_tools 工具未安裝")
        else:
            print(f"  - {dep:<18}: {icon}")
    print("=" * 60)

def load_project_env():
    """從動態偵測到的 Vault 路徑中載入 .env 檔案"""
    try:
        if sys.platform == "win32":
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    vault = get_vault_path()
    env_path = vault / ".env"
    if env_path.exists():
        load_dotenv(env_path)

load_project_env()

if __name__ == "__main__":
    print_environment_report()
