# book-reader 問題分析與改善計畫

> **版本**：v5.0.2 (改進計畫)
> **日期**：2026-08-21
> **來源**：《不被工作綁住的防彈理財計畫》整理過程問題分析

---

## 執行過程回顧

### 成功項目
- ✅ NotebookLM CLI 環境確認完成
- ✅ 新筆記本建立（ID: `d95e1574-e974-4333-a8c7-86c8b880ef72`）
- ✅ EPUB 來源上傳成功
- ✅ 批次 1-6 成功生成（涵蓋第1-12章）
- ✅ 報告組裝完成（225KB，18個章節段落）
- ✅ 階段二歸檔完成（雙檔分流 + 概念關聯）

### 遭遇問題
1. **NotebookLM API 限流** - 批次 7-8 因 RESOURCE_EXHAUSTED 失敗
2. **QC 誤報** - 因重複章節導致假性失敗
3. **編碼問題** - Windows cp950 無法處理腳本中的 emoji
4. **帳號輪換失效** - 備用帳號認證狀態失效

---

## 問題詳細分析

### 問題 1: NotebookLM API 限流 (HIGH)

**現象**：
- 批次 7-8 嘗試生成第10-12章時，返回 `RESOURCE_EXHAUSTED` 錯誤
- 兩個帳號（asaoka0914@gmail.com, gwa20080808@gmail.com）均被限流
- 冷卻時間 30 分鐘，但實際上限流更久

**根本原因**：
- NotebookLM API 有每秒/每分鐘請求限制
- 快速連續查詢（6個批次 + 多次 QC + 多次 backfill）觸發限流
- 缺乏智能退避機制

**影響**：
- 批次 7-8 失敗，但第10-12章已包含在 Batch 6 中
- 導致不必要的重複嘗試和 Token 浪費

**⚠️ 修正前提（必須先做）**：

本節下方的 `max_requests_per_minute=30`、5 分鐘暫停、以及附錄 A 的限流數字，目前都是**假設值，未經實測驗證**。根據現象描述「冷卻時間 30 分鐘，但實際上限流更久」，真實冷卻時間可能遠超過目前設計的 5 分鐘暫停。依照過去驗證機制的做法（先實驗、再寫防禦碼），實作前應先用小規模測試（例如連續發送遞增數量的請求，記錄實際觸發 RESOURCE_EXHAUSTED 的門檻與實際解除限流所需時間）反推真實參數，再回填到 `RateLimiter` 與附錄 A，避免用錯誤假設寫出「重試又失敗」的無效迴圈。

**改善建議**：

#### 1.1 新增智能退避策略
```python
# 在 02_batch_generate.py 和 04_qc_check.py 中添加
class RateLimiter:
    """NotebookLM API 智能限流器"""
    
    def __init__(self, max_requests_per_minute=30, max_consecutive_errors=3):
        self.request_timestamps = []
        self.max_per_minute = max_requests_per_minute
        self.consecutive_errors = 0
        self.max_errors = max_consecutive_errors
    
    def wait_if_needed(self):
        """檢查是否需要等待以避免限流"""
        now = time.time()
        # 移除 60 秒前的時間戳
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if now - ts < 60
        ]
        
        # 如果接近限制，等待
        if len(self.request_timestamps) >= self.max_per_minute:
            wait_time = 60 - (now - self.request_timestamps[0])
            if wait_time > 0:
                print(f"  接近限流，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
    
    def record_request(self):
        """記錄一次請求"""
        self.request_timestamps.append(time.time())
    
    def record_error(self):
        """記錄錯誤並檢查是否需要暫停（指數退避，而非固定 5 分鐘）"""
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.max_errors:
            # 指數退避：5min -> 10min -> 20min -> ... 上限由外部設定
            backoff_round = self.consecutive_errors - self.max_errors + 1
            pause_time = min(60 * 5 * (2 ** (backoff_round - 1)), self.max_pause_seconds)
            print(f"  連續 {self.consecutive_errors} 次錯誤，暫停 {pause_time} 秒")
            time.sleep(pause_time)
            self.total_pause_rounds += 1
            if self.total_pause_rounds >= self.max_pause_rounds:
                # 超過允許的重試輪數：不再等待，交由上層 orchestrator 存檔並退出
                raise RateLimitExhaustedError(
                    f"已連續退避 {self.total_pause_rounds} 輪仍失敗，停止自動重試，交由 pipeline 層存檔退出"
                )
```

