# Deploy ke Koyeb (Free Tier - 24/7)

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
1. Klik "Create App"
2. Pilih "Docker" sebagai build method
3. Connect ke repository GitHub Anda
4. Pilih branch `main`
5. Instance type: **eco-small** (FREE)
6. Region: Frankfurt (fra) atau Singapore (sgp)
7. Service type: **Worker** (bukan Web)
8. Tambahkan environment variables:
   - `PYTHONUNBUFFERED`: `1`
   - `TZ`: `Asia/Jakarta`
   - `TELEGRAM_BOT_TOKEN`: `@secret:TELEGRAM_BOT_TOKEN`
   - `DERIV_APP_ID`: `@secret:DERIV_APP_ID`
   - `SESSION_SECRET`: `@secret:SESSION_SECRET`
9. Klik "Deploy"

### 5. Deploy via CLI (Alternatif)
```bash
# Install Koyeb CLI
curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | bash

# Login
koyeb login

# Deploy
koyeb deploy . --app deriv-trading-bot
```

## Free Tier Koyeb
- **eco-small**: 512MB RAM, shared CPU
- **Jam gratis**: 5.5 jam/hari per service
- **Untuk 24/7**: Butuh 1 service = cukup dengan free tier

## Monitoring
- Lihat logs di Koyeb Dashboard > App > Logs
- Bot akan otomatis restart jika crash
- Telegram notifications tetap berjalan

## Troubleshooting
1. **Bot tidak jalan**: Cek logs di Koyeb Dashboard
2. **Secrets tidak terbaca**: Pastikan format `@secret:NAMA_SECRET`
3. **Memory limit**: eco-small punya 512MB, cukup untuk bot ini

## File yang Dibutuhkan
- `Dockerfile` - Konfigurasi Docker
- `requirements.txt` - Dependensi Python
- `koyeb.yaml` - Konfigurasi Koyeb (opsional)
- `.dockerignore` - File yang diabaikan saat build
