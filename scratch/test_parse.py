import sys
import os
import importlib.util

sys.path.insert(0, os.path.abspath("scripts"))

file_path = os.path.abspath("scripts/01_init_notebook.py")
spec = importlib.util.spec_from_file_location("init_notebook_mod", file_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fn = mod._parse_toc_response

json_sample = """```json
[
  "Part 1: 導論",
  "Part 2: 核心觀點",
  "Lesson 3: 總結"
]
```"""

raw_sample = """
以下是本書目錄：
Part 1: 導論
Part 2: 核心觀點
Lesson 3: 總結
"""

print("JSON 解析測試結果:", fn(json_sample))
print("Fallback 退回機制測試結果:", fn(raw_sample))
