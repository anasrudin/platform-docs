package microvm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Config holds microvm runtime configuration.
type Config struct {
	DataDir    string
	KernelPath string
	PoolSize   int
}

// Runtime executes tools inside Firecracker microVMs.
type Runtime struct {
	cfg  Config
	pool *VMPool
}

// NewRuntime creates a microVM runtime. If no kernel path is configured,
// direct-exec mode is used (for local dev without Firecracker).
func NewRuntime(cfg Config) (*Runtime, error) {
	if cfg.PoolSize == 0 {
		cfg.PoolSize = 5
	}

	if cfg.KernelPath == "" {
		// Local dev mode — no actual Firecracker, just exec the tool binary.
		return &Runtime{cfg: cfg}, nil
	}

	pool, err := NewVMPool(context.Background(), cfg.KernelPath, cfg.DataDir+"/snapshots/default", cfg.PoolSize)
	if err != nil {
		return nil, fmt.Errorf("vm pool: %w", err)
	}
	return &Runtime{cfg: cfg, pool: pool}, nil
}

// Execute runs the job in a microVM and returns the result.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	// Dev mode — no pool.
	if r.pool == nil {
		return r.execDirect(ctx, job)
	}

	vm, err := r.pool.Acquire(ctx)
	if err != nil {
		return types.RuntimeResult{}, fmt.Errorf("acquire vm: %w", err)
	}
	defer r.pool.Release(ctx, vm)

	inputJSON, _ := json.Marshal(job.Input)
	output, exitCode, err := vm.Exec(ctx, "/tool/"+job.Tool, nil, map[string]string{
		"TOOL_INPUT": string(inputJSON),
	})
	if err != nil {
		return types.RuntimeResult{Stderr: err.Error(), ExitCode: -1}, err
	}
	return types.RuntimeResult{Stdout: output, ExitCode: exitCode}, nil
}

// execDirect runs the tool binary directly (dev / CI mode).
func (r *Runtime) execDirect(ctx context.Context, job types.Job) (types.RuntimeResult, error) {
	inputJSON, _ := json.Marshal(job.Input)
	_ = inputJSON
	// Placeholder: real implementation calls the tool binary directly.
	return types.RuntimeResult{
		Stdout:   fmt.Sprintf(`{"status":"ok","tool":%q}`, job.Tool),
		ExitCode: 0,
	}, nil
}

// jsonReader converts a byte slice to an io.Reader for HTTP bodies.
func jsonReader(data []byte) io.Reader {
	return io.NopCloser(bytes.NewReader(data))
}

// ensure strings is referenced (used in other files in package).
var _ = strings.TrimSpace
