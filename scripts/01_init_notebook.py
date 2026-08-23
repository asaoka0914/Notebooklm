import os
import sys
import re
import argparse
import yaml
import zipfile
import xml.etree.ElementTree as ET
from notebooklm_tools.cli.main import app

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout.reconfigure(encoding='utf-8')

def plan_batches(chapters: list, batch_size: int = 2) -> list:
    """
    規劃批次清單並執行防重疊驗證。
    每批至多 batch_size 章，且嚴格禁止不同批次之間存在重複章節。
    """
    if not chapters:
        return []
    
    batches = []
    seen = set()
    total = len(chapters)
    batch_idx = 1

    for i in range(0, total, batch_size):
        chunk = chapters[i:i + batch_size]
        # 檢查 chunk 內部與全域是否重疊
        overlap = seen.intersection(set(chunk))
        if overlap:
            raise ValueError(f"批次規劃發現重疊章節：{overlap}，請檢查章節目錄來源！")
        for ch in chunk:
            seen.add(ch)
        batches.append({
            "batch": batch_idx,
            "chapters": chunk
        })
        batch_idx += 1

    return batches

def extract_epub_cover(book_path, output_cover_path):
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return False
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            try:
                container_data = z.read('META-INF/container.xml')
                root = ET.fromstring(container_data)
                rootfile_path = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile').attrib['full-path']
            except Exception:
                rootfile_path = 'OEBPS/content.opf'

            opf_data = z.read(rootfile_path)
            opf_dir = os.path.dirname(rootfile_path)
            opf_root = ET.fromstring(opf_data)

            cover_href = None
            manifest = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')
            if manifest is not None:
                for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                    item_id = item.attrib.get('id', '').lower()
                    properties = item.attrib.get('properties', '').lower()
                    if 'cover-image' in properties or 'cover' in item_id:
                        cover_href = item.attrib.get('href')
                        break

            if cover_href and not cover_href.endswith('.xhtml') and not cover_href.endswith('.html'):
                img_zip_path = os.path.normpath(os.path.join(opf_dir, cover_href)).replace('\\', '/')
                img_data = z.read(img_zip_path)
                os.makedirs(os.path.dirname(output_cover_path), exist_ok=True)
                with open(output_cover_path, 'wb') as img_out:
                    img_out.write(img_data)
                print(f"✅ Successfully extracted EPUB cover to {output_cover_path}")
                return True
            else:
                # 嘗試直接從 manifest 找 image/cover.jpg
                for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                    href = item.attrib.get('href', '')
                    if ('cover' in href.lower() or 'cover' in item.attrib.get('id', '').lower()) and (href.endswith('.jpg') or href.endswith('.png') or href.endswith('.jpeg')):
                        img_zip_path = os.path.normpath(os.path.join(opf_dir, href)).replace('\\', '/')
                        img_data = z.read(img_zip_path)
                        os.makedirs(os.path.dirname(output_cover_path), exist_ok=True)
                        with open(output_cover_path, 'wb') as img_out:
                            img_out.write(img_data)
                        print(f"✅ Successfully extracted EPUB cover image to {output_cover_path}")
                        return True
    except Exception as e:
        print(f"⚠️ Failed to extract EPUB cover: {e}")
    return False

def extract_epub_metadata(book_path):
    """從 EPUB 的 OPF 檔案中擷取作者 (creator)、書名 (title) 等元數據。"""
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return {}
    meta = {}
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            opf_files = [f for f in z.namelist() if f.endswith('.opf')]
            if not opf_files:
                return {}
            content = z.read(opf_files[0])
            root = ET.fromstring(content)
            
            # 擷取作者 (dc:creator)
            creators = []
            for elem in root.findall('.//{http://purl.org/dc/elements/1.1/}creator'):
                if elem.text and elem.text.strip():
                    creators.append(elem.text.strip())
            if creators:
                meta['author'] = ', '.join(creators)
                
            # 擷取書名 (dc:title)
            titles = []
            for elem in root.findall('.//{http://purl.org/dc/elements/1.1/}title'):
                if elem.text and elem.text.strip():
                    titles.append(elem.text.strip())
            if titles:
                meta['title'] = titles[0]
    except Exception as e:
        print(f"⚠️ Failed to extract EPUB metadata: {e}")
    return meta

