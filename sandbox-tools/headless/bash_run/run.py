#!/usr/bin/env python3
"""
bash_run — runs a bash script inside the sandbox.
Input  (TOOL_INPUT): {"script": "echo hello", "timeout": 30}
Output (stdout):     {"stdout": "...", "stderr": "...", "exit_code": 0}
"""

import json
import os
import subprocess
import tempfile


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        out({"error": f"invalid input JSON: {e}", "exit_code": 1})
        return

    script = inp.get("script", "")
    if not script:
        out({"error": "script field is required", "exit_code": 1})
        return

    timeout = int(inp.get("timeout", 30))

    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write("#!/usr/bin/env bash\nset -euo pipefail\n")
        f.write(script)
        tmp_path = f.name

    os.chmod(tmp_path, 0o755)

    try:
        result = subprocess.run(
            ["bash", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out({
            "stdout":    result.stdout,
            "stderr":    result.stderr,
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        out({"stdout": "", "stderr": "timeout exceeded", "exit_code": -1})
    except Exception as e:
        out({"stdout": "", "stderr": str(e), "exit_code": -1})
    finally:
        os.unlink(tmp_path)


def out(d: dict):
    print(json.dumps(d))


if __name__ == "__main__":
    main()
