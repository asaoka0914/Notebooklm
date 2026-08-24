import os
import sys
import re
import json
import argparse
import yaml

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MAX_RETRY_BATCH = 3

# 模組層級安全匯入與初始化 OpenCC（只初始化一次，避免每次 QC 比對或 backfill pass 重複載入字典表）
try:
    import opencc
    _CC = opencc.OpenCC('s2t')  # 簡→繁
except Exception:
    _CC = None
    print("⚠️ [Notice] 未偵測到 opencc 套件，QC 比對將略過簡繁同化（建議執行 pip install opencc-python-reimplemented）。")

def _normalize(s):
    """將文字進行繁簡同化、數字同化（阿拉伯數字轉中文數字）並移除常見標點符號，徹底解決第1章 vs 第一章格式不匹配。"""
    if _CC is not None:
        try:
            s = _CC.convert(s)  # 先同化為繁體
        except Exception:
            pass
    # 阿拉伯數字轉中文數字同化 (第 1 章 -> 第一章, 1 -> 一)
    num_map = {
        '10': '十', '11': '十一', '12': '十二', '13': '十三', '14': '十四', '15': '十五',
        '16': '十六', '17': '十七', '18': '十八', '19': '十九', '20': '二十',
        '1': '一', '2': '二', '3': '三', '4': '四', '5': '五',
        '6': '六', '7': '七', '8': '八', '9': '九', '0': '零'
    }
    # 替換 "第 N 章" 為 "第 中文數字 章"
    def _rep_num(m):
        n = m.group(1)
        return f"第{num_map.get(n, n)}章"
    s = re.sub(r'第\s*(\d{1,2})\s*章', _rep_num, s)

    return re.sub(r'[\s:："\u2018\u2019\u201c\u201d\'\.,;!?、《》【】「」()\(\)\-_–—]', '', s)

def detect_duplicate_chapters(headings):
    """檢測章節標題清單中是否存在重複（基於標準化比對）"""
    seen = {}
    duplicates = []
    for h in headings:
        norm = _normalize(h)
        if not norm:
            continue
        if norm in seen:
            duplicates.append((seen[norm], h))
        else:
            seen[norm] = h
    return duplicates

