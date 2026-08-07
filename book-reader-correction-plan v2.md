# book-reader 技能修正計畫

> 產生日期：2026-08-07
> 依據：本次執行《被動投資學》讀書報告時的實測問題

---

## 問題清單與修正方案

### 問題 1：認證失敗時無自動恢復機制 🔴 P0

**根本原因分析**

Google Cookie 本身沒有過期（SID 有效期至 2027-09-11，剩 399 天），真正失效的是 **CSRF Token（SNlM0e）**。

```
認證流程鏈路：
  1. 客戶端用 Google SID Cookie 發送請求
  2. NotebookLM 用 CSRF Token（SNlM0e）防跨站請求
  3. Google 會定期 rotate CSRF token（不通知客戶端）
  4. notebooklm_tools 的 _refresh_auth_tokens() 嘗試刷新：
     - 呼叫 rotate_google_cookies() → 觸發 Google RotateCookies 端點
     - 抓取 NotebookLM 首頁提取新 CSRF
     - 若失敗（網路/結構變化）→ 丟出 ValueError
  5. Layer 2 _try_reload_or_headless_auth() 嘗試 headless auth：
     - 需要 Chrome 已經以 --remote-debugging-port=9223 運行
     - 若沒有 → 返回 False → 認證失敗
```

**關鍵缺陷**：`_try_reload_or_headless_auth()` **不主動啟動 Chrome**，它假設 Chrome 已經在運行。這是 library 的設計限制。

**症狀**
- NotebookLM 認證過期（`ClientAuthenticationError`）時，`login --clear --force` 啟動 Chrome CDP 流程
- 使用者未在第一時間手動登入，300 秒超時後直接失敗
- 沒有自動重試或降級策略

**修正方案**

在 `scripts/01_init_notebook.py` 的開頭加入自動認證恢復邏輯：

```python
def ensure_auth():
    """檢查認證有效性，過期時自動啟動 Chrome headless 重認證。"""
    from notebooklm_tools.core.auth import check_auth, save_tokens_to_cache
    from notebooklm_tools.utils.auth_browser import run_headless_auth
    import subprocess, time, os, shutil

    result = check_auth(profile='default', live=True)
    if result.valid:
        return True

    print("⚠️  認證過期，嘗試自動恢復...")

    # 1. 先嘗試 headless auth（需要 Chrome 已以 --remote-debugging-port 啟動）
    tokens = run_headless_auth(profile_name='default', timeout=60)
    if tokens:
        print("✅ 認證已自動恢復（透過現有 Chrome CDP）")
        return True

    # 2. 啟動 Chrome 偵錯模式
    chrome_path = _find_chrome_path()
    if not chrome_path:
        print("❌ 無法找到 Chrome，請手動執行: nlm login")
        return False

    print("🚀 啟動 Chrome 偵錯模式...")
    chrome_proc = subprocess.Popen([
        chrome_path,
        '--remote-debugging-port=9223',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions',
        '--user-data-dir=' + os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google\\Chrome\\User Data\\Default'),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 等待 CDP 就緒（最多 15 秒）
    cdp_ready = False
    for i in range(15):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen('http://127.0.0.1:9223/json', timeout=2)
            cdp_ready = True
            break
        except Exception:
            if i == 14:
                chrome_proc.terminate()
                print("❌ Chrome CDP 無法就緒")
                return False

    if not cdp_ready:
        chrome_proc.terminate()
        return False

    # 3. 再次嘗試 headless auth
    tokens = run_headless_auth(port=9223, profile_name='default', timeout=60)
    chrome_proc.terminate()

    if tokens:
        save_tokens_to_cache(tokens)
        print("✅ 認證已自動恢復（透過自動啟動 Chrome）")
        return True

    print("❌ 自動認證恢復失敗，請手動執行: python -c \"from notebooklm_tools.cli.main import app; app(['login', '--clear', '--force'])\"")
    return False


def _find_chrome_path():
    """在 Windows 上尋找 Chrome 可執行檔。"""
    import glob
    candidates = glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    candidates += glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
    return candidates[0] if candidates else None
```

在 `init_notebook()` 函數開頭呼叫 `ensure_auth()`：

```python
def init_notebook():
    if not ensure_auth():
        sys.exit(1)
    # ... 後續邏輯不變
```

---

### 問題 2：Obsidian 存檔路徑硬編碼且環境不相容 🔴 P1

