# Deriv Auto Trading Bot

Bot Telegram untuk auto trading Binary Options di platform Deriv.

## Overview

Bot ini menggunakan strategi RSI (Relative Strength Index) dengan sistem Martingale untuk trading otomatis. Dibangun dengan Python dan menggunakan WebSocket untuk koneksi real-time ke Deriv API.

## Status: VERIFIED WORKING

Trading nyata berhasil terverifikasi pada 2025-12-05:
- Saldo berubah dari $10,000.00 ke $10,000.56 (+$0.56 USD)
- 3 trades dieksekusi (1 Win, 2 Loss)
- Martingale bekerja dengan baik

## Fitur Utama

- **Strategi RSI**: Analisis teknikal dengan RSI periode 14
  - BUY (Call): RSI < 30 (Oversold)
  - SELL (Put): RSI > 70 (Overbought)
  - WAIT: RSI 30-70 (Netral)
- **Martingale System**: Stake x 2.1 saat loss, reset ke base saat win
- **Multi-Account**: Support akun Demo dan Real
- **Real-time Monitoring**: Notifikasi instant via Telegram
- **Session Management**: Target jumlah trade dengan auto-stop

## Supported Symbols

| Symbol | Nama | Durasi Support | Keterangan |
|--------|------|----------------|------------|
| R_100 | Volatility 100 Index | 5t-10t (ticks) | **DEFAULT** - Ideal untuk short-term |
| R_50 | Volatility 50 Index | 5t-10t (ticks) | Short-term trading |
| frxXAUUSD | Gold/USD | 1d-365d (HARI!) | Hanya untuk long-term |

**PENTING**: XAUUSD hanya mendukung durasi HARIAN (min 1 hari), TIDAK bisa ticks/menit!

## Struktur File

```
├── main.py           # Entry point & Telegram handlers
├── strategy.py       # Modul strategi RSI
├── deriv_ws.py       # WebSocket client untuk Deriv API
├── trading.py        # Trading manager & Martingale
├── keep_alive.py     # Flask server untuk keep-alive
├── test_real_trade.py # Script test trading nyata
├── check_contracts.py # Check available contracts
└── requirements.txt  # Dependencies
```

## Setup & Konfigurasi

### Environment Variables (Secrets)

Bot memerlukan secrets berikut di Replit:

| Secret | Deskripsi |
|--------|-----------|
| `TELEGRAM_BOT_TOKEN` | Token dari @BotFather |
| `DERIV_TOKEN_DEMO` | API token akun demo Deriv |
| `DERIV_TOKEN_REAL` | API token akun real Deriv |

### Cara Mendapatkan Token

1. **Telegram Bot Token**: 
   - Chat dengan @BotFather di Telegram
   - Kirim `/newbot` dan ikuti instruksi
   
2. **Deriv API Token**:
   - Login ke [Deriv.com](https://deriv.com)
   - Buka Settings > API Token
   - Buat token dengan scope "Read" dan "Trade"

## Telegram Commands

| Command | Deskripsi |
|---------|-----------|
| `/start` | Mulai bot dan tampilkan menu |
| `/akun` | Kelola akun (saldo, switch demo/real) |
| `/autotrade [stake] [durasi] [target]` | Mulai auto trading |
| `/stop` | Hentikan trading |
| `/status` | Cek status bot |
| `/help` | Panduan penggunaan |

### Format Auto Trade

```
/autotrade [stake] [durasi] [target]
```

Contoh:
- `/autotrade` - Default ($0.50, 5t, 5 trade)
- `/autotrade 0.5` - Stake $0.5
- `/autotrade 1 5t 10` - $1, 5 ticks, 10 trade
- `/autotrade 0.50 5t 0` - Unlimited

Format Durasi:
- `5t` = 5 ticks (DEFAULT - untuk Volatility Index)
- `30s` = 30 detik
- `1m` = 1 menit (hanya untuk symbol tertentu)

### Minimum Stake

**Minimum stake: $0.50 USD**

## Arsitektur

### WebSocket Connection
- Menggunakan `websocket-client` native untuk low latency
- Auto reconnect jika disconnect
- Thread-safe untuk concurrent operations

### Trading Flow
1. Subscribe ke tick stream (R_100 Volatility Index)
2. Kumpulkan 15+ ticks untuk kalkulasi RSI
3. Analisis signal (BUY/SELL/WAIT)
4. Eksekusi trade jika ada signal valid
5. Subscribe ke contract updates
6. Deteksi win/loss secara real-time
7. Apply Martingale jika loss
8. Repeat sampai target tercapai

## Catatan Keamanan

- Token disimpan di Replit Secrets (terenkripsi)
- Tidak ada hardcoded credentials
- WebSocket menggunakan WSS (encrypted)

## Development

### Dependencies
- python-telegram-bot v22+
- websocket-client
- flask
- python-dotenv

### Running Locally
```bash
pip install -r requirements.txt
python main.py
```

### Test Trading
```bash
python test_real_trade.py
```

## Recent Changes (2025-12-05)

1. **Fixed Symbol**: Switched from XAUUSD to R_100 (Volatility 100 Index)
   - XAUUSD only supports daily durations (not suitable for auto trading)
   - R_100 supports tick durations (5t) - ideal for quick trades
   
2. **Fixed Minimum Stake**: Changed from $0.35 to $0.50
   - Deriv API requires minimum $0.50 USD stake
   
3. **Verified Real Trading**: Successfully executed real trades
   - Balance changed from $10,000.00 to $10,000.56
   - Martingale working correctly

4. **Added check_contracts.py**: Script to verify available contract types

## Disclaimer

Trading memiliki risiko tinggi. Bot ini untuk tujuan edukasi. Gunakan akun demo untuk testing sebelum menggunakan uang asli.
