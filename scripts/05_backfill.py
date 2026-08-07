import os
import sys
import json
import argparse
import yaml

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_backfill(missing_chapters, notebook_id=None, book_title=None):
    """針對 QC 比對發現的缺漏章節清單進行獨立補跑與寫入。"""
    if not missing_chapters:
        print("✅ 無缺漏章節，無需執行補課 (Backfill)。")
        return True

    config_path = os.path.join(BASE_DIR, "config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    book_title = book_title or config.get("book_title", "讀書報告")
    notebook_id = notebook_id or config.get("notebook_id")
    rule_filename = config.get("rule_source_filename", "讀書報告核心概念.md")
    rule_path = os.path.join(BASE_DIR, rule_filename)

    if not os.path.exists(rule_path):
        rule_path = os.path.join(BASE_DIR, "source", rule_filename)

    rule_prompt = ""
    if os.path.exists(rule_path):
        with open(rule_path, "r", encoding="utf-8") as rf:
            rule_prompt = rf.read()

    raw_dir = os.path.join(BASE_DIR, "raw_outputs", book_title) if book_title else os.path.join(BASE_DIR, "raw_outputs")
    os.makedirs(raw_dir, exist_ok=True)

    print(f"\n==========================================")
    print(f"🚀 啟動自動補課流程 (Backfill) — 缺漏 {len(missing_chapters)} 章節")
    print(f"==========================================")

    from _auth_utils import ensure_auth
    import importlib.util
    
    gen_path = os.path.join(BASE_DIR, "scripts", "02_batch_generate.py")
    spec_g = importlib.util.spec_from_file_location("batch_gen", gen_path)
    gen_mod = importlib.util.module_from_spec(spec_g)
    spec_g.loader.exec_module(gen_mod)
    run_query_via_cli = gen_mod.run_query_via_cli

    ensure_auth()

    for idx, chap_name in enumerate(missing_chapters, start=1):
        print(f"\n[Backfill {idx}/{len(missing_chapters)}] 補跑章節：{chap_name}...")
        prompt = (
            f"{rule_prompt}\n\n"
            f"特別針對以下章節進行完整、無遺漏的重點擷取：\n"
            f"## {chap_name}\n"
            f"請務必符合結構化格式（📌核心概念、💡重點擷取），每章字數盡可能充實。"
        )

        res = run_query_via_cli(notebook_id, prompt)
        if res and isinstance(res, dict) and res.get("answer"):
            output_file = os.path.join(raw_dir, f"batch_backfill_{idx}.json")
            with open(output_file, "w", encoding="utf-8") as wf:
                json.dump(res, wf, ensure_ascii=False, indent=2)
            print(f"✅ 補課章節已成功寫入 {output_file}")
        else:
            print(f"❌ 補課章節 {chap_name} 擷取失敗。")

    print("\n✅ 補課階段完成！重新觸發報告組裝...")
    asm_path = os.path.join(BASE_DIR, "scripts", "03_assemble_report.py")
    spec_a = importlib.util.spec_from_file_location("assemble_mod", asm_path)
    asm_mod = importlib.util.module_from_spec(spec_a)
    spec_a.loader.exec_module(asm_mod)
    asm_mod.assemble_report()
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing chapters.")
    parser.add_argument("--chapters", nargs="+", help="Missing chapter titles")
    args = parser.parse_args()
    if args.chapters:
        run_backfill(args.chapters)
