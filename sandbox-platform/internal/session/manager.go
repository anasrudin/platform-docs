// Package session manages execution sessions with PostgreSQL storage.
package session

import (
	"database/sql"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/sandbox/platform/pkg/types"
)

// Manager handles session lifecycle operations.
type Manager struct {
	db *sql.DB
}

// NewManager creates a session manager backed by PostgreSQL.
func NewManager(db *sql.DB) *Manager {
	return &Manager{db: db}
}

// InitDB creates the sessions and jobs tables if they don't exist.
func (m *Manager) InitDB() error {
	schema := `
	CREATE TABLE IF NOT EXISTS sessions (
		id         TEXT PRIMARY KEY,
		runtime    TEXT NOT NULL DEFAULT 'wasm',
		status     TEXT NOT NULL DEFAULT 'active',
		created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);

	CREATE TABLE IF NOT EXISTS jobs (
		id          TEXT PRIMARY KEY,
		session_id  TEXT NOT NULL REFERENCES sessions(id),
		tool        TEXT NOT NULL,
		tier        TEXT NOT NULL DEFAULT 'wasm',
		input       JSONB,
		status      TEXT NOT NULL DEFAULT 'pending',
		output      TEXT,
		error_msg   TEXT,
		duration_ms BIGINT DEFAULT 0,
		created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);

	CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
	CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
	`
	_, err := m.db.Exec(schema)
	if err != nil {
		return fmt.Errorf("init schema: %w", err)
	}
	slog.Info("database schema initialized")
	return nil
}

// Create creates a new session with the given runtime tier.
func (m *Manager) Create(runtime types.Tier) (*types.Session, error) {
	id := uuid.New().String()
	now := time.Now()

	_, err := m.db.Exec(
		`INSERT INTO sessions (id, runtime, status, created_at, updated_at) VALUES ($1, $2, $3, $4, $5)`,
		id, string(runtime), "active", now, now,
	)
	if err != nil {
		return nil, fmt.Errorf("create session: %w", err)
	}

	slog.Info("session created", "id", id, "runtime", runtime)
	return &types.Session{
		ID:        id,
		Runtime:   runtime,
		Status:    "active",
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

// Get retrieves a session by ID.
func (m *Manager) Get(id string) (*types.Session, error) {
	var s types.Session
	var runtime string
	err := m.db.QueryRow(
		`SELECT id, runtime, status, created_at, updated_at FROM sessions WHERE id = $1`,
		id,
	).Scan(&s.ID, &runtime, &s.Status, &s.CreatedAt, &s.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("get session %s: %w", id, err)
	}
	s.Runtime = types.Tier(runtime)
	return &s, nil
}

// CreateJob creates a new job for a session.
func (m *Manager) CreateJob(sessionID, tool string, tier types.Tier, input []byte) (*types.Job, error) {
	id := uuid.New().String()
	now := time.Now()

	_, err := m.db.Exec(
		`INSERT INTO jobs (id, session_id, tool, tier, input, status, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
		id, sessionID, tool, string(tier), input, string(types.StatusPending), now, now,
	)
	if err != nil {
		return nil, fmt.Errorf("create job: %w", err)
	}

	return &types.Job{
		ID:        id,
		SessionID: sessionID,
		Tool:      tool,
		Tier:      tier,
		Status:    types.StatusPending,
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

// UpdateJob updates the status, output, and duration of a job.
func (m *Manager) UpdateJob(id string, status types.JobStatus, output string, errMsg string, durationMs int64) error {
	_, err := m.db.Exec(
		`UPDATE jobs SET status = $1, output = $2, error_msg = $3, duration_ms = $4, updated_at = NOW() WHERE id = $5`,
		string(status), output, errMsg, durationMs, id,
	)
	if err != nil {
		return fmt.Errorf("update job %s: %w", id, err)
	}
	return nil
}
