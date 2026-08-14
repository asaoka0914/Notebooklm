import unittest
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

class TestGenerateBookSummary(unittest.TestCase):
    def test_summary_prompt_structure(self):
        import importlib.util
        script_path = os.path.join(BASE_DIR, 'scripts', '06_generate_book_summary.py')
        spec = importlib.util.spec_from_file_location('gen_summary', script_path)
        summary_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(summary_module)
        
        prompt = summary_module.build_book_summary_prompt('測試書名', '測試作者')
        self.assertIn('一、全書 TL;DR', prompt)
        self.assertIn('二、核心心智模型與底層理論', prompt)
        self.assertIn('三、全書邏輯架構與論證脈絡', prompt)
        self.assertIn('四、實踐清單與行動法則', prompt)
        self.assertIn('五、經典案例、反直覺洞見與金句', prompt)
        self.assertIn('六、Obsidian 概念關聯與延伸閱讀', prompt)

    def test_qc_dependency_check(self):
        import importlib.util
        script_path = os.path.join(BASE_DIR, 'scripts', '06_generate_book_summary.py')
        spec = importlib.util.spec_from_file_location('gen_summary', script_path)
        summary_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(summary_module)
        
        can_run = summary_module.check_qc_prerequisite('non_existent_book_title')
        self.assertFalse(can_run)

    def test_assemble_report_core_split(self):
        import importlib.util
        script_path = os.path.join(BASE_DIR, 'scripts', '03_assemble_report.py')
        spec = importlib.util.spec_from_file_location('asm_mod', script_path)
        asm_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(asm_mod)
        self.assertTrue(hasattr(asm_mod, 'assemble_report_core'))
        self.assertTrue(callable(asm_mod.assemble_report_core))

if __name__ == '__main__':
    unittest.main()
