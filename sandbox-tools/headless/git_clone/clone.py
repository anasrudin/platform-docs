#!/usr/bin/env python3
"""
git_clone — clones a git repository into the sandbox work directory.
Input (TOOL_INPUT): {"url": "https://github.com/...", "branch": "main", "depth": 1}
Output: {"path": "/work/repo", "files": ["README.md", ...], "exit_code": 0}
"""

import json
import os
import subprocess
import sys

WORK_DIR = "/work"


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"invalid input: {e}")
        return

    url = inp.get("url", "")
    if not url:
        fail("url field is required")
        return

    branch = inp.get("branch", "")
    depth = int(inp.get("depth", 1))

    os.makedirs(WORK_DIR, exist_ok=True)
    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = os.path.join(WORK_DIR, repo_name)

    cmd = ["git", "clone", "--depth", str(depth)]
    if branch:
        cmd += ["--branch", branch]
    cmd += [url, dest]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(json.dumps({
            "path": "",
            "files": [],
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }))
        return

    # List top-level files.
    files = os.listdir(dest) if os.path.isdir(dest) else []
    print(json.dumps({"path": dest, "files": sorted(files), "exit_code": 0}))


def fail(msg: str):
    print(json.dumps({"path": "", "files": [], "stderr": msg, "exit_code": 1}))


if __name__ == "__main__":
    main()
