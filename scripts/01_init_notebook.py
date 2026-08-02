import os
import sys
import yaml
import zipfile
import xml.etree.ElementTree as ET
from notebooklm_tools.cli.main import app

# 確保 stdout 為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def extract_epub_cover(book_path, output_cover_path):
    """
    從本地 EPUB 檔案解壓提取封面圖片並存為 output_cover_path
    如果解壓失敗或無封面，優雅 return False 且不砸毀流程
    """
    if not os.path.exists(book_path) or not book_path.lower().endswith(".epub"):
        return False

    try:
        with zipfile.ZipFile(book_path, 'r') as z:
            # 1. 讀取 META-INF/container.xml
            try:
                container_data = z.read('META-INF/container.xml')
                root = ET.fromstring(container_data)
                rootfile_path = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile').attrib['full-path']
            except Exception:
                rootfile_path = 'OEBPS/content.opf'

            # 2. 讀取 OPF 檔
            opf_data = z.read(rootfile_path)
            opf_dir = os.path.dirname(rootfile_path)
            opf_root = ET.fromstring(opf_data)

            # 尋找 cover image item
            cover_href = None
            manifest = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')
            if manifest is not None:
                for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                    item_id = item.attrib.get('id', '').lower()
                    properties = item.attrib.get('properties', '').lower()
                    if 'cover-image' in properties or 'cover' in item_id:
                        cover_href = item.attrib.get('href')
                        break

            if cover_href:
                img_zip_path = os.path.normpath(os.path.join(opf_dir, cover_href)).replace('\\', '/')
                img_data = z.read(img_zip_path)
                os.makedirs(os.path.dirname(output_cover_path), exist_ok=True)
                with open(output_cover_path, 'wb') as img_out:
                    img_out.write(img_data)
                print(f"✅ Successfully extracted EPUB cover to {output_cover_path}")
                return True
    except Exception as e:
        print(f"Notice: Could not extract cover from EPUB ({e}). Skipping cover.")
    return False

def init_notebook():
    config_path = os.path.join("config", "book_config.yaml")
    if not os.path.exists(config_path):
        print(f"Error: Config file {config_path} not found.")
        sys.exit(1)
        
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    notebook_id = config.get("notebook_id")
    rule_filename = config.get("rule_source_filename", "讀書報告核心概念.md")
    rule_source_path = os.path.join("source", rule_filename)
    book_local_path = config.get("book_local_path", "")
    
    if not notebook_id:
        print("Error: notebook_id is missing in config.")
        sys.exit(1)
        
    print(f"Initializing Notebook ID: {notebook_id}")

    # 嘗試解壓封面
    if book_local_path and os.path.exists(book_local_path):
        cover_out_path = os.path.join("final", "cover.jpg")
        extract_epub_cover(book_local_path, cover_out_path)
    
    # 檢查 Notebook 內的 Sources 清單
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
    except Exception as e:
        print(f"Warning: Failed to parse sources JSON. Output raw: {res_text[:200]}")
        
    rule_exists = False
    for s in sources:
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
