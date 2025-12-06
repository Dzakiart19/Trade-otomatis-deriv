# Deploy ke Koyeb (24/7 Non-Stop)

## Langkah-langkah Deploy

### 1. Buat Akun Koyeb
- Buka https://www.koyeb.com
- Daftar dengan GitHub atau email

### 2. Siapkan Repository
Push project ini ke GitHub:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/deriv-trading-bot.git
git push -u origin main
```

### 3. Buat Secrets di Koyeb
Di Koyeb Dashboard > Settings > Secrets, tambahkan:
- `TELEGRAM_BOT_TOKEN`: Token bot Telegram Anda
- `DERIV_APP_ID`: App ID dari Deriv (contoh: 114791)
- `SESSION_SECRET`: Random string untuk enkripsi (generate dengan: `openssl rand -base64 32`)

### 4. Deploy via Koyeb Dashboard

1. Klik **"Create App"**
2. Pilih **"Docker"** sebagai build method
3. Connect ke repository GitHub Anda
4. Pilih branch `main`

**PENTING - Konfigurasi Service:**

5. **Service type**: Pilih **"Web"** (BUKAN Worker!)
6. **Instance type**: **eco-small** (FREE)
7. **Region**: Frankfurt (fra) atau Singapore (sgp)
8. **Port**: `8000`

**Environment Variables:**
| Key | Value |
|-----|-------|
| `PYTHONUNBUFFERED` | `1` |
| `TZ` | `Asia/Jakarta` |
| `PORT` | `8000` |
| `TELEGRAM_BOT_TOKEN` | `@secret:TELEGRAM_BOT_TOKEN` |
| `DERIV_APP_ID` | `@secret:DERIV_APP_ID` |
| `SESSION_SECRET` | `@secret:SESSION_SECRET` |

**Health Check Configuration:**
| Setting | Value |
|---------|-------|
| Type | HTTP |
| Port | `8000` |
| Path | `/api/health` atau `/health` |
| Interval | 30 seconds |
| Timeout | 10 seconds |
| Grace Period | 60 seconds |

9. Klik **"Deploy"**

### 5. Deploy via koyeb.yaml (CLI)

File `koyeb.yaml` sudah dikonfigurasi dengan benar. Jalankan:

```bash
# Install Koyeb CLI
curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | bash

# Login
koyeb login

# Deploy
koyeb deploy . --app deriv-trading-bot
```

## Kenapa Bot Gagal Deploy Sebelumnya?

**Masalah**: "TCP health check failed on port 8000"

**Penyebab**:
1. Port tidak sesuai - Dockerfile EXPOSE 8000 tapi app jalan di 5000
2. Health check tidak dikonfigurasi dengan benar
3. Service type Worker tidak punya HTTP response

**Solusi yang sudah diperbaiki**:
1. Aplikasi sekarang jalan di port 8000 (sesuai Dockerfile)
2. Health check endpoint tersedia di `/health` dan `/api/health`
3. Menggunakan Web service type dengan HTTP health check

## Mengakses Dashboard

Setelah deploy sukses, domain dashboard Anda akan muncul di:
- Koyeb Dashboard > App > Service > **Public URL**
- Format: `https://your-app-name-xxxx.koyeb.app`

Dashboard tersedia di root URL tersebut.

## Free Tier Koyeb
- **eco-small**: 512MB RAM, shared CPU
- **Jam gratis**: Cukup untuk 24/7 dengan 1 service
- **Biaya tambahan**: $0 jika tetap di free tier

## Monitoring
- Lihat logs di Koyeb Dashboard > App > Logs
- Bot akan otomatis restart jika crash (karena health check)
- Telegram notifications tetap berjalan 24/7

## Troubleshooting

### 1. "TCP health check failed"
- Pastikan PORT environment variable = 8000
- Pastikan health check path = `/api/health` atau `/health`
- Pastikan service type = Web

### 2. Bot tidak jalan
- Cek logs di Koyeb Dashboard
- Pastikan semua secrets sudah diisi

### 3. Secrets tidak terbaca
- Pastikan format `@secret:NAMA_SECRET`
- Pastikan secret sudah dibuat di Settings > Secrets

### 4. Memory limit
- eco-small punya 512MB, cukup untuk bot ini
- Jika butuh lebih, upgrade ke instance type yang lebih besar

## File yang Dibutuhkan
- `Dockerfile` - Konfigurasi Docker (EXPOSE 8000)
- `requirements.txt` - Dependensi Python
- `koyeb.yaml` - Konfigurasi Koyeb (opsional tapi recommended)
- `.dockerignore` - File yang diabaikan saat build

## Health Check Endpoints
Bot menyediakan 2 endpoint untuk health check:
- `GET /health` - Simple health check
- `GET /api/health` - Detailed health check dengan info subscribers

Kedua endpoint tidak butuh authentication.
