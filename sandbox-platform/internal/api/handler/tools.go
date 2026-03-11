package handler

import (
	"github.com/gofiber/fiber/v2"
	"github.com/sandbox/platform/internal/tool/registry"
)

// ToolsHandler handles GET /v1/tools.
type ToolsHandler struct {
	tools *registry.Registry
}

// NewToolsHandler creates a ToolsHandler.
func NewToolsHandler(tools *registry.Registry) *ToolsHandler {
	return &ToolsHandler{tools: tools}
}

// List returns all registered tools.
func (h *ToolsHandler) List(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{"tools": h.tools.All()})
}
