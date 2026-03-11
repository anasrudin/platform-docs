// Package artifacts provides upload and download of job artifacts via MinIO.
package artifacts

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

// Store handles artifact upload and download against a MinIO bucket.
type Store struct {
	endpoint  string // e.g. http://localhost:9000
	accessKey string
	secretKey string
	bucket    string
	localDir  string // optional local filesystem fallback for dev/test
}

// Config holds MinIO connection settings.
type Config struct {
	Endpoint  string // MINIO_ENDPOINT
	AccessKey string // MINIO_ACCESS_KEY
	SecretKey string // MINIO_SECRET_KEY
	Bucket    string // MINIO_ARTIFACTS_BUCKET, default platform-artifacts
	LocalDir  string // ARTIFACTS_LOCAL_DIR, optional dev/test fallback
}

// ConfigFromEnv reads artifact store config from environment variables.
func ConfigFromEnv() Config {
	return Config{
		Endpoint:  envOr("MINIO_ENDPOINT", "http://localhost:9000"),
		AccessKey: envOr("MINIO_ACCESS_KEY", "minioadmin"),
		SecretKey: envOr("MINIO_SECRET_KEY", "minioadmin"),
		Bucket:    envOr("MINIO_ARTIFACTS_BUCKET", "platform-artifacts"),
		LocalDir:  envOr("ARTIFACTS_LOCAL_DIR", ""),
	}
}

// New creates an artifact Store.
func New(cfg Config) *Store {
	return &Store{
		endpoint:  cfg.Endpoint,
		accessKey: cfg.AccessKey,
		secretKey: cfg.SecretKey,
		bucket:    cfg.Bucket,
		localDir:  cfg.LocalDir,
	}
}

// Upload writes src to MinIO at <bucket>/<artifactID>/<name>.
// Returns the MinIO key on success.
func (s *Store) Upload(artifactID, name string, src io.Reader) (string, error) {
	key := fmt.Sprintf("%s/%s", artifactID, name)

	if s.localDir != "" {
		if err := s.writeLocal(key, src); err != nil {
			return "", fmt.Errorf("upload to local store: %w", err)
		}
		slog.Info("artifact uploaded to local store", "key", key, "dir", s.localDir)
		return key, nil
	}

	// Write to temp file first, then push via mc.
	tmp, err := os.CreateTemp("", "artifact-*")
	if err != nil {
		return "", fmt.Errorf("create temp file: %w", err)
	}
	defer os.Remove(tmp.Name())

	if _, err := io.Copy(tmp, src); err != nil {
		tmp.Close()
		return "", fmt.Errorf("buffer artifact: %w", err)
	}
	tmp.Close()

	if err := s.pushToMinio(tmp.Name(), key); err != nil {
		return "", fmt.Errorf("upload to MinIO: %w", err)
	}

	slog.Info("artifact uploaded", "key", key, "bucket", s.bucket)
	return key, nil
}

// Download fetches an artifact by key and writes it to dst.
func (s *Store) Download(key string, dst io.Writer) error {
	if s.localDir != "" {
		return s.readLocal(key, dst)
	}

	tmp, err := os.CreateTemp("", "artifact-dl-*")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	tmpName := tmp.Name()
	tmp.Close()
	defer os.Remove(tmpName)

	if err := s.pullFromMinio(key, tmpName); err != nil {
		// Fallback to HTTP GET (works when MinIO bucket is public read).
		slog.Warn("mc pull failed, trying HTTP fallback", "err", err)
		url := fmt.Sprintf("%s/%s/%s", s.endpoint, s.bucket, key)
		if httpErr := s.httpGet(url, tmpName); httpErr != nil {
			return fmt.Errorf("download failed: mc: %w | http: %v", err, httpErr)
		}
	}

	f, err := os.Open(tmpName)
	if err != nil {
		return fmt.Errorf("open downloaded file: %w", err)
	}
	defer f.Close()

	_, err = io.Copy(dst, f)
	return err
}

// URL returns the direct MinIO URL for an artifact key.
func (s *Store) URL(key string) string {
	if s.localDir != "" {
		return "/artifacts/" + key
	}
	return fmt.Sprintf("%s/%s/%s", s.endpoint, s.bucket, key)
}

