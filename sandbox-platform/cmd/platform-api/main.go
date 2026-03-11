package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/internal/queue"
	"github.com/sandbox/platform/internal/router"
	"github.com/sandbox/platform/internal/session"
	"github.com/sandbox/platform/pkg/types"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	// Initialize database
	dsn := envOrDefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/platform?sslmode=disable")
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		slog.Error("failed to open database", "err", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		slog.Error("failed to ping database", "err", err)
		os.Exit(1)
	}

	sessionMgr := session.NewManager(db)
	if err := sessionMgr.InitDB(); err != nil {
		slog.Error("failed to init schema", "err", err)
		os.Exit(1)
	}

	// Initialize Redis
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

	// Initialize Router
	r := router.New(qc)

	mux := http.NewServeMux()

	// Health endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, req *http.Request) {
		status := make(map[string]string)
		
		dbStatus := "healthy"
		if err := db.Ping(); err != nil {
			dbStatus = "unhealthy: " + err.Error()
		}
		status["postgres"] = dbStatus

		redisStatus := "healthy"
		if err := rdb.Ping(context.Background()).Err(); err != nil {
			redisStatus = "unhealthy: " + err.Error()
		}
		status["redis"] = redisStatus

		overallStatus := "healthy"
		for _, s := range status {
			if s != "healthy" {
				overallStatus = "degraded"
				break
			}
		}

		resp := types.HealthResponse{
			Status:   overallStatus,
			Version:  "0.1.0-local",
			Services: status,
		}

		w.Header().Set("Content-Type", "application/json")
		if overallStatus != "healthy" {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		json.NewEncoder(w).Encode(resp)
	})

	// Create Session endpoint
	mux.HandleFunc("/sessions", func(w http.ResponseWriter, req *http.Request) {
		if req.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var reqBody types.CreateSessionRequest
		if err := json.NewDecoder(req.Body).Decode(&reqBody); err != nil && err != io.EOF {
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		tier := types.TierWASM // default
		if reqBody.Runtime != "" {
			tier = types.Tier(reqBody.Runtime)
		}

		sess, err := sessionMgr.Create(tier)
		if err != nil {
			http.Error(w, "Internal server error: "+err.Error(), http.StatusInternalServerError)
			return
		}

		resp := types.CreateSessionResponse{
			SessionID: sess.ID,
			Runtime:   sess.Runtime,
			Status:    sess.Status,
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// Execute Job endpoint
	mux.HandleFunc("/execute", func(w http.ResponseWriter, req *http.Request) {
		if req.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var reqBody types.ExecuteRequest
		if err := json.NewDecoder(req.Body).Decode(&reqBody); err != nil {
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if reqBody.Tool == "" {
			http.Error(w, "Tool name is required", http.StatusBadRequest)
			return
		}

		sessionID := reqBody.SessionID
		var sess *types.Session
		var err error

		if sessionID == "" {
			// Auto-create session if not provided
			sess, err = sessionMgr.Create(r.Resolve(reqBody.Tool))
			if err != nil {
				http.Error(w, "Failed to create session: "+err.Error(), http.StatusInternalServerError)
				return
			}
			sessionID = sess.ID
		} else {
			sess, err = sessionMgr.Get(sessionID)
			if err != nil {
				http.Error(w, "Session not found: "+err.Error(), http.StatusNotFound)
				return
			}
		}

		inputBytes, _ := json.Marshal(reqBody.Input)
		tier := r.Resolve(reqBody.Tool)

		// Create job in DB
		job, err := sessionMgr.CreateJob(sessionID, reqBody.Tool, tier, inputBytes)
		if err != nil {
			http.Error(w, "Failed to create job: "+err.Error(), http.StatusInternalServerError)
			return
		}

		// Attach input from request
		job.Input = reqBody.Input

		// Execute job by pushing to redis queue
		start := time.Now()
		result, execErr := r.Execute(req.Context(), *job)
		durationMs := time.Since(start).Milliseconds()

		status := types.StatusCompleted
		output := result.Stdout
		errMsg := result.Stderr

		if execErr != nil {
			status = types.StatusFailed
			errMsg = execErr.Error()
		} else if result.ExitCode != 0 {
			status = types.StatusFailed
			if errMsg == "" {
				errMsg = fmt.Sprintf("Process exited with code %d", result.ExitCode)
			}
		}

		// Update job in DB
		if err := sessionMgr.UpdateJob(job.ID, status, output, errMsg, durationMs); err != nil {
			slog.Error("failed to update job status", "job_id", job.ID, "err", err)
		}

		resp := types.ExecuteResponse{
			JobID:    job.ID,
			Status:   status,
			Output:   output,
			ErrorMsg: errMsg,
			Duration: durationMs,
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	srv := &http.Server{
		Addr:    ":8080",
		Handler: mux,
	}

	go func() {
		slog.Info("Starting API server", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server error", "err", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.Info("Shutting down API server")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("server shutdown error", "err", err)
	}
}

func envOrDefault(key, def string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return def
}
