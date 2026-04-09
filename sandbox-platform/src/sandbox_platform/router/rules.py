"""Default tool-to-tier routing rules.

Mirrors internal/router/rules.go.
"""

from sandbox_platform.types import Tier


def default_rules() -> dict[str, Tier]:
    """Return the built-in tool → tier mapping."""
    return {
        # WASM tier — fast, stateless tools
        "html_parse": Tier.WASM,
        "json_parse": Tier.WASM,
        "markdown_convert": Tier.WASM,
        "docx_generate": Tier.WASM,
        "echo": Tier.WASM,
        "hello": Tier.WASM,
        # MicroVM tier — I/O, network, subprocess
        "python_run": Tier.MICROVM,
        "bash_run": Tier.MICROVM,
        "git_clone": Tier.MICROVM,
        "file_ops": Tier.MICROVM,
        # GUI tier — requires a display
        "browser_open": Tier.GUI,
        "web_scrape": Tier.GUI,
        "excel_edit": Tier.GUI,
        "office_automation": Tier.GUI,
    }
