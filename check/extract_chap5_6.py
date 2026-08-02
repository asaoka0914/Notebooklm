import json

with open('chap5_6_raw.json', 'rb') as f:
    raw = f.read().decode('utf-16')

idx = raw.find('{')
json_str = raw[idx:]

# 修正內部 question 欄位或不合規點
# 簡單的定位 'answer' 的內容:
start_tag = '"answer": "'
start = json_str.find(start_tag) + len(start_tag)

# 尋送下一個 Key: conversation_id
end_tag = '",\r\n  "conversation_id":'
end = json_str.find(end_tag)
if end == -1:
    end_tag = '",\n  "conversation_id":'
    end = json_str.find(end_tag)

answer_content = json_str[start:end]

# 處理 Python 字串解碼
# 替換 JSON 轉義字元 \n, \", \\ 
ans_clean = answer_content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')

with open('chap5_6_clean.md', 'w', encoding='utf-8') as out:
    out.write(ans_clean)

print("Saved clean answer into chap5_6_clean.md, total length:", len(ans_clean))
