#!/usr/bin/env python3
"""
file_ops — read, write, list, delete files within the sandbox work directory.
Input: {"op": "read|write|list|delete", "path": "...", "content": "..."}
Output: {"result": "...", "exit_code": 0}
"""

import json
import os

WORK_DIR = "/work"


def safe_path(p: str) -> str:
    """Resolve path and ensure it stays within WORK_DIR."""
    abs_p = os.path.realpath(os.path.join(WORK_DIR, p.lstrip("/")))
    if not abs_p.startswith(WORK_DIR):
        raise ValueError(f"path traversal detected: {p!r}")
    return abs_p


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        out({"error": f"invalid input: {e}", "exit_code": 1})
        return

    op = inp.get("op", "")
    path = inp.get("path", "")
    content = inp.get("content", "")

    try:
        if op == "read":
            full = safe_path(path)
            with open(full) as f:
                out({"result": f.read(), "exit_code": 0})

        elif op == "write":
            full = safe_path(path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
            out({"result": f"written {len(content)} bytes", "exit_code": 0})

        elif op == "list":
            full = safe_path(path or ".")
            entries = os.listdir(full)
            out({"result": sorted(entries), "exit_code": 0})

        elif op == "delete":
            full = safe_path(path)
            os.remove(full)
            out({"result": "deleted", "exit_code": 0})

        else:
            out({"error": f"unknown op: {op!r}", "exit_code": 1})

    except Exception as e:
        out({"error": str(e), "exit_code": 1})


def out(d: dict):
    print(json.dumps(d))


if __name__ == "__main__":
    main()
