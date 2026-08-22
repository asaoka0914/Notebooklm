import json
import sys
from notebooklm_tools.cli.main import app

with open(r'g:\我的雲端硬碟\Project\Notebooklm\讀書報告核心概念.md', 'r', encoding='utf-8') as f:
    prompt_text = f.read()

notebook_id = "d7ec78f8-4df3-44ea-95ff-ea6939058106"
q = f"請詳細閱讀本筆記的所有來源文件內容，嚴格按照以下【讀書報告規範】輸出完全忠於原文、涵蓋每一個章節的完整讀書報告：\n\n{prompt_text}"

print("Sending query to notebook...")
try:
    app(["query", "notebook", notebook_id, q])
except SystemExit as e:
    print(f"Exit code: {e.code}")
