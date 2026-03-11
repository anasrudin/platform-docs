package main

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/pkg/types"
)

// AgentConfig holds all configuration for the node agent.
type AgentConfig struct {
	NodeID   string
	RedisURL string
	DataDir  string
}

// Agent is the process that runs on each sandbox node. It:
//  1. Registers itself with the scheduler via Redis
//  2. Polls for assigned jobs
//  3. Dispatches each job to the correct runtime
//  4. Reports results back via Redis
type Agent struct {
	cfg     AgentConfig
	rdb     *redis.Client
	runtime *RuntimeManager
}

// NewAgent creates and initialises a node agent.
func NewAgent(cfg AgentConfig) (*Agent, error) {
	opt, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	rdb := redis.NewClient(opt)

	runtime, err := NewRuntimeManager(cfg.DataDir)
	if err != nil {
		return nil, fmt.Errorf("init runtime manager: %w", err)
	}

	return &Agent{cfg: cfg, rdb: rdb, runtime: runtime}, nil
}

// Run starts the agent event loop. Blocks until ctx is cancelled.
func (a *Agent) Run(ctx context.Context) error {
	if err := a.register(ctx); err != nil {
		return fmt.Errorf("register node: %w", err)
	}

	// Heartbeat ticker so the scheduler knows we are alive.
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	jobQueue := fmt.Sprintf("node:%s:jobs", a.cfg.NodeID)
	slog.Info("agent ready", "node_id", a.cfg.NodeID, "queue", jobQueue)

	for {
		select {
		case <-ctx.Done():
			return a.deregister(context.Background())

		case <-ticker.C:
			if err := a.heartbeat(ctx); err != nil {
				slog.Warn("heartbeat failed", "err", err)
			}

		default:
			// Blocking pop with 1s timeout.
			result, err := a.rdb.BLPop(ctx, time.Second, jobQueue).Result()
			if err != nil {
				if err == redis.Nil || ctx.Err() != nil {
					continue
				}
				slog.Error("blpop error", "err", err)
				continue
			}
			if len(result) < 2 {
				continue
			}
			go a.handleJob(ctx, result[1])
		}
	}
}

// handleJob decodes a job message and dispatches it to the executor.
func (a *Agent) handleJob(ctx context.Context, payload string) {
	exec, err := NewExecutor(a.cfg.NodeID, a.rdb, a.runtime)
	if err != nil {
		slog.Error("create executor", "err", err)
		return
	}
	if err := exec.Execute(ctx, payload); err != nil {
		slog.Error("execute job", "err", err)
	}
}

// register writes node metadata into Redis so the scheduler can route to it.
func (a *Agent) register(ctx context.Context) error {
	key := fmt.Sprintf("node:%s", a.cfg.NodeID)
	return a.rdb.HSet(ctx, key,
		"id", a.cfg.NodeID,
		"status", "active",
		"registered_at", time.Now().UTC().Format(time.RFC3339),
		"load", "0",
	).Err()
}

// deregister marks the node offline.
func (a *Agent) deregister(ctx context.Context) error {
	key := fmt.Sprintf("node:%s", a.cfg.NodeID)
	return a.rdb.HSet(ctx, key, "status", "offline").Err()
}

// heartbeat updates the last-seen timestamp and current load.
func (a *Agent) heartbeat(ctx context.Context) error {
	load := a.runtime.CurrentLoad()
	key := fmt.Sprintf("node:%s", a.cfg.NodeID)
	return a.rdb.HSet(ctx, key,
		"last_seen", time.Now().UTC().Format(time.RFC3339),
		"load", fmt.Sprintf("%.4f", load),
	).Err()
}

// ensure types package is referenced at compile time.
var _ types.Tier = types.TierWASM