> **銜接說明**：`RateLimitExhaustedError` 由上層 pipeline 捕捉，觸發「問題 6」新增的斷路器 / 斷點續傳機制，而不是讓腳本無限迴圈等待。

#### 1.2 修改批次生成邏輯
```python
# 在 02_batch_generate.py 的查詢循環中添加
for batch_num, chapters in enumerate(batches, 1):
    rate_limiter.wait_if_needed()
    
    result = run_query_via_cli(notebook_id, query, timeout_sec=300)
    rate_limiter.record_request()
    
    if result.error:
        rate_limiter.record_error()
        continue
    
    # 保存結果...
```

#### 1.3 新增限流狀態監控
```python
# 新增 scripts/rate_limit_monitor.py
def check_rate_limit_status():
    """檢查 NotebookLM 限流狀態"""
    # 發送測試查詢
    # 如果成功，恢復正常
    # 如果失敗，記錄時間並等待
    pass
```

#### 1.4 兩帳號同時限流時的處理（兩帳號都失效已實際發生過）
```python
# 在 02_batch_generate.py / 04_qc_check.py 頂層邏輯中
def handle_all_accounts_exhausted(state: dict, checkpoint_path: str):
    """當所有帳號都被限流，安全存檔並退出，而不是持續空等"""
    state['status'] = 'paused_rate_limited'
    state['paused_at'] = datetime.now().isoformat()
    save_checkpoint(state, checkpoint_path)
    print(f"[PAUSED] 所有帳號皆被限流，進度已存於 {checkpoint_path}，請稍後重新執行以自動接續")
    sys.exit(2)  # 使用專屬 exit code，方便外層排程判斷「暫停」而非「錯誤」
```

---

### 問題 2: QC 誤報 - 重複章節導致假性失敗 (HIGH)

**現象**：
- QC 檢查顯示 `passed_all: false`
- 錯誤訊息：「符合期望 15 章節但 3 章節短缺」
- 實際問題：報告中有 18 個 H2 段落，但只有 15 個唯一章節

**根本原因**：
- Batch 2 查詢了第2-3章（重複），Batch 6 查詢了第9-12章
- 03_assemble_report.py 將所有批次內容合併，未去重
- 04_qc_check.py 使用簡單字符串匹配檢查章節覆蓋度

**影響**：
- QC 反覆失敗，觸發不必要的 backfill 嘗試
- 浪費 API 請求額度

**⚠️ 注意：下方 2.1 只是事後清理，未解決根因**

真正浪費 API 額度的是「查詢階段就查詢了重疊節圍」（Batch 2 查了第2-3章，Batch 6 又查了第9-12章），而不只是組裝階段權存在重複內容。先做 2.1（事後去重）只能修報告結果，不能避免重複生成本身消耗的 API 額度。應先做 2.0。

#### 2.0 （優先於 2.1）批次規劃階段防重疊
```python
# 在 02_batch_generate.py 產生批次清單前加入驗證
def plan_batches(chapters: list, batch_size: int) -> list:
    """規劃批次，並確保無章節範圍重疊"""
    batches = [chapters[i:i + batch_size] for i in range(0, len(chapters), batch_size)]
    seen = set()
    for batch in batches:
        overlap = seen & set(batch)
        if overlap:
            raise ValueError(f"批次規劃發現重疊章節：{overlap}，請檢查 chapter list 來源")
        seen.update(batch)
    return batches
```

