#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BoBo-wiki 結構規範嚴格驗證工具 (validate_schema.py)

功能：
1. 檢驗 wiki/summaries/ 下所有摘要檔案是否符合 Frontmatter 與 4模組/6模組 Schema
2. 檢驗 wiki/concepts/ 下所有概念筆記是否符合 Frontmatter (title 必須繁中) 與 4大核心章節 (非佔位符)
3. Hard-Fail 判定：只要有任一檔案不合規，立即 Exit Code 1，阻斷 Agent 偷工減料

用法：
    python check/validate_schema.py
    python check/validate_schema.py --target wiki/summaries/an-gan-tou-zi-fa-summary.md
"""

import io
import os
import re
import sys
import argparse
from pathlib import Path

# UTF-8 Windows 控制台防護
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_DIR = PROJECT_ROOT / "wiki" / "summaries"
CONCEPTS_DIR = PROJECT_ROOT / "wiki" / "concepts"

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML Frontmatter，回傳 (屬性dict, 剩餘內文)。"""
    if not content.startswith("---"):
        return {}, content
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    
    yaml_text = parts[1]
    body = parts[2]
    
    meta = {}
    for line in yaml_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            # 處理簡易引號與清單
            v = v.strip('"\'')
            meta[k] = v
            
    return meta, body

def validate_summary(file_path: Path) -> list[str]:
    """驗證 Summary 檔案格式。"""
    errors = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [f"無法讀取檔案: {e}"]

    meta, body = parse_frontmatter(content)
    
    # 1. 檢驗 Frontmatter 必要屬性
    required_meta = ["slug", "type", "title", "original_ref"]
    for rm in required_meta:
        if rm not in meta or not meta[rm]:
            errors.append(f"缺少 Frontmatter 必要屬性: '{rm}'")
            
    if meta.get("type") not in ("book-summary", "article-summary", "summary"):
        errors.append(f"Frontmatter 'type' 不正確: '{meta.get('type')}' (應為 book-summary 或 article-summary)")

    # 2. 檢驗章節標題 (4 模組或 6 模組)
    has_executive_summary = bool(re.search(r'##\s+(?:[📌一1]\s*[,、.]?\s*)?(?:全書核心|一句話核心|Executive Summary|Core Message)', body, re.IGNORECASE))
    has_concepts = bool(re.search(r'##\s+(?:[🧠二2]\s*[,、.]?\s*)?(?:核心心智模型|核心觀點|Key Takeaways|Mental Models)', body, re.IGNORECASE))
    has_playbook = bool(re.search(r'##\s+(?:[🛠️三3]\s*[,、.]?\s*)?(?:實踐清單|實踐建議|行動法則|Actionable)', body, re.IGNORECASE))
    has_connections = bool(re.search(r'##\s+(?:[🔗四4六6]\s*[,、.]?\s*)?(?:Obsidian|概念關聯|概念標籤|Knowledge Graph)', body, re.IGNORECASE))

    if not has_executive_summary:
        errors.append("缺少模組一：全書核心 / 一句話核心 (Core Message)")
    if not has_concepts:
        errors.append("缺少模組二：核心心智模型 / 核心觀點 (Mental Models / Key Takeaways)")
    if not has_playbook:
        errors.append("缺少模組三/四：實踐清單 / 行動守則 (Actionable Playbook)")
    if not has_connections:
        errors.append("缺少概念關聯模組：Obsidian 概念關聯 (Knowledge Graph Connections)")

    return errors

