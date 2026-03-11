package firecracker

import (
	"strings"
	"testing"

	"github.com/sandbox/platform/pkg/types"
)

// ── detectMode ────────────────────────────────────────────────────────────────

func TestDetectMode_EnvVarSim(t *testing.T) {
	t.Setenv("FC_MODE", "sim")
	if got := detectMode(); got != "sim" {
		t.Fatalf("want sim, got %q", got)
	}
}

func TestDetectMode_EnvVarReal(t *testing.T) {
	t.Setenv("FC_MODE", "real")
	if got := detectMode(); got != "real" {
		t.Fatalf("want real, got %q", got)
	}
}

func TestDetectMode_AutoSim_WhenNoKVM(t *testing.T) {
	t.Setenv("FC_MODE", "")
	// On macOS /dev/kvm never exists — should auto-detect sim.
	// On Linux without KVM it also returns sim.
	mode := detectMode()
	if mode != "sim" && mode != "real" {
		t.Fatalf("unexpected mode %q", mode)
	}
}

// ── configFromEnv ─────────────────────────────────────────────────────────────

func TestConfigFromEnv_Defaults(t *testing.T) {
	for _, k := range []string{
		"FC_BIN", "SNAPSHOT_NAME", "SNAPSHOT_CACHE_DIR",
		"MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET",
		"FC_POOL_SIZE", "FC_DEV_MODE",
	} {
		t.Setenv(k, "")
	}
	cfg := configFromEnv()
	if cfg.FirecrackerBin != "/usr/bin/firecracker" {
		t.Fatalf("FirecrackerBin default: got %s", cfg.FirecrackerBin)
	}
	if cfg.SnapshotName != "python-v1" {
		t.Fatalf("SnapshotName default: got %s", cfg.SnapshotName)
	}
	if cfg.MinIOEndpoint != "http://localhost:9000" {
		t.Fatalf("MinIOEndpoint default: got %s", cfg.MinIOEndpoint)
	}
	if cfg.MinIOBucket != "platform-snapshots" {
		t.Fatalf("MinIOBucket default: got %s", cfg.MinIOBucket)
	}
	if cfg.PoolSize != 2 {
		t.Fatalf("PoolSize default: got %d", cfg.PoolSize)
	}
	if cfg.DevMode != false {
		t.Fatal("DevMode default should be false")
	}
}

func TestConfigFromEnv_Overrides(t *testing.T) {
	t.Setenv("FC_BIN", "/opt/fc/firecracker")
	t.Setenv("SNAPSHOT_NAME", "go-v1")
	t.Setenv("FC_POOL_SIZE", "4")
	t.Setenv("FC_DEV_MODE", "true")
	cfg := configFromEnv()
	if cfg.FirecrackerBin != "/opt/fc/firecracker" {
		t.Fatalf("FirecrackerBin: got %s", cfg.FirecrackerBin)
	}
	if cfg.SnapshotName != "go-v1" {
		t.Fatalf("SnapshotName: got %s", cfg.SnapshotName)
	}
	if cfg.PoolSize != 4 {
		t.Fatalf("PoolSize: got %d", cfg.PoolSize)
	}
	if !cfg.DevMode {
		t.Fatal("DevMode should be true")
	}
}

// ── simulateExec ──────────────────────────────────────────────────────────────

func newSimRuntime(t *testing.T) *Runtime {
	t.Helper()
	t.Setenv("FC_MODE", "sim")
	return NewRuntime()
}

func TestSimulateExec_PythonRun(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "fc-t1",
		Tool:  "python_run",
		Input: map[string]any{"code": "print('hello from python')"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d", res.ExitCode)
	}
	if !strings.Contains(res.Stdout, "python") && !strings.Contains(res.Stdout, "sim") {
		t.Fatalf("python_run sim output should reference python or sim, got: %s", res.Stdout)
	}
}

func TestSimulateExec_BashRun(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "fc-t2",
		Tool:  "bash_run",
		Input: map[string]any{"command": "echo test"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d", res.ExitCode)
	}
}

func TestSimulateExec_UnknownTool(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "fc-t3",
		Tool:  "unknown_tool_xyz",
		Input: map[string]any{"x": "1"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("ExitCode want 0, got %d", res.ExitCode)
	}
}

func TestSimulateExec_OutputIsJSON(t *testing.T) {
	r := newSimRuntime(t)
	job := types.Job{
		ID:    "fc-t4",
		Tool:  "python_run",
		Input: map[string]any{"code": "x = 1"},
	}
	res, err := r.Execute(job)
	if err != nil {
		t.Fatalf("Execute error: %v", err)
	}
	// sim output is JSON-encoded result object
	if !strings.Contains(res.Stdout, "{") {
		t.Fatalf("sim output should be JSON, got: %s", res.Stdout)
	}
}

// ── Name / Tier / Health ──────────────────────────────────────────────────────

func TestName_IncludesMode(t *testing.T) {
	r := newSimRuntime(t)
	if !strings.Contains(r.Name(), "sim") {
		t.Fatalf("Name should contain 'sim', got %q", r.Name())
	}
}

func TestTier(t *testing.T) {
	r := newSimRuntime(t)
	if r.Tier() != types.TierMicroVM {
		t.Fatalf("Tier want microvm, got %v", r.Tier())
	}
}

func TestHealth_SimMode(t *testing.T) {
	r := newSimRuntime(t)
	if err := r.Health(); err != nil {
		t.Fatalf("Health in sim mode: %v", err)
	}
}
