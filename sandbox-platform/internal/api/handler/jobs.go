package handler

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/internal/storage/object"
	"github.com/sandbox/platform/pkg/types"
)

// JobsHandler handles GET /v1/job/:id.
type JobsHandler struct {
	rdb   *redis.Client
	minio *object.MinIOClient
}

// NewJobsHandler creates a JobsHandler.
func NewJobsHandler(rdb *redis.Client, minio *object.MinIOClient) *JobsHandler {
	return &JobsHandler{rdb: rdb, minio: minio}
}

// Get fetches job status and optionally a presigned output URL.
func (h *JobsHandler) Get(c *fiber.Ctx) error {
	jobID := c.Params("id")
	if jobID == "" {
		return fiber.NewError(fiber.StatusBadRequest, "job id required")
	}

	key := fmt.Sprintf("job:result:%s", jobID)
	raw, err := h.rdb.Get(c.Context(), key).Bytes()
	if err == redis.Nil {
		// Job is still pending or running.
		return c.JSON(fiber.Map{"job_id": jobID, "status": "pending"})
	}
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "failed to fetch job")
	}

	var envelope struct {
		Job    types.Job           `json:"job"`
		Result types.RuntimeResult `json:"result"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "malformed job result")
	}

	resp := fiber.Map{
		"job_id":      envelope.Job.ID,
		"status":      envelope.Job.Status,
		"tool":        envelope.Job.Tool,
		"duration_ms": envelope.Job.DurationMs,
		"logs":        envelope.Job.Logs,
	}

	if envelope.Job.Status == types.StatusCompleted && envelope.Result.OutputKey != "" {
		url, err := h.minio.PresignedGetURL(c.Context(), envelope.Result.OutputKey, 15*time.Minute)
		if err == nil {
			resp["output_url"] = url
		}
	}
	if envelope.Job.Status == types.StatusFailed {
		resp["error"] = envelope.Job.ErrorMsg
	}

	return c.JSON(resp)
}
