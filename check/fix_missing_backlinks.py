#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修復缺失反向連結：在概念頁的 ## 🔗 關聯資料 區段加入指向 summary 的連結，並清除多餘的重複區段。
支援自訂 vault_root 路徑，若未指定則自動探索上一層或標準目錄。

用法：
    python check/fix_missing_backlinks.py
"""
import io, os, re, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def resolve_vault_root() -> Path:
    current_parent = Path(__file__).resolve().parent.parent
    if (current_parent / "wiki" / "summaries").exists():
        return current_parent
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
CONCEPTS_DIR = VAULT_ROOT / "wiki" / "concepts"
SUMMARIES_DIR = VAULT_ROOT / "wiki" / "summaries"

LINK_PATTERN = re.compile(r'\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]')


def slugify_target(raw_target: str) -> str:
    t = raw_target.strip()
    t = re.sub(r'^wiki/(summaries|concepts)/', '', t)
    t = re.sub(r'-summary$', '', t)
    return t


def load_summary_titles() -> dict:
    """Load {summary_slug: title} from frontmatter."""
    titles = {}
    if not SUMMARIES_DIR.exists():
        return titles
    for f in SUMMARIES_DIR.glob("*.md"):
        if f.name.startswith('.'):
            continue
        slug = re.sub(r'-summary$', '', f.stem)
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'title:\s*["\'](.+?)["\']', text)
        if not m:
            m = re.search(r'title:\s*([^\n\r]+)', text)
        titles[slug] = m.group(1).strip() if m else slug
    return titles


def fix_missing_backlinks(summary_titles: dict) -> list:
    """Add missing backlinks to concept pages. Returns list of (concept_slug, summary_slug) added."""
    fixes = []
    if not CONCEPTS_DIR.exists():
        return fixes

    for f in sorted(CONCEPTS_DIR.glob("*.md")):
        if f.name.startswith('.'):
            continue
        concept_slug = re.sub(r'-summary$', '', f.stem)
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.split('\n')

        # First, collect what summaries already link FROM this concept
        existing_summary_refs = set()
        for line in lines:
            m = LINK_PATTERN.search(line)
            if m:
                target = slugify_target(m.group(1))
                if target.endswith('-summary') or '/summaries/' in m.group(1):
                    existing_summary_refs.add(target.replace('-summary', ''))
                elif target in [re.sub(r'-summary$', '', sf.stem) for sf in SUMMARIES_DIR.glob("*.md")]:
                    existing_summary_refs.add(target)

        # Now find which summaries link TO this concept
        needs_backlink = []
        for sf in SUMMARIES_DIR.glob("*.md"):
            if sf.name.startswith('.'):
                continue
            s_slug = re.sub(r'-summary$', '', sf.stem)
            s_text = sf.read_text(encoding="utf-8", errors="replace")
            for m in LINK_PATTERN.finditer(s_text):
                raw = m.group(1).strip()
                if raw.startswith('wiki/concepts/'):
                    raw_slug = re.sub(r'^wiki/concepts/', '', raw)
                    raw_slug = re.sub(r'-summary$', '', raw_slug)
                    if raw_slug == concept_slug:
                        if s_slug not in existing_summary_refs:
                            needs_backlink.append(s_slug)
                else:
                    target = slugify_target(raw)
                    if target == concept_slug and target not in ['wiki/summaries/', 'raw/']:
                        if s_slug not in existing_summary_refs:
                            needs_backlink.append(s_slug)

        # Also clean up duplicate "## 相關概念" if ## 🔗 關聯資料 / 相關條目 already exists
        cleaned_lines = []
        has_primary_relations = False
        skip_duplicate_section = False
        
        for line in lines:
            if re.search(r'^#+\s*.*(關聯資料|相關條目|Knowledge Graph)', line, re.IGNORECASE):
                has_primary_relations = True
                skip_duplicate_section = False
                cleaned_lines.append(line)
                continue
            if has_primary_relations and re.search(r'^#+\s*.*相關概念', line, re.IGNORECASE):
                skip_duplicate_section = True
                continue
            if skip_duplicate_section:
                if line.startswith('#'):
                    skip_duplicate_section = False
                    cleaned_lines.append(line)
                elif line.strip().startswith('-') or line.strip() == '':
                    # skip list items under duplicate section
                    continue
                else:
                    skip_duplicate_section = False
                    cleaned_lines.append(line)
                continue
            cleaned_lines.append(line)

        lines = cleaned_lines
        
        if needs_backlink:
            new_lines = []
            added = False
            in_relations = False

            for line in lines:
                if not added and re.search(r'^#+\s*.*(關聯資料|相關概念|相關條目|Knowledge Graph)', line, re.IGNORECASE):
                    in_relations = True
                    new_lines.append(line)
                    continue

                if in_relations and not added:
                    if line.startswith('#'):
                        # Reached next section, insert before next section
                        for s_slug in sorted(set(needs_backlink)):
                            title = summary_titles.get(s_slug, s_slug)
                            new_lines.append(f"- [[wiki/summaries/{s_slug}-summary|{title}]]")
                        new_lines.append("")
                        new_lines.append(line)
                        added = True
                        in_relations = False
                        continue
                    new_lines.append(line)
                    continue

                new_lines.append(line)

            if not added and in_relations:
                for s_slug in sorted(set(needs_backlink)):
                    title = summary_titles.get(s_slug, s_slug)
                    new_lines.append(f"- [[wiki/summaries/{s_slug}-summary|{title}]]")
                added = True

            if not added:
                new_lines.append("")
                new_lines.append("## 🔗 關聯資料")
                for s_slug in sorted(set(needs_backlink)):
                    title = summary_titles.get(s_slug, s_slug)
                    new_lines.append(f"- [[wiki/summaries/{s_slug}-summary|{title}]]")
                added = True

            new_text = '\n'.join(new_lines)
            if new_text != text:
                f.write_text(new_text, encoding="utf-8")
                for s_slug in set(needs_backlink):
                    fixes.append((concept_slug, s_slug))
                print(f"  {concept_slug}.md: added {len(set(needs_backlink))} backlink(s)")
        elif lines != text.split('\n'):
            # Saved deduplication cleanup
            f.write_text('\n'.join(lines), encoding="utf-8")
            print(f"  {concept_slug}.md: cleaned duplicate section")

    return fixes


def main():
    summary_titles = load_summary_titles()
    print(f"Loaded {len(summary_titles)} summary titles")
    print(f"Scanning {len(list(CONCEPTS_DIR.glob('*.md')))} concept files in {VAULT_ROOT}...")
    fixes = fix_missing_backlinks(summary_titles)
    print(f"\nAdded {len(fixes)} missing backlink(s)")
    print("Done.")


if __name__ == "__main__":
    main()
