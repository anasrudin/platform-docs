// Package router maps tool names to execution tier (wasm, microvm, gui).
package router

import (
	"fmt"

	"github.com/sandbox/platform/pkg/types"
)

// Router determines which runtime tier handles a given tool.
type Router struct {
	rules map[string]types.Tier
}

// New creates a Router loaded with default routing rules.
func New() *Router {
	r := &Router{rules: make(map[string]types.Tier)}
	for tool, tier := range defaultRules() {
		r.rules[tool] = tier
	}
	return r
}

// Resolve returns the tier for the given tool name.
// Returns an error if the tool is unknown.
func (r *Router) Resolve(tool string) (types.Tier, error) {
	tier, ok := r.rules[tool]
	if !ok {
		return "", fmt.Errorf("no routing rule for tool %q", tool)
	}
	return tier, nil
}

// Register adds or overrides a routing rule at runtime.
func (r *Router) Register(tool string, tier types.Tier) {
	r.rules[tool] = tier
}
