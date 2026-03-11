package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/sandbox/platform/internal/api/handler"
	"github.com/sandbox/platform/internal/api/middleware"
	"github.com/sandbox/platform/internal/queue"
	"github.com/sandbox/platform/internal/storage/object"
	"github.com/sandbox/platform/internal/tool/registry"
)

// Server wires together Fiber app, handlers, and middleware.
type Server struct {
	app     *fiber.App
	cfg     *Config
	metrics *http.Server
}

// NewServer assembles all components and registers routes.
func NewServer(cfg *Config) (*Server, error) {
	// --- Infrastructure clients ---
	redisClient, err := queue.NewRedisClient(cfg.Redis.URL)
	if err != nil {
		return nil, fmt.Errorf("redis: %w", err)
	}

	minioClient, err := object.NewMinIOClient(object.MinIOConfig{
		Endpoint:  cfg.MinIO.Endpoint,
		AccessKey: cfg.MinIO.AccessKey,
		SecretKey: cfg.MinIO.SecretKey,
		Bucket:    cfg.MinIO.Bucket,
		UseSSL:    cfg.MinIO.UseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("minio: %w", err)
	}

	toolReg := registry.New()

	producer := queue.NewProducer(redisClient, cfg.Redis.JobStream)

	// --- Handlers ---
	execHandler := handler.NewExecuteHandler(producer, toolReg)
	jobsHandler := handler.NewJobsHandler(redisClient, minioClient)
	toolsHandler := handler.NewToolsHandler(toolReg)
	nodesHandler := handler.NewNodesHandler(redisClient)
	dashboardHandler := handler.NewDashboardHandler(redisClient, toolReg)

	// --- Fiber app ---
	app := fiber.New(fiber.Config{
		ErrorHandler:          errorHandler,
		DisableStartupMessage: true,
	})

	app.Use(recover.New())
	app.Use(middleware.Telemetry())
	app.Use(middleware.Auth(cfg.Server.JWTPublicKey))

	// Routes
	v1 := app.Group("/v1")
	v1.Post("/execute", execHandler.Handle)
	v1.Get("/job/:id", jobsHandler.Get)
	v1.Get("/tools", toolsHandler.List)
	v1.Get("/nodes", nodesHandler.List)
	v1.Get("/dashboard", dashboardHandler.Get)
	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// Prometheus metrics on a separate port
	metricsMux := http.NewServeMux()
	metricsMux.Handle("/metrics", promhttp.Handler())
	metricsSrv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.Metrics.Port),
		Handler: metricsMux,
	}

	return &Server{app: app, cfg: cfg, metrics: metricsSrv}, nil
}

// Start begins listening. It blocks until ctx is cancelled.
func (s *Server) Start(ctx context.Context) error {
	// Start metrics server in background.
	go func() {
		slog.Info("metrics server listening", "port", s.cfg.Metrics.Port)
		if err := s.metrics.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("metrics server error", "err", err)
		}
	}()

	addr := fmt.Sprintf(":%d", s.cfg.Server.Port)
	slog.Info("api server listening", "addr", addr)

	// Graceful shutdown when context is cancelled.
	go func() {
		<-ctx.Done()
		slog.Info("shutting down api server")
		_ = s.app.Shutdown()
		_ = s.metrics.Shutdown(context.Background())
	}()

	return s.app.Listen(addr)
}

// errorHandler formats Fiber errors as JSON.
func errorHandler(c *fiber.Ctx, err error) error {
	code := fiber.StatusInternalServerError
	var e *fiber.Error
	if errors.As(err, &e) {
		code = e.Code
	}
	return c.Status(code).JSON(fiber.Map{"error": err.Error()})
}
