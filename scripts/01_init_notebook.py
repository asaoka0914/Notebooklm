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

def main():
    parser = argparse.ArgumentParser(description="Initialize NotebookLM source rules & local cover.")
    parser.add_argument("--notebook-id", help="NotebookLM notebook ID")
    parser.add_argument("--book-path", help="Path to local book file (EPUB/PDF)")
    args = parser.parse_args()

    config_path = os.path.join("config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    notebook_id = args.notebook_id or config.get("notebook_id")
    book_local_path = args.book_path or config.get("book_local_path", "")
    rule_filename = config.get("rule_source_filename", "讀書報告核心概念.md")
    rule_source_path = os.path.join("source", rule_filename)

    if not notebook_id:
        print("Error: notebook_id is missing in CLI args or config.")
        sys.exit(1)

    print(f"Initializing Notebook ID: {notebook_id}")

    if book_local_path and os.path.exists(book_local_path):
        cover_out_path = os.path.join("final", "cover.jpg")
        extract_epub_cover(book_local_path, cover_out_path)

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
    main()
