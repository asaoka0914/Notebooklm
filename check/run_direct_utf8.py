import io
import sys

# 強制 Python 程序的全域環境使用 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from notebooklm_tools.cli.main import app

notebook_id = "d7ec78f8-4df3-44ea-95ff-ea6939058106"
q = "請詳細閱讀本筆記的所有來源文件內容，嚴格按照【讀書報告核心概念.md】的結構輸出完整章節重點。包含：1. 忠實度 2. 涵蓋度 (每個章節都不省略) 3. 輸出📌 核心概念 與 💡 重點擷取。"

print("開始向 NotebookLM 查詢完整報告內容...")
try:
    # 呼叫 SDK 獲取原生 response 物件或讓 app 列印至 UTF-8 stdout
    app(["query", "notebook", notebook_id, q])
except SystemExit as e:
    pass