若必須重跑某一批次（例如 backfill 缺失章節），應明確標註為「replace」而非「新增」，避免與先前批次重疊生成。

**改善建議**：

#### 2.1 新增章節去重邏輯
```python
# 在 03_assemble_report.py 中添加
def deduplicate_sections(content: str) -> str:
    """移除重複的章節段落"""
    import re
    
    # 找到所有 H2 段落
    sections = re.findall(r'^(##\s+.+?\n(?:.*?\n)*?)(?=\n##\s+|\Z)', content, re.MULTILINE)
    
    seen_titles = set()
    unique_sections = []
    
    for section in sections:
        # 提取章節標題
        match = re.match(r'^##\s+(.+)$', section, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # 標準化標題（移除重複的「第X章」標記）
            normalized = re.sub(r'[｜|].*', '', title).strip()
            
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique_sections.append(section)
    
    return '\n\n'.join(unique_sections)
```

#### 2.2 修改 QC 檢查邏輯
```python
# 在 04_qc_check.py 中修改 ground truth 匹配
def check_chapter_coverage(report_path: str, ground_truth: list) -> dict:
    """檢查章節覆蓋度（支持模糊匹配）"""
    with open(report_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    # 提取報告中的所有章節標題
    report_headings = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
    
    # 標準化比較
    def normalize(s: str) -> str:
        # 移除特殊字符和空格
        s = re.sub(r'[｜|\s]', '', s)
        s = re.sub(r'第(\d+)章', r'\1', s)  # 「第10章」-> 「10」
        return s.lower()
    
    missing = []
    for gt_chapter in ground_truth:
        normalized_gt = normalize(gt_chapter)
        # 檢查是否有任何報告章節匹配
        found = any(normalize(rh) == normalized_gt for rh in report_headings)
        if not found:
            missing.append(gt_chapter)
    
    return {
        'passed': len(missing) == 0,
        'missing': missing,
        'total_ground_truth': len(ground_truth),
        'total_report_sections': len(report_headings)
    }
```

#### 2.3 新增 QC 報告改进
```python
# 在 04_qc_check.py 的输出中添加详细报告
def generate_qc_report(result: dict) -> str:
    """生成詳細 QC 報告"""
    report = []
    report.append("=" * 50)
    report.append("QC Check Report")
    report.append("=" * 50)
    
    report.append(f"\nGround Truth Chapters: {result['total_ground_truth']}")
    report.append(f"Report Sections: {result['total_report_sections']}")
    
    if result['missing']:
        report.append(f"\nMissing Chapters ({len(result['missing'])}):")
        for ch in result['missing']:
            report.append(f"  - {ch}")
    
    # 檢測重複章節
    duplicates = detect_duplicates(result.get('report_headings', []))
    if duplicates:
        report.append(f"\nDuplicate Sections ({len(duplicates)}):")
        for dup in duplicates:
            report.append(f"  - {dup}")
    
    return '\n'.join(report)
```

---

### 問題 3: Windows 編碼問題 (MEDIUM)

**現象**：
- 所有腳本包含大量 emoji（如 ✅❌⚠️🔄 等）
- Windows PowerShell/CMD 使用 cp950 編碼
- 輸出時拋出 `UnicodeEncodeError`

**根本原因**：
- 腳本未檢測和控制台編碼
- print 語句直接使用 emoji 字符

**影響**：
- 無法在 Windows 終端直接查看腳本輸出
- 需要額外的編碼處理層

**⚠️ 作用範圍限定（重要）**：

下方 `safe_print()` 去除 emoji 的邏輯**只能用於控制台輸出（print 與 stdout）**，絕對不能套用到實際寫入報告檔案的內容。因為 QC 的 schema 驗證目前依賴 `📌 核心概念` 這類 emoji 開頭的標題來判斷結構（見此檔案开頭的相關背景説明），若誤將 emoji 移除邏輯套用到寫檔流程，會直接打斷 QC 的章節判斷機制。實作時應在函式命名與注釋上明確區分（例如 `safe_console_print()`），避免日後被誤用在寫檔邏輯中。另建議 3.2 與 3.3 擇一實作即可，同時存在會增加維護成本。

