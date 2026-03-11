package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	nodeID := flag.String("node-id", "", "unique node identifier (required)")
	redisURL := flag.String("redis", "redis://localhost:6379", "Redis URL")
	dataDir := flag.String("data-dir", "/var/sandbox", "data directory for VM images and WASM modules")
	flag.Parse()

	if *nodeID == "" {
		slog.Error("--node-id is required")
		os.Exit(1)
	}

	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	agent, err := NewAgent(AgentConfig{
		NodeID:   *nodeID,
		RedisURL: *redisURL,
		DataDir:  *dataDir,
	})
	if err != nil {
		slog.Error("init agent", "err", err)
		os.Exit(1)
	}

	slog.Info("node agent starting", "node_id", *nodeID)
	if err := agent.Run(ctx); err != nil {
		slog.Error("agent stopped", "err", err)
		os.Exit(1)
	}
}