// ── MinIO helpers ─────────────────────────────────────────────────────────────

func (s *Store) mcAlias() (mc, alias string, cleanup func(), err error) {
	mc, err = exec.LookPath("mc")
	if err != nil {
		return "", "", nil, fmt.Errorf("mc not found: %w", err)
	}
	alias = fmt.Sprintf("art-%d", time.Now().UnixNano())
	setup := exec.Command(mc, "alias", "set", alias,
		s.endpoint, s.accessKey, s.secretKey, "--quiet")
	if out, setupErr := setup.CombinedOutput(); setupErr != nil {
		return "", "", nil, fmt.Errorf("mc alias set: %w: %s", setupErr, out)
	}
	cleanup = func() { exec.Command(mc, "alias", "remove", alias).Run() } //nolint:errcheck
	return mc, alias, cleanup, nil
}

// MCAvailable reports whether the MinIO client is available in PATH.
func MCAvailable() bool {
	_, err := exec.LookPath("mc")
	return err == nil
}

func (s *Store) pushToMinio(localPath, key string) error {
	mc, alias, cleanup, err := s.mcAlias()
	if err != nil {
		return err
	}
	defer cleanup()

	dest := fmt.Sprintf("%s/%s/%s", alias, s.bucket, key)
	cp := exec.Command(mc, "cp", "--quiet", localPath, dest)
	if out, err := cp.CombinedOutput(); err != nil {
		return fmt.Errorf("mc cp: %w: %s", err, out)
	}
	return nil
}

func (s *Store) pullFromMinio(key, dest string) error {
	mc, alias, cleanup, err := s.mcAlias()
	if err != nil {
		return err
	}
	defer cleanup()

	src := fmt.Sprintf("%s/%s/%s", alias, s.bucket, key)
	cp := exec.Command(mc, "cp", "--quiet", src, dest)
	if out, err := cp.CombinedOutput(); err != nil {
		return fmt.Errorf("mc cp: %w: %s", err, out)
	}
	return nil
}

func (s *Store) httpGet(url, dest string) error {
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

// ── Bucket bootstrap ──────────────────────────────────────────────────────────

// EnsureBucket creates the artifact bucket if it does not exist.
func (s *Store) EnsureBucket() error {
	if s.localDir != "" {
		return EnsureLocalDir(s.localDir)
	}

	mc, err := exec.LookPath("mc")
	if err != nil {
		return fmt.Errorf("mc not found: %w", err)
	}

	alias := fmt.Sprintf("art-init-%d", time.Now().UnixNano())
	setup := exec.Command(mc, "alias", "set", alias,
		s.endpoint, s.accessKey, s.secretKey, "--quiet")
	if out, err := setup.CombinedOutput(); err != nil {
		return fmt.Errorf("mc alias set: %w: %s", err, out)
	}
	defer exec.Command(mc, "alias", "remove", alias).Run() //nolint:errcheck

	mb := exec.Command(mc, "mb", "--ignore-existing", "--quiet",
		fmt.Sprintf("%s/%s", alias, s.bucket))
	if out, err := mb.CombinedOutput(); err != nil {
		return fmt.Errorf("mc mb: %w: %s", err, out)
	}
	return nil
}

func (s *Store) writeLocal(key string, src io.Reader) error {
	path := LocalPath(s.localDir, key)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create local artifact dir: %w", err)
	}

	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create local artifact file: %w", err)
	}
	defer f.Close()

	if _, err := io.Copy(f, src); err != nil {
		return fmt.Errorf("write local artifact file: %w", err)
	}
	return nil
}

func (s *Store) readLocal(key string, dst io.Writer) error {
	path := LocalPath(s.localDir, key)
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("open local artifact file: %w", err)
	}
	defer f.Close()

	_, err = io.Copy(dst, f)
	return err
}

// ── Local dir bootstrap (for tests / sim) ─────────────────────────────────────

// EnsureLocalDir creates a local directory to simulate an artifact store.
func EnsureLocalDir(dir string) error {
	return os.MkdirAll(dir, 0o755)
}

// LocalPath returns the local filesystem path for an artifact (used in tests).
func LocalPath(baseDir, key string) string {
	return filepath.Join(baseDir, filepath.FromSlash(key))
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
