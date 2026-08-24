# Windows 除錯腳本防錯修正計畫

> **建立日期**：2026-08-21  
> **背景**：在 Windows 環境（例如另一台筆電）上執行 EPUB 探勘或 NotebookLM CLI 測試（`notebook list`、`query`、`source add --help` 等）時，過程中連續出現終端機編碼錯誤與路徑拼寫/目錄不存在問題，導致測試中斷（Exit code 1）。本計畫彙整針對此類「臨時除錯/測試腳本」的通用防錯機制。

---

## 一、核心修正重點

### 1. UTF-8 輸出修正（建議合併使用，一勞永逸）
Windows 終端機預設使用 `cp950`（Big5），無法輸出含有 Emoji（如 `📊`）或特殊 Unicode 字元，導致 `UnicodeEncodeError` 中斷腳本。建議在除錯腳本中同時採用三層防護：
1. **設定環境變數**：`os.environ["PYTHONIOENCODING"] = "utf-8"`
2. **包裝標準輸出**：將 `sys.stdout` 與 `sys.stderr` 包裝為 `io.TextIOWrapper(..., encoding='utf-8', errors='replace')`
3. **印出摘要時容錯**：對擷取到的字串或 preview 加上 `errors='replace'`，確保即使有未預期字元也不會崩潰。

### 2. 路徑統一 + 自動建目錄
避免在腳本各處以字串硬編碼路徑（防止拼寫錯誤如 `BoBob-wiki` vs `BoBo-wiki`）：
- 統一使用 `pathlib.Path` 定義單一基準路徑變數（例如 `SCRATCH_DIR`）。
- 後續檔案皆以 `SCRATCH_DIR / "filename"` 組合成路徑。
- 寫檔前一律執行 `SCRATCH_DIR.mkdir(parents=True, exist_ok=True)` 確保父目錄存在。

### 3. `safe_write()` 包裝函式
單一步驟的檔案寫入失敗不應造成整個測試流程崩潰：
- 封裝 `safe_write(path: Path, content: str, label: str)` 函式，內部包含自動建立父目錄與 `try...except` 捕捉。
- 若特定步驟存檔異常（如權限問題），僅印出警告並繼續執行後續測試（例如避免因 `FileNotFoundError` 導致後續的 `notebook create --help` 測試未執行）。

---

## 二、推薦除錯腳本通用範本 (Template)

```python
import os
import sys
import io
import subprocess
from pathlib import Path

# 1. UTF-8 編碼防護（三層防護合併使用）
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 2. 單一基準路徑定義與自動建目錄（以專案根目錄為基準）
BASE_DIR = Path(r"g:\我的雲端硬碟\Project\Notebooklm")  # 或本機桌面對應之 Project\Notebooklm
SCRATCH_DIR = BASE_DIR / "scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

# 3. 安全寫檔包裝函式
def safe_write(path: Path, content: str, label: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(content)
        print(f"✅ Saved {label}: {path}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to save {label} ({path}): {e}")
        return False

# --- 範例測試流程 ---
# result = subprocess.run([...], capture_output=True)
# raw_stdout = result.stdout.decode('utf-8', errors='replace')
# safe_write(SCRATCH_DIR / "test_result.json", raw_stdout, "測試輸出")
```

---

## 三、修正範圍與注意事項

> [!IMPORTANT]
> **嚴格限制修改範圍**：
> - 本計畫之規範與修正**僅限於臨時除錯腳本 / 探勘測試腳本**。
> - **嚴禁**修改已核准上線之正式 Pipeline 模組：`scripts/01_init_notebook.py` ~ `06_generate_book_summary.py` 以及 `_auth_pool.py` / `_auth_utils.py`。

---

## 四、驗收標準

1. **編碼測試**：執行含有 Emoji 輸出的 CLI 測試指令，確認終端機不再跳出 `UnicodeEncodeError`。
2. **路徑與目錄建立**：刻意刪除 `scratch` 目錄後重新執行測試腳本，確認能自動建立目錄並將 `notebooks.json`、`query_test.json`、`source_add_help.txt`、`notebook_create_help.txt` 寫入正確路徑 `Project\Notebooklm\scratch\`。
3. **容錯性**：若模擬寫檔失敗，腳本依然能順利跑完所有後續測試步驟。
4. **輸出核對**：回報輸出檔案之完整路徑與檔案大小供查核。

