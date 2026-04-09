#!/usr/bin/env python3
"""
office_automation — automates LibreOffice via subprocess (headless or display mode).
Supports: convert, print-to-pdf, merge-docs.
Input:  {"op": "convert", "input_file": "/work/doc.docx", "output_format": "pdf"}
Output: {"output_file": "/work/doc.pdf", "exit_code": 0}
"""

import json
import os
import subprocess

WORK_DIR = "/work"
LIBREOFFICE = "libreoffice"


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        out({"error": str(e), "exit_code": 1})
        return

    op = inp.get("op", "convert")

    try:
        if op == "convert":
            _convert(inp)
        elif op == "merge":
            _merge(inp)
        else:
            out({"error": f"unknown op: {op}", "exit_code": 1})
    except Exception as e:
        out({"error": str(e), "exit_code": 1})


def _convert(inp: dict):
    src = _safe(inp.get("input_file", ""))
    fmt = inp.get("output_format", "pdf")

    cmd = [
        LIBREOFFICE,
        "--headless",
        "--norestore",
        "--convert-to",
        fmt,
        "--outdir",
        WORK_DIR,
        src,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        out({"error": result.stderr, "exit_code": result.returncode})
        return

    base = os.path.splitext(os.path.basename(src))[0]
    output_file = os.path.join(WORK_DIR, f"{base}.{fmt}")
    out({"output_file": output_file, "exit_code": 0})


def _merge(inp: dict):
    files = [_safe(f) for f in inp.get("files", [])]
    if len(files) < 2:
        out({"error": "merge requires at least 2 files", "exit_code": 1})
        return
    out({"error": "merge not yet implemented", "exit_code": 1})


def _safe(path: str) -> str:
    abs_p = os.path.realpath(os.path.join(WORK_DIR, path.lstrip("/")))
    if not abs_p.startswith(WORK_DIR):
        raise ValueError("path traversal")
    return abs_p


def out(d: dict):
    print(json.dumps(d))


if __name__ == "__main__":
    main()
