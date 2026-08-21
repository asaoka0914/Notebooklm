import os
import sys
import argparse
import yaml
import re
import importlib.util

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

spec_02 = importlib.util.spec_from_file_location('module_02', os.path.join(BASE_DIR, 'scripts', '02_batch_generate.py'))
module_02 = importlib.util.module_from_spec(spec_02)
spec_02.loader.exec_module(module_02)
run_query_via_cli = module_02.run_query_via_cli
from _auth_utils import ensure_auth_with_pool

def build_book_summary_prompt(book_title, author=''):
    p = []
    p.append(f'請針對整本書《{book_title}》（作者：{author}），以繁體中文生成一份高深度、結構嚴謹的全書精華導讀。')
    p.append('')
    p.append('請嚴格依照以下【6 大核心模組】格式輸出：')
    p.append('')
    p.append(f'# 《{book_title}》全書核心精華導讀')
    p.append('')
    p.append('## 📌 一、全書核心(Executive Summary)')
    p.append('- **一句話主旨**：本書核心欲解決的問題與核心論點。')
    p.append('- **作者核心主張**：舊思維範式 vs. 本書提出的新範式。')
    p.append('- **適用對象與情境**：適合誰閱讀、何種決策場景最具參考價值。')
    p.append('')
    p.append('## 🧠 二、核心心智模型與底層理論 (Core Mental Models & Concepts)')
    p.append('(請提煉 6 ~ 8 個貫穿全書的核心心智模型/重要概念，每個概念請包含機制定義與核心價值。概念連結請一律使用 [[english-slug|中文概念名稱]] 格式，如 [[purpose-teleology|目的論]])')
    p.append('1. **[[concept-slug-a|概念名稱 A]]**：')
    p.append('   - **機制定義**：...')
    p.append('   - **核心價值**：...')
    p.append('(以此類推 6~8 項)')
    p.append('')
    p.append('## 🗺️ 三、全書邏輯架構與論證脈絡 (Structural Flow)')
    p.append('- **第一階段：問題診斷**（作者發現的核心盲點）')
    p.append('- **第二階段：機制解析**（現象背後的運作規律）')
    p.append('- **第三階段：解法框架**（應對策略與推論體系）')
    p.append('')
    p.append('## 🛠️ 四、實踐清單與行動法則 (Actionable Playbook)')
    p.append('- **黃金原則 (Do\'s)**：3~5 條關鍵實踐法則。')
    p.append('- **常見誤區 (Don\'ts)**：3~5 個必須避免的直覺盲點。')
    p.append('- **落地執行清單 (Checklist)**：條列式執行檢查點。')
    p.append('')
    p.append('## 💡 五、經典案例、反直覺洞見與金句 (Key Insights & Quotes)')
    p.append('- **反直覺洞見**：顛覆常識的觀點。')
    p.append('- **代表性案例 / 數據實驗**：書中支撐論點的關鍵案例。')
    p.append('- **全書精選金句**：3~5 句極具啟發性的原文金句。')
    p.append('')
    p.append('## 🔗 六、Obsidian 概念關聯與延伸閱讀 (Knowledge Graph Connections)')
    p.append('- **核心概念導引**：列出本篇關鍵概念（一律使用 [[concept-slug|中文名稱]] 格式，如 [[purpose-teleology|目的論]]、[[separation-of-tasks|課題分離]]）')
    p.append('- **知識庫關聯主題**：關聯的主題或領域')
    return '\n'.join(p)

def check_qc_prerequisite(book_title):
    qc_status_path = os.path.join(BASE_DIR, "qc_status.json")
    if not os.path.exists(qc_status_path):
        print(f"❌ [QC Check Guard] 找不到 QC 狀態檔: {qc_status_path}")
        print("👉 必須先執行 04_qc_check.py 檢驗章節涵蓋度並通過後，方可生成摘要。")
        return False

    try:
        import json
        with open(qc_status_path, "r", encoding="utf-8") as qf:
            st = json.load(qf)
        
        status_title = st.get("book_title")
        if status_title and status_title != book_title:
            print(f"❌ [QC Check Guard] QC 狀態記錄之書名 (《{status_title}》) 與當前書籍 (《{book_title}》) 不符合！請重新執行 04_qc_check.py。")
            return False

        if not st.get("passed_all", False):
            print("❌ [QC Check Guard] 04_qc_check.py 檢驗未達 100% 通過標準！請先補齊章節與修復問題。")
            return False
    except Exception as e:
        print(f"❌ [QC Check Guard] 讀取 QC 狀態檔失敗: {e}")
        return False

    report_path = os.path.join(BASE_DIR, 'final', book_title, f'{book_title}.md')
    if not os.path.exists(report_path):
        print(f'❌ [QC Check Guard] 找不到最終報告檔案: {report_path}')
        print('👉 必須先執行 01~04 步驟完成全書章節擷取與 QC 驗證後，方可生成摘要。')
        return False

    failed_path = os.path.join(BASE_DIR, 'failed_batches.json')
    if os.path.exists(failed_path):
        try:
            import json
            with open(failed_path, 'r', encoding='utf-8') as ff:
                failed_items = json.load(ff)
            if failed_items:
                print(f'❌ [QC Check Guard] 尚有 {len(failed_items)} 個批次未成功補齊，請先執行 05_backfill.py！')
                return False
        except Exception:
            pass
    return True

def generate_book_summary(notebook_id=None, book_title=None, author=''):
    config_path = os.path.join(BASE_DIR, 'config', 'book_config.yaml')
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

    notebook_id = notebook_id or config.get('notebook_id')
    book_title = book_title or config.get('book_title', 'default_book')
    author = author or config.get('author', '')

    if not notebook_id:
        print('Error: notebook_id is missing.')
        return False

    if not check_qc_prerequisite(book_title):
        return False

    ensure_auth_with_pool()
    prompt = build_book_summary_prompt(book_title, author)
    print(f'\n🚀 [Step 06] 正在向 NotebookLM 請求生成《{book_title}》的標準 6 模組全書深度摘要...')
    res = run_query_via_cli(notebook_id, prompt, timeout_sec=300)

    if not res or not res.get('answer'):
        print('❌ 生成全書深度摘要失敗（回應為空或逾時）。')
        return False

    answer_text = res.get('answer', '').strip()
    scratch_dir = os.path.join(BASE_DIR, 'scratch')
    os.makedirs(scratch_dir, exist_ok=True)
    summary_path = os.path.join(scratch_dir, 'temp_book_summary.md')

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(answer_text)

    print(f'✅ [Step 06 Success] 全書深度摘要已產出至暫存檔: {summary_path}')
    print(f'📊 摘要長度: {len(answer_text)} 字元')
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate 6-module depth book summary via NotebookLM.')
    parser.add_argument('--notebook-id', help='NotebookLM notebook ID')
    parser.add_argument('--title', help='Book title')
    parser.add_argument('--author', default='', help='Book author')
    args = parser.parse_args()
    success = generate_book_summary(args.notebook_id, args.title, args.author)
    if not success:
        sys.exit(1)
