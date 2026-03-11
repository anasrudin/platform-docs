package router

import "github.com/sandbox/platform/pkg/types"

// defaultRules returns the built-in tool → tier mapping.
func defaultRules() map[string]types.Tier {
	return map[string]types.Tier{
		// WASM tier — fast, stateless tools
		"html_parse":       types.TierWASM,
		"json_parse":       types.TierWASM,
		"markdown_convert": types.TierWASM,
		"docx_generate":    types.TierWASM,
		"echo":             types.TierWASM,
		"hello":            types.TierWASM,

		// MicroVM tier — I/O, network, subprocess
		"python_run": types.TierMicroVM,
		"bash_run":   types.TierMicroVM,
		"git_clone":  types.TierMicroVM,
		"file_ops":   types.TierMicroVM,

		// GUI tier — requires a display
		"browser_open":      types.TierGUI,
		"web_scrape":        types.TierGUI,
		"excel_edit":        types.TierGUI,
		"office_automation": types.TierGUI,
	}
}
