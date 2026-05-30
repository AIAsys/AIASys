#!/usr/bin/env python3
"""
Merge all 画板/*.pen into a single aggregated .pen file.

Part of the pencil-design skill. Run from any directory by passing
the target design-set directory as an argument.

Strategy:
  - Each 画板/*.pen contains 1 top-level frame (children[0])
  - The aggregated .pen file collects all frames in its top-level children[]
  - Default mode keeps historical behavior: skip duplicates and append new frames
  - `--sync` rebuilds the aggregated file from the current artboards only,
    replacing existing frames by id and pruning stale/duplicate top-level views
  - All frames are repositioned in a grid layout
  - Handles JSON parse errors caused by smart/curly quotes (U+201C/U+201D)

Usage:
  # From the design-set directory (auto-detect main .pen file)
  python3 merge_artboards.py design/frontend/原型资产/工作区壳层

  # Dry-run (preview only)
  python3 merge_artboards.py design/frontend/原型资产/工作区壳层

  # Write merged result
  python3 merge_artboards.py design/frontend/原型资产 --write

  # Full sync (recommended after editing existing artboards)
  python3 merge_artboards.py design/frontend/原型资产 --sync --write

Directory layout expected:
  <target-dir>/
  ├── <name>-v1.pen       # Aggregated file (first *.pen found at top level)
  ├── 画板/                # Individual artboard files
  └── README.md
"""

import json
import glob
import re
import sys
import os

# Grid layout constants
ARTBOARD_WIDTH = 1600
ARTBOARD_HEIGHT = 1100
GRID_COLS = 4
GAP_X = 120
GAP_Y = 120
MARGIN = 80


def fix_smart_quotes(text: str) -> str:
    """Fix curly/smart quotes (U+201C/U+201D) in .pen JSON files.

    Two distinct problems:
      A) Smart quotes used as JSON structural delimiters → replace with ASCII "
      B) Smart quotes inside string content → escape as \"
    """
    # Phase 1: Fix key delimiters
    text = re.sub(r'\u201c([\w-]+)\u201d(\s*:)', r'"\1"\2', text)

    # Phase 2: Handle each line
    lines = text.split('\n')
    result = []
    for line in lines:
        if '\u201c' not in line and '\u201d' not in line:
            result.append(line)
            continue

        colon_pos = line.find(':')
        if colon_pos == -1:
            line = line.replace('\u201c', '\\"').replace('\u201d', '\\"')
            result.append(line)
            continue

        key_part = line[:colon_pos + 1]
        value_part = line[colon_pos + 1:]

        stripped = value_part.lstrip()
        if stripped and stripped[0] in ('\u201c', '\u201d'):
            first_open = value_part.find('\u201c')
            last_close = value_part.rfind('\u201d')
            if first_open != -1 and last_close != -1 and first_open < last_close:
                inner = value_part[first_open + 1:last_close]
                inner = inner.replace('\u201c', '\\"').replace('\u201d', '\\"')
                value_part = (
                    value_part[:first_open]
                    + '"'
                    + inner
                    + '"'
                    + value_part[last_close + 1:]
                )
        else:
            value_part = value_part.replace('\u201c', '\\"').replace('\u201d', '\\"')

        value_part = value_part.replace('\u201c', '\\"').replace('\u201d', '\\"')
        result.append(key_part + value_part)

    return '\n'.join(result)


def load_pen(path: str) -> dict:
    """Load a .pen file, auto-fixing smart quote issues if needed."""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fixed = fix_smart_quotes(text)
        return json.loads(fixed)


def compute_grid_positions(count: int) -> list[tuple[int, int]]:
    """Return (x, y) positions for `count` frames in a grid."""
    positions = []
    for i in range(count):
        col = i % GRID_COLS
        row = i // GRID_COLS
        x = MARGIN + col * (ARTBOARD_WIDTH + GAP_X)
        y = MARGIN + row * (ARTBOARD_HEIGHT + GAP_Y)
        positions.append((x, y))
    return positions


def find_main_pen(target_dir: str) -> str:
    """Find the aggregated .pen file in the target directory.

    Looks for *.pen files at the top level (not in 画板/).
    If multiple exist, prefers files matching *-v*.pen pattern.
    """
    candidates = [
        f for f in glob.glob(os.path.join(target_dir, "*.pen"))
        if os.path.isfile(f)
    ]
    if not candidates:
        print(f"Error: no .pen files found in {target_dir}", file=sys.stderr)
        sys.exit(1)

    # Prefer versioned files like *-v1.pen
    versioned = [f for f in candidates if re.search(r'-v\d+\.pen$', f)]
    if versioned:
        return versioned[0]

    return candidates[0]


