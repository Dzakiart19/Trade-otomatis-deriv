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
| R_75 | Volatility 75 Index | 5t-10t (ticks) | Medium volatility |
| R_50 | Volatility 50 Index | 5t-10t (ticks) | Short-term trading |
| R_25 | Volatility 25 Index | 5t-10t (ticks) | Low volatility |
| R_10 | Volatility 10 Index | 5t-10t (ticks) | Very low volatility |
| 1HZ100V | Volatility 100 (1s) Index | 5t-10t (ticks) | 1-second ticks - very fast |
| 1HZ75V | Volatility 75 (1s) Index | 5t-10t (ticks) | 1-second ticks |
| 1HZ50V | Volatility 50 (1s) Index | 5t-10t (ticks) | 1-second ticks |
| frxXAUUSD | Gold/USD | 1d-365d (HARI!) | Hanya untuk long-term |

**PENTING**: XAUUSD hanya mendukung durasi HARIAN (min 1 hari), TIDAK bisa ticks/menit!

**User bisa memilih symbol melalui:**
1. Menu inline buttons di Telegram (Auto Trade > Pilih Symbol)
2. Command: `/autotrade [stake] [durasi] [target] [symbol]`

## Struktur File

```
├── main.py           # Entry point & Telegram handlers
├── strategy.py       # Modul strategi RSI
├── deriv_ws.py       # WebSocket client untuk Deriv API
├── trading.py        # Trading manager & Martingale
├── symbols.py        # Konfigurasi trading pairs
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
| `/autotrade [stake] [durasi] [target] [symbol]` | Mulai auto trading |
| `/stop` | Hentikan trading |
| `/status` | Cek status bot |
| `/help` | Panduan penggunaan |

### Format Auto Trade

```
/autotrade [stake] [durasi] [target] [symbol]
```

Contoh:
- `/autotrade` - Default ($0.50, 5t, 5 trade, R_100)
- `/autotrade 0.5` - Stake $0.5 dengan R_100
- `/autotrade 1 5t 10` - $1, 5 ticks, 10 trade dengan R_100
- `/autotrade 0.50 5t 0 R_50` - Unlimited dengan R_50
- `/autotrade 1 1d 3 frxXAUUSD` - $1, 1 hari, 3 trade dengan Gold/USD

Format Durasi:
- `5t` = 5 ticks (DEFAULT - untuk Synthetic Index)
- `30s` = 30 detik
- `1m` = 1 menit
- `1d` = 1 hari (untuk XAUUSD)

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

5. **Multi-Pair Trading Support**: User bisa memilih trading pair
   - Tambah 9 symbol baru (R_75, R_50, R_25, R_10, 1HZ100V, 1HZ75V, 1HZ50V, frxXAUUSD)
   - Menu inline untuk pemilihan symbol di Telegram
   - Command /autotrade sekarang support parameter symbol
   - Validasi durasi otomatis berdasarkan symbol
   - Konfigurasi terpusat di symbols.py

6. **IDR Currency Conversion**: Tampilan saldo dalam Rupiah
   - Saldo ditampilkan dalam USD dan IDR
   - Profit/Loss juga dalam IDR
   - Kurs: 1 USD = Rp 15,800

7. **Bug Fix: Telegram Notifications** (Latest)
   - Fixed: "There is no current event loop in thread" error
   - Menggunakan synchronous HTTP requests untuk mengirim notifikasi
   - Notifikasi WIN/LOSS sekarang muncul instant tanpa error
   - Thread-safe untuk WebSocket callbacks

8. **Progress Notification**
   - User menerima update real-time saat bot menganalisis market
   - Format: "📊 Menganalisis market... (X/15 tick) | RSI: XX | Trend: XX"
   - Update dikirim setiap 5 tick selama fase pengumpulan data
   - Tidak spam - berhenti setelah RSI siap dikalkulasi

## Disclaimer

Trading memiliki risiko tinggi. Bot ini untuk tujuan edukasi. Gunakan akun demo untuk testing sebelum menggunakan uang asli.
