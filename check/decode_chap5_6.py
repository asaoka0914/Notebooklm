import io
import sys
import re

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\chap5_6_raw.json'

with open(file_path, 'rb') as f:
    raw = f.read()

text = raw.decode('utf-16le', errors='ignore')

start_str = '"answer": "'
start_idx = text.find(start_str)

if start_idx != -1:
    content_start = start_idx + len(start_str)
    end_idx = text.find('",\n  "conversation_id":', content_start)
    if end_idx == -1:
        end_idx = text.find('",\r\n  "conversation_id":', content_start)
    if end_idx == -1:
        end_idx = text.find('"conversation_id":', content_start) - 10
    
    ans_raw = text[content_start:end_idx]
    
    def replace_u(match):
        return chr(int(match.group(1), 16))
        
    decoded_text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_u, ans_raw)
    decoded_text = decoded_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        
    out_path = r'g:\我的雲端硬碟\Project\Notebooklm\chap5_6_decoded.md'
    with open(out_path, 'w', encoding='utf-8') as out:
        out.write(decoded_text)
    print(f"Decoded UTF-8 markdown saved to {out_path}! Length: {len(decoded_text)} chars.")
else:
    print("Start index not found.")
