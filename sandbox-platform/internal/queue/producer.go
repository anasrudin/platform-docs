// Package queue provides Redis-backed job distribution.
package queue

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// JobMessage is the payload pushed onto the Redis stream.
type JobMessage struct {
	JobID   string `json:"job_id"`
	Tool    string `json:"tool"`
	Tier    string `json:"tier"`
	AgentID string `json:"agent_id"`
	Input   string `json:"input"` // raw JSON
}

// NewRedisClient parses a Redis URL and returns a connected client.
func NewRedisClient(url string) (*redis.Client, error) {
	opt, err := redis.ParseURL(url)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	return redis.NewClient(opt), nil
}

// Producer pushes job messages to a Redis list.
type Producer struct {
	rdb    *redis.Client
	stream string
}

// NewProducer creates a Producer for the given stream key.
func NewProducer(rdb *redis.Client, stream string) *Producer {
	return &Producer{rdb: rdb, stream: stream}
}

// Push serialises msg and appends it to the Redis list.
func (p *Producer) Push(ctx context.Context, msg JobMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("marshal job: %w", err)
	}
	return p.rdb.RPush(ctx, p.stream, data).Err()
}
