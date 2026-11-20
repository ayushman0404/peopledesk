"""Run local repository checks from any directory; no live provider accounts."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
for suite in ("verify.py", "verify_company.py", "verify_copilot.py", "verify_routines.py"):
    print("\nRunning " + suite, flush=True)
    subprocess.run(
        [sys.executable, "-X", "utf8", str(root / "tests" / suite)],
        cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=True,
    )
print("\nAll requested suites passed.", flush=True)
