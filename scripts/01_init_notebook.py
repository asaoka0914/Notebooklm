import os
import sys
import argparse
import yaml
import zipfile
import xml.etree.ElementTree as ET
from notebooklm_tools.cli.main import app

sys.stdout.reconfigure(encoding='utf-8')

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

def extract_epub_toc(book_path):
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return []
    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            toc_files = [f for f in z.namelist() if f.endswith('.ncx') or 'nav' in f.lower()]
            chapters = []
            for tf in toc_files:
                content = z.read(tf)
                root = ET.fromstring(content)
                for elem in root.iter():
                    text = elem.text.strip() if elem.text else ""
                    if text and ("章" in text or "Chapter" in text or "法則" in text):
                        if text not in chapters:
                            chapters.append(text)
            return chapters
    except Exception as e:
        print(f"Notice: EPUB TOC parsing error: {e}")
    return []

def discover_actual_toc(notebook_id):
    """Query NotebookLM with a fresh isolated UUID to discover real chapter list."""
    import uuid
    from notebooklm_tools.services.auth import AuthManager
    from notebooklm_tools.core.client import NotebookLMClient
    
    auth = AuthManager()
    profile = auth.load_profile()
    client = NotebookLMClient(cookies=profile.cookies, csrf_token=profile.csrf_token, session_id=profile.session_id)
    fresh_conv_id = str(uuid.uuid4())
    prompt = (
        "請僅依據來源書籍本身的實際內容（不要包含附錄、注釋、參考書目等非正文部分），"
        "列出這本書「正文」的完整章節目錄清單，格式為：\n"
        "第X章：章節標題\n"
        "請勿自行推測或延伸不存在的章節，如果全書只到第 N 章，請明確只列出 N 個項目，"
        "並在最後一行註明：「總章節數：N」。"
    )
    res = client.query(notebook_id, prompt, conversation_id=fresh_conv_id)
    return res.get("answer", "") if res else ""

from _auth_utils import ensure_auth

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def init_notebook():
    if not ensure_auth():
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Initialize NotebookLM source rules & local cover.")
    parser.add_argument("--notebook-id", help="NotebookLM notebook ID")
    parser.add_argument("--book-path", help="Path to local book file (EPUB/PDF)")
    parser.add_argument("--title", help="Book title")
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

    if not notebook_id:
        print("Error: notebook_id is missing in CLI args or config.")
        sys.exit(1)

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
            for line in raw_gt.split('\n'):
                line_str = line.strip()
                if line_str and ("章" in line_str or "Chapter" in line_str or "法則" in line_str):
                    gt_chapters.append(line_str)

    if gt_chapters:
        gt_json_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
        import json
        with open(gt_json_path, "w", encoding="utf-8") as gtf:
            json.dump({"total_chapters": len(gt_chapters), "chapters": gt_chapters}, gtf, ensure_ascii=False, indent=2)
        print(f"✅ Ground Truth TOC saved with {len(gt_chapters)} chapters to {gt_json_path}")

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

if __name__ == "__main__":
    init_notebook()
