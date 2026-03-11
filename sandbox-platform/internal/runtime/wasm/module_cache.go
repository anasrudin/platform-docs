package wasm

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// ModuleCache tracks which WASM modules have been loaded to avoid redundant
// stat calls on the hot path.
type ModuleCache struct {
	mu    sync.RWMutex
	paths map[string]string // tool name → absolute path
}

// NewModuleCache creates an empty ModuleCache.
func NewModuleCache() *ModuleCache {
	return &ModuleCache{paths: make(map[string]string)}
}

// Resolve returns the absolute path to a tool's .wasm file.
// The first call stats the filesystem; subsequent calls return from cache.
func (c *ModuleCache) Resolve(dir, tool string) (string, error) {
	c.mu.RLock()
	if p, ok := c.paths[tool]; ok {
		c.mu.RUnlock()
		return p, nil
	}
	c.mu.RUnlock()

	path := filepath.Join(dir, tool+".wasm")
	if _, err := os.Stat(path); err != nil {
		return "", fmt.Errorf("wasm module not found at %s: %w", path, err)
	}

	c.mu.Lock()
	c.paths[tool] = path
	c.mu.Unlock()

	return path, nil
}

// Invalidate removes a cached entry, forcing a re-stat on next access.
func (c *ModuleCache) Invalidate(tool string) {
	c.mu.Lock()
	delete(c.paths, tool)
	c.mu.Unlock()
}
