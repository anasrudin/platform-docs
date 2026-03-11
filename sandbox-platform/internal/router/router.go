package router

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/sandbox/platform/internal/queue"
	"github.com/sandbox/platform/pkg/types"
)

type Router struct {
	mu    sync.RWMutex
	rules map[string]types.Tier
	qc    *queue.Client
}

func New(rdbClient *queue.Client) *Router {
	r := &Router{
		rules: make(map[string]types.Tier),
		qc:    rdbClient,
	}
	for tool, tier := range defaultRules() {
		r.rules[tool] = tier
	}
	return r
}

func (r *Router) Resolve(tool string) types.Tier {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if tier, ok := r.rules[tool]; ok {
		return tier
	}
	return types.TierWASM // Default to WASM
}

func (r *Router) Register(tool string, tier types.Tier) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.rules[tool] = tier
}

// Execute routes and executes a job by pushing it to the required queue, and waits for a result.
func (r *Router) Execute(ctx context.Context, job types.Job) (types.RuntimeResult, error) {
	tier := r.Resolve(job.Tool)
	job.Tier = tier

	slog.Info("routing execution", "tool", job.Tool, "tier", tier, "job_id", job.ID)
	
	// Push to redis
	if err := r.qc.PushJob(ctx, job); err != nil {
		return types.RuntimeResult{Stderr: "failed to push job", ExitCode: 1}, fmt.Errorf("queue push: %w", err)
	}

	// Wait for response via redis
	res, err := r.qc.WaitForJobResult(ctx, job.ID, 30*time.Second)
	if err != nil {
		return types.RuntimeResult{Stderr: err.Error(), ExitCode: 1}, fmt.Errorf("wait result: %w", err)
	}

	return *res, nil
}
