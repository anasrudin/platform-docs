// Package wasm provides an execution runtime for WASM-tier tools.
// In local dev mode, it executes built-in functions that simulate WASM modules.
package wasm

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Runtime executes WASM-tier tools.
// In local mode, it uses built-in Go functions that simulate WASM module execution.
type Runtime struct {
	handlers map[string]HandlerFunc
}

// HandlerFunc is a function that processes tool input and returns output.
type HandlerFunc func(input map[string]any) (string, error)

// NewRuntime creates a WASM Runtime with built-in tool handlers.
func NewRuntime() *Runtime {
	r := &Runtime{
		handlers: make(map[string]HandlerFunc),
	}
	r.registerBuiltins()
	return r
}

// Name returns the engine name.
func (r *Runtime) Name() string {
	return "wasm-runtime"
}

// Tier returns the tier this engine handles.
func (r *Runtime) Tier() types.Tier {
	return types.TierWASM
}

// Health checks if the runtime is operational.
func (r *Runtime) Health() error {
	return nil
}

// Execute runs a WASM-tier tool with the given job input.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	handler, ok := r.handlers[job.Tool]
	if !ok {
		// Default handler — echo the input back
		handler = r.handlers["echo"]
	}

	start := time.Now()
	output, err := handler(job.Input)
	duration := time.Since(start)

	if err != nil {
		slog.Error("wasm execution failed", "tool", job.Tool, "error", err, "duration_ms", duration.Milliseconds())
		return types.RuntimeResult{
			Stderr:   err.Error(),
			ExitCode: 1,
		}, nil
	}

	slog.Info("wasm execution complete", "tool", job.Tool, "duration_ms", duration.Milliseconds())
	return types.RuntimeResult{
		Stdout:   output,
		ExitCode: 0,
	}, nil
}

// RegisterHandler adds a custom tool handler.
func (r *Runtime) RegisterHandler(tool string, handler HandlerFunc) {
	r.handlers[tool] = handler
}

// registerBuiltins adds the default built-in tool handlers.
func (r *Runtime) registerBuiltins() {
	// echo — returns the input as JSON
	r.handlers["echo"] = func(input map[string]any) (string, error) {
		b, _ := json.MarshalIndent(input, "", "  ")
		return string(b), nil
	}

	// hello — returns a greeting
	r.handlers["hello"] = func(input map[string]any) (string, error) {
		name, _ := input["name"].(string)
		if name == "" {
			name = "World"
		}
		return fmt.Sprintf("Hello, %s! (from WASM runtime)", name), nil
	}

	// json_parse — parses and re-formats JSON
	r.handlers["json_parse"] = func(input map[string]any) (string, error) {
		data, ok := input["data"].(string)
		if !ok {
			return "", fmt.Errorf("missing 'data' field")
		}
		var parsed any
		if err := json.Unmarshal([]byte(data), &parsed); err != nil {
			return "", fmt.Errorf("invalid JSON: %w", err)
		}
		b, _ := json.MarshalIndent(parsed, "", "  ")
		return string(b), nil
	}

	// html_parse — simulates HTML parsing
	r.handlers["html_parse"] = func(input map[string]any) (string, error) {
		html, ok := input["html"].(string)
		if !ok {
			return "", fmt.Errorf("missing 'html' field")
		}
		return fmt.Sprintf("Parsed HTML document (%d bytes)", len(html)), nil
	}

	// markdown_convert — simulates markdown conversion
	r.handlers["markdown_convert"] = func(input map[string]any) (string, error) {
		md, ok := input["markdown"].(string)
		if !ok {
			return "", fmt.Errorf("missing 'markdown' field")
		}
		return fmt.Sprintf("<html><body>%s</body></html>", md), nil
	}
}
