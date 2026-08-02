import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    raw = f.read()

text = raw.decode('utf-16le', errors='ignore')

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
    
    # 進行 unicode-escape 解碼以還原中文與符號
    try:
        # 將轉義字元包裝成 unicode_escape 能處理的格式
        decoded_text = ans_raw.encode('latin1').decode('unicode_escape')
    except Exception:
        # 手動替換 \uXXXX
        import re
        def replace_u(match):
            return chr(int(match.group(1), 16))
        decoded_text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_u, ans_raw)
        decoded_text = decoded_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        
    with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
        out.write(decoded_text)
    print(f"Decoded UTF-8 markdown successfully saved! Length: {len(decoded_text)} chars.")
else:
    print("Start index not found.")
