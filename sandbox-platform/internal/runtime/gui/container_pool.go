package gui

import (
	"context"
	"log/slog"
	"sync"
)

// ContainerPool maintains a set of pre-warmed GUI containers.
type ContainerPool struct {
	mu        sync.Mutex
	available []*DockerRunner
	size      int
}

// NewContainerPool creates a pool (containers are started lazily on first Acquire).
func NewContainerPool(size int) *ContainerPool {
	return &ContainerPool{size: size}
}

// Acquire returns a running container, starting one if none are available.
func (p *ContainerPool) Acquire(ctx context.Context) (*DockerRunner, error) {
	p.mu.Lock()
	if len(p.available) > 0 {
		c := p.available[0]
		p.available = p.available[1:]
		p.mu.Unlock()
		return c, nil
	}
	p.mu.Unlock()

	// Spin up a fresh container.
	c := &DockerRunner{}
	if err := c.Start(ctx); err != nil {
		return nil, err
	}
	return c, nil
}

// Release stops the used container and starts a replacement asynchronously.
func (p *ContainerPool) Release(ctx context.Context, c *DockerRunner) {
	_ = c.Stop(ctx)

	go func() {
		fresh := &DockerRunner{}
		if err := fresh.Start(ctx); err != nil {
			slog.Error("replenish gui pool", "err", err)
			return
		}
		p.mu.Lock()
		if len(p.available) < p.size {
			p.available = append(p.available, fresh)
		} else {
			_ = fresh.Stop(context.Background())
		}
		p.mu.Unlock()
	}()
}
