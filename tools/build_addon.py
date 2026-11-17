"""Build the installable add-on file.

Usage: python3 tools/build_addon.py [--out DIR] [--version X.Y.Z]

Zips the contents of src/special_fields_by_ankoma/ (no top-level folder, no
__pycache__, no compiled files) into
<out>/special_fields_by_ankoma-<version>.ankiaddon, the layout AnkiWeb and
Anki's "Install from file" expect. The default output directory is outside
the project tree's source folders: ./dist (ignored by git).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "special_fields_by_ankoma"
REQUIRED = ["__init__.py", "model.py", "config.py", "engine.py", "settings_dialog.py",
            "import_flow.py", "config.json", "config.md", "manifest.json"]
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--version", default=None, help="overrides human_version in the packaged manifest")
    args = ap.parse_args()

    missing = [name for name in REQUIRED if not (SRC / name).is_file()]
    if missing:
        print("missing required files: " + ", ".join(missing), file=sys.stderr)
        return 1

    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    if args.version:
        manifest["human_version"] = args.version
    version = manifest.get("human_version", "0.0.0")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ("special_fields_by_ankoma-%s.ankiaddon" % version)

    names = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_dir() or path.suffix in SKIP_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(SRC).parts):
                continue
            arc = path.relative_to(SRC).as_posix()
            if arc == "manifest.json":
                zf.writestr(arc, json.dumps(manifest, indent=2) + "\n")
            else:
                zf.write(path, arc)
            names.append(arc)
    print("wrote %s (%d files)" % (target, len(names)))
    for n in names:
        print("  " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
