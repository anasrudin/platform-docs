package firecracker

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// SnapshotMeta mirrors the meta.json written by snapshot-builder.sh.
type SnapshotMeta struct {
	Name      string    `json:"name"`
	Version   string    `json:"version"`
	Kernel    string    `json:"kernel"`
	Rootfs    string    `json:"rootfs"`
	VCPUs     int       `json:"vcpus"`
	MemMiB    int       `json:"mem_mib"`
	CreatedAt time.Time `json:"created_at"`
	DryRun    bool      `json:"dry_run,omitempty"`
	Files     struct {
		State string `json:"state"`
		Mem   string `json:"mem"`
	} `json:"files"`
}

// SnapshotPaths holds the local paths to all snapshot files.
type SnapshotPaths struct {
	StateFile string
	MemFile   string
	MetaFile  string
	Meta      SnapshotMeta
}

// SnapshotStore downloads and caches snapshots from MinIO.
// On cache hit it returns immediately; on miss it pulls via `mc cp`.
type SnapshotStore struct {
	endpoint  string // e.g. http://localhost:9000
	accessKey string
	secretKey string
	bucket    string
	cacheDir  string // local cache root
}

func newSnapshotStore(cfg Config) *SnapshotStore {
	return &SnapshotStore{
		endpoint:  cfg.MinIOEndpoint,
		accessKey: cfg.MinIOAccessKey,
		secretKey: cfg.MinIOSecretKey,
		bucket:    cfg.MinIOBucket,
		cacheDir:  cfg.SnapshotCacheDir,
	}
}

// Ensure returns local paths for the named snapshot, downloading from MinIO if needed.
func (s *SnapshotStore) Ensure(name string) (SnapshotPaths, error) {
	localDir := filepath.Join(s.cacheDir, name)
	paths := SnapshotPaths{
		StateFile: filepath.Join(localDir, "vmstate.bin"),
		MemFile:   filepath.Join(localDir, "memory.bin"),
		MetaFile:  filepath.Join(localDir, "meta.json"),
	}

	// If all files are cached locally, use them.
	if s.allExist(paths.StateFile, paths.MemFile, paths.MetaFile) {
		slog.Debug("snapshot cache hit", "name", name)
		return s.loadMeta(paths)
	}

	slog.Info("snapshot not cached, downloading from MinIO", "name", name)
	if err := os.MkdirAll(localDir, 0o755); err != nil {
		return paths, fmt.Errorf("mkdir %s: %w", localDir, err)
	}

	prefix := fmt.Sprintf("%s/%s/", s.bucket, name)
	if err := s.pullFromMinio(prefix, localDir); err != nil {
		// Fallback: try plain HTTP download (anonymous or presigned)
		slog.Warn("mc pull failed, trying HTTP download", "err", err)
		if httpErr := s.httpDownload(name, paths); httpErr != nil {
			return paths, fmt.Errorf("MinIO download failed: mc: %w | http: %v", err, httpErr)
		}
	}

	return s.loadMeta(paths)
}

// pullFromMinio uses the `mc` CLI if available.
func (s *SnapshotStore) pullFromMinio(prefix, destDir string) error {
	mc, err := exec.LookPath("mc")
	if err != nil {
		return fmt.Errorf("mc not found: %w", err)
	}

	alias := fmt.Sprintf("fc-dl-%d", time.Now().UnixNano())
	setup := exec.Command(mc, "alias", "set", alias,
		s.endpoint, s.accessKey, s.secretKey, "--quiet")
	if out, err := setup.CombinedOutput(); err != nil {
		return fmt.Errorf("mc alias set: %w: %s", err, out)
	}
	defer exec.Command(mc, "alias", "remove", alias).Run() //nolint:errcheck

	mirror := exec.Command(mc, "mirror", "--quiet",
		alias+"/"+prefix, destDir)
	if out, err := mirror.CombinedOutput(); err != nil {
		return fmt.Errorf("mc mirror: %w: %s", err, out)
	}
	return nil
}

// httpDownload fetches snapshot files via plain HTTP GET from MinIO.
func (s *SnapshotStore) httpDownload(name string, paths SnapshotPaths) error {
	base := fmt.Sprintf("%s/%s/%s", s.endpoint, s.bucket, name)
	files := map[string]string{
		base + "/vmstate.bin": paths.StateFile,
		base + "/memory.bin":  paths.MemFile,
		base + "/meta.json":   paths.MetaFile,
	}
	for url, dest := range files {
		if err := downloadFile(url, dest); err != nil {
			return fmt.Errorf("GET %s: %w", url, err)
		}
	}
	return nil
}

func downloadFile(url, dest string) error {
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

func (s *SnapshotStore) loadMeta(paths SnapshotPaths) (SnapshotPaths, error) {
	data, err := os.ReadFile(paths.MetaFile)
	if err != nil {
		return paths, fmt.Errorf("read meta.json: %w", err)
	}
	if err := json.Unmarshal(data, &paths.Meta); err != nil {
		return paths, fmt.Errorf("parse meta.json: %w", err)
	}
	return paths, nil
}

func (s *SnapshotStore) allExist(files ...string) bool {
	for _, f := range files {
		if _, err := os.Stat(f); err != nil {
			return false
		}
	}
	return true
}
