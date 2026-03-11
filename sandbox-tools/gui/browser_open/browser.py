#!/usr/bin/env python3
"""
browser_open — opens a URL in a headless Chromium browser and captures a screenshot.
Input:  {"url": "https://example.com", "wait_ms": 2000, "screenshot": true}
Output: {"title": "...", "screenshot_b64": "...", "exit_code": 0}
"""

import base64
import json
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(json.dumps({"error": "playwright not installed", "exit_code": 1}))
    sys.exit(0)


def main():
    raw = os.environ.get("TOOL_INPUT", "{}")
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        out({"error": str(e), "exit_code": 1})
        return

    url = inp.get("url", "")
    if not url:
        out({"error": "url is required", "exit_code": 1})
        return

    wait_ms = int(inp.get("wait_ms", 2000))
    do_screenshot = inp.get("screenshot", True)

    display = os.environ.get("DISPLAY", ":99")
    os.environ["DISPLAY"] = display

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path="/usr/bin/chromium-browser",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(wait_ms)

            title = page.title()
            screenshot_b64 = ""
            if do_screenshot:
                img_bytes = page.screenshot(full_page=False)
                screenshot_b64 = base64.b64encode(img_bytes).decode()

            out({"title": title, "screenshot_b64": screenshot_b64, "exit_code": 0})
        except Exception as e:
            out({"error": str(e), "exit_code": 1})
        finally:
            browser.close()


def out(d: dict):
    print(json.dumps(d))


if __name__ == "__main__":
    main()
