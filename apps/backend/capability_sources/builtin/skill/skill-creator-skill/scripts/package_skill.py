#!/usr/bin/env python3
"""
Skill Packager - Packages a skill folder for distribution or AIASys installation.

Supports two output formats:
  - .skill (zip) — for external sharing
  - directory copy — for AIASys builtin skill installation

Usage:
    python -m scripts.package_skill <path/to/skill-folder> [output-directory]

Example:
    python -m scripts.package_skill skills/public/my-skill
    python -m scripts.package_skill skills/public/my-skill ./dist
    python -m scripts.package_skill skills/public/my-skill --format dir
"""

import argparse
import fnmatch
import shutil
import sys
import zipfile
from pathlib import Path
from scripts.quick_validate import validate_skill

# Patterns to exclude when packaging skills.
EXCLUDE_DIRS = {"__pycache__", "node_modules"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}
# Directories excluded only at the skill root (not when nested deeper).
ROOT_EXCLUDE_DIRS = {"evals"}


def should_exclude(rel_path: Path) -> bool:
    """Check if a path should be excluded from packaging."""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    # rel_path is relative to skill_path.parent, so parts[0] is the skill
    # folder name and parts[1] (if present) is the first subdir.
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def package_skill(skill_path, output_dir=None, fmt="zip"):
    """
    Package a skill folder into a .skill file or copy as directory.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory (defaults to current directory)
        fmt: Output format — "zip" for .skill file, "dir" for directory copy (AIASys builtin)

    Returns:
        Path to the created output, or None if error
    """
    skill_path = Path(skill_path).resolve()

    # Validate skill folder exists
    if not skill_path.exists():
        print(f"Error: Skill folder not found: {skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"Error: Path is not a directory: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"Error: SKILL.md not found in {skill_path}")
        return None

    # Run validation before packaging
    print("Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"Validation failed: {message}")
        print("   Please fix the validation errors before packaging.")
        return None
    print(f"OK: {message}\n")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()

    if fmt == "dir":
        # Directory copy mode — for AIASys builtin skill installation
        target_dir = output_path / skill_name
        if target_dir.exists():
            print(f"Error: Target directory already exists: {target_dir}")
            return None
        import shutil
        shutil.copytree(skill_path, target_dir, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".DS_Store", "node_modules"
        ))
        print(f"Successfully copied skill to: {target_dir}")
        print(f"   Install to AIASys: cp -r {target_dir} apps/backend/skills/builtin/")
        return target_dir

    # Zip mode — .skill file for external sharing
    skill_filename = output_path / f"{skill_name}.skill"
    try:
        with zipfile.ZipFile(skill_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in skill_path.rglob('*'):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(skill_path.parent)
                if should_exclude(arcname):
                    print(f"  Skipped: {arcname}")
                    continue
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")

        print(f"\nSuccessfully packaged skill to: {skill_filename}")
        return skill_filename

    except Exception as e:
        print(f"Error creating .skill file: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Package a skill folder")
    parser.add_argument("skill_path", help="Path to the skill folder")
    parser.add_argument("output_dir", nargs="?", default=None, help="Output directory")
    parser.add_argument("--format", choices=["zip", "dir"], default="zip",
                        help="Output format: zip (default, .skill file) or dir (directory copy for AIASys)")
    args = parser.parse_args()

    print(f"Packaging skill: {args.skill_path}")
    if args.output_dir:
        print(f"   Output directory: {args.output_dir}")
    print(f"   Format: {args.format}")
    print()

    result = package_skill(args.skill_path, args.output_dir, fmt=args.format)

    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