def run_single_qc_pass(report_path):
    """執行單次 QC 比對檢查，回傳 (passed_all, missing_chapters, cover_status)"""
    failed_path = os.path.join(BASE_DIR, "failed_batches.json")
    if not os.path.exists(report_path):
        print(f"❌ [FAIL] Final report not found at {report_path}")
        return False, [], "SKIPPED"

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    passed_all = True

    # 0.5 封面圖片完整性檢查
    print("\n--- 0.5 Book Cover Image Integrity Check ---")
    cover_jpg_path = os.path.join(os.path.dirname(report_path), "cover.jpg")
    cover_status = "SKIPPED"
    if os.path.exists(cover_jpg_path):
        if '<img' in content and 'alt="書籍封面"' in content:
            print("✅ [PASS] 封面圖片已正確內嵌於報告中。")
            cover_status = "PASS"
        else:
            print(f"❌ [FAIL] 封面圖片存在於 {cover_jpg_path}，但報告中未偵測到內嵌的封面 img 標籤。")
            passed_all = False
            cover_status = "FAIL"
    else:
        print("ℹ️ [INFO] 本書無封面圖片 (cover.jpg)，已略過封面檢查。")

    # 1. 失敗批次檢查
    if os.path.exists(failed_path):
        try:
            with open(failed_path, "r", encoding="utf-8") as ff:
                failed_items = json.load(ff)
            if failed_items:
                print(f"⚠️ [WARN] Found {len(failed_items)} failed batch(es) in {failed_path}")
                passed_all = False
        except Exception:
            pass
    else:
        print("✅ [PASS] No failed batches recorded (100% generation success).")

    # 2. 標題與章節密度檢查
    main_body = content.split("## 📚 參考文獻")[0]
    chapters = re.split(r'\n(?=##\s+)', main_body)
    chap_blocks = [c for c in chapters[1:] if c.strip()]

    print(f"\n--- 1. Chapter Density & Structure Check ({len(chap_blocks)} chapters found) ---")
    if not chap_blocks:
        print("❌ [FAIL] No H2 (##) chapter headings found in report.")
        passed_all = False

    found_chapter_titles = []
    has_density_warnings = False

    for c_idx, chap in enumerate(chap_blocks, start=1):
        lines = chap.strip().split('\n')
        h2_title = lines[0].strip('# ').strip() if lines else f"Chapter {c_idx}"
        found_chapter_titles.append(h2_title)

        # 同步擷取區塊內的 H3 (###) 子小節標題，避免巢狀章節被誤判為缺漏
        for line in lines[1:]:
            line_str = line.strip()
            if line_str.startswith("### ") and not any(tag in line_str for tag in ["📌", "💡", "📚", "核心概念", "重點擷取"]):
                h3_title = line_str.lstrip('#').strip()
                if h3_title and h3_title not in found_chapter_titles:
                    found_chapter_titles.append(h3_title)

        chap_len = len(chap)

        # 判定是否為 Part/部/篇/卷 或純章節大標題（其下包含子小節）
        is_part_header = bool(re.match(r'^(?:Part\s*[\dIVXLCDMivxlcdm]+|第\s*[\d一二三四五六七八九十百]+\s*[部篇卷]|前言|總結|附錄)', h2_title, re.IGNORECASE))
        # 判定此區塊內是否包含 H3 子小節（如 ### 1-1 或 ### 📌）
        has_subsections = "### " in chap

        has_concept = "📌 核心概念" in chap or "核心概念" in chap
        has_details = "💡 重點擷取" in chap or "重點擷取" in chap

        status_flag = "✅"
        # 若為 Part 總綱標題或帶有子小節的章節標題，豁免單獨的 1000 字限制與結構標籤檢查
        if is_part_header or (has_subsections and (has_concept or has_details)):
            status_flag = "✅ [章節/總綱]"
        elif chap_len < 1000 or not (has_concept and has_details):
            status_flag = "⚠️"
            has_density_warnings = True

        print(f"{status_flag} {h2_title[:40]}... | Length: {chap_len} chars | Concept: {has_concept} | Details: {has_details}")

    # 2.1 重複章節偵測 (重複章節提醒)
    duplicates = detect_duplicate_chapters(found_chapter_titles)
    if duplicates:
        print(f"\n⚠️ [WARN] 偵測到 {len(duplicates)} 組重複或高度雷同的章節段落：")
        for orig, dup in duplicates:
            print(f"   ⚠️ 重複段落: 《{dup}》 與先前 《{orig}》 雷同")

    # 2.5 Ground Truth TOC 1對1核對 (Hard-Fail 檢驗)
    gt_json_path = os.path.join(BASE_DIR, "config", "ground_truth_toc.json")
    missing_chapters = []
    if os.path.exists(gt_json_path):
        print("\n--- 1.5 Ground Truth 1-to-1 Chapter Coverage Check ---")
        try:
            with open(gt_json_path, "r", encoding="utf-8") as gtf:
                gt_data = json.load(gtf)
            total_gt = gt_data.get("total_chapters", 0)
            gt_chapters = gt_data.get("chapters", [])

            for gt_chap in gt_chapters:
                norm_gt = _normalize(gt_chap)
                matched = any(norm_gt == _normalize(fc) or norm_gt in _normalize(fc) or _normalize(fc) in norm_gt for fc in found_chapter_titles)
                if not matched:
                    missing_chapters.append(gt_chap)

            if missing_chapters:
                print(f"❌ [HARD-FAIL] 發現全書 {total_gt} 章節中，有 {len(missing_chapters)} 章節完全缺漏：")
                for mc in missing_chapters:
                    print(f"   ❌ 缺漏章節: {mc}")
                passed_all = False
            else:
                print(f"✅ [PASS] 報告完整涵蓋全書 Ground Truth {total_gt} 章節，無任何遺漏！")
        except Exception as e:
            print(f"Notice: Failed to load Ground Truth TOC for QC check: {e}")

    # 3. 腳註一致性檢查 (雙向)
    print("\n--- 2. Citation Consistency Check ---")
    text_body = content.split("## 📚 參考文獻與原文引用腳註")[0] if "## 📚 參考文獻與原文引用腳註" in content else content
    ref_body = content.split("## 📚 參考文獻與原文引用腳註")[1] if "## 📚 參考文獻與原文引用腳註" in content else ""

    text_citations = set()
    matches = re.findall(r'\[(\d+(?:\s*[-,]\s*\d+)*)\]', text_body)
    for match in matches:
        for part in re.split(r',\s*', match):
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    text_citations.update(range(s, e + 1))
                except ValueError:
                    pass
            else:
                try:
                    text_citations.add(int(part))
                except ValueError:
                    pass

    ref_citations = set()
    ref_matches = re.findall(r'^\[(\d+)\]\s*"', ref_body, re.MULTILINE)
    for rm in ref_matches:
        ref_citations.add(int(rm))

    print(f"Total Unique Citations in Text: {len(text_citations)}")
    print(f"Total Unique Citations in References: {len(ref_citations)}")

    missing_in_ref = text_citations - ref_citations
    missing_in_text = ref_citations - text_citations

    if missing_in_ref:
        print(f"❌ [FAIL] Citations present in text but missing in References: {sorted(list(missing_in_ref))}")
        passed_all = False
    else:
        print("✅ [PASS] All text citations have matching entries in References.")

    if missing_in_text:
        print(f"⚠️ [WARN] Orphan citations in References not cited in text: {sorted(list(missing_in_text))}")
    else:
        print("✅ [PASS] No orphan citations in References.")

    return passed_all, missing_chapters, cover_status

