"""
extract_icons.py — Bulk-extract 2DArt/UI icons from Icarus PAK files using umodel.

Reads data/icon_paths.json, converts /Game/... paths to umodel package names,
and exports all textures as PNG into assets/icons/.

Usage:
    python extract_icons.py [--workers N] [--dry-run]
"""

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UMODEL = str(Path(__file__).parent / "assets" / "umodel_win32" / "umodel_64.exe")
PAK_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Content\Paks"
OUT_DIR = str(Path(__file__).parent / "assets" / "icons")
ICON_PATHS_JSON = str(Path(__file__).parent / "data" / "icon_paths.json")

GAME_TAG = "ue4.27"
DEFAULT_WORKERS = 8

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_package(game_path: str) -> str:
    """Convert '/Game/Assets/2DArt/...' to 'Assets/2DArt/...' (umodel format)."""
    p = game_path.lstrip("/")
    p = re.sub(r"^Game/", "", p)
    return p


def run_umodel(package: str, dry_run: bool = False) -> tuple[str, bool, str]:
    """Run umodel for a single package. Returns (package, success, message)."""
    cmd = [
        UMODEL,
        "-export", "-png", "-nooverwrite",
        f"-game={GAME_TAG}",
        f"-path={PAK_PATH}",
        f"-out={OUT_DIR}",
        f"-pkg={package}",  # use -pkg= to avoid hyphens in names being parsed as flags
    ]

    if dry_run:
        return package, True, "dry-run"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip().splitlines()[-1]
            return package, False, err
        # Check if it was skipped (nooverwrite) or exported
        if "already exists" in result.stdout or "Skipping" in result.stdout:
            return package, True, "skipped"
        return package, True, "ok"
    except subprocess.TimeoutExpired:
        return package, False, "timeout"
    except Exception as e:
        return package, False, str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    dry_run = "--dry-run" in sys.argv
    workers = DEFAULT_WORKERS
    for arg in sys.argv[1:]:
        if arg.startswith("--workers="):
            workers = int(arg.split("=")[1])

    # Load paths
    with open(ICON_PATHS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    all_game_paths: list[str] = data["_all"]

    packages = [to_package(p) for p in all_game_paths]
    total = len(packages)

    print(f"Extracting {total} icons -> {OUT_DIR}")
    print(f"Workers: {workers}  |  Game: {GAME_TAG}  |  Dry-run: {dry_run}")
    print("-" * 60)

    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    ok = skipped = failed = 0
    failures: list[tuple[str, str]] = []
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_umodel, pkg, dry_run): pkg for pkg in packages}

        for i, future in enumerate(as_completed(futures), 1):
            pkg, success, msg = future.result()
            if success:
                if msg == "skipped":
                    skipped += 1
                else:
                    ok += 1
            else:
                failed += 1
                failures.append((pkg, msg))

            # Progress every 50 completions
            if i % 50 == 0 or i == total:
                elapsed = time.perf_counter() - t0
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                print(
                    f"  [{i:4d}/{total}]  ok={ok}  skipped={skipped}  "
                    f"failed={failed}  {rate:.1f}/s  ETA {eta:.0f}s"
                )

    elapsed = time.perf_counter() - t0
    print("-" * 60)
    print(f"Done in {elapsed:.1f}s — exported={ok}  skipped={skipped}  failed={failed}")

    if failures:
        print(f"\nFailed ({len(failures)}):")
        for pkg, err in failures[:20]:
            print(f"  {pkg}: {err}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

        fail_log = Path(__file__).parent / "extract_icons_failures.txt"
        with open(fail_log, "w", encoding="utf-8") as f:
            for pkg, err in failures:
                f.write(f"{pkg}\t{err}\n")
        print(f"\nFailure log: {fail_log}")


if __name__ == "__main__":
    main()
