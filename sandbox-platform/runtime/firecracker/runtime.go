// Package firecracker provides a Firecracker microVM runtime for sandbox execution.
//
// Execution modes:
//   - "real"  — boots VMs from MinIO snapshots via /dev/kvm (Linux required)
//   - "sim"   — enhanced simulation that returns realistic mock output
//
// Mode is selected by:
//   1. FC_MODE env var ("real" | "sim")
//   2. Presence of /dev/kvm (auto-detect: kvm → real, no kvm → sim)
package firecracker

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/google/uuid"
	"github.com/sandbox/platform/pkg/types"
)

// Config holds all runtime configuration sourced from environment variables.
type Config struct {
	// Firecracker binary path
	FirecrackerBin string // FC_BIN, default /usr/bin/firecracker

	// Snapshot
	SnapshotName     string // SNAPSHOT_NAME, default python-v1
	SnapshotCacheDir string // SNAPSHOT_CACHE_DIR, default /var/sandbox/cache

	// MinIO
	MinIOEndpoint  string // MINIO_ENDPOINT
	MinIOAccessKey string // MINIO_ACCESS_KEY
	MinIOSecretKey string // MINIO_SECRET_KEY
	MinIOBucket    string // MINIO_BUCKET, default platform-snapshots

	// Pool
	PoolSize int // FC_POOL_SIZE, default 2

	// DevMode: use TCP instead of vsock for guest communication
	DevMode bool // FC_DEV_MODE=true
}

func configFromEnv() Config {
	return Config{
		FirecrackerBin:   envOr("FC_BIN", "/usr/bin/firecracker"),
		SnapshotName:     envOr("SNAPSHOT_NAME", "python-v1"),
		SnapshotCacheDir: envOr("SNAPSHOT_CACHE_DIR", "/var/sandbox/cache"),
		MinIOEndpoint:    envOr("MINIO_ENDPOINT", "http://localhost:9000"),
		MinIOAccessKey:   envOr("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey:   envOr("MINIO_SECRET_KEY", "minioadmin"),
		MinIOBucket:      envOr("MINIO_BUCKET", "platform-snapshots"),
		PoolSize:         envInt("FC_POOL_SIZE", 2),
		DevMode:          os.Getenv("FC_DEV_MODE") == "true",
	}
}

// ── Runtime ───────────────────────────────────────────────────────────────────

// Runtime implements types.RuntimeEngine for Firecracker microVMs.
type Runtime struct {
	cfg   Config
	pool  *VMPool
	store *SnapshotStore
	mode  string // "real" or "sim"
}

// NewRuntime creates and initialises the Firecracker runtime.
// It selects real vs sim mode automatically and pre-warms the VM pool.
func NewRuntime() *Runtime {
	cfg := configFromEnv()
	mode := detectMode()

	store := newSnapshotStore(cfg)
	pool := newVMPool(cfg, store)

	r := &Runtime{cfg: cfg, pool: pool, store: store, mode: mode}

	if mode == "real" {
		go func() {
			if err := pool.Warmup(); err != nil {
				slog.Error("VM pool warmup failed, falling back to sim mode",
					"err", err)
				r.mode = "sim"
			} else {
				slog.Info("VM pool ready", "size", cfg.PoolSize,
					"snapshot", cfg.SnapshotName)
			}
		}()
	}

	return r
}

// Name returns the engine identifier.
func (r *Runtime) Name() string {
	return fmt.Sprintf("firecracker-%s", r.mode)
}

// Tier returns the execution tier handled by this runtime.
func (r *Runtime) Tier() types.Tier {
	return types.TierMicroVM
}

// Health reports whether the runtime is operational.
func (r *Runtime) Health() error {
	if r.mode == "sim" {
		return nil
	}
	if _, err := os.Stat(r.cfg.FirecrackerBin); err != nil {
		return fmt.Errorf("firecracker binary not found: %w", err)
	}
	if len(r.pool.ready) == 0 {
		slog.Warn("health check: VM pool empty (warming up)")
	}
	return nil
}

// Execute runs a job in a microVM (real mode) or simulates it (sim mode).
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	if r.mode == "sim" {
		return r.simulateExec(job)
	}
	return r.realExec(job)
}

