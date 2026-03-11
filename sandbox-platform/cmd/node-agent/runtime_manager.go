package main

import (
	"fmt"
	"sync/atomic"

	"github.com/sandbox/platform/internal/runtime/gui"
	"github.com/sandbox/platform/internal/runtime/microvm"
	"github.com/sandbox/platform/internal/runtime/wasm"
	"github.com/sandbox/platform/pkg/types"
)

// RuntimeManager owns all runtime executors on this node.
type RuntimeManager struct {
	wasm    *wasm.Runtime
	microvm *microvm.Runtime
	gui     *gui.Runtime

	activeJobs atomic.Int64
	maxJobs    int64
}

// NewRuntimeManager creates runtimes using the given data directory.
func NewRuntimeManager(dataDir string) (*RuntimeManager, error) {
	wasmRT, err := wasm.NewRuntime(dataDir + "/wasm-modules")
	if err != nil {
		return nil, fmt.Errorf("wasm runtime: %w", err)
	}

	microvmRT, err := microvm.NewRuntime(microvm.Config{
		DataDir:  dataDir + "/vm-images",
		PoolSize: 10,
	})
	if err != nil {
		return nil, fmt.Errorf("microvm runtime: %w", err)
	}

	guiRT, err := gui.NewRuntime(gui.Config{
		PoolSize: 3,
	})
	if err != nil {
		return nil, fmt.Errorf("gui runtime: %w", err)
	}

	return &RuntimeManager{
		wasm:    wasmRT,
		microvm: microvmRT,
		gui:     guiRT,
		maxJobs: 100,
	}, nil
}

// RuntimeFor returns the runtime matching the requested tier.
func (rm *RuntimeManager) RuntimeFor(tier types.Tier) (Executor, error) {
	switch tier {
	case types.TierWASM:
		return rm.wasm, nil
	case types.TierMicroVM:
		return rm.microvm, nil
	case types.TierGUI:
		return rm.gui, nil
	default:
		return nil, fmt.Errorf("unknown tier: %q", tier)
	}
}

// CurrentLoad returns a 0.0–1.0 fraction of capacity used.
func (rm *RuntimeManager) CurrentLoad() float64 {
	active := rm.activeJobs.Load()
	if rm.maxJobs == 0 {
		return 0
	}
	return float64(active) / float64(rm.maxJobs)
}

// Executor is the common interface all runtimes implement.
type Executor interface {
	Execute(job types.Job) (types.RuntimeResult, error)
}
