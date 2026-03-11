package firecracker

import (
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"
)

// VMPool maintains a warm pool of Firecracker microVMs ready for execution.
// Each VM is single-use: after job completion the VM is destroyed and a new
// one is pre-warmed from snapshot in the background.
type VMPool struct {
	mu       sync.Mutex
	ready    chan *FirecrackerVM
	cfg      Config
	store    *SnapshotStore
	nextCID  atomic.Uint32
	stopping chan struct{}
	wg       sync.WaitGroup
}

func newVMPool(cfg Config, store *SnapshotStore) *VMPool {
	p := &VMPool{
		cfg:      cfg,
		store:    store,
		ready:    make(chan *FirecrackerVM, cfg.PoolSize),
		stopping: make(chan struct{}),
	}
	// CIDs 0-2 are reserved by the kernel; start at 3.
	p.nextCID.Store(3)
	return p
}

// Warmup fills the pool up to PoolSize. Blocking: waits for the first VM.
func (p *VMPool) Warmup() error {
	snap, err := p.store.Ensure(p.cfg.SnapshotName)
	if err != nil {
		return fmt.Errorf("ensure snapshot %q: %w", p.cfg.SnapshotName, err)
	}

	// Start all VMs concurrently, block until at least one is ready.
	errs := make(chan error, p.cfg.PoolSize)
	for i := 0; i < p.cfg.PoolSize; i++ {
		p.wg.Add(1)
		go func() {
			defer p.wg.Done()
			vm, err := p.bootVM(snap)
			if err != nil {
				errs <- err
				return
			}
			select {
			case p.ready <- vm:
			case <-p.stopping:
				_ = vm.destroy()
			}
		}()
	}

	// Wait for at least one VM or all failures.
	select {
	case vm := <-p.ready:
		p.ready <- vm // put it back
		return nil
	case err := <-errs:
		return fmt.Errorf("warmup: %w", err)
	case <-time.After(60 * time.Second):
		return fmt.Errorf("warmup timeout after 60s")
	}
}

// Acquire pops a ready VM from the pool. Blocks up to timeout.
func (p *VMPool) Acquire(timeout time.Duration) (*FirecrackerVM, error) {
	select {
	case vm := <-p.ready:
		return vm, nil
	case <-time.After(timeout):
		return nil, fmt.Errorf("pool acquire timeout after %s", timeout)
	}
}

// Release destroys the VM and replenishes the pool with a fresh one.
// Call this after job execution regardless of success/failure.
func (p *VMPool) Release(vm *FirecrackerVM) {
	_ = vm.destroy()
	p.wg.Add(1)
	go func() {
		defer p.wg.Done()
		select {
		case <-p.stopping:
			return
		default:
		}
		snap, err := p.store.Ensure(p.cfg.SnapshotName)
		if err != nil {
			slog.Error("pool replenish: ensure snapshot", "err", err)
			return
		}
		newVM, err := p.bootVM(snap)
		if err != nil {
			slog.Error("pool replenish: boot VM", "err", err)
			return
		}
		select {
		case p.ready <- newVM:
			slog.Debug("pool replenished", "pool_size", len(p.ready))
		case <-p.stopping:
			_ = newVM.destroy()
		}
	}()
}

// Drain stops all background goroutines and destroys pooled VMs.
func (p *VMPool) Drain() {
	close(p.stopping)
	p.wg.Wait()
	for {
		select {
		case vm := <-p.ready:
			_ = vm.destroy()
		default:
			return
		}
	}
}

func (p *VMPool) bootVM(snap SnapshotPaths) (*FirecrackerVM, error) {
	cid := p.nextCID.Add(1)
	workDir := fmt.Sprintf("%s/vms/vm-%d", p.cfg.SnapshotCacheDir, cid)
	return newVM(snap, cid, workDir, p.cfg)
}
