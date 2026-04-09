# HAProxy — Baremetal / Local Config

Static config tanpa service discovery. Backend di-hardcode.

## Cara pakai

### Local dev (semua service di localhost)

```bash
haproxy -f services/controller/haproxy/baremetal/haproxy.cfg
```

### Single-node server (ganti IP)

Edit `haproxy.cfg`, cari semua `127.0.0.1` dan ganti dengan IP server:

```
server fc-1   10.0.1.10:8081 check
server wasm-1 10.0.1.10:8082 check
server gui-1  10.0.1.10:8083 check
```

### Multi-node server (tambah baris server)

```
backend sandbox_microvm
    server fc-1 10.0.1.10:8081 check
    server fc-2 10.0.1.11:8081 check
    server fc-3 10.0.1.12:8081 check
```

## Mau pakai service discovery?

Gunakan `../server/` yang pakai consul-template.
HAProxy config akan auto-update saat node join/leave Consul.