**改善建議**：

#### 3.1 新增編碼自動檢測
```python
# 在所有腳本開頭添加
import sys
import io

def setup_encoding():
    """自動設置輸出編碼"""
    if sys.platform == 'win32':
        # Windows 環境
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, 
                encoding='utf-8',
                errors='replace'
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, 
                encoding='utf-8',
                errors='replace'
            )
        except:
            pass  # 如果失敗，使用默認編碼

# 在每个脚本开头调用
setup_encoding()
```

#### 3.2 修改 print 函數
```python
# 创建安全的 print 函数
def safe_print(*args, **kwargs):
    """安全的打印函数，自动处理编码"""
    try:
        # 移除 emoji 或非 ASCII 字符
        cleaned_args = []
        for arg in args:
            if isinstance(arg, str):
                # 只保留 ASCII 和中文字符
                cleaned = ''.join(
                    c for c in arg 
                    if ord(c) < 128 or (0x2E80 <= ord(c) <= 0x9FFF)
                )
                cleaned_args.append(cleaned)
            else:
                cleaned_args.append(arg)
        print(*cleaned_args, **kwargs)
    except Exception as e:
        # 如果仍然失败，降级到简单打印
        print(f"[Output Error: {e}]")
```

#### 3.3 简化 emoji 使用
```python
# 建议使用文本替代 emoji
EMOJI_MAP = {
    'success': '[OK]',
    'error': '[FAIL]',
    'warning': '[WARN]',
    'info': '[INFO]',
    'loading': '[...]',
}

# 使用方式
print(f"{EMOJI_MAP['success']} Chapter 1 completed")
```

---

### 問題 4: 帳號輪換機制失效 (MEDIUM)

**現象**：
- Auth Pool 配置了 2 個帳號
- 但只有 Default Profile 有有效認證
- 其他 Profile（Profile 1, 3, 4, 5）認證失效

**根本原因**：
- `nlm login` 命令需要手動交互
- 腳本無法自動處理多帳號輪換
- 缺少帳號健康狀態檢查

**影響**：
- 限流時無法自動切換帳號
- 浪費時間嘗試無效帳號

**改善建議**：

#### 4.1 新增帳號健康檢查
```python
# 在 _auth_utils.py 中添加
def check_account_health(email: str) -> dict:
    """檢查帳號健康狀態

    注意：不能使用 --help 作為測試！--help 不需要認證，不管帳號是否登入
    都會 returncode == 0，導致健康檢查永遠回報「有效」，完全達不到過濾失效帳號的作用。
    必須發送一個真實需要認證的輕量級命令（例如查詢目前帳號的筆記本列表）。
    """
    result = subprocess.run([
        'python', '-m', 'notebooklm_tools.cli.main',
        'notebook', 'list',  # 需要實際認證的輕量命令，不是 --help
        '--profile', email,
        '--timeout', '15',
    ], capture_output=True, timeout=20)

    # 進一步判斷：returncode == 0 不代表一定登入成功，還需確認輸出中沒有 auth 錯誤字樣
    stderr_text = (result.stderr or b'').decode('utf-8', errors='ignore').lower()
    auth_failed = any(kw in stderr_text for kw in ['unauthorized', 'auth', 'login required', 'expired'])

    return {
        'email': email,
        'valid': result.returncode == 0 and not auth_failed,
        'last_checked': datetime.now().isoformat()
    }

def get_available_accounts() -> list:
    """獲取可用的帳號列表"""
    accounts = load_auth_pool()
    available = []
    
    for account in accounts:
        if not account.get('enabled', True):
            continue
        
        health = check_account_health(account['email'])
        if health['valid']:
            available.append(account)
    
    return available
```

