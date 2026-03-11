#!/usr/bin/env python3
"""
python_run — executes arbitrary Python code inside the sandbox.
Input (via TOOL_INPUT env var):
  {"code": "print(1+1)", "timeout": 30}
Output (stdout, JSON):
  {"stdout": "2\n", "stderr": "", "exit_code": 0}
"""

import json
import os
import subprocess
import sys
import tempfile

def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"invalid input JSON: {e}")
        return

    code = inp.get("code", "")
    if not code:
        fail("code field is required")
        return

    timeout = int(inp.get("timeout", 30))

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        out = {"stdout": "", "stderr": "timeout exceeded", "exit_code": -1}
    except Exception as e:
        out = {"stdout": "", "stderr": str(e), "exit_code": -1}
    finally:
        os.unlink(tmp_path)

    print(json.dumps(out))


def fail(msg: str):
    print(json.dumps({"stdout": "", "stderr": msg, "exit_code": 1}))


if __name__ == "__main__":
    main()
