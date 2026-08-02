import os
import sys
import re
import json
import argparse
import yaml

sys.stdout.reconfigure(encoding='utf-8')

def qc_check():
    parser = argparse.ArgumentParser(description="QC check for assembled book report.")
    parser.add_argument("--title", help="Book title")
    args = parser.parse_args()

    config_path = os.path.join("config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    book_title = args.title or config.get("book_title", "")
    if args.title and os.path.exists(os.path.join("final", book_title, f"{book_title}.md")):
        report_path = os.path.join("final", book_title, f"{book_title}.md")
    elif args.title and os.path.exists(os.path.join("final", book_title, "full_report.md")):
        report_path = os.path.join("final", book_title, "full_report.md")
    else:
        report_path = os.path.join("final", "full_report.md")

    failed_path = "failed_batches.json"

    print("==========================================")
    print("      Starting Automated QC Check         ")
    print("==========================================")

    if not os.path.exists(report_path):
        print(f"❌ [FAIL] Final report not found at {report_path}")
        sys.exit(1)

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
    # 拆分內文與參考文獻
    main_body = content.split("## 📚 參考文獻")[0]
    chapters = re.split(r'\n(?=##\s+)', main_body)
    chap_blocks = [c for c in chapters[1:] if c.strip()]

    print(f"\n--- 1. Chapter Density & Structure Check ({len(chap_blocks)} chapters found) ---")
    if not chap_blocks:
        print("❌ [FAIL] No H2 (##) chapter headings found in report.")
        passed_all = False

    for c_idx, chap in enumerate(chap_blocks, start=1):
        lines = chap.strip().split('\n')
        h2_title = lines[0] if lines else f"Chapter {c_idx}"
        chap_len = len(chap)

        # 檢查結構元素
        has_concept = "📌 核心概念" in chap or "核心概念" in chap
        has_details = "💡 重點擷取" in chap or "重點擷取" in chap

        status_flag = "✅"
        if chap_len < 1000 or not (has_concept and has_details):
            status_flag = "⚠️"
            passed_all = False

        print(f"{status_flag} {h2_title[:40]}... | Length: {chap_len} chars | Concept: {has_concept} | Details: {has_details}")

    # 3. 腳註一致性檢查 (雙向)
    print("\n--- 2. Citation Consistency Check ---")
    
    # 尋找內文中的所有引號數字 [1], [2], [1-3], [4, 5]
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

    # 尋找 References 區塊中的所有 [N] 標記
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

    print("\n==========================================")
    if passed_all:
        print("🎉 QC RESULT: ALL CHECKS PASSED PERFECTLY!")
    else:
        print("⚠️ QC RESULT: COMPLETED WITH WARNINGS/ISSUES.")
    print("==========================================")

if __name__ == "__main__":
    qc_check()
