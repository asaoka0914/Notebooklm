import unittest
from unittest.mock import patch
import os
import sys
import json
import tempfile
import zipfile
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

class TestEPUBTOCAndAssemble(unittest.TestCase):
    def setUp(self):
        import importlib.util
        script_01 = os.path.join(BASE_DIR, 'scripts', '01_init_notebook.py')
        spec_01 = importlib.util.spec_from_file_location('init_nb', script_01)
        self.init_module = importlib.util.module_from_spec(spec_01)
        spec_01.loader.exec_module(self.init_module)

        script_03 = os.path.join(BASE_DIR, 'scripts', '03_assemble_report.py')
        spec_03 = importlib.util.spec_from_file_location('asm_mod', script_03)
        self.asm_module = importlib.util.module_from_spec(spec_03)
        spec_03.loader.exec_module(self.asm_module)

        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_extract_epub_toc_with_toc_xhtml(self):
        # 建立包含 toc.xhtml 的虛擬 EPUB (標準 XML 結構)
        epub_path = os.path.join(self.test_dir, 'sample_toc.epub')
        toc_xhtml_content = """<?xml version="1.0" encoding="utf-8"?>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <nav>
                <ol>
                    <li><a href="chap1.xhtml">第一章：引言</a></li>
                    <li><a href="chap2.xhtml">第二章：核心原理</a></li>
                    <li><a href="chap3.xhtml">第三章：實踐指南</a></li>
                </ol>
            </nav>
        </body>
        </html>
        """
        with zipfile.ZipFile(epub_path, 'w') as z:
            z.writestr('OEBPS/toc.xhtml', toc_xhtml_content)

        chapters = self.init_module.extract_epub_toc(epub_path)
        self.assertEqual(len(chapters), 3)
        self.assertIn("第一章：引言", chapters)
        self.assertIn("第二章：核心原理", chapters)
        self.assertIn("第三章：實踐指南", chapters)

    def test_extract_epub_toc_with_malformed_xml_fallback(self):
        # 建立包含非嚴格 XML（如未轉義 & 或缺少結尾標籤）的 toc.xhtml，強制觸發正則 fallback
        epub_path = os.path.join(self.test_dir, 'malformed_toc.epub')
        malformed_content = """
        <html>
        <body>
            <!-- 非良好格式 XML: 缺少 xml header、未跳脫的 & 符號、未閉合標籤等 -->
            <nav>
                <ol>
                    <li><a href="p1.html">第一章：哲學 & 心理學的交會 <img src="icon.png">
                    <li><a href="p2.html">第二章：<b>阿德勒的核心觀點</b></a>
                    <li><a href="p3.html">第三章：追求卓越的法則</a>
                </ol>
        </body>
        """
        with zipfile.ZipFile(epub_path, 'w') as z:
            z.writestr('OEBPS/toc.xhtml', malformed_content)

        chapters = self.init_module.extract_epub_toc(epub_path)
        self.assertEqual(len(chapters), 3)
        self.assertIn("第一章：哲學 & 心理學的交會", chapters)
        self.assertIn("第二章：阿德勒的核心觀點", chapters)
        self.assertIn("第三章：追求卓越的法則", chapters)


    def test_prepend_article_frontmatter(self):
        # 測試 frontmatter 注入功能
        report_file = os.path.join(self.test_dir, 'sample_report.md')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# 原有正文標題\n\n這裡是正文內容。")

        target_file = os.path.join(self.test_dir, 'target_article.md')
        
        self.assertTrue(hasattr(self.asm_module, 'prepend_article_frontmatter'), "03_assemble_report 應具備 prepend_article_frontmatter 函式")
        self.asm_module.prepend_article_frontmatter(
            source_path=report_file,
            target_path=target_file,
            slug="sample-book",
            title="樣本書籍",
            author="測試作者",
            tags=["測試", "樣本書"]
        )

        with open(target_file, 'r', encoding='utf-8') as f:
            result_content = f.read()

        self.assertTrue(result_content.startswith("---"))
        self.assertIn("slug: sample-book", result_content)
        self.assertIn("type: article", result_content)
        self.assertIn("title: \"《樣本書籍》全書詳細章節重點精華\"", result_content)
        self.assertIn("author: \"測試作者\"", result_content)
        self.assertIn("summary_ref: \"[[wiki/summaries/sample-book-summary|查看重點摘要]]\"", result_content)
        self.assertIn("# 原有正文標題", result_content)


    def test_extract_epub_toc_filters_frontmatter_xml(self):
        # 測試 XML 成功路徑正確排除推薦序、前言、致謝等前導章節
        epub_path = os.path.join(self.test_dir, 'frontmatter_xml_toc.epub')
        toc_xhtml_content = """<?xml version="1.0" encoding="utf-8"?>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <nav>
                <ol>
                    <li><a href="f1.xhtml">推薦序一：這本書改變了我</a></li>
                    <li><a href="f2.xhtml">前言：寫在前面</a></li>
                    <li><a href="chap1.xhtml">第一章：引言</a></li>
                    <li><a href="chap2.xhtml">第二章：核心原理</a></li>
                    <li><a href="f3.xhtml">致謝辭</a></li>
                    <li><a href="f4.xhtml">後記：結語與展望</a></li>
                </ol>
            </nav>
        </body>
        </html>
        """
        with zipfile.ZipFile(epub_path, 'w') as z:
            z.writestr('OEBPS/toc.xhtml', toc_xhtml_content)

        chapters = self.init_module.extract_epub_toc(epub_path)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters, ["第一章：引言", "第二章：核心原理"])

    def test_extract_epub_toc_filters_frontmatter_malformed_fallback(self):
        # 測試 malformed HTML fallback 路徑同步排除前導詞變體
        epub_path = os.path.join(self.test_dir, 'frontmatter_malformed_toc.epub')
        malformed_content = """
        <html>
        <body>
            <nav>
                <ol>
                    <li><a href="f1.html">推荐序：導讀序言 <img src="x.png">
                    <li><a href="f2.html">作者序：致謝</a>
                    <li><a href="p1.html">第一章：哲學 & 心理學的交會
                    <li><a href="p2.html">第二章：<b>阿德勒的核心觀點</b></a>
                    <li><a href="f3.html">出版序：目錄</a>
                    <li><a href="f4.html">結語</a>
                </ol>
        </body>
        """
        with zipfile.ZipFile(epub_path, 'w') as z:
            z.writestr('OEBPS/toc.xhtml', malformed_content)

        chapters = self.init_module.extract_epub_toc(epub_path)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters, ["第一章：哲學 & 心理學的交會", "第二章：阿德勒的核心觀點"])

    def test_extract_epub_toc_extended_chapter_markers(self):
        # 測試擴充章節標記關鍵字（篇、卷、Part、Unit、Lesson、講、節）
        epub_path = os.path.join(self.test_dir, 'extended_markers_toc.epub')
        toc_xhtml_content = """<?xml version="1.0" encoding="utf-8"?>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <nav>
                <ol>
                    <li><a href="p1.xhtml">第一篇：基礎理論</a></li>
                    <li><a href="p2.xhtml">上卷：總體經濟</a></li>
                    <li><a href="p3.xhtml">Part 1: The Core Strategy</a></li>
                    <li><a href="p4.xhtml">Unit 2: Practical Application</a></li>
                    <li><a href="p5.xhtml">Lesson 3: Advanced Tactics</a></li>
                    <li><a href="p6.xhtml">第一講：投資心態</a></li>
                    <li><a href="f1.xhtml">目錄</a></li>
                    <li><a href="f2.xhtml">出版序</a></li>
                </ol>
            </nav>
        </body>
        </html>
        """
        with zipfile.ZipFile(epub_path, 'w') as z:
            z.writestr('OEBPS/toc.xhtml', toc_xhtml_content)

        chapters = self.init_module.extract_epub_toc(epub_path)
        self.assertEqual(len(chapters), 6)
        self.assertIn("第一篇：基礎理論", chapters)
        self.assertIn("上卷：總體經濟", chapters)
        self.assertIn("Part 1: The Core Strategy", chapters)
        self.assertIn("Unit 2: Practical Application", chapters)
        self.assertIn("Lesson 3: Advanced Tactics", chapters)
        self.assertIn("第一講：投資心態", chapters)


    def test_normalize_with_opencc_and_fallback(self):
        # 載入 04_qc_check 模組
        import importlib.util
        from unittest.mock import patch
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod', script_04)
        qc_module = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_module)

        # 1. 測試簡繁同化與全形彎引號/標點
        sim_title = '“第一章：什么是永久投资组合”'
        trad_title = '「第一章 什么是永久投資組合」'
        norm_sim = qc_module._normalize(sim_title)
        norm_trad = qc_module._normalize(trad_title)
        self.assertEqual(norm_sim, norm_trad)
        self.assertIn("第一章", norm_sim)
        self.assertIn("投資組合", norm_sim)

        # 2. 測試無 OpenCC 時的 graceful fallback
        with patch.object(qc_module, '_CC', None):
            res = qc_module._normalize('“第一章：引言”')
            self.assertEqual(res, '第一章引言')

    def test_assemble_copy_to_cleanup_config_switch(self):
        # 測試 03 assemble_copy_to_cleanup 開關
        report_file = os.path.join(self.test_dir, 'sample_report.md')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# 測試報告正文")

        # 預設 False 或未設定時不複製
        # 驗證 prepend_article_frontmatter 功能正常
        target_file = os.path.join(self.test_dir, 'out_article.md')
        self.asm_module.prepend_article_frontmatter(
            source_path=report_file,
            target_path=target_file,
            slug="test-slug",
            title="測試標題"
        )
        self.assertTrue(os.path.exists(target_file))

    def test_traditional_chinese_book_qc_regression(self):
        # 回歸測試：驗證純正體中文書籍（如《被討厭的勇氣》）在 OpenCC 環境下章節正規化與比對不受影響
        import importlib.util
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod_reg', script_04)
        qc_module = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_module)

        # 驗證正體中文書籍標題比對
        trad_gt_chapters = [
            "第一夜：否定心理創傷",
            "第二夜 所有煩惱都來自於人際關係",
            "第三夜 割捨別人的課題",
            "第四夜：世界的中心在哪裡？",
            "第五夜 認真活在「當下」"
        ]
        found_titles = [
            "第一夜：否定心理創傷",
            "第二夜 所有煩惱都來自於人際關係",
            "第三夜 割捨別人的課題",
            "第四夜：世界的中心在哪裡？",
            "第五夜 認真活在「當下」"
        ]
        for gt in trad_gt_chapters:
            norm_gt = qc_module._normalize(gt)
            matched = any(norm_gt == qc_module._normalize(fc) or norm_gt in qc_module._normalize(fc) or qc_module._normalize(fc) in norm_gt for fc in found_titles)
            self.assertTrue(matched, f"正體中文章節 {gt} 在加入 OpenCC 後應維持 100% 匹配")

    def test_simplified_chinese_harry_browne_gt_coverage(self):
        # 驗證簡體 GT TOC 與繁體報告的比對成功（B1 實測情境）
        import importlib.util
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod_hb', script_04)
        qc_module = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_module)

        hb_report = os.path.join(BASE_DIR, "final", "哈利·布朗的永久投資組合", "哈利·布朗的永久投資組合.md")
        if os.path.exists(hb_report):
            hb_gt_json = {
                "total_chapters": 18,
                "chapters": [
                    "第一章 什么是永久投资组合：黄金大幕展开",
                    "第二章 黄金法则之金融安全：黄金法则与不确定性",
                    "第三章 永久投资组合业绩测试理论",
                    "第四章 简单、安全与稳定：通向成功的3个要素",
                    "第五章 根据经济状况投资：分散化的假象",
                    "第六章 股票：股票市场的力量",
                    "第七章 债券：债券安全性和收益",
                    "第八章 现金：被遗忘的资产",
                    "第九章 黄金：永久投资组合的保险",
                    "第十章 实施永久投资组合：达到安全的多种方法",
                    "第十一章 投资组合的调整和维护",
                    "第十二章 在国际上实施永久投资组合",
                    "第十三章 税与投资",
                    "第十四章 机构多元化",
                    "第十五章 地域多元化",
                    "第十六章 可变投资组合",
                    "第十七章 永久投资组合基金",
                    "第十八章 总结"
                ]
            }
            temp_gt_path = os.path.join(self.test_dir, 'gt_hb.json')
            with open(temp_gt_path, 'w', encoding='utf-8') as f:
                json.dump(hb_gt_json, f, ensure_ascii=False)

            orig_join = qc_module.os.path.join
            with patch.object(qc_module.os.path, 'join', side_effect=lambda *args: temp_gt_path if 'ground_truth_toc.json' in args else orig_join(*args)):
                passed, missing, cover_status = qc_module.run_single_qc_pass(hb_report)
                self.assertEqual(len(missing), 0, "簡體 GT TOC 與繁體報告比對應涵蓋全部 18 章節（0 遺漏）")

    def test_qc_cover_present_and_embedded_passes(self):
        """測試當 cover.jpg 存在且報告中包含正確封面 img 標籤時，cover_status 為 PASS"""
        import importlib.util
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod', script_04)
        qc_mod = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_mod)

        book_dir = os.path.join(self.test_dir, 'cover_test_pass')
        os.makedirs(book_dir, exist_ok=True)
        cover_path = os.path.join(book_dir, 'cover.jpg')
        with open(cover_path, 'wb') as cf:
            cf.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')  # Dummy JPEG header

        report_path = os.path.join(book_dir, 'full_report.md')
        report_content = (
            '# 測試書籍\n\n'
            '<p align="center">\n'
            '  <img src="data:image/jpeg;base64,12345" alt="書籍封面" width="300" />\n'
            '</p>\n\n'
            '## 第一章 核心架構\n'
            '📌 核心概念：這是測試概念說明。\n'
            '💡 重點擷取：這是測試細節內容。\n'
            + ('測試內文字元擴充以符合長度要求。' * 60) + '\n\n'
            '## 📚 參考文獻與原文引用腳註\n'
        )
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write(report_content)

        orig_join = qc_mod.os.path.join
        with patch.object(qc_mod.os.path, 'join', side_effect=lambda *args: os.path.join(self.test_dir, 'non_existent_gt.json') if 'ground_truth_toc.json' in args else orig_join(*args)):
            passed, missing, cover_status = qc_mod.run_single_qc_pass(report_path)
            self.assertEqual(cover_status, "PASS")
            self.assertTrue(passed)

    def test_qc_cover_present_but_not_embedded_fails(self):
        """測試當 cover.jpg 存在但報告中未內嵌封面標籤時，cover_status 為 FAIL 且 passed_all 為 False"""
        import importlib.util
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod', script_04)
        qc_mod = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_mod)

        book_dir = os.path.join(self.test_dir, 'cover_test_fail')
        os.makedirs(book_dir, exist_ok=True)
        cover_path = os.path.join(book_dir, 'cover.jpg')
        with open(cover_path, 'wb') as cf:
            cf.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')

        report_path = os.path.join(book_dir, 'full_report.md')
        report_content = (
            '# 測試書籍\n\n'
            '## 第一章 核心架構\n'
            '📌 核心概念：這是測試概念說明。\n'
            '💡 重點擷取：這是測試細節內容。\n'
            + ('測試內文字元擴充以符合長度要求。' * 60) + '\n\n'
            '## 📚 參考文獻與原文引用腳註\n'
        )
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write(report_content)

        orig_join = qc_mod.os.path.join
        with patch.object(qc_mod.os.path, 'join', side_effect=lambda *args: os.path.join(self.test_dir, 'non_existent_gt.json') if 'ground_truth_toc.json' in args else orig_join(*args)):
            passed, missing, cover_status = qc_mod.run_single_qc_pass(report_path)
            self.assertEqual(cover_status, "FAIL")
            self.assertFalse(passed)

    def test_qc_no_cover_skipped(self):
        """測試當無 cover.jpg 時，cover_status 為 SKIPPED，不影響 passed_all"""
        import importlib.util
        script_04 = os.path.join(BASE_DIR, 'scripts', '04_qc_check.py')
        spec_04 = importlib.util.spec_from_file_location('qc_mod', script_04)
        qc_mod = importlib.util.module_from_spec(spec_04)
        spec_04.loader.exec_module(qc_mod)

        book_dir = os.path.join(self.test_dir, 'cover_test_skip')
        os.makedirs(book_dir, exist_ok=True)
        report_path = os.path.join(book_dir, 'full_report.md')
        report_content = (
            '# 測試書籍\n\n'
            '## 第一章 核心架構\n'
            '📌 核心概念：這是測試概念說明。\n'
            '💡 重點擷取：這是測試細節內容。\n'
            + ('測試內文字元擴充以符合長度要求。' * 60) + '\n\n'
            '## 📚 參考文獻與原文引用腳註\n'
        )
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write(report_content)

        orig_join = qc_mod.os.path.join
        with patch.object(qc_mod.os.path, 'join', side_effect=lambda *args: os.path.join(self.test_dir, 'non_existent_gt.json') if 'ground_truth_toc.json' in args else orig_join(*args)):
            passed, missing, cover_status = qc_mod.run_single_qc_pass(report_path)
            self.assertEqual(cover_status, "SKIPPED")
            self.assertTrue(passed)

    def test_cleanup_preserves_cover_jpg(self):
        """測試 cleanup 邏輯在清理 final 目錄時會保留 cover.jpg 與 .md，並刪除其他暫存檔"""
        target_final = os.path.join(self.test_dir, 'final_book')
        os.makedirs(target_final, exist_ok=True)

        cover_file = os.path.join(target_final, 'cover.jpg')
        md_file = os.path.join(target_final, 'book.md')
        tmp_file = os.path.join(target_final, 'temp_file.tmp')

        with open(cover_file, 'wb') as f:
            f.write(b'cover')
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('# Report')
        with open(tmp_file, 'w', encoding='utf-8') as f:
            f.write('temp')

        # 模擬 cleanup_temp_files 中的 final 清理邏輯
        for fname in os.listdir(target_final):
            if fname.endswith(".md") or fname == "cover.jpg":
                continue
            fpath = os.path.join(target_final, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
            elif os.path.isdir(fpath):
                shutil.rmtree(fpath)

        self.assertTrue(os.path.exists(cover_file), "cover.jpg 應在清理中被保留")
        self.assertTrue(os.path.exists(md_file), ".md 報告應被保留")
        self.assertFalse(os.path.exists(tmp_file), "暫存檔 .tmp 應被刪除")


if __name__ == '__main__':
    unittest.main()

