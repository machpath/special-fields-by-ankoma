"""Load the add-on package fresh in a subprocess, as Anki does, and route
real `import_file` calls through it (see smoke_addon_load.py)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"


def test_addon_load_and_routing(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("PYTHONPATH", None)  # the script puts src/ on sys.path itself
    proc = subprocess.run(
        [sys.executable, str(HERE / "smoke_addon_load.py"), str(SRC), str(tmp_path)],
        env=env, capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "ADDON LOAD + ROUTING OK" in out, out
