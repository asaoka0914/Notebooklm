import os
import sys
import json
import time
import re
import argparse
import subprocess
import yaml

# 確保 stdout 為 UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout.reconfigure(encoding='utf-8')

class RateLimitExhaustedError(Exception):
    """當所有重試與輪換帳號皆無法解除限流時拋出"""
    pass

class RateLimiter:
    """NotebookLM API 智能限流器與指數退避控制器"""
    def __init__(self, max_requests_per_minute=30, max_consecutive_errors=3, max_pause_seconds=600):
        self.request_timestamps = []
        self.max_per_minute = max_requests_per_minute
        self.consecutive_errors = 0
        self.max_errors = max_consecutive_errors
        self.max_pause_seconds = max_pause_seconds
        self.total_pause_rounds = 0
        self.max_pause_rounds = 5

    def wait_if_needed(self):
        """檢查滑動視窗內之請求數，若接近限制則主動等待"""
        now = time.time()
        self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 60]
        if len(self.request_timestamps) >= self.max_per_minute:
            wait_time = 60 - (now - self.request_timestamps[0]) + 0.5
            if wait_time > 0:
                print(f"  ⏳ 接近 API 限流頻率 ({len(self.request_timestamps)}/{self.max_per_minute} req/min)，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)

    def record_request(self):
        """記錄一次請求時間戳"""
        self.request_timestamps.append(time.time())

    def record_success(self):
        """成功時重置連續錯誤計數器"""
        self.consecutive_errors = 0

    def record_error_and_backoff(self):
        """記錄錯誤並執行指數退避"""
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.max_errors:
            backoff_round = self.consecutive_errors - self.max_errors + 1
            pause_time = min(5 * (2 ** (backoff_round - 1)), self.max_pause_seconds)
            print(f"  ⚠️ 連續 {self.consecutive_errors} 次請求錯誤，啟動指數退避暫停 {pause_time} 秒...")
            time.sleep(pause_time)
            self.total_pause_rounds += 1
            if self.total_pause_rounds >= self.max_pause_rounds:
                raise RateLimitExhaustedError(
                    f"已連續退避 {self.total_pause_rounds} 輪仍失敗，觸發全局中斷保護"
                )

def is_thinking_fragment(text):
    """檢查是否僅為模型思考片段"""
    if len(text.strip()) < 300 and ("Analyzing" in text or "focusing now on" in text or "Confirming" in text):
        return True
    return False

def is_artifact_redirect(text):
    """檢查是否為模型導引至 Artifact 的打發回應"""
    keywords = ["專屬報告", "專屬成果", "Artifact", "分頁中查看", "查看該文件"]
    match_count = sum(1 for kw in keywords if kw in text)
    if match_count >= 2 and len(text.strip()) < 600:
        return True
    return False

def validate_schema(data):
    """ Schema 有效性檢查 """
    if not isinstance(data, dict):
        return False
    answer = data.get("answer", "")
    if not answer or len(answer) < 300:
        return False
    if is_thinking_fragment(answer) or is_artifact_redirect(answer):
        return False
    # 只要包含任何標題標記與條列即視為有效內容
    if not re.search(r'#{1,5}\s*\S+', answer):
        return False
    return True

def extract_summary(previous_batch_json):
    """從上一批 JSON 中擷取簡短摘要作為上下文"""
    try:
        answer = previous_batch_json.get("answer", "")
        if not answer:
            return ""
        # 取第一段或前 200 字
        paragraphs = [p.strip() for p in answer.split('\n\n') if p.strip() and not p.startswith('#')]
        if paragraphs:
            clean = re.sub(r'[*#]', '', paragraphs[0])
            return clean[:200]
        return answer[:150].strip()
    except Exception:
        return ""

from _auth_utils import ensure_auth_with_pool, is_auth_error, switch_google_account_interactive

def wait_for_account_switch(notebook_id=None, timeout_sec=300):
    """
    當遇 RESOURCE_EXHAUSTED 限流時，優先透過帳號池自動輪換下一個帳號；
    若帳號池無可用帳號，再彈出 Chrome 帳號身分選單讓使用者選擇。
    """
    print("\n" + "="*70)
    print("⚠️ [Quota Limit Alert] 當前 Google 帳號 NotebookLM 今日配額已達上限！")
    print("="*70 + "\n")

    # 0. 輪換前先確保筆記本已共用給帳號池成員
    if notebook_id:
        try:
            from _auth_pool import sync_notebook_collaborators
            sync_notebook_collaborators(notebook_id)
        except Exception:
            pass

    # 1. 優先透過帳號池自動輪換或自動等待冷卻
    try:
        from _auth_pool import ensure_auth_pool, sync_notebook_collaborators
        from notebooklm_tools.core.auth import check_auth
        print("🔄 正在嘗試自動輪換至帳號池中的下一個可用個人帳號（若全數冷卻則自動等待解鎖）...")
        if ensure_auth_pool():
            res = check_auth('default', live=True)
            if getattr(res, 'valid', False):
                print("🎉 [Account Switched] 帳號切換/解鎖成功！新憑證已生效。")
                if notebook_id:
                    sync_notebook_collaborators(notebook_id)
                return True
    except Exception as e:
        print(f"Notice: 自動輪換過程拋出異常: {e}，切換為手動選擇...")

    # 2. 互動式手動切換
    if switch_google_account_interactive(timeout_sec=60):
        from notebooklm_tools.core.auth import check_auth
        res = check_auth(profile='default', live=True)
        if getattr(res, 'valid', False):
            print("🎉 [Account Switched] 新帳號憑證已生效！自動 Resume 重試當前批次...")
            return True
        print("⚠️ 已切換但新憑證仍未通過驗證，請確認選的帳號確實有該筆記本存取權限且未被限流。")

    print("❌ 帳號切換未完成。也可手動執行 `python -c \"from notebooklm_tools.cli.main import app; app(['login', '--clear', '--force'])\"` 作為備用。")
    return False

def run_query_via_cli(notebook_id, prompt, timeout_sec=300, rate_limiter=None):
    """直接調用 notebooklm_tools Python API 執行 query，支援中途 Token 恢復、RateLimiter 與限流時輪詢等待"""
    from notebooklm_tools.services.auth import AuthManager
    from notebooklm_tools.core.client import NotebookLMClient
    
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        if rate_limiter:
            rate_limiter.wait_if_needed()
            
        auth = AuthManager()
        profile = auth.load_profile()
        client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
        
        try:
            if rate_limiter:
                rate_limiter.record_request()
            res = client.query(notebook_id, prompt)
            if res and isinstance(res, dict) and res.get("answer"):
                if rate_limiter:
                    rate_limiter.record_success()
                return res
        except Exception as e:
            if rate_limiter:
                rate_limiter.record_error_and_backoff()
            err_msg = str(e)
            if "RESOURCE_EXHAUSTED" in err_msg or "error code 8" in err_msg:
                if wait_for_account_switch(notebook_id=notebook_id, timeout_sec=300):
                    # 帳號切換成功，重新實例化 client
                    auth = AuthManager()
                    profile = auth.load_profile()
                    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
                    continue
                # 修正：帳號池與互動式切換皆失敗 → 判定為全域配額耗盡，立即拋出例外中止，不再浪費重試次數
                raise RateLimitExhaustedError(
                    "帳號池所有帳號均在冷卻中且無法切換帳號，全域配額耗盡（Batch 層級偵測）"
                )
            elif is_auth_error(e):
                print(f"⚠️ 檢測到執行中途 Token 旋轉/失效 ({err_msg[:100]})，嘗試中途自動恢復...")
                if ensure_auth_with_pool():
                    # 關鍵：強制重新載入 profile 並建立新 Client 物件
                    auth = AuthManager()
                    profile = auth.load_profile()
                    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
                    print("✅ 憑證與 Client 已重新載入，進行當前批次重試...")
                    continue
            else:
                print(f"    [SDK Error]: {err_msg[:300]}")
                
        if attempt < max_retries:
            time.sleep(3)
            
    return None

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_batch_generation():
    parser = argparse.ArgumentParser(description="Batch generate book report using NotebookLM.")
    parser.add_argument("--notebook-id", help="NotebookLM notebook ID")
    parser.add_argument("--title", help="Book title")
    parser.add_argument("--relogin", action="store_true", help="Clear localized session and force Chrome login before running.")
    args = parser.parse_args()

    if args.relogin:
        from notebooklm_tools.cli.main import app as cli_app
        print("🚀 [Relogin] 正在清除舊 Session 並彈出 Chrome 瀏覽器登入新 Google 帳號...")
        try:
            cli_app(['login', '--clear', '--force'])
            print("✅ 新帳號登入完成！繼續執行批次生成...\n")
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            sys.exit(1)

    config_path = os.path.join(BASE_DIR, "config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    notebook_id = args.notebook_id or config.get("notebook_id")
    book_title = args.title or config.get("book_title", "default_book")
    batch_strategy = config.get("batch_strategy", {})
    batches = batch_strategy.get("batches", [])
    delay_sec = batch_strategy.get("batch_delay_seconds", 8)

    if not notebook_id:
        print("Error: notebook_id is missing.")
        sys.exit(1)

    if not batches:
        print("❌ [Error] batch_strategy.batches 為空！")
        print("   請先確認書籍已在 NotebookLM 網頁上傳，並執行 01_init_notebook.py 以自動產生批次配置。")
        sys.exit(1)

    raw_dir = os.path.join(BASE_DIR, "raw_outputs", book_title)
    os.makedirs(raw_dir, exist_ok=True)

    failed_batches = []
    previous_summary = ""
    rate_limiter = RateLimiter(max_requests_per_minute=30, max_consecutive_errors=3)

    for b in batches:
        b_num = b.get("batch")
        ch_list = b.get("chapters", [])
        ch_range_str = " 與 ".join(ch_list)
        out_filename = f"batch_{b_num:02d}.json"
        out_filepath = os.path.join(raw_dir, out_filename)

        # 1. 檢查中斷續傳
        if os.path.exists(out_filepath) and os.path.getsize(out_filepath) > 0:
            print(f"[Batch {b_num:02d}] Checked existing output ({out_filename}), skipping query.")
            try:
                with open(out_filepath, "r", encoding="utf-8") as rf:
                    past_data = json.load(rf)
                    previous_summary = extract_summary(past_data)
            except Exception:
                previous_summary = ""
            continue

        # 2. 構建核心 Prompt (明確要求不產生腳註標號與原文引用，集中所有配額於中文內文)
        prompt = (
            f"請嚴格依據來源檔案《讀書報告核心概念.md》中的撰寫規範與原則，"
            f"針對原書 {ch_range_str} 進行極度詳細、深度且不遺漏細節的繁體中文導讀報告撰寫。\n"
            f"【重要輸出限制】：請將所有輸出配額完全集中於豐富、詳盡的章節細節與數據分析。"
            f"嚴禁在文中插入任何腳註引用標號（例如切勿出現 [1]、[2] 或 [1-3] 等數字標籤），亦切勿產生任何原文引用附錄。\n\n"
        )
        if previous_summary:
            prompt += (
                f"【前情提要】：\n{previous_summary}\n\n"
                f"請確保本批內容與前述章節在概念上連貫，避免重複解釋已提及的核心概念。\n"
            )

        print(f"\n[Batch {b_num:02d}] Generating report for {ch_range_str}...")

        max_retries = 3
        success = False
        last_err = ""

        for attempt in range(1, max_retries + 1):
            attempt_prompt = prompt
            if attempt > 1:
                # 重試時微調，強調直接輸出 Markdown，切勿導向 Artifact
                attempt_prompt += "\n（注意事項：請務必直接在對話中輸出完整 Markdown 報告內文，切勿提示至 Artifact 或專屬成果分頁查看。）"

            print(f"  Attempt {attempt}/{max_retries}...")
            try:
                data = run_query_via_cli(notebook_id, attempt_prompt, timeout_sec=300, rate_limiter=rate_limiter)
                if data and validate_schema(data):
                    with open(out_filepath, "w", encoding="utf-8") as wf:
                        json.dump(data, wf, ensure_ascii=False, indent=2)
                    print(f"  [Success] Batch {b_num:02d} saved! Answer character length: {len(data.get('answer',''))}")
                    
                    # 即時解析並在對話視窗/Console 印出「涵蓋度自我檢查清單」
                    ans_text = data.get("answer", "")
                    checklist_match = re.search(r'(?:📋\s*涵蓋度自我檢查清單|涵蓋度自我檢查清單).*', ans_text, re.DOTALL)
                    if checklist_match:
                        print("  📋 [Coverage Checklist]:")
                        for line in checklist_match.group(0).split('\n'):
                            if line.strip() and ('✅' in line or 'CHAPTER' in line or 'Chapter' in line or '*' in line or '-' in line):
                                print(f"     {line.strip()}")

                    previous_summary = extract_summary(data)
                    success = True
                    break
                else:
                    if data:
                        ans_peek = data.get("answer", "")[:100].replace('\n', ' ')
                        last_err = f"Validation failed. Peek: '{ans_peek}'"
                    else:
                        last_err = "Empty or unparseable JSON returned."
            except RateLimitExhaustedError as rle:
                last_err = str(rle)
                print(f"  🛑 [Circuit Breaker] {last_err}")
                failed_batches.append({
                    "batch": b_num,
                    "chapters": ch_list,
                    "error": last_err
                })
                # 修正：寫出失敗紀錄後，立即終止整個批次生成任務，不再嘗試後續 Batch
                failed_batches_path = os.path.join(BASE_DIR, "failed_batches.json")
                with open(failed_batches_path, "w", encoding="utf-8") as ff:
                    json.dump(failed_batches, ff, ensure_ascii=False, indent=2)
                print(f"\n[FATAL] 全域配額耗盡或已達限流上限，已中止批次生成。已完成的 Batch 已保留（中斷續傳機制），"
                      f"待帳號冷卻結束或新增帳號後，重新執行本腳本即可自動從中斷處繼續。")
                sys.exit(1)
            except Exception as e:
                last_err = str(e)

            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"  [Warning] Attempt {attempt} failed ({last_err}). Waiting {wait_time}s...")
                time.sleep(wait_time)

        if not success:
            print(f"  [FAILED] Batch {b_num:02d} failed after {max_retries} attempts.")
            if not any(fb.get("batch") == b_num for fb in failed_batches):
                failed_batches.append({
                    "batch": b_num,
                    "chapters": ch_list,
                    "error": last_err
                })

        print(f"  Throttling: waiting {delay_sec}s before next query...")
        time.sleep(delay_sec)

    if failed_batches:
        failed_batches_path = os.path.join(BASE_DIR, "failed_batches.json")
        with open(failed_batches_path, "w", encoding="utf-8") as ff:
            json.dump(failed_batches, ff, ensure_ascii=False, indent=2)
        print(f"\n[Notice] Batch generation finished with failed items. Details in {failed_batches_path}")
    else:
        print(f"\n[Complete] All batches generated successfully!")

if __name__ == "__main__":
    run_batch_generation()
