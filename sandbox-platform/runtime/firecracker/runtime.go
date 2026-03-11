// Package firecracker provides a stub runtime for Firecracker microVM execution.
// In local dev mode, it simulates microVM execution by returning mocked results.
package firecracker

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Runtime is a stub that simulates Firecracker microVM execution.
type Runtime struct{}

// NewRuntime creates a new Firecracker stub runtime.
func NewRuntime() *Runtime {
	return &Runtime{}
}

// Name returns the engine name.
func (r *Runtime) Name() string {
	return "firecracker-runtime-stub"
}

// Tier returns the tier this engine handles.
func (r *Runtime) Tier() types.Tier {
	return types.TierMicroVM
}

// Health checks if the runtime is operational.
func (r *Runtime) Health() error {
	return nil // Stub is always healthy
}

// Execute simulates a Firecracker microVM execution.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()

	slog.Info("firecracker stub executing", "tool", job.Tool, "job_id", job.ID)

	// Simulate VM boot + execution time
	time.Sleep(50 * time.Millisecond)

	result := map[string]any{
		"tool":     job.Tool,
		"status":   "completed",
		"runtime":  "firecracker-stub",
		"vm_id":    fmt.Sprintf("fc-vm-%s", job.ID[:8]),
		"boot_ms":  20,
		"exec_ms":  30,
		"input":    job.Input,
		"output":   fmt.Sprintf("[stub] Executed %s in simulated microVM", job.Tool),
		"metadata": map[string]string{
			"kernel":   "vmlinux-5.10",
			"rootfs":   "ubuntu-22.04",
			"mem_mb":   "128",
			"vcpu":     "1",
			"snapshot": "warm-pool-1",
		},
	}

	b, _ := json.MarshalIndent(result, "", "  ")

	slog.Info("firecracker stub complete", "tool", job.Tool, "duration_ms", time.Since(start).Milliseconds())

	return types.RuntimeResult{
		Stdout:   string(b),
		ExitCode: 0,
	}, nil
}