**症狀**
- SKILL.md 寫死兩條路徑：
  - 家中：`G:\我的雲端硬碟\Obsidian\BoBo-wiki\raw`
  - 公司：`C:\Users\asaoka.zhong\Desktop\obsidian\BoBo-wiki\raw`
- 兩條路徑都不存在，實際路徑是 `C:\Users\asaoka.zhong\Desktop\Project\Obsidian\BoBo-wiki\raw`
- 本次靠手動 `cp` 解決

**修正方案**

在 `scripts/03_assemble_report.py` 中動態搜尋 Obsidian 路徑：

```python
def find_obsidian_raw_dir():
    """動態搜尋 Obsidian BoBo-wiki raw 目錄。"""
    candidates = []
    home = os.path.expanduser('~')

    # 常見位置
    search_paths = [
        # 專案目錄
        os.path.join(home, 'Desktop', 'Project', 'Obsidian', 'BoBo-wiki', 'raw'),
        os.path.join(home, 'Desktop', 'obsidian', 'BoBo-wiki', 'raw'),
        # 雲端硬碟（Windows 常见挂载点）
        os.path.join(home, 'OneDrive', 'Obsidian', 'BoBo-wiki', 'raw'),
        os.path.join(home, 'Desktop', '我的雲端硬碟', 'Obsidian', 'BoBo-wiki', 'raw'),
        # 其他可能位置
        os.path.join(home, 'Obsidian', 'BoBo-wiki', 'raw'),
    ]

    for p in search_paths:
        if os.path.isdir(p):
            candidates.append(p)

    # 也掃描 Desktop 下所有 Obsidian 目錄
    desktop = os.path.join(home, 'Desktop')
    if os.path.isdir(desktop):
        for entry in os.listdir(desktop):
            candidate = os.path.join(desktop, entry, 'Obsidian', 'BoBo-wiki', 'raw')
            if os.path.isdir(candidate):
                if candidate not in candidates:
                    candidates.append(candidate)

    if not candidates:
        print("⚠️  警告：未找到 Obsidian BoBo-wiki/raw 目錄，報告僅儲存於技能 final/ 目錄")
        return None

    # 優先選擇包含現有其他讀書報告的目錄
    for cand in candidates:
        md_files = [f for f in os.listdir(cand) if f.endswith('_讀書報告.md')]
        if md_files:
            return cand

    return candidates[0]
```

在 `assemble_report()` 結尾追加：

```python
    # 自動複製至 Obsidian
    obsidian_dir = find_obsidian_raw_dir()
    if obsidian_dir:
        short_title = book_title.split('：')[0] if '：' in book_title else book_title
        obsidian_path = os.path.join(obsidian_dir, f"{short_title}_讀書報告.md")
        import shutil
        shutil.copy2(final_report_path, obsidian_path)
        print(f"✅ 報告已複製至 Obsidian：{obsidian_path}")
    else:
        print("⚠️  未找到 Obsidian 目錄，報告請手動複製至目標路徑")
```

同時更新 SKILL.md 中的 Obsidian 路徑說明為動態搜尋邏輯。

---

### 問題 3：SKILL.md 三處版本不同步 🔴 P1

**發現**
| 位置 | 行數 | 狀態 |
|------|------|------|
| `~/.claude/skills/book-reader/SKILL.md` | 179 | ✅ 最新版（含完整 pipeline） |
| `~/.gemini/config/skills/book-reader/SKILL.md` | 107 | ❌ 舊版 |
| `~/.local/share/chezmoi/dot_gemini/.../SKILL.md` | 107 | ❌ 舊版 |

**修正方案**

執行以下命令同步：

```bash
# 從 claude 同步到 gemini
cp ~/.claude/skills/book-reader/SKILL.md ~/.gemini/config/skills/book-reader/SKILL.md

# 同步到 chezmoi
cp ~/.claude/skills/book-reader/SKILL.md ~/.local/share/chezmoi/dot_gemini/config/skills/book-reader/SKILL.md

# 用 chezmoi 管理並 commit
cd ~/.local/share/chezmoi
chezmoi add dot_gemini/config/skills/book-reader/SKILL.md
chezmoi commit -m "sync book-reader SKILL.md to latest"
```

---

### 問題 4：禁止詞過濾不徹底 🟡 P2

**症狀**
最終報告中發現 2 處禁止詞：
- 「這顯示」1 次（第 8 章，引用柏格數據時）
- 「這意味著」1 次（第 13 章，退休金計算時）

这是 NotebookLM 未嚴格遵守 `讀書報告核心概念.md` 約束的結果。

**修正方案**

