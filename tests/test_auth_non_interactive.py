import unittest
import os
import sys
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

from _auth_utils import _select_chrome_profile_interactive, switch_google_account_interactive

class TestAuthUtilsNonInteractive(unittest.TestCase):
    @patch('_auth_utils.list_chrome_profiles_with_email')
    @patch('sys.stdin.isatty', return_value=False)
    def test_select_chrome_profile_non_interactive_fallback(self, mock_isatty, mock_list_profiles):
        mock_list_profiles.return_value = [
            {'dir': 'Default', 'email': 'asaoka0914@gmail.com', 'name': 'Asaoka'},
            {'dir': 'Profile 1', 'email': 'work@nidec.com', 'name': 'Company'}
        ]
        result = _select_chrome_profile_interactive()
        self.assertEqual(result, 'Default', "非互動環境下應安全自動 fallback 到 Default profile 而不 crash")

    @patch('_auth_utils.list_chrome_profiles_with_email')
    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', side_effect=EOFError)
    def test_select_chrome_profile_eof_fallback(self, mock_input, mock_isatty, mock_list_profiles):
        mock_list_profiles.return_value = [
            {'dir': 'Default', 'email': 'asaoka0914@gmail.com', 'name': 'Asaoka'},
            {'dir': 'Profile 1', 'email': 'work@nidec.com', 'name': 'Company'}
        ]
        result = _select_chrome_profile_interactive()
        self.assertEqual(result, 'Default', "遇到 EOFError 時應安全 fallback 到 Default profile")

    @patch('_auth_utils.list_chrome_profiles_with_email')
    @patch('sys.stdin.isatty', return_value=False)
    def test_switch_google_account_non_interactive(self, mock_isatty, mock_list_profiles):
        mock_list_profiles.return_value = [
            {'dir': 'Default', 'email': 'asaoka0914@gmail.com', 'name': 'Asaoka'}
        ]
        result = switch_google_account_interactive()
        self.assertFalse(result, "非互動環境下應回傳 False 取消切換而非拋出例外")

if __name__ == '__main__':
    unittest.main()
