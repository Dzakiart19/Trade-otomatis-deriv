# Deriv Auto Trading Bot v2.0

Bot Telegram untuk auto trading Binary Options di platform Deriv.

## Overview

Bot ini menggunakan strategi multi-indicator (RSI, EMA, MACD, Stochastic) dengan sistem Adaptive Martingale untuk trading otomatis. Dibangun dengan Python dan menggunakan WebSocket untuk koneksi real-time ke Deriv API.

## Status: VERIFIED WORKING

Trading nyata berhasil terverifikasi pada 2025-12-05:
- Saldo berubah dari $10,000.00 ke $10,000.56 (+$0.56 USD)
- 3 trades dieksekusi (1 Win, 2 Loss)
- Martingale bekerja dengan baik

## Fitur Utama

### Multi-Indicator Strategy (v2.0)
- **RSI (14 period)**: Oversold < 30, Overbought > 70
- **EMA Crossover (9/21)**: Bullish/Bearish trend confirmation
- **MACD**: Momentum confirmation with histogram
- **Stochastic (14,3)**: Additional overbought/oversold filter
- **ATR (14 period)**: Volatility measurement for TP/SL

### Adaptive Martingale System (v2.0)
- **Dynamic Multiplier** based on rolling win rate:
  - Win Rate > 60%: Aggressive (2.5x)
  - Win Rate 40-60%: Normal (2.1x)
  - Win Rate < 40%: Conservative (1.8x)
- **Max 5 Martingale levels** to limit risk
- **Automatic recovery tracking** for optimization

### Session Analytics (v2.0)
- Rolling win rate (last 20 trades)
- Max drawdown tracking
- Martingale success rate
- Best performing RSI ranges
- Hourly P/L breakdown
- JSON export for external analysis

### Risk Management
- Max Session Loss: 20% dari balance awal
- Max Consecutive Losses: 5x loss berturut
- Daily Loss Limit: $50 USD per hari
- Balance Check sebelum setiap trade
- Exponential backoff for retry (5s, 10s, 20s, 40s, max 60s)

### Additional Features
- **Real-time Monitoring**: Notifikasi instant via Telegram
- **Progress Notifications**: Visual progress bar saat collecting data
- **Multi-Account**: Support akun Demo dan Real
- **Session Management**: Target jumlah trade dengan auto-stop
- **Trade Journal**: CSV logging untuk setiap trade
- **Error Logging**: Detailed error logs untuk debugging

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

## Struktur File

```
├── main.py           # Entry point & Telegram handlers
├── strategy.py       # Multi-indicator strategy (RSI, EMA, MACD, Stoch, ATR)
├── deriv_ws.py       # WebSocket client untuk Deriv API
├── trading.py        # Trading manager, Adaptive Martingale & Analytics
├── symbols.py        # Konfigurasi trading pairs
├── keep_alive.py     # Flask server untuk keep-alive
├── test_real_trade.py # Script test trading nyata
├── check_contracts.py # Check available contracts
└── logs/             # Trade journals, session summaries, analytics
    ├── trades_YYYYMMDD.csv
    ├── session_YYYYMMDD_HHMMSS.txt
    ├── analytics_YYYYMMDD_HHMMSS.json
    └── errors.log
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

## Signal Generation (v2.0)

### Buy (CALL) Signal Requirements:
- RSI < 30 (Oversold) - Score: +0.40
- EMA9 > EMA21 (Bullish) - Score: +0.25
- MACD Histogram > 0 - Score: +0.20
- Stochastic < 20 (Oversold) - Score: +0.15
- Trend UP - Score: +0.10

**Minimum confidence threshold: 0.50**

### Sell (PUT) Signal Requirements:
- RSI > 70 (Overbought) - Score: +0.40
- EMA9 < EMA21 (Bearish) - Score: +0.25
- MACD Histogram < 0 - Score: +0.20
- Stochastic > 80 (Overbought) - Score: +0.15
- Trend DOWN - Score: +0.10

## Trading Flow

1. Subscribe ke tick stream (R_100 Volatility Index)
2. Kumpulkan 21+ ticks untuk kalkulasi semua indikator
3. Calculate RSI, EMA, MACD, Stochastic, ATR
4. Analisis signal dengan multi-indicator scoring
5. Eksekusi trade jika confidence >= 0.50
6. Subscribe ke contract updates
7. Deteksi win/loss secara real-time
8. Apply Adaptive Martingale jika loss
9. Track analytics dan update rolling win rate
10. Repeat sampai target tercapai

## Risk Management Constants

| Konstanta | Nilai | Deskripsi |
|-----------|-------|-----------|
| MAX_LOSS_PERCENT | 0.20 | Stop jika loss 20% dari balance awal |
| MAX_CONSECUTIVE_LOSSES | 5 | Stop setelah 5x loss berturut |
| MAX_DAILY_LOSS | 50.0 | Max loss $50/hari |
| TRADE_COOLDOWN | 2.0 | Min 2 detik antar trade |
| SIGNAL_TIMEOUT | 120.0 | Timeout 120 detik untuk processing |
| MAX_BUY_RETRY | 5 | Max 5x retry untuk buy |
| RETRY_BASE_DELAY | 5.0 | Base delay exponential backoff |
| RETRY_MAX_DELAY | 60.0 | Max delay untuk retry |
| MAX_MARTINGALE_LEVEL | 5 | Max 5 level martingale |

## Adaptive Martingale Constants

| Konstanta | Nilai | Deskripsi |
|-----------|-------|-----------|
| MULTIPLIER_AGGRESSIVE | 2.5 | Untuk win rate > 60% |
| MULTIPLIER_NORMAL | 2.1 | Untuk win rate 40-60% |
| MULTIPLIER_CONSERVATIVE | 1.8 | Untuk win rate < 40% |
| WIN_RATE_AGGRESSIVE | 60.0 | Threshold untuk aggressive mode |
| WIN_RATE_CONSERVATIVE | 40.0 | Threshold untuk conservative mode |

## Recent Changes (2025-12-05)

### Version 2.0 - Major Update

1. **Multi-Indicator Strategy**
   - Added EMA (9/21) crossover for trend confirmation
   - Added MACD (12/26/9) for momentum
   - Added Stochastic (14,3) for overbought/oversold
   - Added ATR (14) for volatility measurement
   - Scoring system untuk signal confidence

2. **Adaptive Martingale**
   - Dynamic multiplier based on rolling win rate
   - Max 5 levels to limit exposure
   - Recovery tracking for optimization

3. **Session Analytics**
   - Rolling win rate tracking
   - Max drawdown monitoring
   - RSI performance by range
   - Hourly P/L breakdown
   - JSON export capability

4. **Improved Error Handling**
   - Exponential backoff for retries
   - Max 5 retries (up from 3)
   - Better error logging

5. **Enhanced Progress Notifications**
   - Visual progress bar
   - Immediate feedback on first tick
   - Better debugging logs

6. **Fixed Progress Notification Bug**
   - Added proper logging for debugging
   - Fixed callback execution

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

## Catatan Keamanan

- Token disimpan di Replit Secrets (terenkripsi)
- Tidak ada hardcoded credentials
- WebSocket menggunakan WSS (encrypted)

## Disclaimer

Trading memiliki risiko tinggi. Bot ini untuk tujuan edukasi. Gunakan akun demo untuk testing sebelum menggunakan uang asli.
