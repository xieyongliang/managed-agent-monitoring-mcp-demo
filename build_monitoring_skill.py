#!/usr/bin/env python3
"""Build a credential-free Skill ZIP from an explicit file allowlist."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    skill = root / "skills/cloud-monitoring"
    files = {
        "SKILL.md": skill / "SKILL.md",
        "scripts/monitor.py": skill / "scripts/monitor.py",
        "scripts/requirements.txt": skill / "scripts/requirements.txt",
        "scripts/tools.py": root / "tools.py",
        "scripts/byteplus_tools.py": root / "byteplus_tools.py",
    }
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        for name, source in files.items():
            archive.write(source, "cloud-monitoring/" + name)
    print(f"Built {args.output} with {len(files)} allowlisted files")


if __name__ == "__main__":
    main()
