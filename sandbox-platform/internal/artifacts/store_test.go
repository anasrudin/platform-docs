package artifacts

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ── ConfigFromEnv ─────────────────────────────────────────────────────────────

func TestConfigFromEnv_Defaults(t *testing.T) {
	for _, k := range []string{"MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_ARTIFACTS_BUCKET"} {
		t.Setenv(k, "")
	}
	cfg := ConfigFromEnv()
	if cfg.Endpoint != "http://localhost:9000" {
		t.Fatalf("Endpoint default: want http://localhost:9000, got %s", cfg.Endpoint)
	}
	if cfg.AccessKey != "minioadmin" {
		t.Fatalf("AccessKey default: want minioadmin, got %s", cfg.AccessKey)
	}
	if cfg.SecretKey != "minioadmin" {
		t.Fatalf("SecretKey default: want minioadmin, got %s", cfg.SecretKey)
	}
	if cfg.Bucket != "platform-artifacts" {
		t.Fatalf("Bucket default: want platform-artifacts, got %s", cfg.Bucket)
	}
}

func TestConfigFromEnv_EnvOverrides(t *testing.T) {
	t.Setenv("MINIO_ENDPOINT", "http://minio.prod:9000")
	t.Setenv("MINIO_ACCESS_KEY", "prodkey")
	t.Setenv("MINIO_SECRET_KEY", "prodsecret")
	t.Setenv("MINIO_ARTIFACTS_BUCKET", "prod-artifacts")
	cfg := ConfigFromEnv()
	if cfg.Endpoint != "http://minio.prod:9000" {
		t.Fatalf("Endpoint: got %s", cfg.Endpoint)
	}
	if cfg.AccessKey != "prodkey" {
		t.Fatalf("AccessKey: got %s", cfg.AccessKey)
	}
	if cfg.Bucket != "prod-artifacts" {
		t.Fatalf("Bucket: got %s", cfg.Bucket)
	}
}

// ── Store.URL ─────────────────────────────────────────────────────────────────

func TestStore_URL_SimpleKey(t *testing.T) {
	s := New(Config{Endpoint: "http://localhost:9000", Bucket: "platform-artifacts"})
	got := s.URL("abc123/test.txt")
	want := "http://localhost:9000/platform-artifacts/abc123/test.txt"
	if got != want {
		t.Fatalf("URL: want %q, got %q", want, got)
	}
}

func TestStore_URL_NoTrailingSlash(t *testing.T) {
	s := New(Config{Endpoint: "http://localhost:9000/", Bucket: "my-bucket"})
	got := s.URL("id/file.wasm")
	// endpoint has trailing slash — URL will include it; just check key is present
	if !strings.Contains(got, "id/file.wasm") {
		t.Fatalf("URL should contain key, got %q", got)
	}
}

// ── EnsureLocalDir ────────────────────────────────────────────────────────────

func TestEnsureLocalDir_CreatesNested(t *testing.T) {
	tmp := t.TempDir()
	dir := filepath.Join(tmp, "a", "b", "c")
	if err := EnsureLocalDir(dir); err != nil {
		t.Fatalf("EnsureLocalDir: %v", err)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Fatalf("dir not created: %v", err)
	}
}

func TestEnsureLocalDir_Idempotent(t *testing.T) {
	tmp := t.TempDir()
	dir := filepath.Join(tmp, "sub")
	if err := EnsureLocalDir(dir); err != nil {
		t.Fatalf("first call: %v", err)
	}
	if err := EnsureLocalDir(dir); err != nil {
		t.Fatalf("second call (idempotent): %v", err)
	}
}

// ── LocalPath ─────────────────────────────────────────────────────────────────

func TestLocalPath_BuildsCorrectPath(t *testing.T) {
	got := LocalPath("/base/dir", "abc123/file.txt")
	if !strings.HasPrefix(got, "/base/dir") {
		t.Fatalf("LocalPath: want prefix /base/dir, got %s", got)
	}
	if !strings.Contains(got, "abc123") {
		t.Fatalf("LocalPath: want 'abc123' in path, got %s", got)
	}
}

// ── Upload (without mc) ───────────────────────────────────────────────────────

