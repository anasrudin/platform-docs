# Log Schema

All services in the platform must emit structured JSON logs to stdout.

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `ts` | string | RFC 3339 timestamp with milliseconds, UTC |
| `level` | string | Log level: `debug`, `info`, `warn`, `error` |
| `service` | string | Name of the service emitting the log (e.g., `platform-api`) |
| `trace_id` | string | UUID v4 trace ID for request correlation |
| `msg` | string | Human-readable log message |
| `duration_ms` | number | (Optional) Latency of the operation in milliseconds |

## Example

```json
{
  "ts": "2026-04-09T12:00:00.000Z",
  "level": "info",
  "service": "platform-api",
  "trace_id": "abc-123",
  "msg": "session started",
  "duration_ms": 4
}
```
