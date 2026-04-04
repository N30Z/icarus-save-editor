"""
update_data.py — Update data/ JSON tables from the Icarus data.pak.

Extracts data.pak to a temp directory using UnrealPak, then copies new or
changed files into data/, reporting every file that was added or modified.

Usage:
    python update_data.py [--dry-run]
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UNREALPAK = Path(__file__).parent / "assets" / "UnrealPak" / "Engine" / "Binaries" / "Win64" / "UnrealPak.exe"
DATA_PAK  = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Content\Data\data.pak")
DATA_DIR  = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_pak(pak: Path, out: Path) -> None:
    """Run UnrealPak -Extract into out/."""
    result = subprocess.run(
        [str(UNREALPAK), str(pak), "-Extract", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"UnrealPak failed:\n{result.stderr[-2000:]}")


def files_equal(a: Path, b: Path) -> bool:
    """True if both files exist and have identical content."""
    if not a.exists() or not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()


def pretty_json(path: Path) -> None:
    """Re-format a JSON file with 4-space indent in place (no-op if invalid)."""
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # leave as-is if not valid JSON


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    print(f"Source : {DATA_PAK}")
    print(f"Target : {DATA_DIR}")
    print(f"Dry-run: {dry_run}")
    print("-" * 60)

    if not UNREALPAK.exists():
        raise FileNotFoundError(f"UnrealPak not found: {UNREALPAK}")
    if not DATA_PAK.exists():
        raise FileNotFoundError(f"data.pak not found: {DATA_PAK}")

    with tempfile.TemporaryDirectory(prefix="icarus_data_") as tmp_str:
        tmp = Path(tmp_str)

        print("Extracting data.pak …")
        extract_pak(DATA_PAK, tmp)

        # UnrealPak preserves the build-machine path inside the pak.
        # Find the actual root that contains our JSON files.
        # Walk until we find a directory that has DataTableMetadata.json.
        extracted_root = None
        for candidate in [tmp, *tmp.rglob("DataTableMetadata.json")]:
            if candidate.name == "DataTableMetadata.json":
                extracted_root = candidate.parent
                break

        if extracted_root is None:
            raise RuntimeError("Could not locate DataTableMetadata.json in extracted files")

        print(f"Extracted root: {extracted_root}")
        print()

        added = []
        updated = []
        skipped = 0

        for src in sorted(extracted_root.rglob("*.json")):
            rel = src.relative_to(extracted_root)
            dst = DATA_DIR / rel

            if files_equal(src, dst):
                skipped += 1
                continue

            is_new = not dst.exists()

            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                pretty_json(dst)

            if is_new:
                added.append(rel)
                print(f"  [ADDED]   {rel}")
            else:
                updated.append(rel)
                print(f"  [UPDATED] {rel}")

        print()
        print("-" * 60)
        print(f"Added: {len(added)}  Updated: {len(updated)}  Unchanged: {skipped}")

        if dry_run and (added or updated):
            print("(dry-run — no files written)")


if __name__ == "__main__":
    main()
