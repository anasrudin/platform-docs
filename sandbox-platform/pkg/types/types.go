package types

import "time"

// Tier represents the execution runtime tier.
type Tier string

const (
	TierWASM    Tier = "wasm"
	TierMicroVM Tier = "microvm"
	TierGUI     Tier = "gui"
)

// JobStatus represents the lifecycle state of a job.
type JobStatus string

const (
	StatusPending   JobStatus = "pending"
	StatusRunning   JobStatus = "running"
	StatusCompleted JobStatus = "completed"
	StatusFailed    JobStatus = "failed"
)

// Session represents an execution session.
type Session struct {
	ID        string    `json:"id"`
	Runtime   Tier      `json:"runtime"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Job is the core execution unit passed between components.
type Job struct {
	ID         string         `json:"id"`
	SessionID  string         `json:"session_id"`
	Tool       string         `json:"tool"`
	Tier       Tier           `json:"tier"`
	Input      map[string]any `json:"input"`
	Status     JobStatus      `json:"status"`
	Output     string         `json:"output,omitempty"`
	ErrorMsg   string         `json:"error_message,omitempty"`
	DurationMs int64          `json:"duration_ms,omitempty"`
	CreatedAt  time.Time      `json:"created_at"`
	UpdatedAt  time.Time      `json:"updated_at"`
}

// ExecuteRequest is the API payload for POST /execute.
type ExecuteRequest struct {
	SessionID string         `json:"session_id"`
	Tool      string         `json:"tool"`
	Input     map[string]any `json:"input"`
}

// ExecuteResponse is the API response for a submitted job.
type ExecuteResponse struct {
	JobID    string         `json:"job_id"`
	Status   JobStatus      `json:"status"`
	Output   string         `json:"output,omitempty"`
	ErrorMsg string         `json:"error_message,omitempty"`
	Duration int64          `json:"duration_ms,omitempty"`
}

// CreateSessionRequest is the API payload for POST /sessions.
type CreateSessionRequest struct {
	Runtime string `json:"runtime"` // "wasm", "microvm", "gui"
}

// CreateSessionResponse is returned when a session is created.
type CreateSessionResponse struct {
	SessionID string `json:"session_id"`
	Runtime   Tier   `json:"runtime"`
	Status    string `json:"status"`
}

// HealthResponse is returned by GET /health.
type HealthResponse struct {
	Status   string            `json:"status"`
	Version  string            `json:"version"`
	Services map[string]string `json:"services"`
}

// RuntimeResult is returned by any runtime executor.
type RuntimeResult struct {
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
}

// RuntimeEngine is the interface that all runtime engines must implement.
type RuntimeEngine interface {
	Name() string
	Tier() Tier
	Execute(job Job) (RuntimeResult, error)
	Health() error
}
