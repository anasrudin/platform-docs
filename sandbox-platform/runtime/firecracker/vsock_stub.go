//go:build !linux

package firecracker

import (
	"fmt"
	"net"
)

// dialVsock is a stub for non-Linux platforms.
// On macOS or Windows, vsock is unavailable; the runtime falls back to TCP (sim mode).
func dialVsock(cid, port uint32) (net.Conn, error) {
	return nil, fmt.Errorf("vsock not supported on this platform (cid=%d port=%d)", cid, port)
}
