import io
import sys
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    data = f.read()

# 轉換成 utf-16-le 字串
text = data.decode('utf-16le', errors='ignore')

# 找到 JSON 的 "answer" 部分
p = text.find('"answer": "')
end_p = text.find('",\n  "citations":', p)

raw_val = text[p+11:end_p]

# 核心解法：用 eval / raw_unicode_escape
fixed = raw_val.encode('raw_unicode_escape').decode('utf-8', errors='ignore')
fixed = fixed.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')

with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
    out.write(fixed)

print("Saved with raw_unicode_escape! Length:", len(fixed))
