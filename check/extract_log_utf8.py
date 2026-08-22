import io
import sys
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

log_path = r'C:\Users\AsaokaHTPC\.gemini\antigravity-ide\brain\01e10d53-9ec6-4d9d-9f2a-6a5172c3a44c\.system_generated\tasks\task-295.log'

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

p = text.find('"answer": "')
end_p = text.find('",\n  "citations":', p)
if end_p == -1:
    end_p = text.find('",\r\n  "citations":', p)

raw_ans = text[p+11:end_p]

# 處理 \n, \", \\ 轉義
ans = raw_ans.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')

with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report_final.md', 'w', encoding='utf-8') as out:
    out.write(ans)

print(f"Final Chinese report saved! Length: {len(ans)} chars.")
