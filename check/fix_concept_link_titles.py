import io
import os
import re
import sys
from pathlib import Path

# Fix terminal encoding
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

vault_root = resolve_vault_root()
concepts_dir = vault_root / "wiki" / "concepts"
summaries_dir = vault_root / "wiki" / "summaries"

# 1. Load summary titles
summary_titles = {}
for sf in summaries_dir.glob("*.md"):
    if sf.name.startswith("."):
        continue
    slug = re.sub(r"-summary$", "", sf.stem)
    text = sf.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'title:\s*["\'](.+?)["\']', text)
    if not m:
        m = re.search(r'title:\s*([^\n\r]+)', text)
    if m:
        summary_titles[slug] = m.group(1).strip()
    else:
        summary_titles[slug] = slug

# 2. Load concept titles
concept_titles = {}
for cf in concepts_dir.glob("*.md"):
    if cf.name.startswith("."):
        continue
    slug = cf.stem
    text = cf.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'title:\s*["\'](.+?)["\']', text)
    if not m:
        m = re.search(r'title:\s*([^\n\r]+)', text)
    if m:
        concept_titles[slug] = m.group(1).strip()
    else:
        concept_titles[slug] = slug

print(f"Loaded {len(summary_titles)} summary titles and {len(concept_titles)} concept titles.")


def fix_links_in_text(text: str, target_cf_name: str = "") -> (str, int):
    lines = text.split("\n")
    new_lines = []
    replaced_count = 0

    for line in lines:
        def replace_link(match):
            nonlocal replaced_count
            full_match = match.group(0)
            prefix = match.group(1) or ""
            target_slug = match.group(2).strip()
            suffix = match.group(3) or ""
            alias = match.group(4).strip() if match.group(4) else None

            # Skip raw articles and outputs
            if prefix.startswith("raw/") or prefix.startswith("outputs/"):
                return full_match

            # Case A: Explicit or matching Summary
            if prefix.startswith("wiki/summaries/") or suffix == "-summary" or target_slug in summary_titles:
                if target_slug in summary_titles:
                    correct_title = summary_titles[target_slug]
                    has_chinese = bool(alias and re.search(r'[\u4e00-\u9fff]', alias))
                    if alias is None or not has_chinese:
                        replaced_count += 1
                        return f"[[wiki/summaries/{target_slug}-summary|{correct_title}]]"

            # Case B: Explicit or matching Concept
            if prefix.startswith("wiki/concepts/") or target_slug in concept_titles:
                if target_slug in concept_titles:
                    correct_title = concept_titles[target_slug]
                    has_chinese = bool(alias and re.search(r'[\u4e00-\u9fff]', alias))
                    if alias is None or not has_chinese:
                        replaced_count += 1
                        return f"[[{target_slug}|{correct_title}]]"

            return full_match

        new_line = re.sub(
            r'\[\[(?:(wiki/(?:summaries|concepts)/|raw/|outputs/))?([a-zA-Z0-9_-]+?)(-summary)?(?:\|([^\]]+))?\]\]',
            replace_link,
            line
        )
        new_lines.append(new_line)

    return "\n".join(new_lines), replaced_count


def process_single_file(file_path: Path):
    text = file_path.read_text(encoding="utf-8", errors="replace")
    new_text, count = fix_links_in_text(text, file_path.name)
    if new_text != text:
        file_path.write_text(new_text, encoding="utf-8")
        print(f"Updated {file_path.name}: fixed {count} link(s)")
    else:
        print(f"No changes needed for {file_path.name}")


def process_all_files():
    modified_files = 0
    total_replaced = 0
    for cf in sorted(concepts_dir.glob("*.md")):
        if cf.name.startswith("."):
            continue
        text = cf.read_text(encoding="utf-8", errors="replace")
        new_text, count = fix_links_in_text(text, cf.name)
        if new_text != text:
            cf.write_text(new_text, encoding="utf-8")
            modified_files += 1
            total_replaced += count
            print(f"Updated: {cf.name} ({count} fixed)")

    print(f"\nDone! Modified {modified_files} concept files, fixed {total_replaced} link aliases.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_name = sys.argv[1]
        target_file = concepts_dir / (target_name if target_name.endswith(".md") else f"{target_name}.md")
        if target_file.exists():
            process_single_file(target_file)
        else:
            print(f"File not found: {target_file}")
    else:
        process_all_files()
