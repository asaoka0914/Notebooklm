import io
import sys
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    data = f.read()

# 測試用 unicode_escape 還原
text_utf16 = data.decode('utf-16le', errors='ignore')
p = text_utf16.find('"answer": "')
end_p = text_utf16.find('",\n  "citations":', p)

raw_ans = text_utf16[p+11:end_p]

# 嘗試用 encode('latin1').decode('utf-8') 或 latin1 / unicode_escape 解雙重編碼
try:
    fixed = raw_ans.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
except Exception:
    fixed = raw_ans

fixed = fixed.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')

with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
    out.write(fixed)

print("Check length:", len(fixed))
