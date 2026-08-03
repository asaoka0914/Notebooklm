import os
import sys
import json
import re
import argparse
import yaml

sys.stdout.reconfigure(encoding='utf-8')

def remove_checklist_sections(text):
    """從 Markdown 內容中剔除『涵蓋度自我檢查清單』區塊"""
    # 匹配從 ### 📋 涵蓋度自我檢查清單 (或類似標題) 開始到下一個標題或分割線前的所有內容
    pattern = r'#{2,5}\s*(?:📋\s*)?涵蓋度自我檢查清單.*?(?=(?:\n#{2,5}\s*|\n---|\Z))'
    cleaned = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned

def normalize_headings(text):
    """
    標題階層正規化：
    - 章節標題（如 第一章、CHAPTER 1）-> H2 (##)
    - 章節內子結構（如 1.1, 📌 核心概念, 💡 重點擷取）-> H3 (###)
    - 其它非標題行的 # 開頭移除
    """
    lines = text.split('\n')
    norm_lines = []
    
    for line in lines:
        stripped = line.strip()
        # 1. 識別章節大標題 (如：#### 洞察市場真實面... 或 #### 第 1 章：... 或 #### CHAPTER 1...)
        if re.match(r'^(?:#{1,6}\s*)?(?:洞察市場真實面|第\s*\d+\s*章|第[一二三四五六七八九十]+\s*章|CHAPTER\s*\d+|前言|總結|附錄)', stripped, re.IGNORECASE):
            clean_title = re.sub(r'^#{1,6}\s*', '', stripped)
            norm_lines.append(f"\n## {clean_title}\n")
        # 2. 識別子結構 (如：##### 1.1 ..., 📌 核心概念, 💡 重點擷取)
        elif re.match(r'^(?:#{1,6}\s*)?(?:\d+\.\d+|📌|💡|核心概念|重點擷取)', stripped):
            clean_subtitle = re.sub(r'^#{1,6}\s*', '', stripped)
            norm_lines.append(f"\n### {clean_subtitle}\n")
        else:
            norm_lines.append(line)
            
    return '\n'.join(norm_lines)

def parse_citations(text, citation_map, batch_offset):
    """解析內文中的 [1], [1-3], [4, 5] 並對應至全域編號"""
    pattern = r'\[(\d+(?:\s*[-,]\s*\d+)*)\]'
    
    def remap_match(match):
        raw_str = match.group(1)
        nums = []
        for part in re.split(r',\s*', raw_str):
            if '-' in part:
                try:
                    start, end = map(int, part.split('-'))
                    nums.extend(range(start, end + 1))
                except ValueError:
                    pass
            else:
                try:
                    nums.append(int(part))
                except ValueError:
                    pass
        
        g_nums = []
        for n in nums:
            if (batch_offset, n) in citation_map:
                g_nums.append(citation_map[(batch_offset, n)])
            else:
                g_nums.append(n)
                
        if not g_nums:
            return match.group(0)
            
        if len(g_nums) > 2 and g_nums == list(range(g_nums[0], g_nums[-1] + 1)):
            return f"[{g_nums[0]}-{g_nums[-1]}]"
        else:
            return f"[{', '.join(map(str, g_nums))}]"

    return re.sub(pattern, remap_match, text)