def main():
    write = "--write" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        script = os.path.basename(sys.argv[0])
        print(f"Usage: python3 {script} <target-dir> [--write] [--sync]")
        print(f"Example: python3 {script} design/frontend/原型资产 --sync --write")
        sys.exit(1)

    sync = "--sync" in sys.argv

    target_dir = os.path.abspath(args[0])
    if not os.path.isdir(target_dir):
        print(f"Error: {target_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    artboards_dir = None
    for dirname in ("画板", "artboards"):
        candidate = os.path.join(target_dir, dirname)
        if os.path.isdir(candidate):
            artboards_dir = candidate
            break
    if artboards_dir is None:
        print(f"Error: no 画板/ or artboards/ directory in {target_dir}", file=sys.stderr)
        sys.exit(1)

    main_file = find_main_pen(target_dir)
    print(f"Target: {target_dir}")
    print(f"Main file: {os.path.basename(main_file)}")

    # Load main file
    main_data = load_pen(main_file)
    existing_ids = {child['id'] for child in main_data['children']}

    print(f"  Existing artboards: {len(main_data['children'])}")
    for c in main_data['children']:
        print(f"    - {c['id']}: {c['name']}")

    # Collect artboards
    artboard_files = sorted(glob.glob(os.path.join(artboards_dir, "*.pen")))
    to_add = []
    sync_frames = []
    skipped = []
    errors = []
    seen_artboard_ids = {}

    for fpath in artboard_files:
        fname = os.path.basename(fpath)
        try:
            data = load_pen(fpath)
        except Exception as e:
            errors.append((fname, str(e)))
            continue

        children = data.get('children', [])
        if not children:
            skipped.append((fname, "empty children"))
            continue

        frame = children[0]
        artboard_id = frame.get('id', '?')
        artboard_name = frame.get('name', '?')

        if artboard_id in seen_artboard_ids:
            errors.append(
                (fname, f"duplicate artboard id={artboard_id} already provided by {seen_artboard_ids[artboard_id]}")
            )
            continue
        seen_artboard_ids[artboard_id] = fname

        sync_frames.append((fname, frame))

        if sync:
            print(f"  Will sync: {fname} (id={artboard_id}, name={artboard_name})")
            continue

        if artboard_id in existing_ids:
            skipped.append((fname, f"duplicate id={artboard_id}"))
            continue

        to_add.append((fname, frame))
        print(f"  Will add: {fname} (id={artboard_id}, name={artboard_name})")

    print(f"\nSummary:")
    print(f"  To add: {len(to_add)}")
    print(f"  Sync candidates: {len(sync_frames)}")
    print(f"  Skipped (duplicate/empty): {len(skipped)}")
    for fname, reason in skipped:
        print(f"    - {fname}: {reason}")
    print(f"  Errors: {len(errors)}")
    for fname, err in errors:
        print(f"    - {fname}: {err}")

    if sync:
        if not sync_frames:
            print("\nNo artboards found to sync. Done.")
            return
        all_children = [frame for _, frame in sync_frames]
        removed_count = max(len(main_data['children']) - len(all_children), 0)
        print(f"\nSync mode: rebuilding aggregated file from artboards only")
        print(f"  Previous top-level frames: {len(main_data['children'])}")
        print(f"  New top-level frames: {len(all_children)}")
        print(f"  Removed stale/duplicate frames: {removed_count}")
    else:
        if not to_add:
            print("\nNo new artboards to add. Done.")
            return

        # Merge
        all_children = list(main_data['children'])
        for _, frame in to_add:
            all_children.append(frame)

    # Reassign positions in a grid
    positions = compute_grid_positions(len(all_children))
    for child, (x, y) in zip(all_children, positions):
        child['x'] = x
        child['y'] = y

    main_data['children'] = all_children

    total = len(all_children)
    print(f"\nResult: {total} artboards total")

    if write:
        out = json.dumps(main_data, ensure_ascii=False, indent=2)
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f"Written to {main_file}")
    else:
        print("\n[DRY RUN] Use --write to actually write the file.")
        print("Artboard layout preview:")
        for i, child in enumerate(all_children):
            x, y = positions[i]
            if sync:
                marker = " (SYNC)"
            else:
                marker = " (existing)" if child['id'] in existing_ids else " (NEW)"
            print(f"  [{i+1}/{total}] ({x}, {y}) {child['id']}: {child['name']}{marker}")


if __name__ == "__main__":
    main()
