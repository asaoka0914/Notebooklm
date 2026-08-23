import unittest
import time
import os
import sys
import importlib.util

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

spec_02 = importlib.util.spec_from_file_location('mod_02', os.path.join(BASE_DIR, 'scripts', '02_batch_generate.py'))
mod_02 = importlib.util.module_from_spec(spec_02)
spec_02.loader.exec_module(mod_02)
RateLimiter = mod_02.RateLimiter
RateLimitExhaustedError = mod_02.RateLimitExhaustedError

spec_01 = importlib.util.spec_from_file_location('mod_01', os.path.join(BASE_DIR, 'scripts', '01_init_notebook.py'))
mod_01 = importlib.util.module_from_spec(spec_01)
spec_01.loader.exec_module(mod_01)
plan_batches = mod_01.plan_batches

spec_04 = importlib.util.spec_from_file_location('mod_04', os.path.join(BASE_DIR, 'scripts', '04_qc_check.py'))
mod_04 = importlib.util.module_from_spec(spec_04)
spec_04.loader.exec_module(mod_04)
detect_duplicate_chapters = mod_04.detect_duplicate_chapters

class TestImprovements(unittest.TestCase):
    def test_rate_limiter_window_and_records(self):
        """測試 RateLimiter 滑動視窗計數與請求紀錄"""
        limiter = RateLimiter(max_requests_per_minute=5, max_consecutive_errors=2)
        for _ in range(4):
            limiter.record_request()
        self.assertEqual(len(limiter.request_timestamps), 4)
        
        # 成功請求重置錯誤計數
        limiter.consecutive_errors = 1
        limiter.record_success()
        self.assertEqual(limiter.consecutive_errors, 0)

    def test_rate_limiter_exponential_backoff_and_circuit_breaker(self):
        """測試 RateLimiter 在連續錯誤時的退避與達到上限拋出 RateLimitExhaustedError"""
        limiter = RateLimiter(max_requests_per_minute=30, max_consecutive_errors=2, max_pause_seconds=1)
        limiter.max_pause_rounds = 2
        
        # 第一次錯誤（未達 max_errors）
        limiter.record_error_and_backoff()
        self.assertEqual(limiter.consecutive_errors, 1)
        self.assertEqual(limiter.total_pause_rounds, 0)

        # 第二次錯誤（達 max_errors，暫停 round 1）
        limiter.record_error_and_backoff()
        self.assertEqual(limiter.consecutive_errors, 2)
        self.assertEqual(limiter.total_pause_rounds, 1)

        # 第三次錯誤（暫停 round 2，達到 max_pause_rounds 拋出例外）
        with self.assertRaises(RateLimitExhaustedError):
            limiter.record_error_and_backoff()

    def test_plan_batches_no_overlap(self):
        """測試 plan_batches 能正確規劃批次且無重疊"""
        chapters = ["第1章", "第2章", "第3章", "第4章", "第5章"]
        batches = plan_batches(chapters, batch_size=2)
        self.assertEqual(len(batches), 3)
        self.assertEqual(batches[0]["chapters"], ["第1章", "第2章"])
        self.assertEqual(batches[1]["chapters"], ["第3章", "第4章"])
        self.assertEqual(batches[2]["chapters"], ["第5章"])

    def test_plan_batches_empty(self):
        """測試空章節清單"""
        batches = plan_batches([])
        self.assertEqual(batches, [])

    def test_detect_duplicate_chapters(self):
        """測試 QC 重複章節標題偵測功能"""
        headings = [
            "第 1 章：理財基礎",
            "第 2 章：投資概念",
            "第1章 理財基礎",  # 重複
            "第 3 章：資產配置"
        ]
        dups = detect_duplicate_chapters(headings)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0][0], "第 1 章：理財基礎")
        self.assertEqual(dups[0][1], "第1章 理財基礎")

    def test_auth_pool_valid_token_skips_chrome_launch(self):
        """測試當本地 Token 仍有效時，ensure_auth_pool 會直接略過 Chrome 啟動"""
        spec_pool = importlib.util.spec_from_file_location('mod_pool', os.path.join(BASE_DIR, 'scripts', '_auth_pool.py'))
        mod_pool = importlib.util.module_from_spec(spec_pool)
        spec_pool.loader.exec_module(mod_pool)

        from unittest.mock import patch
        with patch.object(mod_pool, 'is_current_token_valid', return_value=True), \
             patch.object(mod_pool, 'fetch_token_headless') as mock_fetch:
            res = mod_pool.ensure_auth_pool()
            self.assertTrue(res)
            mock_fetch.assert_not_called()

    def test_run_query_circuit_breaker_on_resource_exhausted(self):
        """測試 run_query_via_cli 在 RESOURCE_EXHAUSTED 且切換帳號失敗時直接拋出 RateLimitExhaustedError"""
        from unittest.mock import patch, MagicMock
        with patch.object(mod_02, 'wait_for_account_switch', return_value=False), \
             patch('notebooklm_tools.services.auth.AuthManager'), \
             patch('notebooklm_tools.core.client.NotebookLMClient') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.query.side_effect = Exception("RESOURCE_EXHAUSTED: Quota exceeded")
            mock_client_cls.return_value = mock_client
            
            with self.assertRaises(RateLimitExhaustedError):
                mod_02.run_query_via_cli("fake_nb_id", "fake_prompt")

    def test_batch_generate_circuit_breaker_aborts_all_batches(self):
        """測試 run_batch_generation 在遭遇 RateLimitExhaustedError 時會寫出 failed_batches.json 並以 sys.exit(1) 中止"""
        import tempfile
        import shutil
        from unittest.mock import patch

        temp_dir = tempfile.mkdtemp()
        try:
            config_dir = os.path.join(temp_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            config_yaml = os.path.join(config_dir, "book_config.yaml")
            with open(config_yaml, "w", encoding="utf-8") as f:
                f.write("""
notebook_id: test_nb_123
book_title: test_circuit_breaker_book
batch_strategy:
  batch_delay_seconds: 0
  batches:
    - batch: 1
      chapters: ["第一章"]
    - batch: 2
      chapters: ["第二章"]
""")
            with patch.object(mod_02, 'BASE_DIR', temp_dir), \
                 patch.object(mod_02, 'run_query_via_cli', side_effect=RateLimitExhaustedError("全域配額耗盡")), \
                 patch('sys.argv', ['02_batch_generate.py']):
                with self.assertRaises(SystemExit) as cm:
                    mod_02.run_batch_generation()
                self.assertEqual(cm.exception.code, 1)

            # 驗證 failed_batches.json 存在且僅處理到 batch 1 就被熔斷中斷
            failed_json = os.path.join(temp_dir, "failed_batches.json")
            self.assertTrue(os.path.exists(failed_json))
            import json
            with open(failed_json, "r", encoding="utf-8") as rf:
                failed_data = json.load(rf)
            self.assertEqual(len(failed_data), 1)
            self.assertEqual(failed_data[0]["batch"], 1)

            # 驗證 batch 2 根本沒有被嘗試執行（沒有輸出 batch_02.json）
            batch_02 = os.path.join(temp_dir, "raw_outputs", "test_circuit_breaker_book", "batch_02.json")
            self.assertFalse(os.path.exists(batch_02))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()