def assemble_report():
    parser = argparse.ArgumentParser(description="Assemble report JSONs into Markdown.")
    parser.add_argument("--title", help="Book title")
    args = parser.parse_args()

    config_path = os.path.join("config", "book_config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    book_title = args.title or config.get("book_title", "讀書報告")
    
    # 支援子資料夾 (raw_outputs/<book_title>) 與根目錄雙相容
    raw_dir = os.path.join("raw_outputs", book_title) if os.path.exists(os.path.join("raw_outputs", book_title)) else "raw_outputs"
    final_dir = os.path.join("final", book_title) if args.title else "final"
    os.makedirs(final_dir, exist_ok=True)

    batch_files = sorted([f for f in os.listdir(raw_dir) if f.startswith("batch_") and f.endswith(".json")])
    if not batch_files:
        print(f"Error: No batch JSON files found in {raw_dir}.")
        sys.exit(1)

    full_markdown_parts = []
    full_markdown_parts.append(f"# 《{book_title}》全書導讀與深度分析報告\n")

    # 檢查是否有提取好的 cover.jpg，轉為 Base64 直接內嵌（縮小長寬至 50%，面積與體積變為 1/4）
    cover_image_path = os.path.join(final_dir, "cover.jpg")
    if os.path.exists(cover_image_path):
        import base64
        import io
        from PIL import Image
        
        try:
            with Image.open(cover_image_path) as img:
                # 實體長寬再縮至 50%
                new_width = max(1, img.width // 2)
                new_height = max(1, img.height // 2)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                resized_img.convert("RGB").save(buffer, format="JPEG", quality=85)
                b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
                # 使用 HTML img 標籤限定顯示寬度為 300px (Obsidian 即時渲染最合適尺寸)
                full_markdown_parts.append(f'\n<img src="data:image/jpeg;base64,{b64_str}" alt="書籍封面" width="300" />\n')
        except Exception as e:
            print(f"Warning: Failed to process cover image resizing: {e}")
            with open(cover_image_path, "rb") as img_f:
                b64_str = base64.b64encode(img_f.read()).decode("utf-8")
            full_markdown_parts.append(f'\n<img src="data:image/jpeg;base64,{b64_str}" alt="書籍封面" width="300" />\n')
        # 內嵌後可選擇保留或移除獨立圖片，此處留存全內嵌單一檔案

    full_markdown_parts.append("\n---\n")

    global_citation_counter = 1
    citation_map = {}
    references_list = []

    # 第一階段：構建全域腳註對照表
    for b_idx, b_file in enumerate(batch_files, start=1):
        fpath = os.path.join(raw_dir, b_file)
        with open(fpath, "r", encoding="utf-8") as rf:
            data = json.load(rf)

        refs = data.get("references", [])
        for ref in refs:
            local_num = ref.get("citation_number")
            cited_text = ref.get("cited_text", "").strip()
            if local_num is not None and cited_text:
                citation_map[(b_idx, local_num)] = global_citation_counter
                references_list.append({
                    "id": global_citation_counter,
                    "text": cited_text,
                    "batch": b_idx
                })
                global_citation_counter += 1

    # 第二階段：內容過濾（剔除檢查清單）、標題正規化與腳註重映射
    for b_idx, b_file in enumerate(batch_files, start=1):
        fpath = os.path.join(raw_dir, b_file)
        with open(fpath, "r", encoding="utf-8") as rf:
            data = json.load(rf)

        answer = data.get("answer", "")
        # 1. 剔除涵蓋度自我檢查清單
        clean_answer = remove_checklist_sections(answer)
        # 2. 標題正規化
        norm_answer = normalize_headings(clean_answer)
        # 3. 腳註重編號
        remapped_answer = parse_citations(norm_answer, citation_map, b_idx)
        
        full_markdown_parts.append(remapped_answer)
        full_markdown_parts.append("\n\n---\n")

    # 第三階段：附錄 References 區塊生成（若有）
    if references_list:
        full_markdown_parts.append("\n## 📚 參考文獻與原文引用腳註 (References & Citations)\n\n")
        for ref_item in references_list:
            c_id = ref_item["id"]
            c_txt = ref_item["text"]
            full_markdown_parts.append(f"[{c_id}] \"{c_txt}\"\n\n")

    final_report_filename = f"{book_title}.md"
    final_report_path = os.path.join(final_dir, final_report_filename)
    with open(final_report_path, "w", encoding="utf-8") as wf:
        wf.write('\n'.join(full_markdown_parts))

    print(f"[Success] Assembled full report saved to {final_report_path}")
    print(f"Total Sections Processed: {len(batch_files)}")
    print(f"Total Citations Remapped: {len(references_list)}")

if __name__ == "__main__":
    assemble_report()