FRONTMATTER_KEYWORDS = (
    "封面", "推薦序", "推荐序", "前言", "致謝", "致谢",
    "序言", "緒論", "作者序", "譯者序", "出版序",
    "後記", "结语", "結語", "目錄", "目录", "Table of Contents",
)

def _is_frontmatter(text: str) -> bool:
    return any(kw in text for kw in FRONTMATTER_KEYWORDS)

CHAPTER_MARKERS = (
    "章", "Chapter", "chapter", "篇", "Part", "part", "PART",
    "Unit", "unit", "Lesson", "lesson", "法則", "夜", "卷", "節", "讲", "講", "堂", "課", "课"
)

def _is_chapter_candidate(text: str) -> bool:
    if not text or _is_frontmatter(text):
        return False
    # 1. 包含章節關鍵標記
    if any(marker in text for marker in CHAPTER_MARKERS):
        return True
    # 2. 符合「數字 + 標點/空格 + 標題」格式（如 "1 理財要分身有術", "01. 基礎入門"）
    if re.match(r'^(?:\d{1,3}|[一二三四五六七八九十百]+)[\s.:：、\-\–][\u4e00-\u9fa5a-zA-Z]', text):
        return True
    return False


def extract_epub_toc(book_path):
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return []
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            toc_files = [f for f in z.namelist() if f.endswith('.ncx') or 'nav' in f.lower() or 'toc' in f.lower()]
            chapters = []
            for tf in toc_files:
                try:
                    content = z.read(tf)
                    root = ET.fromstring(content)
                    for elem in root.iter():
                        # 擷取 element text 或 tail text
                        text = (elem.text or "").strip()
                        if _is_chapter_candidate(text):
                            if text not in chapters:
                                chapters.append(text)
                except Exception as inner_e:
                    # XML parsing fallback: 優先採用 Python 內建 html.parser 解析殘破 HTML，其次退回 Lookahead 正則
                    try:
                        raw_str = content.decode('utf-8', errors='ignore')
                        from html.parser import HTMLParser
                        class TOCHTMLParser(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.in_a = False
                                self.current_text = []
                                self.extracted = []
                            def handle_starttag(self, tag, attrs):
                                if tag.lower() == 'a':
                                    self.in_a = True
                                    self.current_text = []
                                elif tag.lower() in ('li', 'ol', 'ul', 'nav', 'p', 'div', 'tr') and self.in_a:
                                    # 遇到容器標籤但 <a> 未閉合，自動截斷前一個 <a>
                                    txt = "".join(self.current_text).strip()
                                    if txt:
                                        self.extracted.append(txt)
                                    self.in_a = False
                                    self.current_text = []
                            def handle_endtag(self, tag):
                                if tag.lower() == 'a' and self.in_a:
                                    txt = "".join(self.current_text).strip()
                                    if txt:
                                        self.extracted.append(txt)
                                    self.in_a = False
                                    self.current_text = []
                            def handle_data(self, data):
                                if self.in_a:
                                    self.current_text.append(data)

                        parser = TOCHTMLParser()
                        parser.feed(raw_str)
                        if parser.in_a:
                            txt = "".join(parser.current_text).strip()
                            if txt:
                                parser.extracted.append(txt)

                        candidates = parser.extracted
                        if not candidates:
                            # 備用正則：限制在標籤邊界內不跨越下個 <li>/<nav>/<ol>
                            candidates = re.findall(r'<a[^>]*>(.*?)(?:</a>|(?=\s*<li|\s*</li|\s*</ol|\s*</ul|\s*</nav|\Z))', raw_str, flags=re.DOTALL | re.IGNORECASE)

                        for m in candidates:
                            clean_m = re.sub(r'<[^>]+>', '', m).strip()
                            clean_m = re.sub(r'\s+', ' ', clean_m)
                            if _is_chapter_candidate(clean_m):
                                if clean_m not in chapters:
                                    chapters.append(clean_m)
                    except Exception:
                        pass
            return chapters
    except Exception as e:
        print(f"Notice: EPUB TOC parsing error: {e}")
    return []

def discover_actual_toc(notebook_id):
    """Query NotebookLM with a fresh isolated UUID to discover real chapter list, requesting strict JSON output."""
    import uuid
    from notebooklm_tools.services.auth import AuthManager
    from notebooklm_tools.core.client import NotebookLMClient

    auth = AuthManager()
    profile = auth.load_profile()
    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
    fresh_conv_id = str(uuid.uuid4())
    prompt = (
        "請僅依據來源書籍本身的實際內容（不要包含附錄、注釋、參考書目、推薦序等非正文部分），"
        "列出這本書「正文」的完整章節目錄清單。\n"
        "請「只」輸出一個合法 JSON 陣列，不要有任何前言、說明文字、Markdown code fence 或其他內容，"
        "格式範例：[\"第1章 xxx\", \"第2章 xxx\", \"Part 1: xxx\"]\n"
        "請保留書中原本的章節命名方式（可能是「第X章」「Chapter X」「Part X」「Unit X」或純標題），"
        "不要自行套用固定格式硬改章節名稱。"
        "請勿自行推測或延伸不存在的章節，如果全書只到第 N 章，請明確只列出 N 個項目。"
    )
    res = client.query(notebook_id, prompt, conversation_id=fresh_conv_id)
    return res.get("answer", "") if res else ""

def _parse_toc_response(raw_gt):
    """優先嘗試解析 JSON 陣列，失敗則退回關鍵字逐行過濾（保留原本的相容性）。"""
    import json, re

    # 1. 嘗試直接解析（可能夾雜 code fence，先剝除）
    cleaned = raw_gt.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return [x.strip() for x in parsed if x.strip()]
    except Exception:
        pass

    # 2. JSON 解析失敗，退回原本的關鍵字過濾（使用統一的 CHAPTER_MARKERS 集合）
    chapters = []
    for line in raw_gt.split('\n'):
        line_str = line.strip()
        if _is_chapter_candidate(line_str):
            chapters.append(line_str)
    return chapters

from _auth_utils import ensure_auth_with_pool

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def init_notebook():
    if not ensure_auth_with_pool():
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Initialize NotebookLM source rules & local cover.")
    parser.add_argument("--notebook-id", help="NotebookLM notebook ID")
    parser.add_argument("--book-path", "--epub", dest="book_path", help="Path to local book file (EPUB/PDF)")
    parser.add_argument("--title", help="Book title")
    parser.add_argument("--author", help="Book author")
    parser.add_argument("--output-dir", help="Optional output directory")
    parser.add_argument("--relogin", action="store_true", help="Clear localized session and force Chrome login before running.")
    args = parser.parse_args()

    if args.relogin:
        print("🚀 [Relogin] 正在清除舊 Session 並彈出 Chrome 瀏覽器登入新 Google 帳號...")
        try:
            app(['login', '--clear', '--force'])
            print("✅ 新帳號登入完成！繼續執行初始化...\n")
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            sys.exit(1)

    config_path = os.path.join(BASE_DIR, "config", "book_config.yaml")
    template_path = os.path.join(BASE_DIR, "config", "book_config.yaml.template")
    if not os.path.exists(config_path) and os.path.exists(template_path):
        import shutil
        shutil.copy2(template_path, config_path)
        print(f"Notice: Created initial {config_path} from template.")

    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    notebook_id = args.notebook_id or config.get("notebook_id")
    book_local_path = args.book_path or config.get("book_local_path", "")
    book_title = args.title or config.get("book_title", "")
    rule_filename = config.get("rule_source_filename", "讀書報告核心概念.md")
    rule_source_path = os.path.join(BASE_DIR, rule_filename)
    if not os.path.exists(rule_source_path):
        rule_source_path = os.path.join(BASE_DIR, "source", rule_filename)

    # 擷取 EPUB 元數據（若有提供電子書檔）
    epub_meta = {}
    if book_local_path and os.path.exists(book_local_path):
        epub_meta = extract_epub_metadata(book_local_path)
        if not book_title and epub_meta.get("title"):
            book_title = epub_meta["title"]

    if not notebook_id:
        print("Error: notebook_id is missing in CLI args or config.")
        sys.exit(1)

    # 檢測是否為不同書籍，若更換書名則自動清除舊的 ground_truth_toc 與 qc_status 殘留
    old_title = config.get("book_title", "")
    is_new_book = bool(book_title and old_title and book_title != old_title)
    if is_new_book:
        print(f"🔄 檢測到新書籍（《{book_title}》vs 舊《{old_title}》），重置舊書狀態快取...")
        gt_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
        if os.path.exists(gt_path):
            try:
                os.remove(gt_path)
                print(f"  ✅ 已清除舊目錄基準：{gt_path}")
            except Exception:
                pass
        qc_path = os.path.join(BASE_DIR, "qc_status.json")
        if os.path.exists(qc_path):
            try:
                os.remove(qc_path)
                print(f"  ✅ 已清除舊 QC 狀態：{qc_path}")
            except Exception:
                pass
        # 若是新書，清空舊的批次配置以觸發重新生成
        if "batch_strategy" in config:
            config["batch_strategy"]["batches"] = []

    # 處理作者資訊：CLI 指定 > EPUB 元數據 > 新書清空 > 維持既有
    if args.author:
        config["author"] = args.author
        print(f"✅ 設定作者（CLI 指定）：{config['author']}")
    elif epub_meta.get("author"):
        config["author"] = epub_meta["author"]
        print(f"✅ 自動從 EPUB 元數據擷取作者：{config['author']}")
    elif is_new_book:
        config["author"] = ""
        print("ℹ️ 新書籍未指定作者，已清除前一本書之作者資訊。")

    print(f"Initializing Notebook ID: {notebook_id}")

    # 解析並儲存 Ground Truth TOC json
    gt_chapters = []
    if book_local_path and os.path.exists(book_local_path):
        cover_out_dir = os.path.join(BASE_DIR, "final", book_title) if book_title else os.path.join(BASE_DIR, "final")
        cover_out_path = os.path.join(cover_out_dir, "cover.jpg")
        extract_epub_cover(book_local_path, cover_out_path)
        gt_chapters = extract_epub_toc(book_local_path)
    
    if not gt_chapters:
        raw_gt = discover_actual_toc(notebook_id)
        if raw_gt:
            gt_chapters = _parse_toc_response(raw_gt)

    if gt_chapters:
        gt_json_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
        import json
        with open(gt_json_path, "w", encoding="utf-8") as gtf:
            json.dump({"total_chapters": len(gt_chapters), "chapters": gt_chapters}, gtf, ensure_ascii=False, indent=2)
        print(f"✅ Ground Truth TOC saved with {len(gt_chapters)} chapters to {gt_json_path}")

        # 自動根據章節清單生成預設批次策略（每 2 章一組），若 config 尚未設定批次則自動注入
        if "batch_strategy" not in config or not config["batch_strategy"].get("batches"):
            auto_batches = plan_batches(gt_chapters, batch_size=2)
            if "batch_strategy" not in config:
                config["batch_strategy"] = {}
            config["batch_strategy"]["batches"] = auto_batches
            if "batch_delay_seconds" not in config["batch_strategy"]:
                config["batch_strategy"]["batch_delay_seconds"] = 8
            print(f"✅ 自動生成 {len(auto_batches)} 個批次策略")

    # 回寫最新設定至 config_path
    config["notebook_id"] = notebook_id
    if book_local_path:
        config["book_local_path"] = book_local_path
    if book_title:
        config["book_title"] = book_title
    with open(config_path, "w", encoding="utf-8") as cwf:
        yaml.dump(config, cwf, allow_unicode=True, sort_keys=False)
    print(f"✅ 書籍配置已更新至 {config_path}")

    print("Checking existing sources in notebook...")
    import io
    import json
    
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        app(["source", "list", notebook_id, "--json"])
    except SystemExit:
        pass
    finally:
        sys.stdout = old_stdout

    res_text = buffer.getvalue()
    sources = []
    try:
        sources = json.loads(res_text)
    except Exception:
        pass

    rule_exists = False
    for s in sources:
        if isinstance(s, dict):
            title = s.get("title", "")
            if "讀書報告核心概念" in title or rule_filename in title:
                rule_exists = True
                print(f"Found rule source: {title} (ID: {s.get('id')})")
                break

    if not rule_exists:
        print(f"Rule source not found. Uploading {rule_source_path}...")
        if not os.path.exists(rule_source_path):
            print(f"Error: Source file {rule_source_path} does not exist.")
            sys.exit(1)
        try:
            app(["source", "add", notebook_id, "--file", rule_source_path, "--wait"])
            print("Successfully added rule source!")
        except SystemExit:
            pass
    else:
        print("Rule source already present in notebook. Skipping upload.")

    # 自動將筆記本共用給帳號池中所有可用帳號，確保多帳號輪換時零障礙
    try:
        from _auth_pool import sync_notebook_collaborators
        print("Syncing notebook collaborators with auth pool accounts...")
        sync_notebook_collaborators(notebook_id)
    except Exception as sync_e:
        print(f"Notice: Collaborator sync skipped or failed ({sync_e})")

if __name__ == "__main__":
    init_notebook()
