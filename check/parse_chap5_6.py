import re

with open('chap5_6_raw.json', 'rb') as f:
    raw = f.read().decode('utf-16')

idx = raw.find('"answer": "')
if idx != -1:
    content_start = idx + len('"answer": "')
    end_idx = raw.find('",\n  "conversation_id":', content_start)
    if end_idx == -1:
        end_idx = raw.find('",\r\n  "conversation_id":', content_start)
    if end_idx == -1:
        end_idx = raw.find('"conversation_id":', content_start) - 10
    
    ans_str = raw[content_start:end_idx]
    
    def unescape_u(match):
        return chr(int(match.group(1), 16))
    
    cleaned = re.sub(r'\\u([0-9a-fA-F]{4})', unescape_u, ans_str)
    cleaned = cleaned.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    with open('chap5_6_clean.md', 'w', encoding='utf-8') as out:
        out.write(cleaned)
    print("Successfully decoded to chap5_6_clean.md. Character count:", len(cleaned))
