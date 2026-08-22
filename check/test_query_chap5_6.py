import os
import sys
import json

# 設定 stdout 為 utf-8 避免 cp950 解碼 emoji 錯誤
sys.stdout.reconfigure(encoding='utf-8')

from notebooklm_tools.cli.main import app

def run_chap_test():
    notebook_id = "d7ec78f8-4df3-44ea-95ff-ea6939058106"
    prompt_text = (
        "請嚴格依據來源檔案《讀書報告核心概念.md》（或《讀書報告核心概念》）中的撰寫規範與原則，"
        "針對原書的 Chapter 5 與 Chapter 6 進行詳細、深度且不遺漏細節的報告撰寫。"
        "輸出請完全使用繁體中文，格式需符合規範中的標題與引述架構。"
    )
    
    output_file = "test_chap5_6_output.json"
    
    # 執行 query 輸出 json
    print("Sending query for Chapter 5-6...")
    try:
        app(["query", "notebook", notebook_id, prompt_text, "--json"])
    except SystemExit:
        pass

if __name__ == "__main__":
    run_chap_test()
