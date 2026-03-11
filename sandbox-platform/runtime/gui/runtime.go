// Package gui provides a stub runtime for GUI/browser execution.
// In local dev mode, it simulates browser automation by returning mocked results.
package gui

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/sandbox/platform/pkg/types"
)

// Runtime is a stub that simulates browser/GUI execution.
type Runtime struct{}

// NewRuntime creates a new GUI stub runtime.
func NewRuntime() *Runtime {
	return &Runtime{}
}

// Name returns the engine name.
func (r *Runtime) Name() string {
	return "gui-runtime-stub"
}

// Tier returns the tier this engine handles.
func (r *Runtime) Tier() types.Tier {
	return types.TierGUI
}

// Health checks if the runtime is operational.
func (r *Runtime) Health() error {
	return nil // Stub is always healthy
}

// Execute simulates a browser/GUI session execution.
func (r *Runtime) Execute(job types.Job) (types.RuntimeResult, error) {
	start := time.Now()

	slog.Info("gui stub executing", "tool", job.Tool, "job_id", job.ID)

	// Simulate browser startup + execution time
	time.Sleep(100 * time.Millisecond)

	result := map[string]any{
		"tool":       job.Tool,
		"status":     "completed",
		"runtime":    "gui-stub",
		"session_id": fmt.Sprintf("browser-%s", job.ID[:8]),
		"warmup_ms":  200,
		"exec_ms":    100,
		"input":      job.Input,
		"output":     fmt.Sprintf("[stub] Executed %s in simulated browser session", job.Tool),
		"metadata": map[string]string{
			"browser":    "chromium-121",
			"display":    ":99",
			"resolution": "1920x1080",
			"stream_url": fmt.Sprintf("ws://localhost:6080/vnc/%s", job.ID[:8]),
		},
	}

	b, _ := json.MarshalIndent(result, "", "  ")

	slog.Info("gui stub complete", "tool", job.Tool, "duration_ms", time.Since(start).Milliseconds())

	return types.RuntimeResult{
		Stdout:   string(b),
		ExitCode: 0,
	}, nil
}
