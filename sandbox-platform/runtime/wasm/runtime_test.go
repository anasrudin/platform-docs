package wasm

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/sandbox/platform/pkg/types"
)

// ── detectMode ────────────────────────────────────────────────────────────────

func TestDetectMode_EnvVarSim(t *testing.T) {
	t.Setenv("WASM_MODE", "sim")
	if got := detectMode("wasmtime"); got != "sim" {
		t.Fatalf("want sim, got %q", got)
	}
}

func TestDetectMode_EnvVarReal(t *testing.T) {
	t.Setenv("WASM_MODE", "real")
	if got := detectMode("wasmtime"); got != "real" {
		t.Fatalf("want real, got %q", got)
	}
}

func TestDetectMode_AutoFallsToSimWhenBinaryMissing(t *testing.T) {
	t.Setenv("WASM_MODE", "")
	mode := detectMode("nonexistent-binary-xyz-9999")
	if mode != "sim" {
		t.Fatalf("want sim (binary absent), got %q", mode)
	}
}

// ── sim execution ─────────────────────────────────────────────────────────────

func newSimRuntime(t *testing.T) *Runtime {
	t.Helper()
	t.Setenv("WASM_MODE", "sim")
	return NewRuntime()
}

func TestSimExec_Echo_ReturnsInputAsJSON(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t1",
		Tool:  "echo",
		Input: map[string]any{"msg": "hello", "n": float64(42)},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d (stderr: %s)", res.ExitCode, res.Stderr)
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(res.Stdout), &out); err != nil {
		t.Fatalf("stdout not JSON: %v\nstdout: %s", err, res.Stdout)
	}
	if out["msg"] != "hello" {
		t.Fatalf("echo: want msg=hello in output, got %v", out["msg"])
	}
}

func TestSimExec_Hello_ContainsName(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{ID: "t2", Tool: "hello", Input: map[string]any{"name": "Platform"}}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d", res.ExitCode)
	}
	if !strings.Contains(res.Stdout, "Platform") {
		t.Fatalf("hello: want 'Platform' in output, got: %s", res.Stdout)
	}
}

func TestSimExec_Hello_DefaultName(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{ID: "t3", Tool: "hello", Input: map[string]any{}}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if !strings.Contains(res.Stdout, "World") {
		t.Fatalf("hello default: want 'World', got: %s", res.Stdout)
	}
}

func TestSimExec_JSONParse_ValidJSON(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t4",
		Tool:  "json_parse",
		Input: map[string]any{"data": `{"key":"value","n":1}`},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d (stderr: %s)", res.ExitCode, res.Stderr)
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(res.Stdout), &out); err != nil {
		t.Fatalf("json_parse output not JSON: %v\nstdout: %s", err, res.Stdout)
	}
	if out["key"] != "value" {
		t.Fatalf("json_parse: want key=value, got %v", out["key"])
	}
}

func TestSimExec_JSONParse_MissingDataField(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{ID: "t5", Tool: "json_parse", Input: map[string]any{}}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 1 {
		t.Fatalf("json_parse missing data: want ExitCode=1, got %d", res.ExitCode)
	}
	if res.Stderr == "" {
		t.Fatal("json_parse missing data: want non-empty stderr")
	}
}

func TestSimExec_JSONParse_InvalidJSON(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t6",
		Tool:  "json_parse",
		Input: map[string]any{"data": "not { valid json"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 1 {
		t.Fatalf("json_parse invalid JSON: want ExitCode=1, got %d", res.ExitCode)
	}
}

func TestSimExec_HTMLParse(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t7",
		Tool:  "html_parse",
		Input: map[string]any{"html": "<html><body>hello</body></html>"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("html_parse: ExitCode want 0, got %d", res.ExitCode)
	}
	if !strings.Contains(res.Stdout, "bytes") {
		t.Fatalf("html_parse: want 'bytes' in output, got: %s", res.Stdout)
	}
}

func TestSimExec_MarkdownConvert(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t8",
		Tool:  "markdown_convert",
		Input: map[string]any{"markdown": "# Title"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("markdown_convert: ExitCode want 0, got %d", res.ExitCode)
	}
	if !strings.Contains(res.Stdout, "html") {
		t.Fatalf("markdown_convert: want 'html' in output, got: %s", res.Stdout)
	}
}

func TestSimExec_UnknownTool_FallsBackToEcho(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "t9",
		Tool:  "no_such_tool_xyz",
		Input: map[string]any{"x": "1"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	// Falls back to echo handler — should succeed
	if res.ExitCode != 0 {
		t.Fatalf("unknown tool fallback: want ExitCode=0, got %d", res.ExitCode)
	}
}

// ── real mode fallback ────────────────────────────────────────────────────────

// TestRealExec_FallsBackToSim verifies that when the WASM module cannot be
// downloaded (unreachable MinIO), realExec falls back to simExec transparently.
func TestRealExec_FallsBackToSimOnMissingModule(t *testing.T) {
	t.Setenv("WASM_MODE", "real")
	t.Setenv("WASM_CACHE_DIR", t.TempDir())   // empty cache, no local module
	t.Setenv("MINIO_ENDPOINT", "http://127.0.0.1:1") // unreachable port
	r := NewRuntime()
	job := types.Job{
		ID:    "t10",
		Tool:  "echo",
		Input: map[string]any{"x": "fallback-test"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	// realExec → module download fails → falls back to simExec (echo handler)
	if res.ExitCode != 0 {
		t.Fatalf("real-exec fallback: want ExitCode=0, got %d (stderr: %s)", res.ExitCode, res.Stderr)
	}
}

// ── custom handler registration ───────────────────────────────────────────────

func TestRegisterHandler_CustomTool(t *testing.T) {
	r := newSimRuntime(t)
	r.RegisterHandler("my_tool", func(input map[string]any) (string, error) {
		return "custom-result", nil
	})
	job := types.Job{ID: "t11", Tool: "my_tool", Input: map[string]any{}}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.Stdout != "custom-result" {
		t.Fatalf("custom handler: want 'custom-result', got %q", res.Stdout)
	}
}

// ── Health ────────────────────────────────────────────────────────────────────

func TestHealth_SimMode(t *testing.T) {
	r := newSimRuntime(t)
	if err := r.Health(); err != nil {
		t.Fatalf("Health in sim mode: %v", err)
	}
}

func TestName_IncludesMode(t *testing.T) {
	r := newSimRuntime(t)
	if !strings.Contains(r.Name(), "sim") {
		t.Fatalf("Name should contain 'sim', got %q", r.Name())
	}
}

func TestTier(t *testing.T) {
	r := newSimRuntime(t)
	if r.Tier() != types.TierWASM {
		t.Fatalf("Tier want wasm, got %v", r.Tier())
	}
}
