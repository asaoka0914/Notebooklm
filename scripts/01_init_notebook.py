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

def _split_paragraph_aligned(text: str, target_size: int) -> list:
    """
    依段落邊界（\\n\\n）切成接近 target_size 字元的大區塊。
    若段落內部存在遠大於 target_size 的巨型連續字串，
    則依固定字元長度並回探空格/標點邊界進行穩健切分。
    """
    raw_paragraphs = [p for p in text.split('\n\n') if p.strip()]
    paragraphs = []

    for p in raw_paragraphs:
        if len(p) > int(target_size * 1.5):
            # 針對巨型段落，以 target_size 回探自然邊界
            idx = 0
            p_len = len(p)
            while idx < p_len:
                if p_len - idx <= int(target_size * 1.2):
                    paragraphs.append(p[idx:].strip())
                    break
                # 在 [idx, idx + target_size] 區間尋找最佳切割點
                end_pos = idx + target_size
                # 優先在 end_pos 前方 500 字元內尋找標點或空格邊界
                search_start = max(idx, end_pos - 500)
                sub_slice = p[search_start:end_pos]
                
                # 尋找中文標點、英文句尾標點或空格
                split_offset = -1
                for m in re.finditer(r'([。！？\n]|(?:\.|\?|!)\s+|\s+)', sub_slice):
                    split_offset = m.end()
                
                if split_offset != -1:
                    cut_point = search_start + split_offset
                else:
                    cut_point = end_pos
                
                chunk_slice = p[idx:cut_point].strip()
                if chunk_slice:
                    paragraphs.append(chunk_slice)
                idx = cut_point
        else:
            paragraphs.append(p)

    chunks, current, current_len = [], [], 0
    for p in paragraphs:
        # 若單一段落本身就已接近或達到 target_size（例如經過巨型段落切分出的 sub_chunk）
        if len(p) >= int(target_size * 0.8):
            if current:
                # 若先前累積的內容很小（例如開頭短標題），合併到此大段落前方，不單獨成極小 chunk
                if current_len < int(target_size * 0.5):
                    chunks.append('\n\n'.join(current) + '\n\n' + p)
                    current, current_len = [], 0
                    continue
                else:
                    chunks.append('\n\n'.join(current))
                    current, current_len = [], 0
            chunks.append(p)
            continue

        current.append(p)
        current_len += len(p)
        if current_len >= target_size:
            chunks.append('\n\n'.join(current))
            current, current_len = [], 0
    if current:
        chunks.append('\n\n'.join(current))
    return chunks

def _extract_clean_first_phrase(chunk: str, max_len: int = 20) -> str:
    """
    從 chunk 內容中尋找第一句真實的正文，嚴格過濾 Markdown 圖片、URL、純符號與 HTML 標籤。
    所擷取的文字必須 100% 逐字存在於原文中，以利 NotebookLM RAG 與 QC 比對。
    若該 chunk 僅含圖片或 URL 等無效正文，則回傳空字串。
    """
    for raw_line in chunk.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        # 過濾包含 Markdown 圖片語法的行：![...](...)
        if re.search(r'!\[.*?\]\(.*?\)', line):
            continue
        # 過濾純 URL：http:// 或 https://
        if re.match(r'^https?://\S+$', line):
            continue
        # 過濾 Markdown 連結行：[title](url)
        if re.match(r'^\[.*?\]\(.*?\)$', line):
            continue
        # 過濾 HTML 標籤行
        if re.match(r'^<[^>]+>$', line):
            continue

        # 在行內尋找第一段合法的中文或英文字詞起始點
        m = re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', line)
        if m:
            start_idx = m.start()
            candidate = line[start_idx:start_idx + max_len].strip()
            # 若擷取後的片段仍包含圖片/網址前綴，則跳過本行
            if "![" in candidate or "http://" in candidate or "https://" in candidate:
                continue
            if candidate:
                return candidate

    return ""

