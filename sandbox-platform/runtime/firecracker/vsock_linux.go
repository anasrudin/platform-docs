//go:build linux

package firecracker

import (
	"fmt"
	"net"
	"os"
	"syscall"
)

// AF_VSOCK is the Linux address family for VM sockets.
const afVsock = 40 // syscall.AF_VSOCK on Linux

// dialVsock opens a stream connection to (cid, port) using VM sockets (vsock).
// This is the native Linux implementation.
func dialVsock(cid, port uint32) (net.Conn, error) {
	fd, err := syscall.Socket(afVsock, syscall.SOCK_STREAM, 0)
	if err != nil {
		return nil, fmt.Errorf("vsock socket: %w", err)
	}

	addr := &syscall.SockaddrVM{CID: cid, Port: port}
	if err := syscall.Connect(fd, addr); err != nil {
		_ = syscall.Close(fd)
		return nil, fmt.Errorf("vsock connect cid=%d port=%d: %w", cid, port, err)
	}

	file := os.NewFile(uintptr(fd), fmt.Sprintf("vsock:%d:%d", cid, port))
	conn, err := net.FileConn(file)
	_ = file.Close() // net.FileConn dups the fd; close the original
	if err != nil {
		return nil, fmt.Errorf("vsock FileConn: %w", err)
	}
	return conn, nil
}
