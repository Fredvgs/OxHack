"""PostToolUse hook: ruff-format the .py file Claude just edited. Never blocks (always exits 0).

Reads the hook's JSON input on stdin; tool_input.file_path is absolute.
"""

import json
import subprocess
import sys

try:
    path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
except ValueError:
    sys.exit(0)
if path.endswith(".py"):
    subprocess.run([sys.executable, "-m", "ruff", "format", "--quiet", path], check=False)