def build_transcript_anchors(text_path: str, target_chunk_chars: int = 5000) -> list:
    """
    為逐字稿生成一份「章節標題」等效清單：每個元素都是逐字存在於原文中的錨點文字，
    可直接餵給既有的 chapters 陣列與 ground_truth_toc.json，不需另建新的資料結構。
    """
    with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    ts_pattern = re.compile(r'\d{1,2}:\d{2}:\d{2}')
    chunks = _split_paragraph_aligned(text, target_chunk_chars)
    anchors = []

    has_timestamps = len(ts_pattern.findall(text)) >= 5
    for chunk in chunks:
        if has_timestamps:
            m = ts_pattern.search(chunk)
            anchor = m.group(0) if m else _extract_clean_first_phrase(chunk, max_len=20)
        else:
            anchor = _extract_clean_first_phrase(chunk, max_len=20)
        if anchor and anchor not in anchors:
            anchors.append(anchor)

    return anchors

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
                # 優先順序 1: 具有 properties="cover-image" 的項目
                for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                    properties = item.attrib.get('properties', '').lower()
                    href = item.attrib.get('href', '').lower()
                    if 'cover-image' in properties and not href.endswith('.xhtml') and not href.endswith('.html'):
                        cover_href = item.attrib.get('href')
                        break

                # 優先順序 2: manifest 中 id 或 href 包含 cover 且排除 backcover/back_cover 的圖片
                if not cover_href:
                    for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                        item_id = item.attrib.get('id', '').lower()
                        href = item.attrib.get('href', '').lower()
                        if ('backcover' in item_id or 'back_cover' in item_id or 'backcover' in href or 'back_cover' in href):
                            continue
                        if ('cover' in item_id or 'cover' in href) and (href.endswith('.jpg') or href.endswith('.png') or href.endswith('.jpeg')):
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
                # 嘗試直接從 zip 搜尋 cover.jpg (排除 backcover)
                for name in z.namelist():
                    name_lower = name.lower()
                    if ('backcover' in name_lower or 'back_cover' in name_lower):
                        continue
                    if name_lower.endswith(('cover.jpg', 'cover.jpeg', 'cover.png')):
                        img_data = z.read(name)
                        os.makedirs(os.path.dirname(output_cover_path), exist_ok=True)
                        with open(output_cover_path, 'wb') as img_out:
                            img_out.write(img_data)
                        print(f"✅ Successfully extracted EPUB cover image from zip to {output_cover_path}")
                        return True
    except Exception as e:
        print(f"⚠️ Failed to extract EPUB cover: {e}")
    return False