def qc_check():
    parser = argparse.ArgumentParser(description="QC check for assembled book report.")
    parser.add_argument("--title", help="Book title")
    parser.add_argument("--auto-backfill", action="store_true", help="Auto trigger 05_backfill.py if missing chapters found.")
    parser.add_argument("--clean-temp", action="store_true", help="Automatically clean temporary files in raw_outputs and final after QC pass.")
    args = parser.parse_args()

    config_path = os.path.join(BASE_DIR, "config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    book_title = args.title or config.get("book_title", "")
    if args.title and os.path.exists(os.path.join(BASE_DIR, "final", book_title, f"{book_title}.md")):
        report_path = os.path.join(BASE_DIR, "final", book_title, f"{book_title}.md")
    elif args.title and os.path.exists(os.path.join(BASE_DIR, "final", book_title, "full_report.md")):
        report_path = os.path.join(BASE_DIR, "final", book_title, "full_report.md")
    elif os.path.exists(os.path.join(BASE_DIR, "final", "full_report.md")):
        report_path = os.path.join(BASE_DIR, "final", "full_report.md")
    else:
        report_path = os.path.join(BASE_DIR, "final", book_title, f"{book_title}.md")

    print("==========================================")
    print("      Starting Automated QC Check         ")
    print("==========================================")

    # 執行首次單次 QC
    passed_all, missing_chapters, cover_status = run_single_qc_pass(report_path)

    # 若開啟 --auto-backfill 且有缺漏，進入閉環自動補課與 re-check 迴圈 (MAX_RETRY_BATCH = 3)
    if missing_chapters and args.auto_backfill:
        import importlib.util
        bf_path = os.path.join(BASE_DIR, "scripts", "05_backfill.py")
        
        for retry in range(1, MAX_RETRY_BATCH + 1):
            print(f"\n🔄 [Auto-Backfill Retry {retry}/{MAX_RETRY_BATCH}] 發現缺漏章節，觸發自動補課流程...")
            spec = importlib.util.spec_from_file_location("backfill_mod", bf_path)
            bf_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bf_mod)
            
            # 執行補課並會自動觸發 03_assemble_report 重新組裝
            bf_mod.run_backfill(missing_chapters)

            # 補完重組後，重新執行單次 QC 驗證！
            print(f"\n🔍 [Re-QC Check Pass {retry}] 補課與重組完成，重新驗證報告涵蓋度...")
            passed_all, missing_chapters, cover_status = run_single_qc_pass(report_path)

            if passed_all and not missing_chapters:
                print(f"🎉 [Auto-Backfill Success] 於第 {retry} 次補課後，全書章節 100% 涵蓋且 QC 完全通過！")
                break

    # EPUB 來源一致性 WARN
    if cover_status == "SKIPPED":
        book_local_path = config.get("book_local_path", "")
        if book_local_path and book_local_path.lower().endswith(".epub") and os.path.exists(book_local_path):
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(book_local_path, 'r') as z:
                    try:
                        container_data = z.read('META-INF/container.xml')
                        root = ET.fromstring(container_data)
                        rootfile_path = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile').attrib['full-path']
                    except Exception:
                        rootfile_path = 'OEBPS/content.opf'
                    opf_data = z.read(rootfile_path)
                    opf_root = ET.fromstring(opf_data)
                    manifest = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')
                    if manifest is not None:
                        for item in manifest.findall('{http://www.idpf.org/2007/opf}item'):
                            props = item.attrib.get('properties', '').lower()
                            item_id = item.attrib.get('id', '').lower()
                            href = item.attrib.get('href', '').lower()
                            if ('cover-image' in props or 'cover' in item_id) and any(href.endswith(ext) for ext in ('.jpg', '.jpeg', '.png')):
                                print(f"⚠️ [WARN] 原始 EPUB 含有封面圖片，但 final/cover.jpg 未提取。建議重新執行 01_init_notebook.py 提取封面。")
                                break
            except Exception:
                pass

    print("\n==========================================")
    qc_status_path = os.path.join(BASE_DIR, "qc_status.json")
    try:
        with open(qc_status_path, "w", encoding="utf-8") as qf:
            json.dump({
                "passed_all": bool(passed_all and not missing_chapters),
                "book_title": book_title,
                "report_path": report_path,
                "cover_check": cover_status
            }, qf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write qc_status.json: {e}")

    if passed_all and not missing_chapters:
        print("🎉 QC RESULT: ALL CHECKS PASSED PERFECTLY!")
        print("==========================================")

        # 暫存檔清理邏輯（帶有強制安全防護與顯式路徑提示）
        def cleanup_temp_files():
            if not book_title or not book_title.strip():
                print("⚠️ [安全保護] 未指定具體書籍名稱 (book_title)，為防止誤刪其他書籍資料，已強制中止暫存檔清理！")
                return

            import shutil
            import tempfile
            cleaned_any = False
            clean_title = book_title.strip()
            
            # 1. 清理系統 Temp 目錄下的 raw_outputs/<book_title>
            target_temp_raw = os.path.join(tempfile.gettempdir(), "book-reader", "raw_outputs", clean_title)
            if os.path.exists(target_temp_raw):
                try:
                    if os.path.isdir(target_temp_raw):
                        shutil.rmtree(target_temp_raw)
                    cleaned_any = True
                    print(f"🧹 已成功清理系統 Temp 暫存目錄: {target_temp_raw}")
                except Exception as e:
                    print(f"Notice: Failed to clean temp raw_outputs: {e}")

            # 2. 清理專案本地目錄下的 raw_outputs/<book_title>（若存在）
            target_local_raw = os.path.join(BASE_DIR, "raw_outputs", clean_title)
            if os.path.exists(target_local_raw):
                try:
                    if os.path.isdir(target_local_raw):
                        shutil.rmtree(target_local_raw)
                    cleaned_any = True
                    print(f"🧹 已成功清理專案本地 raw_outputs 暫存目錄: {target_local_raw}")
                except Exception as e:
                    print(f"Notice: Failed to clean local raw_outputs: {e}")

            # 3. 清理 final 子目錄中除了目標 .md 與 cover.jpg 以外的中間檔
            target_final = os.path.join(BASE_DIR, "final", clean_title)
            if os.path.exists(target_final) and os.path.isdir(target_final):
                try:
                    for fname in os.listdir(target_final):
                        if fname.endswith(".md") or fname == "cover.jpg":
                            continue
                        fpath = os.path.join(target_final, fname)
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                        elif os.path.isdir(fpath):
                            shutil.rmtree(fpath)
                        cleaned_any = True
                    print(f"🧹 已成功清理 final/{clean_title} 中的中間暫存圖片與非 md 檔案")
                except Exception as e:
                    print(f"Notice: Failed to clean final intermediate files: {e}")

            if cleaned_any:
                print("✨ 暫存檔清理完畢！")

        clean_title = book_title.strip() if book_title else ""
        import tempfile
        target_raw_display = os.path.join(tempfile.gettempdir(), "book-reader", "raw_outputs", clean_title) if clean_title else "[未指定書籍]"
        target_final_display = os.path.join(BASE_DIR, "final", clean_title) if clean_title else "[未指定書籍]"

        if args.clean_temp:
            cleanup_temp_files()
        else:
            try:
                print("\n❓ 報告已確認無誤且通過 QC，是否清理當前書籍的暫存檔？")
                print(f"   ► 欲清理 raw_outputs 目錄: {target_raw_display}")
                print(f"   ► 欲清理 final 中間圖片/非md檔: {target_final_display}")
                ans = input("確認清理 (y/N): ").strip().lower()
                if ans == 'y':
                    cleanup_temp_files()
            except (EOFError, KeyboardInterrupt):
                pass
    else:
        print("⚠️ QC RESULT: COMPLETED WITH WARNINGS/ISSUES.")
        print("==========================================")

if __name__ == "__main__":
    qc_check()
