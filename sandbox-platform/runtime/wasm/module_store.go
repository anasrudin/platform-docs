package wasm

import (
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// ModuleStore downloads and caches .wasm modules from MinIO.
// On cache hit it returns immediately; on miss it pulls via `mc cp` or HTTP GET.
type ModuleStore struct {
	endpoint  string // e.g. http://localhost:9000
	accessKey string
	secretKey string
	bucket    string
	cacheDir  string // local cache root
}

func newModuleStore(cfg Config) *ModuleStore {
	return &ModuleStore{
		endpoint:  cfg.MinIOEndpoint,
		accessKey: cfg.MinIOAccessKey,
		secretKey: cfg.MinIOSecretKey,
		bucket:    cfg.MinIOBucket,
		cacheDir:  cfg.ModuleCacheDir,
	}
}

// Ensure returns the local path to <tool>.wasm, downloading from MinIO if needed.
func (s *ModuleStore) Ensure(tool string) (string, error) {
	filename := tool + ".wasm"
	localPath := filepath.Join(s.cacheDir, filename)

	if _, err := os.Stat(localPath); err == nil {
		slog.Debug("module cache hit", "tool", tool)
		return localPath, nil
	}

	slog.Info("module not cached, downloading from MinIO", "tool", tool)
	if err := os.MkdirAll(s.cacheDir, 0o755); err != nil {
		return "", fmt.Errorf("mkdir %s: %w", s.cacheDir, err)
	}

	key := fmt.Sprintf("%s/%s", s.bucket, filename)
	if err := s.pullFromMinio(key, localPath); err != nil {
		slog.Warn("mc pull failed, trying HTTP download", "err", err)
		url := fmt.Sprintf("%s/%s/%s", s.endpoint, s.bucket, filename)
		if httpErr := downloadModuleFile(url, localPath); httpErr != nil {
			return "", fmt.Errorf("MinIO download failed: mc: %w | http: %v", err, httpErr)
		}
	}

	return localPath, nil
}

func (s *ModuleStore) pullFromMinio(key, dest string) error {
	mc, err := exec.LookPath("mc")
	if err != nil {
		return fmt.Errorf("mc not found: %w", err)
	}

	alias := fmt.Sprintf("wasm-dl-%d", time.Now().UnixNano())
	setup := exec.Command(mc, "alias", "set", alias,
		s.endpoint, s.accessKey, s.secretKey, "--quiet")
	if out, err := setup.CombinedOutput(); err != nil {
		return fmt.Errorf("mc alias set: %w: %s", err, out)
	}
	defer exec.Command(mc, "alias", "remove", alias).Run() //nolint:errcheck

	cp := exec.Command(mc, "cp", "--quiet", alias+"/"+key, dest)
	if out, err := cp.CombinedOutput(); err != nil {
		return fmt.Errorf("mc cp: %w: %s", err, out)
	}
	return nil
}

func downloadModuleFile(url, dest string) error {
	resp, err := http.Get(url) //nolint:noctx
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, resp.Body)
	return err
}
