import json
import sys
from notebooklm_tools.cli.main import app

with open(r'g:\我的雲端硬碟\Project\Notebooklm\讀書報告核心概念.md', 'r', encoding='utf-8') as f:
    prompt_text = f.read()

notebook_id = "d7ec78f8-4df3-44ea-95ff-ea6939058106"

print("Starting report creation...")
try:
    app(["report", "create", notebook_id, "--format", "Create Your Own", "--prompt", prompt_text, "-y", "-j"])
except SystemExit as e:
    print(f"Exit code: {e.code}")
