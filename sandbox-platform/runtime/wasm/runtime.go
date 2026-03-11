// Package wasm provides a Wasmtime-backed execution runtime for WASM-tier tools.
//
// Execution modes:
//   - "real" — runs .wasm modules fetched from MinIO via the `wasmtime` CLI
//   - "sim"  — built-in Go functions that simulate WASM module execution
//
// Mode is selected by:
//  1. WASM_MODE env var ("real" | "sim")
//  2. Presence of `wasmtime` in PATH (auto-detect: found → real, missing → sim)
package wasm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Config holds WASM runtime configuration from environment variables.
type Config struct {
	WasmtimeBin    string // WASMTIME_BIN, default "wasmtime" (resolved via PATH)
	MinIOEndpoint  string // MINIO_ENDPOINT
	MinIOAccessKey string // MINIO_ACCESS_KEY
	MinIOSecretKey string // MINIO_SECRET_KEY
	MinIOBucket    string // MINIO_WASM_BUCKET, default platform-modules
	ModuleCacheDir string // WASM_CACHE_DIR, default /var/sandbox/wasm-cache
	ExecTimeout    time.Duration
}

func configFromEnv() Config {
	return Config{
		WasmtimeBin:    envOr("WASMTIME_BIN", "wasmtime"),
		MinIOEndpoint:  envOr("MINIO_ENDPOINT", "http://localhost:9000"),
		MinIOAccessKey: envOr("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey: envOr("MINIO_SECRET_KEY", "minioadmin"),
		MinIOBucket:    envOr("MINIO_WASM_BUCKET", "platform-modules"),
		ModuleCacheDir: envOr("WASM_CACHE_DIR", "/var/sandbox/wasm-cache"),
		ExecTimeout:    30 * time.Second,
	}
}

// ── Runtime ───────────────────────────────────────────────────────────────────

// Runtime implements types.RuntimeEngine for WASM-tier tools.
type Runtime struct {
	cfg      Config
	store    *ModuleStore
	mode     string // "real" or "sim"
	handlers map[string]HandlerFunc
}

// HandlerFunc processes tool input in sim mode.
type HandlerFunc func(input map[string]any) (string, error)

// NewRuntime creates a WASM Runtime, auto-selecting real vs sim mode.
func NewRuntime() *Runtime {
	cfg := configFromEnv()
	mode := detectMode(cfg.WasmtimeBin)

	r := &Runtime{
		cfg:      cfg,
		store:    newModuleStore(cfg),
		mode:     mode,
		handlers: make(map[string]HandlerFunc),
	}
	r.registerBuiltins()

	slog.Info("wasm runtime initialised", "mode", mode)
	return r
}

// Name returns the engine identifier.
func (r *Runtime) Name() string {
	return fmt.Sprintf("wasm-%s", r.mode)
}

// Tier returns the execution tier handled by this runtime.
func (r *Runtime) Tier() types.Tier {
	return types.TierWASM
}

// Health checks whether the runtime is operational.
func (r *Runtime) Health() error {
	if r.mode == "sim" {
		return nil
	}
	if _, err := exec.LookPath(r.cfg.WasmtimeBin); err != nil {
		return fmt.Errorf("wasmtime not found: %w", err)
	}
	return nil
}

// Execute runs a WASM-tier tool in real or sim mode.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	if r.mode == "real" {
		return r.realExec(job)
	}
	return r.simExec(job)
}

// RegisterHandler adds a custom sim-mode tool handler.
func (r *Runtime) RegisterHandler(tool string, h HandlerFunc) {
	r.handlers[tool] = h
}

// ── Real execution ────────────────────────────────────────────────────────────

