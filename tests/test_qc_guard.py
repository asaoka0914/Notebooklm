import unittest
import os
import sys
import json
import tempfile
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

class TestQCGuardAndDependencies(unittest.TestCase):
    def setUp(self):
        import importlib.util
        script_path = os.path.join(BASE_DIR, 'scripts', '06_generate_book_summary.py')
        spec = importlib.util.spec_from_file_location('gen_summary', script_path)
        self.summary_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.summary_module)
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_qc_guard_fails_when_qc_status_missing(self):
        # 覆寫 BASE_DIR 測試無 qc_status.json 的情況
        original_base = self.summary_module.BASE_DIR
        try:
            self.summary_module.BASE_DIR = self.test_dir
            # 即使 report 存在，但沒有 qc_status.json 時必須 Hard-Fail
            book_title = "測試書籍A"
            final_dir = os.path.join(self.test_dir, 'final', book_title)
            os.makedirs(final_dir, exist_ok=True)
            with open(os.path.join(final_dir, f"{book_title}.md"), "w", encoding="utf-8") as f:
                f.write("# 測試內容")

            can_run = self.summary_module.check_qc_prerequisite(book_title)
            self.assertFalse(can_run, "當 qc_status.json 不存在時必須回傳 False (Hard-Fail)")
        finally:
            self.summary_module.BASE_DIR = original_base

    def test_qc_guard_fails_on_title_mismatch(self):
        # 測試 qc_status.json 中的 book_title 與當前檢查目標不符時攔截
        original_base = self.summary_module.BASE_DIR
        try:
            self.summary_module.BASE_DIR = self.test_dir
            book_title_a = "測試書籍A"
            book_title_b = "測試書籍B"
            
            final_dir_b = os.path.join(self.test_dir, 'final', book_title_b)
            os.makedirs(final_dir_b, exist_ok=True)
            with open(os.path.join(final_dir_b, f"{book_title_b}.md"), "w", encoding="utf-8") as f:
                f.write("# 測試內容B")

            # 寫入書籍 A 通過的 qc_status
            with open(os.path.join(self.test_dir, "qc_status.json"), "w", encoding="utf-8") as f:
                json.dump({"passed_all": True, "book_title": book_title_a}, f)

            can_run = self.summary_module.check_qc_prerequisite(book_title_b)
            self.assertFalse(can_run, "當 qc_status.json 書名不匹配時必須回傳 False")
        finally:
            self.summary_module.BASE_DIR = original_base

    def test_qc_guard_passes_when_title_and_status_match(self):
        original_base = self.summary_module.BASE_DIR
        try:
            self.summary_module.BASE_DIR = self.test_dir
            book_title = "測試書籍A"
            
            final_dir = os.path.join(self.test_dir, 'final', book_title)
            os.makedirs(final_dir, exist_ok=True)
            with open(os.path.join(final_dir, f"{book_title}.md"), "w", encoding="utf-8") as f:
                f.write("# 測試內容A")

            with open(os.path.join(self.test_dir, "qc_status.json"), "w", encoding="utf-8") as f:
                json.dump({"passed_all": True, "book_title": book_title}, f)

            can_run = self.summary_module.check_qc_prerequisite(book_title)
            self.assertTrue(can_run, "當書名與 passed_all 均符合且報告存在時應回傳 True")
        finally:
            self.summary_module.BASE_DIR = original_base

if __name__ == '__main__':
    unittest.main()
