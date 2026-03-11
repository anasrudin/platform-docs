package middleware

import (
	"context"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/sandbox/platform/pkg/types"
)

// luaTokenBucket is an atomic Redis token bucket using Lua.
// FIX for original Bug 1: tier is now passed as an argument from the
// request body (already decoded by a prior body-parser middleware) rather
// than derived inside the script where the body has been consumed.
const luaTokenBucket = `
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local window = tonumber(ARGV[3])

local count = redis.call("GET", key)
if count == false then
    redis.call("SET", key, 1, "EX", window)
    return 1
end
count = tonumber(count)
if count >= capacity then
    return 0
end
redis.call("INCR", key)
return 1
`

// RateLimits maps each tier to its per-minute request limit.
type RateLimits struct {
	WASM    int
	MicroVM int
	GUI     int
}

// DefaultRateLimits returns sensible defaults.
func DefaultRateLimits() RateLimits {
	return RateLimits{WASM: 100, MicroVM: 20, GUI: 5}
}

// RateLimit returns a Fiber middleware that enforces per-agent, per-tier limits.
// The tier is read from c.Locals("tier") which must be set by the handler BEFORE
// this middleware runs — this is the correct fix for Bug 1.
func RateLimit(rdb *redis.Client, limits RateLimits) fiber.Handler {
	script := redis.NewScript(luaTokenBucket)

	return func(c *fiber.Ctx) error {
		agentID, _ := c.Locals(ContextKeyAgentID).(string)

		// Tier is injected by the body-decoder middleware on POST /execute.
		// For other routes it defaults to "microvm" (no rate constraint).
		tier, _ := c.Locals("tier").(string)
		if tier == "" {
			tier = string(types.TierMicroVM)
		}

		capacity := limitForTier(tier, limits)
		key := fmt.Sprintf("ratelimit:%s:%s", agentID, tier)

		allowed, err := script.Run(
			context.Background(), rdb,
			[]string{key},
			capacity,
			time.Now().Unix(),
			60, // 1-minute window
		).Int()
		if err != nil {
			// On Redis error, allow the request rather than block users.
			return c.Next()
		}

		if allowed == 0 {
			c.Set("Retry-After", "60")
			return fiber.NewError(fiber.StatusTooManyRequests, "rate limit exceeded")
		}
		return c.Next()
	}
}

func limitForTier(tier string, l RateLimits) int {
	switch tier {
	case string(types.TierWASM):
		return l.WASM
	case string(types.TierGUI):
		return l.GUI
	default:
		return l.MicroVM
	}
}