// realExec downloads the .wasm module and runs it via wasmtime.
// Input is passed as JSON on stdin; the module writes its result to stdout.
func (r *Runtime) realExec(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()
	slog.Info("wasm execute", "job_id", job.ID, "tool", job.Tool, "mode", "real")

	modulePath, err := r.store.Ensure(job.Tool)
	if err != nil {
		slog.Error("module download failed, falling back to sim", "tool", job.Tool, "err", err)
		return r.simExec(job)
	}

	inputJSON, err := json.Marshal(job.Input)
	if err != nil {
		return types.RuntimeResult{Stderr: "marshal input: " + err.Error(), ExitCode: 1}, nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), r.cfg.ExecTimeout)
	defer cancel()

	// wasmtime run <module.wasm> — reads JSON from stdin, writes result to stdout.
	cmd := exec.CommandContext(ctx, r.cfg.WasmtimeBin, "run", modulePath)
	cmd.Stdin = bytes.NewReader(inputJSON)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	execErr := cmd.Run()

	exitCode := 0
	if execErr != nil {
		if exitErr, ok := execErr.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			// wasmtime itself failed (not the module)
			return types.RuntimeResult{
				Stderr:   fmt.Sprintf("wasmtime error: %v", execErr),
				ExitCode: 1,
			}, nil
		}
	}

	slog.Info("wasm execute done",
		"job_id", job.ID,
		"tool", job.Tool,
		"exit_code", exitCode,
		"duration_ms", time.Since(start).Milliseconds(),
	)

	return types.RuntimeResult{
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
		ExitCode: exitCode,
	}, nil
}

// ── Simulation path ───────────────────────────────────────────────────────────

// simExec runs a built-in Go handler that mimics WASM module behaviour.
func (r *Runtime) simExec(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()
	slog.Info("wasm execute", "job_id", job.ID, "tool", job.Tool, "mode", "sim")

	handler, ok := r.handlers[job.Tool]
	if !ok {
		handler = r.handlers["echo"]
	}

	output, err := handler(job.Input)
	if err != nil {
		slog.Error("wasm sim execution failed", "tool", job.Tool, "err", err,
			"duration_ms", time.Since(start).Milliseconds())
		return types.RuntimeResult{Stderr: err.Error(), ExitCode: 1}, nil
	}

	slog.Info("wasm sim complete",
		"tool", job.Tool,
		"duration_ms", time.Since(start).Milliseconds(),
	)
	return types.RuntimeResult{Stdout: output, ExitCode: 0}, nil
}

// ── Built-in sim handlers ──────────────────────────────────────────────────────

func (r *Runtime) registerBuiltins() {
	r.handlers["echo"] = func(input map[string]any) (string, error) {
		b, _ := json.MarshalIndent(input, "", "  ")
		return string(b), nil
	}

	r.handlers["hello"] = func(input map[string]any) (string, error) {
		name, _ := input["name"].(string)
		if name == "" {
			name = "World"
		}
		return fmt.Sprintf("Hello, %s! (from WASM runtime)", name), nil
	}

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

	r.handlers["html_parse"] = func(input map[string]any) (string, error) {
		html, ok := input["html"].(string)
		if !ok {
			return "", fmt.Errorf("missing 'html' field")
		}
		return fmt.Sprintf("Parsed HTML document (%d bytes)", len(html)), nil
	}

	r.handlers["markdown_convert"] = func(input map[string]any) (string, error) {
		md, ok := input["markdown"].(string)
		if !ok {
			return "", fmt.Errorf("missing 'markdown' field")
		}
		return fmt.Sprintf("<html><body>%s</body></html>", md), nil
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// detectMode returns "real" if WASM_MODE=real or wasmtime is in PATH.
// Explicit WASM_MODE always wins.
func detectMode(wasmtimeBin string) string {
	if m := os.Getenv("WASM_MODE"); m == "real" || m == "sim" {
		slog.Info("WASM mode from WASM_MODE env", "mode", m)
		return m
	}
	if _, err := exec.LookPath(wasmtimeBin); err == nil {
		slog.Info("WASM mode auto-detected: wasmtime found", "mode", "real")
		return "real"
	}
	slog.Info("WASM mode auto-detected: wasmtime not in PATH", "mode", "sim")
	return "sim"
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
