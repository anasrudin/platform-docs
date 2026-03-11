package firecracker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/google/uuid"
)

// VMState tracks the lifecycle of a single microVM.
type VMState int

const (
	VMStateBooting VMState = iota
	VMStateReady
	VMStateBusy
	VMStateDestroyed
)

// FirecrackerVM represents a single Firecracker microVM instance.
type FirecrackerVM struct {
	id       string
	cid      uint32
	pid      int
	apiSock  string
	logPath  string
	state    VMState
	snap     SnapshotPaths
	guest    *GuestClient
	bootedAt time.Time
	process  *os.Process
}

// newVM starts a Firecracker process and restores it from a snapshot.
func newVM(snap SnapshotPaths, cid uint32, workDir string, cfg Config) (*FirecrackerVM, error) {
	id := uuid.New().String()[:8]
	apiSock := filepath.Join(workDir, fmt.Sprintf("fc-%s.sock", id))
	logPath := filepath.Join(workDir, fmt.Sprintf("fc-%s.log", id))

	if err := os.MkdirAll(workDir, 0o755); err != nil {
		return nil, fmt.Errorf("mkdir workdir: %w", err)
	}

	// Start the Firecracker process.
	cmd := exec.Command(cfg.FirecrackerBin,
		"--api-sock", apiSock,
		"--log-path", logPath,
		"--level", "Error",
	)
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start firecracker: %w", err)
	}

	vm := &FirecrackerVM{
		id:      id,
		cid:     cid,
		pid:     cmd.Process.Pid,
		apiSock: apiSock,
		logPath: logPath,
		state:   VMStateBooting,
		snap:    snap,
		process: cmd.Process,
	}

	// Wait for API socket.
	if err := vm.waitForSocket(3 * time.Second); err != nil {
		_ = cmd.Process.Kill()
		return nil, fmt.Errorf("FC socket timeout: %w", err)
	}

	// Restore from snapshot.
	if err := vm.restore(snap, cid); err != nil {
		_ = vm.destroy()
		return nil, fmt.Errorf("restore snapshot: %w", err)
	}

	// Resume the VM.
	if err := vm.apiPatch("/vm", map[string]string{"state": "Resumed"}); err != nil {
		_ = vm.destroy()
		return nil, fmt.Errorf("resume VM: %w", err)
	}

	vm.bootedAt = time.Now()
	vm.state = VMStateReady

	// Guest communication: vsock in production, TCP in dev mode.
	guestAddr := ""
	if cfg.DevMode {
		guestAddr = fmt.Sprintf("127.0.0.1:%d", guestAgentPort)
	}
	vm.guest = newGuestClient(cid, guestAddr)

	// Wait for guest agent to be ready.
	if err := vm.guest.WaitReady(15 * time.Second); err != nil {
		_ = vm.destroy()
		return nil, fmt.Errorf("guest not ready: %w", err)
	}

	slog.Info("vm ready", "id", vm.id, "cid", cid, "pid", vm.pid)
	return vm, nil
}

// restore sends the snapshot load request to the Firecracker API.
func (vm *FirecrackerVM) restore(snap SnapshotPaths, cid uint32) error {
	body := map[string]any{
		"snapshot_path": snap.StateFile,
		"mem_file_path": snap.MemFile,
		"backend_type":  "File",
		"enable_diff_snapshots": false,
	}

	// Wire vsock device so the guest can communicate back.
	if vsockErr := vm.apiPut("/vsock", map[string]any{
		"guest_cid": cid,
		"uds_path":  fmt.Sprintf("/tmp/fc-vsock-%s.sock", vm.id),
	}); vsockErr != nil {
		slog.Warn("vsock setup failed (non-fatal in dev mode)", "err", vsockErr)
	}

	return vm.apiPut("/snapshot/load", body)
}

// execute sends a job to the guest agent and returns the result.
func (vm *FirecrackerVM) execute(tool string, input map[string]any) (GuestResponse, error) {
	vm.state = VMStateBusy
	defer func() { vm.state = VMStateReady }()
	return vm.guest.Execute(tool, input)
}

// destroy terminates the Firecracker process and removes its socket/log.
func (vm *FirecrackerVM) destroy() error {
	vm.state = VMStateDestroyed
	if vm.process != nil {
		_ = vm.process.Kill()
		_, _ = vm.process.Wait()
	}
	_ = os.Remove(vm.apiSock)
	_ = os.Remove(vm.logPath)
	slog.Debug("vm destroyed", "id", vm.id)
	return nil
}

// ── Firecracker API helpers ──────────────────────────────────────────────────

func (vm *FirecrackerVM) waitForSocket(timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(vm.apiSock); err == nil {
			return nil
		}
		time.Sleep(50 * time.Millisecond)
	}
	return fmt.Errorf("socket %s not ready after %s", vm.apiSock, timeout)
}

func (vm *FirecrackerVM) apiClient() *http.Client {
	return &http.Client{
		Transport: &http.Transport{
			DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", vm.apiSock)
			},
		},
		Timeout: 10 * time.Second,
	}
}

func (vm *FirecrackerVM) apiPut(path string, body any) error {
	return vm.apiCall("PUT", path, body)
}

func (vm *FirecrackerVM) apiPatch(path string, body any) error {
	return vm.apiCall("PATCH", path, body)
}

func (vm *FirecrackerVM) apiCall(method, path string, body any) error {
	data, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequest(method, "http://localhost"+path, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := vm.apiClient().Do(req)
	if err != nil {
		return fmt.Errorf("FC API %s %s: %w", method, path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("FC API %s %s: HTTP %d: %s", method, path, resp.StatusCode, raw)
	}
	return nil
}