#### 4.2 修改帳號輪換邏輯
```python
# 在 _auth_pool.py 中修改
def get_next_account() -> Optional[dict]:
    """獲取下一個可用帳號"""
    accounts = get_available_accounts()
    
    if not accounts:
        print("[ERROR] No valid accounts available")
        return None
    
    # 使用 round-robin 選擇
    current_index = get_current_index()
    next_account = accounts[current_index % len(accounts)]
    set_current_index((current_index + 1) % len(accounts))
    
    return next_account
```

#### 4.3 新增帳號管理命令
```python
# 新增 scripts/manage_accounts.py
def list_accounts():
    """列出所有帳號及其狀態"""
    pass

def add_account(email: str, profile: str):
    """添加新帳號"""
    pass

def remove_account(email: str):
    """移除帳號"""
    pass

def refresh_token(email: str):
    """刷新帳號 token"""
    pass
```

---

### 問題 5: 工作目錄處理不當 (LOW)

**現象**：
- 多個腳本使用相對路徑
- 當 CWD 不一致時，找不到檔案

**根本原因**：
- 腳本依賴當前工作目錄
- 未統一使用絕對路徑

**影響**：
- 從不同目錄執行時可能失敗

**改善建議**：

#### 5.1 統一路徑處理
```python
# 在所有腳本開頭添加
import os
from pathlib import Path

# 獲取腳本所在目錄
SCRIPT_DIR = Path(__file__).parent.resolve()
# 獲取技能根目錄
SKILL_DIR = SCRIPT_DIR.parent
# 獲取項目根目錄（假設在 BoBo-wiki 下執行）
BASE_DIR = Path(os.getcwd()).resolve()

# 定義統一的路徑訪問函數
def get_path(*parts):
    """獲取統一路徑"""
    return Path(*parts).resolve()

# 使用示例
GROUND_TRUTH_PATH = get_path(SKILL_DIR, 'config', 'ground_truth_toc.json')
RAW_OUTPUTS_PATH = get_path(BASE_DIR, 'raw_outputs')
```

#### 5.2 新增路徑驗證
```python
def validate_paths():
    """驗證所有必需路徑"""
    required_paths = {
        'skill_dir': SKILL_DIR,
        'scripts_dir': SCRIPT_DIR,
        'config_dir': get_path(SKILL_DIR, 'config'),
        'auth_pool_dir': get_path(SKILL_DIR, 'auth_pool'),
    }
    
    missing = []
    for name, path in required_paths.items():
        if not path.exists():
            missing.append(name)
    
    if missing:
        raise FileNotFoundError(f"Missing required directories: {missing}")
    
    return required_paths
```

---

### 問題 6：Pipeline 層級缺少斷路器與斷點續傳（HIGH — 未被原修正案涵蓋，但才是「流程卡住」的直接成因）

**現象**：
- 問題 1、2、4 描述的都是單一次請求/單一批次失敗的處理方式，但整份修正案沒有描述「當連續失敗次數超過一定程度時，整條 pipeline 應該怎麼做」
- 實際案例中「兩個帳號均被限流」已發生過，但目前機制無法讓流程在這種情況下安全收尾，只能人工中斷

**根本原因**：
- 目前修正案全部集中在「單點容錯」（限流退避、QC 模糊匹配、帳號健康檢查），沒有「全局容錯」設計
- 沒有斷點續傳机制，代表每次中斷重跑都從頭開始，進一步浪費已成功的批次額度

**影響**：
- 當限流/認證失效長時間未恢復時，整條 pipeline 會一直重試直到人工中斷，這就是使用者實際體感到的「流程卡住」

**改善建議**：

