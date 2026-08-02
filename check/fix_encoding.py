import io
import sys
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'r', encoding='utf-16le', errors='ignore') as f:
    text = f.read()

start_mark = '"answer": "'
start_pos = text.find(start_mark)
if start_pos != -1:
    content_start = start_pos + len(start_mark)
    end_pos = text.find('",\n  "citations":', content_start)
    if end_pos == -1:
        end_pos = text.find('",\r\n  "citations":', content_start)
    
    val = text[content_start:end_pos]
    
    # 替換 \n, \t, \", \\
    val = val.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
    
    # 正則替換 \uXXXX
    val = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), val)
    
    with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
        out.write(val)
    print(f"Report saved successfully! Length: {len(val)} chars.")
