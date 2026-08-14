import unittest
import os
import sys
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

if __name__ == '__main__':
    unittest.main()
