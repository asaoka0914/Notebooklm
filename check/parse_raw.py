import io
import sys
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    raw = f.read()

text = ""
for enc in ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-8-sig', 'utf-8']:
    try:
        text = raw.decode(enc)
        break
    except Exception:
        pass

# 擷取 "answer": "..." 內容
match = re.search(r'"answer":\s*"(.*?)",\s*"citations":', text, re.DOTALL)
if match:
    ans_raw = match.group(1)
    # 處理轉義字元
    ans_clean = ans_raw.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
        out.write(ans_clean)
    print(f"Successfully extracted! Total length: {len(ans_clean)} chars.")
else:
    print("Pattern match failed.")
