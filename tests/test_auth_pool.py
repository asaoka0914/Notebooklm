import unittest
import os
import sys
import json
import yaml
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

import _auth_pool

class TestAuthPool(unittest.TestCase):
    def setUp(self):
        # 建立臨時測試目錄模擬 auth_pool
        self.test_dir = tempfile.mkdtemp()
        self.orig_pool_dir = _auth_pool.POOL_DIR
        self.orig_pool_config = _auth_pool.POOL_CONFIG
        self.orig_pool_status = _auth_pool.POOL_STATUS

        _auth_pool.POOL_DIR = Path(self.test_dir)
        _auth_pool.POOL_CONFIG = Path(self.test_dir) / "pool_config.yaml"
        _auth_pool.POOL_STATUS = Path(self.test_dir) / "pool_status.json"

        # 寫入預設測試 config
        self.mock_config = {
            "version": 1,
            "strategy": "round_robin",
            "cooldown_minutes": 30,
            "accounts": [
                {
                    "id": "acc_1",
                    "email": "acc1@gmail.com",
                    "token_file": "tokens/acc1.json",
                    "enabled": True,
                    "note": "Account 1"
                },
                {
                    "id": "acc_2",
                    "email": "acc2@gmail.com",
                    "token_file": "tokens/acc2.json",
                    "enabled": True,
                    "note": "Account 2"
                }
            ]
        }
        with open(_auth_pool.POOL_CONFIG, 'w', encoding='utf-8') as f:
            yaml.dump(self.mock_config, f)

    def tearDown(self):
        _auth_pool.POOL_DIR = self.orig_pool_dir
        _auth_pool.POOL_CONFIG = self.orig_pool_config
        _auth_pool.POOL_STATUS = self.orig_pool_status
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_pool_config(self):
        config = _auth_pool.load_pool_config()
        self.assertEqual(len(config.get("accounts", [])), 2)
        self.assertEqual(config["accounts"][0]["id"], "acc_1")

    def test_get_or_init_status_initializes_properly(self):
        status = _auth_pool.get_or_init_status()
        self.assertEqual(status["current_account"], "acc_1")
        self.assertIn("acc_1", status["accounts"])
        self.assertIn("acc_2", status["accounts"])
        self.assertEqual(status["accounts"]["acc_1"]["status"], "active")

    @patch('_auth_utils.list_chrome_profiles_with_email')
    def test_find_chrome_profile_matching(self, mock_list):
        # 測試透過 _auth_utils 比對 email
        mock_list.return_value = [
            {'dir': 'Default', 'email': 'acc1@gmail.com', 'name': 'Acc1'},
            {'dir': 'Profile 2', 'email': 'acc2@gmail.com', 'name': 'Acc2'}
        ]
        profile_1 = _auth_pool.find_chrome_profile_by_email('acc1@gmail.com')
        profile_2 = _auth_pool.find_chrome_profile_by_email('acc2@gmail.com')
        profile_none = _auth_pool.find_chrome_profile_by_email('notfound@gmail.com')

        self.assertEqual(profile_1, 'Default')
        self.assertEqual(profile_2, 'Profile 2')
        self.assertIsNone(profile_none)

    def test_rotate_account_and_cooldown(self):
        status = _auth_pool.get_or_init_status()
        config = _auth_pool.load_pool_config()

        # 當前為 acc_1，觸發輪換
        next_acc = _auth_pool.rotate_account(status, config)
        self.assertIsNotNone(next_acc)
        self.assertEqual(next_acc["id"], "acc_2")

        # 驗證 acc_1 進入冷卻
        self.assertEqual(status["accounts"]["acc_1"]["status"], "cooldown")
        self.assertTrue(_auth_pool.is_account_in_cooldown(status["accounts"]["acc_1"]))

        # 再次輪換，但因為 acc_1 冷卻中且只有 2 個帳號，應輪換回 None
        next_acc_2 = _auth_pool.rotate_account(status, config)
        self.assertIsNone(next_acc_2)

    @patch('_auth_pool.fetch_token_headless', return_value=True)
    def test_ensure_auth_pool_success(self, mock_fetch):
        success = _auth_pool.ensure_auth_pool()
        self.assertTrue(success)
        status = _auth_pool.get_or_init_status()
        self.assertEqual(status["accounts"]["acc_1"]["total_requests"], 1)

    @patch('_auth_pool.fetch_token_headless')
    def test_ensure_auth_pool_rotates_on_failure(self, mock_fetch):
        # 第一次 acc_1 失敗，第二次 acc_2 成功
        mock_fetch.side_effect = [False, True]
        success = _auth_pool.ensure_auth_pool()
        self.assertTrue(success)
        status = _auth_pool.get_or_init_status()
        self.assertEqual(status["current_account"], "acc_2")
    @patch('_auth_pool.fetch_token_headless', return_value=False)
    @patch('_auth_utils.ensure_auth', return_value=True)
    def test_ensure_auth_pool_fallback_on_all_failures(self, mock_ensure_auth, mock_fetch):
        # 當所有帳號都失敗時，驗證會呼叫 fallback ensure_auth()
        success = _auth_pool.ensure_auth_pool()
        self.assertTrue(success)
        mock_ensure_auth.assert_called_once()

if __name__ == '__main__':
    unittest.main()
