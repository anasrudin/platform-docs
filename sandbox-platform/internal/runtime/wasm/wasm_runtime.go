// Package wasm provides an execution runtime for WASM-tier tools.
// It invokes the wasmtime CLI, which must be installed on the node.
// Target startup: ~10ms (module cache hit).
package wasm

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Runtime executes WASM modules via the wasmtime CLI.
type Runtime struct {
	moduleDir string
	cache     *ModuleCache
}

// NewRuntime creates a WASM Runtime. moduleDir is where .wasm files are stored.
func NewRuntime(moduleDir string) (*Runtime, error) {
	if err := os.MkdirAll(moduleDir, 0o755); err != nil {
		return nil, fmt.Errorf("create module dir: %w", err)
	}
	return &Runtime{
		moduleDir: moduleDir,
		cache:     NewModuleCache(),
	}, nil
}

// Execute runs a WASM module with the given job input.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	modulePath, err := r.cache.Resolve(r.moduleDir, job.Tool)
	if err != nil {
		return types.RuntimeResult{}, fmt.Errorf("resolve module %q: %w", job.Tool, err)
	}

	inputJSON := marshalInput(job.Input)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	start := time.Now()

	//nolint:gosec // modulePath comes from the trusted module cache
	cmd := exec.CommandContext(ctx, "wasmtime",
		"--allow-precompiled",
		modulePath,
		"--", inputJSON,
	)

	out, err := cmd.CombinedOutput()
	if err != nil {
		return types.RuntimeResult{
			Stderr:   string(out),
			ExitCode: exitCode(cmd),
		}, fmt.Errorf("wasmtime: %w", err)
	}

	slog.Info("wasm executed", "tool", job.Tool, "duration_ms", time.Since(start).Milliseconds())

	return types.RuntimeResult{
		Stdout:   string(out),
		ExitCode: 0,
	}, nil
}

// modulePath returns the full filesystem path for a tool's .wasm file.
func (r *Runtime) modulePath(tool string) string {
	return filepath.Join(r.moduleDir, tool+".wasm")
}