// ── Real execution path ───────────────────────────────────────────────────────

func (r *Runtime) realExec(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()

	slog.Info("fc execute", "job_id", job.ID, "tool", job.Tool, "mode", "real")

	vm, err := r.pool.Acquire(30 * time.Second)
	if err != nil {
		slog.Error("pool acquire failed, falling back to sim", "err", err)
		return r.simulateExec(job)
	}
	defer r.pool.Release(vm)

	resp, err := vm.execute(job.Tool, job.Input)
	if err != nil {
		return types.RuntimeResult{
			Stderr:   fmt.Sprintf("vm execute error: %v", err),
			ExitCode: 1,
		}, nil
	}

	slog.Info("fc execute done",
		"job_id", job.ID,
		"tool", job.Tool,
		"exit_code", resp.ExitCode,
		"duration_ms", time.Since(start).Milliseconds(),
		"vm_id", vm.id,
	)

	return types.RuntimeResult{
		Stdout:   resp.Stdout,
		Stderr:   resp.Stderr,
		ExitCode: resp.ExitCode,
	}, nil
}

// ── Simulation path ───────────────────────────────────────────────────────────

// simulateExec returns a realistic mock result when KVM is unavailable.
// It is clearly labelled so callers can distinguish from real execution.
func (r *Runtime) simulateExec(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()

	slog.Info("fc execute", "job_id", job.ID, "tool", job.Tool, "mode", "sim")

	// Simulate realistic boot + execution latency.
	time.Sleep(50 * time.Millisecond)

	toolOutput := r.simulateToolOutput(job.Tool, job.Input)

	result := map[string]any{
		"tool":      job.Tool,
		"status":    "completed",
		"runtime":   "firecracker-sim",
		"vm_id":     "fc-sim-" + uuid.New().String()[:8],
		"boot_ms":   20,
		"exec_ms":   time.Since(start).Milliseconds() - 20,
		"output":    toolOutput,
		"snapshot":  r.cfg.SnapshotName,
		"sim_note":  "no /dev/kvm — using simulation (set FC_MODE=real on Linux with KVM)",
		"metadata": map[string]string{
			"kernel":  "vmlinux-5.10.225",
			"rootfs":  r.cfg.SnapshotName + ".ext4",
			"mem_mib": "512",
			"vcpus":   "2",
		},
	}

	b, _ := json.MarshalIndent(result, "", "  ")

	slog.Info("fc sim complete",
		"job_id", job.ID,
		"tool", job.Tool,
		"duration_ms", time.Since(start).Milliseconds(),
	)

	return types.RuntimeResult{Stdout: string(b), ExitCode: 0}, nil
}

func (r *Runtime) simulateToolOutput(tool string, input map[string]any) any {
	switch tool {
	case "python_run":
		code, _ := input["code"].(string)
		if code == "" {
			code = "print('hello from Python')"
		}
		return map[string]any{
			"stdout":    "[sim] " + code + "\n=> hello from Python",
			"exit_code": 0,
		}
	case "bash_run":
		cmd, _ := input["command"].(string)
		return map[string]any{
			"stdout":    "[sim] $ " + cmd + "\n=> command executed",
			"exit_code": 0,
		}
	default:
		return fmt.Sprintf("[sim] %s executed with input: %v", tool, input)
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// detectMode selects "real" if FC_MODE=real or /dev/kvm is accessible.
// Explicit FC_MODE always wins.
func detectMode() string {
	if m := os.Getenv("FC_MODE"); m == "real" || m == "sim" {
		slog.Info("FC mode from FC_MODE env", "mode", m)
		return m
	}
	if _, err := os.Stat("/dev/kvm"); err == nil {
		slog.Info("FC mode auto-detected: /dev/kvm present", "mode", "real")
		return "real"
	}
	slog.Info("FC mode auto-detected: /dev/kvm absent", "mode", "sim")
	return "sim"
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	var n int
	if _, err := fmt.Sscanf(v, "%d", &n); err != nil {
		return def
	}
	return n
}
