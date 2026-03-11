package firecracker

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
)

// GuestRequest is the JSON payload sent to the guest agent.
type GuestRequest struct {
	Tool  string         `json:"tool"`
	Input map[string]any `json:"input"`
}

// GuestResponse is returned by the guest agent.
type GuestResponse struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
}

// GuestClient communicates with the agent running inside a Firecracker VM.
// It sends requests over a vsock connection (Linux) or TCP (dev/test mode).
type GuestClient struct {
	cid     uint32 // vsock CID of the guest VM
	port    uint32 // vsock port the guest agent listens on (8080)
	timeout time.Duration
	tcpAddr string // non-empty → use TCP instead of vsock (dev fallback)
}

const guestAgentPort = 8080

func newGuestClient(cid uint32, tcpAddr string) *GuestClient {
	return &GuestClient{
		cid:     cid,
		port:    guestAgentPort,
		timeout: 30 * time.Second,
		tcpAddr: tcpAddr,
	}
}

// Execute sends a tool execution request to the guest agent and waits for the result.
func (g *GuestClient) Execute(tool string, input map[string]any) (GuestResponse, error) {
	payload, err := json.Marshal(GuestRequest{Tool: tool, Input: input})
	if err != nil {
		return GuestResponse{}, fmt.Errorf("marshal request: %w", err)
	}

	conn, err := g.dial()
	if err != nil {
		return GuestResponse{}, fmt.Errorf("connect to guest: %w", err)
	}
	defer conn.Close()

	_ = conn.SetDeadline(time.Now().Add(g.timeout))

	// Protocol: "POST /execute HTTP/1.0\n\n<json payload>"
	// The guest agent reads until "\n\n" then parses the JSON body.
	msg := fmt.Sprintf("POST /execute HTTP/1.0\nContent-Length: %d\n\n%s",
		len(payload), payload)
	if _, err := io.WriteString(conn, msg); err != nil {
		return GuestResponse{}, fmt.Errorf("send request: %w", err)
	}

	raw, err := io.ReadAll(conn)
	if err != nil {
		return GuestResponse{}, fmt.Errorf("read response: %w", err)
	}

	// Strip a trailing newline added by the agent
	body := strings.TrimRight(string(raw), "\n")
	var resp GuestResponse
	if err := json.Unmarshal([]byte(body), &resp); err != nil {
		return GuestResponse{}, fmt.Errorf("parse response %q: %w", body, err)
	}
	return resp, nil
}

// WaitReady polls the guest agent until it is accepting connections.
func (g *GuestClient) WaitReady(timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		conn, err := g.dial()
		if err == nil {
			conn.Close()
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("guest agent not ready after %s", timeout)
}

// dial opens a connection to the guest: vsock on Linux, TCP otherwise.
func (g *GuestClient) dial() (net.Conn, error) {
	if g.tcpAddr != "" {
		return net.DialTimeout("tcp", g.tcpAddr, 3*time.Second)
	}
	return dialVsock(g.cid, g.port)
}

// httpTransportOverVsock returns an http.Transport that routes over vsock.
// Useful if the guest agent exposes a real HTTP server rather than raw socket.
func httpTransportOverVsock(cid, port uint32) *http.Transport {
	return &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return dialVsock(cid, port)
		},
	}
}