#### 6.1 新增 pipeline 層級斷路器
```python
# 新增 scripts/_pipeline_state.py
class PipelineCircuitBreaker:
    """跨批次、跨帳號的全局容錯上限"""

    def __init__(self, max_total_pause_rounds=3, checkpoint_path='qc_status.json'):
        self.max_total_pause_rounds = max_total_pause_rounds
        self.checkpoint_path = checkpoint_path

    def trip(self, state: dict, reason: str):
        """觸發斷路：存檔並以專屬 exit code 退出，不再自動重試"""
        state['status'] = 'circuit_breaker_tripped'
        state['reason'] = reason
        state['tripped_at'] = datetime.now().isoformat()
        save_checkpoint(state, self.checkpoint_path)
        print(f"[CIRCUIT BREAKER] {reason}，進度已存於 {self.checkpoint_path}")
        sys.exit(2)
```

#### 6.2 斷點續傳：每個批次完成後即時寫入 checkpoint
```python
# 在 02_batch_generate.py 主迴圈中
def run_pipeline_with_resume(state_path: str):
    state = load_checkpoint(state_path) or init_state()
    remaining = [b for b in state['batches'] if b['id'] not in state['completed_batch_ids']]

    for batch in remaining:
        try:
            result = generate_batch(batch)
            state['completed_batch_ids'].append(batch['id'])
            save_checkpoint(state, state_path)  # 每成功一批即時存檔，不等到全部完成
        except RateLimitExhaustedError as e:
            PipelineCircuitBreaker().trip(state, str(e))

    return state
```

> 此設計與問題 1.4 的 `handle_all_accounts_exhausted()` 相互配合：1.4 處理「兩帳號同時失效」的單次事件，6.1/6.2 確保重新執行時能從中斷點接續，而不是從頭重跑。

---

## 立即修復清單

### 高優先級（必須修復）

0. **[新增 scripts/_pipeline_state.py]** Pipeline 層斷路器與斷點續傳（問題 6，真正解決「流程卡住」的關鍵）
   - 實現 `PipelineCircuitBreaker`
   - 每個批次完成後即時寫入 checkpoint，支援中斷後從斷點接續
   - 達到全局容錯上限時安全退出（sys.exit(2)），不再無限重試

1. **[02_batch_generate.py]** 新增智能限流器
   - **先實測驗證真實限流門檻與冷卻時間**，再回填 `RateLimiter` 參數與附錄 A，不使用未驗證的假設值
   - 實現 `RateLimiter` 類（改為指數退避，超過重試上限後扔出 `RateLimitExhaustedError` 交由 pipeline 斷路器處理）
   - 在查詢循環中添加等待邏輯
   - 記錄請求時間戳
   - 新增 `handle_all_accounts_exhausted()` 處理兩帳號同時失效的情況

2. **[04_qc_check.py]** 修復章節匹配邏輯
   - 實現模糊匹配（標準化標題）
   - 檢測並報告重複章節
   - 更新 `passed_all` 判斷條件

3. **[02_batch_generate.py]** 新增批次規劃防重疊（優先於事後去重，才能避免重複生成消耗 API 額度）
   - 新增 `plan_batches()` 驗證，查詢前拒絕重疊章節範圍
   - backfill 重跑需明確標註為 replace，不能與先前批次重疊

4. **[03_assemble_report.py]** 新增去重功能（作為事後保險，非主要修正手段）
   - 組裝前檢測重複章節
   - 自動合併相同章節內容
   - 生成去重後的報告

### 中優先級（建議修復）

5. **[所有 Python 腳本]** 解決編碼問題
   - 添加 `setup_encoding()` 函數
   - 替換 emoji 為文本標記（**僅限控制台輸出**，不得影響寫入報告檔案內容，避免打斷 QC 依賴的 emoji 標題判斷）
   - 使用 `safe_console_print()` 函數（命名明確標示僅用於控制台）

6. **[_auth_pool.py]** 改進帳號輪換
   - 添加帳號健康檢查（**需使用需要真實認證的命令**，不能用 `--help`）
   - 只輪換有效帳號
   - 記錄帳號使用統計

7. **[01_init_notebook.py]** 改進 TOC 解析
   - 增加編碼自動檢測
   - 處理多種 NCX 格式
   - 驗證解析結果

