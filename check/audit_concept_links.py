#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BoBo-wiki 概念雙向連結稽核工具

對 wiki/summaries/ <-> wiki/concepts/ 之間的 [[ ]] wiki-link 做實際檔案掃描比對。
支援自訂 vault_root 路徑，若未指定則自動探索上一層或標準目錄。

用法：
    python check/audit_concept_links.py                 # 只印報告
    python check/audit_concept_links.py --write-report   # 同時寫入 outputs/sync-status.md
"""
import io
import os
import re
import sys
import datetime
from pathlib import Path

# 1. UTF-8 Windows 終端機編碼防護
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def resolve_vault_root() -> Path:
    # 1. If running inside BoBo-wiki
    current_parent = Path(__file__).resolve().parent.parent
    if (current_parent / "wiki" / "summaries").exists():
        return current_parent
    # 2. Standard paths
    candidates = [
        Path(r"g:\我的雲端硬碟\Obsidian\BoBo-wiki"),
        Path(os.path.expanduser(r"~\Desktop\obsidian\BoBo-wiki")),
        Path(os.path.expanduser(r"~\Desktop\Obsidian\BoBo-wiki")),
    ]
    for c in candidates:
        if (c / "wiki" / "summaries").exists():
            return c
    return current_parent

VAULT_ROOT = resolve_vault_root()
SUMMARIES_DIR = VAULT_ROOT / "wiki" / "summaries"
CONCEPTS_DIR = VAULT_ROOT / "wiki" / "concepts"

LINK_PATTERN = re.compile(r'\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]')


def slugify_target(raw_target: str) -> str:
    """去除 wiki/summaries/ 或 wiki/concepts/ 路徑前綴，去除結尾 -summary 後綴。"""
    t = raw_target.strip()
    t = re.sub(r'^wiki/(summaries|concepts)/', '', t)
    t = re.sub(r'-summary$', '', t)
    return t


def load_vault_files(directory: Path) -> dict:
    """回傳 {slug: 完整路徑} 對照表，slug 一律去除 -summary 後綴以統一比對基準。"""
    result = {}
    if not directory.exists():
        return result
    for f in sorted(directory.glob("*.md")):
        if f.name.startswith("."):
            continue
        slug = re.sub(r'-summary$', '', f.stem)
        result[slug] = f
    return result


def extract_summary_targets(text: str, concept_slugs: set, summary_slugs: set):
    """從概念頁全文抓出「意圖指向 summary」的連結目標 slug。"""
    targets = set()
    ambiguous = set()
    for m in LINK_PATTERN.finditer(text):
        raw = m.group(1).strip()
        if raw.startswith('raw/'):
            continue
        if raw.startswith('wiki/concepts/'):
            continue
        is_explicit_summary = raw.startswith('wiki/summaries/') or raw.endswith('-summary')
        slug = slugify_target(raw)
        if is_explicit_summary:
            targets.add(slug)
            continue
        is_concept = slug in concept_slugs
        is_summary = slug in summary_slugs
        if is_concept and is_summary:
            ambiguous.add(slug)
            continue
        if is_concept:
            continue
        targets.add(slug)
    return targets, ambiguous


def extract_concept_targets(text: str) -> set:
    """從摘要全文抓出所有連向 concept 的目標 slug（前向連結）。"""
    targets = set()
    for m in LINK_PATTERN.finditer(text):
        raw = m.group(1).strip()
        if raw.startswith('raw/') or raw.startswith('outputs/'):
            continue
        targets.add(slugify_target(raw))
    return targets


def audit():
    summaries = load_vault_files(SUMMARIES_DIR)
    concepts = load_vault_files(CONCEPTS_DIR)
    concept_slugs = set(concepts.keys())
    summary_slugs = set(summaries.keys())

    summary_to_concepts = {}
    concept_to_summaries = {}

    for slug, path in summaries.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        summary_to_concepts[slug] = extract_concept_targets(text)

    concept_ambiguous = {}
    for slug, path in concepts.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        targets, ambiguous = extract_summary_targets(text, concept_slugs, summary_slugs)
        concept_to_summaries[slug] = targets
        if ambiguous:
            concept_ambiguous[slug] = ambiguous

    report = {
        "missing_concept_file": [],
        "missing_backlink": [],
        "orphan_backlink": [],
        "unreferenced_concept": [],
        "ambiguous_bare_link": [],
    }
    for c_slug, amb_set in concept_ambiguous.items():
        for target_slug in sorted(amb_set):
            report["ambiguous_bare_link"].append((c_slug, target_slug))

    for s_slug, linked_concepts in summary_to_concepts.items():
        for c_slug in linked_concepts:
            if c_slug not in concept_slugs:
                if c_slug not in summary_slugs:
                    report["missing_concept_file"].append((s_slug, c_slug))
                continue
            back = concept_to_summaries.get(c_slug, set())
            if s_slug not in back:
                report["missing_backlink"].append((s_slug, c_slug))

    for c_slug, linked_summaries in concept_to_summaries.items():
        for s_slug in linked_summaries:
            if s_slug not in summary_slugs:
                report["orphan_backlink"].append((c_slug, s_slug))
        if not linked_summaries:
            report["unreferenced_concept"].append(c_slug)

    return report, len(summaries), len(concepts)


def format_report_markdown(report: dict, n_summaries: int, n_concepts: int, scanned_at: str) -> str:
    total_issues = (
        len(report["missing_concept_file"])
        + len(report["missing_backlink"])
        + len(report["orphan_backlink"])
        + len(report["ambiguous_bare_link"])
    )
    
    lines = [f"# Wiki 連結健康檢查 — {scanned_at}", ""]
    lines.append(f"### 掃描摘要統計")
    lines.append(f"- **掃描範圍**：{n_summaries} 篇摘要 (`wiki/summaries/`)、{n_concepts} 篇概念頁 (`wiki/concepts/`)")
    lines.append(f"- **檢查狀態**：{'⚠️ 發現需注意項目' if total_issues > 0 else '✅ 全部連結正常'}")
    lines.append(f"- **異常統計**：缺失概念頁 {len(report['missing_concept_file'])} 筆 | 缺失反向連結 {len(report['missing_backlink'])} 筆 | 孤兒死連結 {len(report['orphan_backlink'])} 筆 | 孤立概念頁 {len(report['unreferenced_concept'])} 筆 | 歧義連結 {len(report['ambiguous_bare_link'])} 筆")
    lines.append("")

    def section(title, items, empty_msg, formatter):
        lines.append(f"### {title}")
        if not items:
            lines.append(f"✅ {empty_msg}")
        else:
            lines.append(f"⚠️ 發現 {len(items)} 筆：")
            for it in items:
                lines.append(f"- {formatter(it)}")
        lines.append("")

    section("缺失概念頁（summary 連到但 wiki/concepts/ 無對應檔案）",
             sorted(report["missing_concept_file"]), "無缺失",
             lambda it: f"`{it[0]}` -> `[[{it[1]}]]`（概念頁不存在）")
    section("缺失反向連結（summary 連了 concept，但 concept 沒連回）",
             sorted(report["missing_backlink"]), "無缺失",
             lambda it: f"`{it[0]}` -> `{it[1]}`（{it[1]}.md 未回連此摘要）")
    section("孤兒反向連結（concept 連到不存在的 summary）",
             sorted(report["orphan_backlink"]), "無死連結",
             lambda it: f"`{it[0]}` -> `{it[1]}`（此摘要檔案不存在）")
    section("孤立概念頁（無任何 summary 連過去）",
             sorted(report["unreferenced_concept"]), "無孤立頁面",
             lambda it: f"`{it}`")
    section("裸連結歧義（slug 同時撞名概念頁與摘要，無法從文字判斷原意，需人工確認）",
             sorted(report["ambiguous_bare_link"]), "無歧義連結",
             lambda it: f"`{it[0]}` -> `[[{it[1]}]]`（{it[1]}.md 與 {it[1]}-summary.md 同時存在，"
                        f"建議改寫為 [[wiki/summaries/{it[1]}-summary|...]] 以消除歧義）")

    return "\n".join(lines)


def main():
    report, n_summaries, n_concepts = audit()
    scanned_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = format_report_markdown(report, n_summaries, n_concepts, scanned_at)
    print(md)

    if "--write-report" in sys.argv:
        out_path = VAULT_ROOT / "outputs" / "sync-status.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"\n✅ 已寫入真實健康檢查報告至：{out_path}")

    critical_issues = (
        len(report["missing_concept_file"])
        + len(report["missing_backlink"])
        + len(report["orphan_backlink"])
    )
    sys.exit(1 if critical_issues > 0 else 0)


if __name__ == "__main__":
    main()
