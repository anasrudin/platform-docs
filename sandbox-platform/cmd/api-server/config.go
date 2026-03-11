package main

import (
	"fmt"
	"strings"

	"github.com/spf13/viper"
)

// Config holds all runtime configuration for the API server.
type Config struct {
	Server   ServerConfig
	Redis    RedisConfig
	MinIO    MinIOConfig
	Metrics  MetricsConfig
	Platform PlatformConfig
}

type ServerConfig struct {
	Port            int    `mapstructure:"port"`
	ShutdownTimeout int    `mapstructure:"shutdown_timeout_seconds"`
	JWTPublicKey    string `mapstructure:"jwt_public_key_path"` // empty = dev mode
}

type RedisConfig struct {
	URL           string `mapstructure:"url"`
	JobStream     string `mapstructure:"job_stream"`
	ConsumerGroup string `mapstructure:"consumer_group"`
}

type MinIOConfig struct {
	Endpoint  string `mapstructure:"endpoint"`
	AccessKey string `mapstructure:"access_key"`
	SecretKey string `mapstructure:"secret_key"`
	Bucket    string `mapstructure:"bucket"`
	UseSSL    bool   `mapstructure:"use_ssl"`
}

type MetricsConfig struct {
	Port int `mapstructure:"port"`
}

type PlatformConfig struct {
	Namespace string `mapstructure:"namespace"`
}

// LoadConfig reads config from file and environment variables.
// Environment variables override file values (SANDBOX_ prefix, dots become underscores).
func LoadConfig(path string) (*Config, error) {
	v := viper.New()

	// Defaults
	v.SetDefault("server.port", 8080)
	v.SetDefault("server.shutdown_timeout_seconds", 30)
	v.SetDefault("redis.url", "redis://localhost:6379")
	v.SetDefault("redis.job_stream", "jobs")
	v.SetDefault("redis.consumer_group", "platform")
	v.SetDefault("minio.endpoint", "localhost:9000")
	v.SetDefault("minio.access_key", "minioadmin")
	v.SetDefault("minio.secret_key", "minioadmin")
	v.SetDefault("minio.bucket", "platform")
	v.SetDefault("minio.use_ssl", false)
	v.SetDefault("metrics.port", 9090)
	v.SetDefault("platform.namespace", "default")

	if path != "" {
		v.SetConfigFile(path)
		if err := v.ReadInConfig(); err != nil {
			return nil, fmt.Errorf("read config: %w", err)
		}
	}

	// Allow env overrides: SANDBOX_SERVER_PORT=9090 overrides server.port
	v.SetEnvPrefix("SANDBOX")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("unmarshal config: %w", err)
	}
	return &cfg, nil
}