def extract_epub_metadata(book_path):
    """從 EPUB 的 OPF 檔案中擷取作者 (creator)、書名 (title) 等元數據。若無 OPF 則從檔名提取。"""
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return {}
    meta = {}
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            opf_files = [f for f in z.namelist() if f.endswith('.opf')]
            if opf_files:
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

    # Fallback: 若無法從 OPF 取得書名，直接由檔案名稱解析（如 "書名 (作者).epub" -> "書名"）
    if not meta.get('title'):
        base_name = os.path.splitext(os.path.basename(book_path))[0]
        # 清理結尾括號中的作者名或附屬說明
        cleaned_title = re.sub(r'[\(（\[【].*?[\)）\]】]$', '', base_name).strip()
        meta['title'] = cleaned_title or base_name

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
    "Unit", "unit", "Lesson", "lesson", "法則", "夜", "卷", "節", "讲", "講", "堂", "課", "课", "Letters", "Letter"
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
    # 3. 符合巢狀小節標記（如 "1-1 誰需要理財教育？", "2-3 與優秀企業家同行", "Letter 1 ..."）
    if re.match(r'^(?:\d{1,2}[\-–—]\d{1,2}|Letters?\s*\d+)[\s.:：、\-\–]?[\u4e00-\u9fa5a-zA-Z]', text, re.IGNORECASE):
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
                    # XML parsing fallback: 採用 Python 內建 html.parser 遞迴解析殘破 HTML 與 a 標籤
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
    parser.add_argument("--source-type", choices=["book", "transcript"], default=None,
                        help="來源類型，預設沿用 config 既有值或 book")
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
    source_type = args.source_type or config.get("source_type", "book")
    config["source_type"] = source_type
    rule_filename = config.get("rule_source_filename", "讀書報告核心概念.md")
    candidate_rule_paths = [
        os.path.join(BASE_DIR, rule_filename),
        os.path.join(BASE_DIR, "plan", rule_filename),
        os.path.join(BASE_DIR, "source", rule_filename),
    ]
    rule_source_path = ""
    for cp in candidate_rule_paths:
        if os.path.exists(cp):
            rule_source_path = cp
            break
    if not rule_source_path:
        rule_source_path = os.path.join(BASE_DIR, "plan", rule_filename)

    # 擷取 EPUB 元數據（若有提供電子書檔）
    epub_meta = {}
    if book_local_path and os.path.exists(book_local_path):
        epub_meta = extract_epub_metadata(book_local_path)
        # 若 CLI 沒給 title，優先採用 EPUB 解析出之書名
        if args.title:
            book_title = args.title
        elif epub_meta.get("title"):
            book_title = epub_meta["title"]
        elif not book_title:
            base_name = os.path.splitext(os.path.basename(book_local_path))[0]
            book_title = re.sub(r'[\(（\[【].*?[\)）\]】]$', '', base_name).strip() or base_name

    if not book_title:
        print("❌ [Error] 無法確認書名！請透過 --title 指定書名，或提供有效的 --epub 電子書路徑。")
        sys.exit(1)

    # 檢查或自動建立 Notebook
    def _create_new_notebook(title_str):
        print(f"🚀 正在自動為《{title_str}》建立全新 NotebookLM 筆記本...")
        import io, json
        old_std = sys.stdout
        sys.stdout = buf = io.StringIO()
        try:
            app(["notebook", "create", title_str, "--json"])
        except SystemExit:
            pass
        finally:
            sys.stdout = old_std
        out_json = buf.getvalue()
        try:
            nb_data = json.loads(out_json)
            nid = nb_data.get("notebook_id")
            if nid:
                print(f"✅ 成功建立筆記本！Notebook ID: {nid}")
                return nid
        except Exception:
            pass
        # 若 JSON 解析失敗嘗試一般輸出 regex 擷取
        m = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', out_json)
        if m:
            nid = m.group(1)
            print(f"✅ 成功建立筆記本！Notebook ID: {nid}")
            return nid
        print("❌ 自動建立筆記本失敗，請確認網路與認證狀態。")
        sys.exit(1)

    # 檢驗現有 notebook_id 是否存在與可用
    def _is_notebook_valid(nid):
        if not nid:
            return False
        import io
        old_std = sys.stdout
        sys.stdout = buf = io.StringIO()
        try:
            app(["source", "list", nid, "--json"])
        except SystemExit:
            pass
        except Exception:
            return False
        finally:
            sys.stdout = old_std
        return "NOT_FOUND" not in buf.getvalue()

    # 若為不同書籍或目前 ID 無效，重置並建立新筆記本
    old_title = config.get("book_title", "")
    is_new_book = bool(book_title and old_title and book_title != old_title)

    if is_new_book or not notebook_id or not _is_notebook_valid(notebook_id):
        if is_new_book and notebook_id:
            print(f"🔄 檢測到新書籍（《{book_title}》vs 舊《{old_title}》），捨棄舊筆記本並建立專屬筆記本...")
        elif notebook_id:
            print(f"⚠️ 筆記本 ID [{notebook_id}] 無效或已被刪除，自動建立新筆記本...")
        notebook_id = _create_new_notebook(book_title)
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
        # 清除舊書的暫存摘要檔 (scratch/temp_book_summary.md)
        old_temp_summary = os.path.join(BASE_DIR, "scratch", "temp_book_summary.md")
        if os.path.exists(old_temp_summary):
            try:
                os.remove(old_temp_summary)
                print(f"  ✅ 已清除舊書暫存摘要：{old_temp_summary}")
            except Exception:
                pass
        # 清除舊的 failed_batches.json
        old_failed = os.path.join(BASE_DIR, "failed_batches.json")
        if os.path.exists(old_failed):
            try:
                os.remove(old_failed)
                print(f"  ✅ 已清除舊失敗批次記錄：{old_failed}")
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
    if source_type == "transcript":
        if not (book_local_path and os.path.exists(book_local_path)):
            print(f"❌ [Error] transcript 模式找不到指定檔案，請確認路徑是否存在：'{book_local_path}'（原生支援 .md, .txt 等純文字檔，請使用絕對路徑）")
            sys.exit(1)
        chunk_chars = config.get("transcript_chunk_chars", 5000)
        gt_chapters = build_transcript_anchors(book_local_path, target_chunk_chars=chunk_chars)
        default_batch_size = 1
    else:
        if book_local_path and os.path.exists(book_local_path):
            cover_out_dir = os.path.join(BASE_DIR, "final", book_title) if book_title else os.path.join(BASE_DIR, "final")
            cover_out_path = os.path.join(cover_out_dir, "cover.jpg")
            extract_epub_cover(book_local_path, cover_out_path)
            gt_chapters = extract_epub_toc(book_local_path)
        
        if not gt_chapters:
            raw_gt = discover_actual_toc(notebook_id)
            if raw_gt:
                gt_chapters = _parse_toc_response(raw_gt)
        default_batch_size = 2

    if gt_chapters:
        gt_json_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
        import json
        with open(gt_json_path, "w", encoding="utf-8") as gtf:
            json.dump({"total_chapters": len(gt_chapters), "chapters": gt_chapters}, gtf, ensure_ascii=False, indent=2)
        print(f"✅ Ground Truth TOC saved with {len(gt_chapters)} chapters to {gt_json_path}")

        # 自動根據章節清單生成預設批次策略，若 config 尚未設定批次或章節有變動則自動重新規劃
        current_batch_chapters = [ch for b in config.get("batch_strategy", {}).get("batches", []) for ch in b.get("chapters", [])]
        if "batch_strategy" not in config or not config["batch_strategy"].get("batches") or current_batch_chapters != gt_chapters:
            auto_batches = plan_batches(gt_chapters, batch_size=default_batch_size)
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

    # 1. 檢查並自動上傳核心概念規則檔
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

    # 2. 檢查並自動上傳電子書來源檔案 (EPUB/PDF)
    if book_local_path and os.path.exists(book_local_path):
        book_base_filename = os.path.basename(book_local_path)
        book_exists = False
        for s in sources:
            if isinstance(s, dict):
                title = s.get("title", "")
                if book_base_filename in title or (book_title and book_title in title):
                    book_exists = True
                    print(f"Found book source: {title} (ID: {s.get('id')})")
                    break
        if not book_exists:
            print(f"Book source not found in notebook. Uploading {book_local_path}...")
            try:
                app(["source", "add", notebook_id, "--file", book_local_path, "--wait"])
                print(f"✅ Successfully added book source: {book_base_filename}")
            except SystemExit:
                pass
            except Exception as e:
                print(f"⚠️ Failed to upload book source: {e}")
        else:
            print("Book source already present in notebook. Skipping upload.")

    # 自動將筆記本共用給帳號池中所有可用帳號，確保多帳號輪換時零障礙
    try:
        from _auth_pool import sync_notebook_collaborators
        print("Syncing notebook collaborators with auth pool accounts...")
        sync_notebook_collaborators(notebook_id)
    except Exception as sync_e:
        print(f"Notice: Collaborator sync skipped or failed ({sync_e})")

if __name__ == "__main__":
    init_notebook()
