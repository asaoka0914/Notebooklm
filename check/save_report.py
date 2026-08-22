import json
import io
import sys

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

# strict=False 允許跳過控制字元錯誤
data = json.loads(text, strict=False)
answer = data.get('answer', '')

with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
    out.write(answer)

print(f"Report saved! Total length: {len(answer)} chars.")
