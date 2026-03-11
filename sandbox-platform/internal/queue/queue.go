package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/pkg/types"
)

type Client struct {
	rdb *redis.Client
}

func NewClient(rdb *redis.Client) *Client {
	return &Client{rdb: rdb}
}

// PushJob pushes a job to the appropriate tier queue.
func (c *Client) PushJob(ctx context.Context, job types.Job) error {
	data, err := json.Marshal(job)
	if err != nil {
		return err
	}
	queueName := "queue:" + string(job.Tier)
	return c.rdb.RPush(ctx, queueName, data).Err()
}

// WaitForJobResult waits for a result to be published for a specific job ID.
func (c *Client) WaitForJobResult(ctx context.Context, jobID string, timeout time.Duration) (*types.RuntimeResult, error) {
	resultKey := "result:" + jobID
	
	val, err := c.rdb.BRPop(ctx, timeout, resultKey).Result()
	if err != nil {
		if err == redis.Nil {
			return nil, fmt.Errorf("timeout waiting for job result")
		}
		return nil, err
	}

	var result types.RuntimeResult
	if err := json.Unmarshal([]byte(val[1]), &result); err != nil {
		return nil, fmt.Errorf("invalid result data: %w", err)
	}

	return &result, nil
}

// PopJob blocks and waits for a job from the given tier queue.
func (c *Client) PopJob(ctx context.Context, tier types.Tier) (*types.Job, error) {
	queueName := "queue:" + string(tier)
	
	val, err := c.rdb.BLPop(ctx, 0, queueName).Result()
	if err != nil {
		return nil, err
	}

	var job types.Job
	if err := json.Unmarshal([]byte(val[1]), &job); err != nil {
		return nil, fmt.Errorf("invalid job data: %w", err)
	}

	return &job, nil
}

// PublishJobResult publishes the execution result for a job.
func (c *Client) PublishJobResult(ctx context.Context, jobID string, result types.RuntimeResult) error {
	resultKey := "result:" + jobID
	data, err := json.Marshal(result)
	if err != nil {
		return err
	}
	
	// Push result and set expiration
	if err := c.rdb.RPush(ctx, resultKey, data).Err(); err != nil {
		return err
	}
	return c.rdb.Expire(ctx, resultKey, 5*time.Minute).Err()
}