def validate_concept(file_path: Path) -> list[str]:
    """驗證 Concept 檔案格式。"""
    errors = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [f"無法讀取檔案: {e}"]

    meta, body = parse_frontmatter(content)
    
    # 1. 檢驗 Frontmatter 必要屬性
    required_meta = ["slug", "title", "type", "status"]
    for rm in required_meta:
        if rm not in meta or not meta[rm]:
            errors.append(f"缺少 Frontmatter 必要屬性: '{rm}'")

    # 2. 檢驗 Title 是否為繁中名稱（禁止直接以英文 slug 當 title）
    title_str = meta.get("title", "")
    if title_str:
        # 若 title 完全沒有中文字元，視為違規
        if not re.search(r'[\u4e00-\u9fa5]', title_str):
            errors.append(f"Frontmatter 'title' 必須為繁體中文名稱，禁止直接使用純英文: '{title_str}'")

    # 3. 檢驗四大核心章節
    has_definition = bool(re.search(r'##\s+(?:📌\s*)?概念定義', body))
    has_mechanism = bool(re.search(r'##\s+(?:🧠\s*)?運作機制與核心價值', body))
    has_pitfalls = bool(re.search(r'##\s+(?:⚠️\s*)?常見誤區與邊界條件', body))
    has_backlinks = bool(re.search(r'##\s+(?:🔗\s*)?關聯資料', body))

    if not has_definition:
        errors.append("缺少章節：## 📌 概念定義")
    if not has_mechanism:
        errors.append("缺少章節：## 🧠 運作機制與核心價值")
    if not has_pitfalls:
        errors.append("缺少章節：## ⚠️ 常見誤區與邊界條件")
    if not has_backlinks:
        errors.append("缺少章節：## 🔗 關聯資料")

    # 4. 內文字數檢查（防單行佔位符）
    clean_body = re.sub(r'#.*', '', body).strip()
    if len(clean_body) < 120:
        errors.append(f"內文過於簡略 ({len(clean_body)} 字元 < 120 字元)，嚴禁單行佔位符，必須提煉機制與核心價值！")

    return errors

def main():
    parser = argparse.ArgumentParser(description="Validate Obsidian summaries & concepts format.")
    parser.add_argument("--target", help="Specific file to validate")
    args = parser.parse_args()

    total_checked = 0
    total_errors = 0

    print("==========================================")
    print("      BoBo-wiki Schema Validator          ")
    print("==========================================")

    if args.target:
        target_path = Path(args.target)
        if not target_path.exists():
            print(f"❌ 找不到目標檔案: {target_path}")
            sys.exit(1)
        
        is_summary = "summaries" in str(target_path)
        is_concept = "concepts" in str(target_path)
        
        if is_summary:
            errs = validate_summary(target_path)
        elif is_concept:
            errs = validate_concept(target_path)
        else:
            print("⚠️ 未知的檔案類型，僅支援 summaries 或 concepts")
            sys.exit(0)
            
        if errs:
            print(f"❌ [{target_path.name}] 發現 {len(errs)} 項格式錯誤：")
            for e in errs:
                print(f"   - {e}")
            sys.exit(1)
        else:
            print(f"✅ [{target_path.name}] 100% 符合規範！")
            sys.exit(0)

    # 批量檢查 summaries
    if SUMMARIES_DIR.exists():
        print(f"\n🔍 正在驗證 wiki/summaries/ ...")
        for f in sorted(SUMMARIES_DIR.glob("*.md")):
            total_checked += 1
            errs = validate_summary(f)
            if errs:
                total_errors += 1
                print(f"❌ [Summary] {f.name} 不合規:")
                for e in errs:
                    print(f"   - {e}")

    # 批量檢查 concepts
    if CONCEPTS_DIR.exists():
        print(f"\n🔍 正在驗證 wiki/concepts/ ...")
        for f in sorted(CONCEPTS_DIR.glob("*.md")):
            total_checked += 1
            errs = validate_concept(f)
            if errs:
                total_errors += 1
                print(f"❌ [Concept] {f.name} 不合規:")
                for e in errs:
                    print(f"   - {e}")

    print("\n==========================================")
    print(f"驗證完成：共檢查 {total_checked} 個檔案，{total_errors} 個檔案有格式瑕疵。")
    print("==========================================")

    if total_errors > 0:
        print("🛑 驗收未通過！請修復上述格式瑕疵。")
        sys.exit(1)
    else:
        print("🎉 恭喜！所有檔案均 100% 符合 Schema 規範！")
        sys.exit(0)

if __name__ == "__main__":
    main()