### 低優先級（可選改進）

8. **[所有腳本]** 統一路徑處理
   - 使用絕對路徑
   - 添加路徑驗證
   - 改善錯誤訊息

9. **[SKILL.md]** 更新文檔
   - 記錄已知問題
   - 添加故障排除指南
   - 說明帳號配置方法

---

## 測試計畫

### 單元測試
```python
# tests/test_rate_limiter.py
def test_rate_limiter():
    limiter = RateLimiter(max_requests_per_minute=5)
    # 發送 5 個請求
    for i in range(5):
        limiter.wait_if_needed()
        limiter.record_request()
    # 第 6 個請求應該等待
    start = time.time()
    limiter.wait_if_needed()
    elapsed = time.time() - start
    assert elapsed >= 10  # 至少等待 10 秒

def test_duplicate_detection():
    content = """## Chapter 1
Content 1

## Chapter 2
Content 2

## Chapter 1 (Duplicate)
Duplicate Content
"""
    result = deduplicate_sections(content)
    assert result.count('Chapter 1') == 1
    assert result.count('Chapter 2') == 1
```

### 整合測試
```python
# tests/test_full_pipeline.py
def test_book_processing():
    # 1. 初始化筆記本
    # 2. 生成批次
    # 3. 運行 QC
    # 4. 驗證結果
    pass
```

---

## 實施時程

| 階段 | 任務 | 預計時間 | 負責人 |
|------|------|---------|--------|
| 階段 1 | 限流器 + QC 修復 | 2 小時 | Agent |
| 階段 2 | 編碼問題 + 路徑統一 | 1 小時 | Agent |
| 階段 3 | 帳號輪換改進 | 1 小時 | Agent |
| 階段 4 | 測試 + 文檔更新 | 1 小時 | Agent |

**總計**：約 5 小時

---

## 驗證標準

### 成功條件
1. ✅ 批次生成不再觸發限流（或智能退避）
2. ✅ QC 正確識別章節覆蓋度（無假性失敗）
3. ✅ Windows 終端可正常顯示輸出
4. ✅ 帳號輪換只使用有效帳號
5. ✅ 從任意目錄執行腳本均成功
6. ✅ 當限流/認證失效超過全局容錯上限時，pipeline 能安全存檔退出，並在重新執行時從斷點接續（不需從頭重跑）

### 失敗條件
- ❌ 批次生成因限流連續失敗 3 次以上
- ❌ QC 仍報假性失敗
- ❌ Windows 終端輸出亂碼或錯誤
- ❌ 帳號輪換嘗試無效帳號
- ❌ 路徑錯誤導致檔案找不到
- ❌ 全局容錯上限後仍無限重試，或中斷後無法從斷點接續（仍需從頭重跑）

---

## 附錄

### A. NotebookLM API 限流政策

> ⚠️ **以下數字目前未有來源驗證，屬於假設值**。實作 `RateLimiter`（見問題 1）前應先實際測試確認，並回填真實數字。尤其現象描述「冷卻時間 30 分鐘，但實際上限流更久」，與下方「每小時 1000 個請求」等描述本身有矛盾，需實際重新確認。

- 每秒最多 10 個請求（待驗證）
- 每分鐘最多 60 個請求（待驗證）
- 每小時最多 1000 個請求（待驗證）
- 超出限流返回 `RESOURCE_EXHAUSTED` 錯誤
- 實際觀察到的冷卻時間超過 30 分鐘（實際數值待實測確認）

### B. 相關問題追蹤
- Issue #1: 限流導致批次失敗
- Issue #2: QC 誤報重複章節
- Issue #3: Windows 編碼錯誤
- Issue #4: 帳號輪換失效

### C. 參考文檔
- [NotebookLM Tools CLI 文件](https://github.com/notebooklm-tools/cli)
- [book-reader SKILL.md](SKILL.md)
- [Auth Pool 配置說明](auth_pool/README.md)