在 `scripts/03_assemble_report.py` 的 `assemble_report()` 中，標題正規化之後、寫入檔案之前，加入禁止詞清理：

```python
def clean_forbidden_phrases(text):
    """移除 NotebookLM 產出中的主觀解讀詞。"""
    forbidden = {
        '這顯示': '數據表明',
        '這意味著': '這表示',
        '這說明': '這表明',
        '這反映了': '這體現了',
        '這代表': '這標誌著',
        '值得注意的是': '',
        '可以發現': '',
        '由此可見': '',
    }
    for old, new in forbidden.items():
        text = text.replace(old, new)
    return text
```

在第二階段內容處理中加入：

```python
        # 2.5 清理禁止詞
        clean_answer = clean_forbidden_phrases(clean_answer)
        # 3. 標題正規化
        norm_answer = normalize_headings(clean_answer)
```

---

### 問題 5：部分章節篇幅不足 1000 字 🟡 P2

**症狀**
7 個章節低於 QC 設定的 1000 字門檻（第 2、5–12 章），主要原因是每批 3 章導致單章篇幅被壓縮。

**修正方案**

在 `config/book_config.yaml` 中調整批次策略為每批 2 章：

```yaml
batch_strategy:
  batches:
    - batch: 1
      chapters: ["第 1 章 主動與被動的投資爭論", "第 2 章 早期研究證實主動投資的失利"]
    - batch: 2
      chapters: ["第 3 章 指數型基金的誕生", "第 4 章 主動型經理人只能靠運氣"]
    - batch: 3
      chapters: ["第 5 章 被動投資的選擇變多了", "第 6 章 共同基金投資組合的被動優勢"]
    - batch: 4
      chapters: ["第 7 章 無法找到未來必勝的基金", "第 8 章 難以掌握進出市場的時機"]
    - batch: 5
      chapters: ["第 9 章 別忙了，轉變投資思維加入被動投資吧！", "第 10 章 實施被動投資的事前準備"]
    - batch: 6
      chapters: ["第 11 章 個別投資人的被動投資案例", "第 12 章 慈善機構與個人信託的被動投資案例"]
    - batch: 7
      chapters: ["第 13 章 退休金的被動投資案例", "第 14 章 投資顧問的被動投資案例"]
  batch_delay_seconds: 8
```

同時更新 SKILL.md 中的批次說明，建議每批 2 章而非 3 章。

---

### 問題 6：`讀書報告核心概念.md` 約束力不足 🟡 P2

**現象**
現有規則寫道「嚴禁加入個人推論」，但 NotebookLM 仍產出「這顯示」「這意味著」等詞。

**修正方案**

將 `讀書報告核心概念.md` 的第 1 條強化：

```markdown
1. **完全忠實**：僅能擷取原文明確記載的事實、數據與觀點，嚴禁加入個人推論、延伸解釋或主觀評論。
   - 禁止詞：不得出現「這顯示」「這意味著」「這說明」「這反映了」「這代表」「值得注意的是」「可以發現」「由此可見」等詞。
   - 若原文有「這顯示」之類的表述，必須改為直接陳述事實（如「數據表明」或改為數據本身）。
```

---

## 執行順序建議

| 順序 | 問題 | 預估工作量 |
|------|------|-----------|
| 1 | 問題 3：SKILL.md 同步 | 5 分鐘（3 個 cp + chezmoi commit） |
| 2 | 問題 4：禁止詞清理 | 10 分鐘（修改 03_assemble_report.py） |
| 3 | 問題 6：規則強化 | 5 分鐘（修改 讀書報告核心概念.md） |
| 4 | 問題 2：Obsidian 路徑動態化 | 20 分鐘（修改 03_assemble_report.py） |
| 5 | 問題 5：批次策略調整 | 5 分鐘（更新 book_config.yaml 模板） |
| 6 | 問題 1：認證自動恢復 | 30 分鐘（修改 01_init_notebook.py） |

總預估：**約 75 分鐘**

---

## 驗證方式

修正完成後，用同一本《被動投資學》EPUB 重新執行完整流程，驗證以下項目：

1. ✅ 認證過期時自動恢復（不依賴手動登入 Chrome）
2. ✅ 報告自動存入 Obsidian 目錄（無需手動 cp）
3. ✅ 三處 SKILL.md 內容一致
4. ✅ 最終報告無禁止詞
5. ✅ 每章 ≥ 1000 字
6. ✅ QC 全部通過（`🎉 QC RESULT: ALL CHECKS PASSED`）
