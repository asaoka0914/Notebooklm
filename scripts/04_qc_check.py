import os
import sys
import re
import json
import argparse
import yaml

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MAX_RETRY_BATCH = 3

def run_single_qc_pass(report_path):
    """執行單次 QC 比對檢查，回傳 (passed_all, missing_chapters)"""
    failed_path = os.path.join(BASE_DIR, "failed_batches.json")
    if not os.path.exists(report_path):
        print(f"❌ [FAIL] Final report not found at {report_path}")
        return False, []

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    passed_all = True

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
    for c_idx, chap in enumerate(chap_blocks, start=1):
        lines = chap.strip().split('\n')
        h2_title = lines[0].strip('# ').strip() if lines else f"Chapter {c_idx}"
        found_chapter_titles.append(h2_title)
        chap_len = len(chap)

        has_concept = "📌 核心概念" in chap or "核心概念" in chap
        has_details = "💡 重點擷取" in chap or "重點擷取" in chap

        status_flag = "✅"
        if chap_len < 1000 or not (has_concept and has_details):
            status_flag = "⚠️"
            passed_all = False

        print(f"{status_flag} {h2_title[:40]}... | Length: {chap_len} chars | Concept: {has_concept} | Details: {has_details}")

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
                matched = any(gt_chap in fc or fc in gt_chap for fc in found_chapter_titles)
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

    return passed_all, missing_chapters

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
    passed_all, missing_chapters = run_single_qc_pass(report_path)

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
            passed_all, missing_chapters = run_single_qc_pass(report_path)

            if passed_all and not missing_chapters:
                print(f"🎉 [Auto-Backfill Success] 於第 {retry} 次補課後，全書章節 100% 涵蓋且 QC 完全通過！")
                break

    print("\n==========================================")
    if passed_all and not missing_chapters:
        print("🎉 QC RESULT: ALL CHECKS PASSED PERFECTLY!")
        print("==========================================")

        # 暫存檔清理邏輯（帶有強制安全防護與顯式路徑提示）
        def cleanup_temp_files():
            if not book_title or not book_title.strip():
                print("⚠️ [安全保護] 未指定具體書籍名稱 (book_title)，為防止誤刪其他書籍資料，已強制中止暫存檔清理！")
                return

            import shutil
            cleaned_any = False
            clean_title = book_title.strip()
            
            # 強制指定具體書籍子目錄，絕不退回根目錄
            target_raw = os.path.join(BASE_DIR, "raw_outputs", clean_title)
            if os.path.exists(target_raw):
                try:
                    if os.path.isdir(target_raw):
                        shutil.rmtree(target_raw)
                    cleaned_any = True
                    print(f"🧹 已成功清理 raw_outputs 暫存目錄: {target_raw}")
                except Exception as e:
                    print(f"Notice: Failed to clean raw_outputs: {e}")

            # 清理 final 子目錄中除了目標 .md 以外的中間檔
            target_final = os.path.join(BASE_DIR, "final", clean_title)
            if os.path.exists(target_final) and os.path.isdir(target_final):
                try:
                    for fname in os.listdir(target_final):
                        if not fname.endswith(".md"):
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
        target_raw_display = os.path.join(BASE_DIR, "raw_outputs", clean_title) if clean_title else "[未指定書籍]"
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