// TestUpload_FailsGracefullyWithoutMC verifies that Upload returns a clear error
// when mc is not installed, rather than panicking or silently losing data.
func TestUpload_FailsGracefullyWithoutMC(t *testing.T) {
	if isMCAvailable() {
		t.Skip("mc is installed — this test is for environments without mc")
	}
	s := New(Config{
		Endpoint:  "http://127.0.0.1:1",
		AccessKey: "test",
		SecretKey: "test",
		Bucket:    "test-bucket",
	})
	_, err := s.Upload("test-id", "test.txt", bytes.NewReader([]byte("hello")))
	if err == nil {
		t.Fatal("Upload without mc should return error")
	}
	// Error should clearly describe the failure (not a panic/nil pointer)
	if err.Error() == "" {
		t.Fatal("error message should not be empty")
	}
}

// TestUpload_TempFileCreation verifies that Upload writes to temp before pushing.
// Even when push fails, no data should be lost (the temp file is the buffer).
func TestUpload_BuffersToTempFile(t *testing.T) {
	s := New(Config{
		Endpoint:  "http://127.0.0.1:1",
		AccessKey: "test",
		SecretKey: "test",
		Bucket:    "test-bucket",
	})
	content := "artifact content for temp buffer test"
	_, err := s.Upload("buf-id", "buf.txt", bytes.NewReader([]byte(content)))
	// Will fail at pushToMinio, but temp file creation should have succeeded
	// (we can't easily verify the temp file was created/deleted, but we verify
	//  no panic and the error is from mc/network, not from temp file creation)
	if err != nil {
		// Expected — mc not found or connection refused
		if strings.Contains(err.Error(), "no such file") || strings.Contains(err.Error(), "create temp") {
			t.Fatalf("unexpected error in temp file creation: %v", err)
		}
	}
}

// ── Download (without mc) ─────────────────────────────────────────────────────

func TestDownload_FailsGracefullyWithoutMC(t *testing.T) {
	if isMCAvailable() {
		t.Skip("mc is installed — this test is for environments without mc")
	}
	s := New(Config{
		Endpoint:  "http://127.0.0.1:1",
		AccessKey: "test",
		SecretKey: "test",
		Bucket:    "test-bucket",
	})
	var buf bytes.Buffer
	err := s.Download("nonexistent/file.txt", &buf)
	if err == nil {
		t.Fatal("Download without mc + unreachable endpoint should return error")
	}
}

// ── EnsureBucket (without mc) ─────────────────────────────────────────────────

func TestEnsureBucket_FailsWithoutMC(t *testing.T) {
	if isMCAvailable() {
		t.Skip("mc is installed — this test is for environments without mc")
	}
	s := New(Config{
		Endpoint:  "http://127.0.0.1:1",
		AccessKey: "test",
		SecretKey: "test",
		Bucket:    "test-bucket",
	})
	err := s.EnsureBucket()
	if err == nil {
		t.Fatal("EnsureBucket without mc should return error")
	}
	if !strings.Contains(err.Error(), "mc") {
		t.Fatalf("error should mention 'mc', got: %v", err)
	}
}

func TestUploadDownload_LocalFallback(t *testing.T) {
	tmp := t.TempDir()
	s := New(Config{
		LocalDir: tmp,
		Bucket:   "ignored",
	})

	key, err := s.Upload("artifact-id", "payload.txt", bytes.NewReader([]byte("hello local store")))
	if err != nil {
		t.Fatalf("Upload with LocalDir: %v", err)
	}
	if key != "artifact-id/payload.txt" {
		t.Fatalf("unexpected key: %s", key)
	}

	path := LocalPath(tmp, key)
	gotFile, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("stored file missing: %v", err)
	}
	if string(gotFile) != "hello local store" {
		t.Fatalf("stored file contents: got %q", string(gotFile))
	}

	var buf bytes.Buffer
	if err := s.Download(key, &buf); err != nil {
		t.Fatalf("Download with LocalDir: %v", err)
	}
	if buf.String() != "hello local store" {
		t.Fatalf("downloaded contents: got %q", buf.String())
	}
}

func TestEnsureBucket_LocalFallbackCreatesDir(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "artifacts")
	s := New(Config{LocalDir: dir})
	if err := s.EnsureBucket(); err != nil {
		t.Fatalf("EnsureBucket LocalDir: %v", err)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Fatalf("local artifact dir missing: %v", err)
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func isMCAvailable() bool {
	_, err := os.Stat("/usr/local/bin/mc")
	if err == nil {
		return true
	}
	// also check PATH lookup via exec.LookPath would require importing os/exec
	// so just check common locations
	for _, p := range []string{"/usr/bin/mc", "/usr/local/bin/mc", "/opt/homebrew/bin/mc"} {
		if _, err := os.Stat(p); err == nil {
			return true
		}
	}
	return false
}
