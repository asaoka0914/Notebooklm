import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    raw = f.read()

text = raw.decode('utf-16le', errors='ignore')

# 找出 "answer": " 開頭與 "citations": 位置
start_str = '"answer": "'
start_idx = text.find(start_str)

if start_idx != -1:
    content_start = start_idx + len(start_str)
    end_idx = text.find('",\n  "citations":', content_start)
    if end_idx == -1:
        end_idx = text.find('",\r\n  "citations":', content_start)
    if end_idx == -1:
        end_idx = text.find('"citations":', content_start) - 10
    
    ans_raw = text[content_start:end_idx]
    ans_clean = ans_raw.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
        out.write(ans_clean)
    print(f"Successfully extracted! Length: {len(ans_clean)} chars.")
else:
    print("Start index not found.")
