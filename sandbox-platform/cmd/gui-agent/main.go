package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/internal/queue"
	"github.com/sandbox/platform/runtime/gui"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})).With("agent", "gui"))

	redisURL := envOrDefault("REDIS_URL", "redis://localhost:6379/0")
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		slog.Error("failed to parse redis url", "err", err)
		os.Exit(1)
	}

	rdb := redis.NewClient(opt)
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		slog.Error("failed to ping redis", "err", err)
		os.Exit(1)
	}
	defer rdb.Close()
	
	qc := queue.NewClient(rdb)
	engine := gui.NewRuntime()
	
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	slog.Info("Starting gui-agent", "tier", engine.Tier())

	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			default:
				jobP, err := qc.PopJob(ctx, engine.Tier())
				if err != nil {
					slog.Error("failed to pop job", "err", err)
					time.Sleep(1 * time.Second)
					continue
				}

				if jobP == nil {
					continue
				}

				job := *jobP
				slog.Info("received job", "job_id", job.ID, "tool", job.Tool)

				res, execErr := engine.Execute(job)
				if execErr != nil {
					res.Stderr = execErr.Error()
					res.ExitCode = 1
				}

				if err := qc.PublishJobResult(ctx, job.ID, res); err != nil {
					slog.Error("failed to publish job result", "job_id", job.ID, "err", err)
				}
			}
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.Info("Shutting down gui-agent")
	cancel()
}

func envOrDefault(key, def string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return def
}
