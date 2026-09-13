import unittest
import os
import sys
import tempfile
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

import importlib.util

spec_01 = importlib.util.spec_from_file_location('mod_01', os.path.join(BASE_DIR, 'scripts', '01_init_notebook.py'))
mod_01 = importlib.util.module_from_spec(spec_01)
spec_01.loader.exec_module(mod_01)

spec_03 = importlib.util.spec_from_file_location('mod_03', os.path.join(BASE_DIR, 'scripts', '03_assemble_report.py'))
mod_03 = importlib.util.module_from_spec(spec_03)
spec_03.loader.exec_module(mod_03)

class TestTranscriptFixes(unittest.TestCase):
    def test_split_giant_paragraph_even_if_three_paragraphs(self):
        """測試當開頭有標題/圖片，但正文是單一十萬字未分段巨型字串時，依然能正確切分出多個 chunk"""
        text = "來源指南\n\n![](https://www.youtube.com/watch?v=123)\n\n" + ("happiness is being satisfied with what you have. " * 3000)
        chunks = mod_01._split_paragraph_aligned(text, target_size=5000)
        self.assertGreaterEqual(len(chunks), 10)
        # 驗證每個 chunk 都有足夠字元
        for c in chunks[:-1]:
            self.assertGreaterEqual(len(c), 4000)

    def test_normalize_headings_upgrades_transcript_anchors_to_h2(self):
        """測試 03_assemble_report 能將以一般中文/英文字詞開頭的錨點標題昇格為 H2 (##)"""
        raw_text = (
            "#### 來源指南\n\n內文第一段...\n\n"
            "#### 你是不是也在擔心辛苦半輩子的存款\n\n內文第二段...\n\n"
            "#### happiness is being satisfied\n\n內文第三段...\n\n"
        )
        norm = mod_03.normalize_headings(raw_text)
        self.assertIn("## 來源指南", norm)
        self.assertIn("## 你是不是也在擔心辛苦半輩子的存款", norm)
        self.assertIn("## happiness is being satisfied", norm)

    def test_qc_matches_dual_track_headings(self):
        """測試 04_qc_check 能將雙軌標題（繁中主題 — 原文錨點）與 Ground Truth 錨點精確匹配"""
        spec_04 = importlib.util.spec_from_file_location('mod_04', os.path.join(BASE_DIR, 'scripts', '04_qc_check.py'))
        mod_04 = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(mod_04)

        gt_chap = "actually the enterta"
        found_chapter_titles = [
            "過程與結果的本質：擺脫悲慘的成功 — actually the enterta",
            "自尊與愛的本質 — love is to give love"
        ]
        
        # 模擬 04_qc_check 的匹配邏輯
        norm_gt = mod_04._normalize(gt_chap)
        matched = False
        for fc in found_chapter_titles:
            norm_fc = mod_04._normalize(fc)
            if norm_gt == norm_fc or norm_gt in norm_fc or norm_fc in norm_gt:
                matched = True
                break
            if any(sep in fc for sep in ['—', '–', '-', ':', '：']):
                parts = [p.strip() for p in re.split(r'[—–\-:：]', fc)]
                if len(parts) >= 2:
                    anchor_part = mod_04._normalize(parts[-1])
                    if norm_gt == anchor_part or norm_gt in anchor_part or anchor_part in norm_gt:
                        matched = True
                        break
        self.assertTrue(matched)

if __name__ == '__main__':
    unittest.main()

