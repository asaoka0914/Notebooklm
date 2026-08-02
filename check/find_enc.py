import json
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = r'g:\我的雲端硬碟\Project\Notebooklm\report_output.json'

with open(file_path, 'rb') as f:
    b = f.read()

# 測試各個 encoding
for enc in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp950', 'gbk']:
    try:
        s = b.decode(enc)
        if '摘要' in s or '核心概念' in s or 'William Bengen' in s or '前言' in s:
            print(f"Match found with encoding: {enc}")
            # 找到解碼正確的段落
            p = s.find('"answer": "')
            if p != -1:
                end_p = s.find('",\n  "citations":', p)
                ans = s[p+11:end_p]
                ans = ans.replace('\\n', '\n').replace('\\"', '"')
                with open(r'g:\我的雲端硬碟\Project\Notebooklm\4percent_rule_report.md', 'w', encoding='utf-8') as out:
                    out.write(ans)
                print("Successfully saved clean Chinese report!")
                break
    except Exception as e:
        pass
