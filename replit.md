# Deriv Auto Trading Bot

## Overview
This project is an automated trading bot designed for the Deriv Binary Options platform. It utilizes a multi-indicator strategy (RSI, EMA, MACD, Stochastic) combined with an Adaptive Martingale system for automatic trading. Built with Python, it connects to the Deriv API via WebSockets for real-time data and trade execution. The bot aims to automate trading decisions, manage risk, and provide real-time monitoring and analytics, making it suitable for both short-term and long-term trading strategies on various volatility indices and forex pairs.

## User Preferences
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
- **Real-time Monitoring**: Instant notifications via Telegram.
- **Progress Notifications**: Visual progress bar during data collection.
- **Trade Journal**: CSV logging for every trade.
- **Error Logging**: Detailed error logs for debugging.
- **Telegram Commands**: Interactive command-based control for starting/stopping trades, managing accounts, and checking status.

### Technical Implementations
- **Multi-Indicator Strategy**:
    - **Indicators**: RSI (14), EMA Crossover (9/21), MACD, Stochastic (14,3), ATR (14).
    - **Signal Generation**: A scoring system evaluates confidence for Buy (CALL) or Sell (PUT) signals based on indicator alignments. Minimum confidence threshold of 0.50.
    - **Advanced Filters (v2.4)**: Multi-Timeframe Trend Confirmation (M5 EMA/RSI), EMA Slope Filter, Enhanced ADX Directional Check, Volume Filter, Price Action Confirmation (wick validation), and a Signal Cooldown System.
    - **Confluence Scoring**: Combines all filter scores (max 100 points) to determine signal strength (STRONG ≥ 70, MEDIUM ≥ 50, WEAK < 50), blocking signals below a minimum confluence score of 50.
- **Adaptive Martingale System**:
    - **Dynamic Multiplier**: Adjusts based on rolling win rate (Aggressive 2.5x for >60% WR, Normal 2.1x for 40-60% WR, Conservative 1.8x for <40% WR).
    - **Levels**: Max 5 Martingale levels to limit risk.
- **Risk Management**:
    - Max Session Loss (20% of initial balance).
    - Max Consecutive Losses (5x).
    - Daily Loss Limit ($50 USD).
    - Balance Check before each trade.
    - Exponential backoff for retries.
    - Auto-Adjust Stake: Dynamically calculates and caps stake to a safe value based on projected Martingale exposure, preventing stops until balance falls below minimum stake.
- **Session Analytics**: Tracks rolling win rate (last 20 trades), max drawdown, Martingale success rate, best performing RSI ranges, hourly P/L breakdown, and JSON export for analysis.
- **Instant Data Preload (v2.5)**:
    - **Historical Data Preload**: Saat bot diaktifkan, semua candle/tick data langsung dimuat dari Deriv API menggunakan `get_ticks_history()`.
    - **No Wait Time**: Bot tidak perlu menunggu data terkumpul - langsung siap trading setelah preload selesai.
    - **Fallback Mechanism**: Jika preload gagal, bot tetap berjalan dan mengumpulkan data dari live stream sebagai fallback.
- **Error Handling & Stability**:
    - Improved WebSocket reconnection with network checks and subscription clearing.
    - Health checks with jitter and increased timeouts.
    - Error recovery for buy failures, including timeout detection and circuit breaker.
    - Graceful shutdown handler.
    - Trade Journal CSV validation with atomic writes and backups.
    - Progress callback error handling.
- **Multi-Account Support**: Supports both Demo and Real Deriv accounts.
- **Chat ID Persistence**: Stores and validates Telegram Chat ID for secure messaging, requiring user confirmation.
- **Per-User Token Authentication (v2.6)**:
    - Users login with their own Deriv API token via Telegram (/login or /start)
    - Tokens are encrypted using Fernet (AES-128) before storage
    - WebSocket connects using user's token automatically after login
    - Auto-reconnect on bot restart if saved session is valid
    - Invalid sessions are auto-cleared when decryption fails (e.g., SESSION_SECRET rotation)
- **Real-Time Trading Notifications (v2.7)**:
    - **Callback Registration Fix**: Trading callbacks are now set up immediately after TradingManager creation in connect_user_deriv()
    - **Faster Updates**: Reduced notification debounce from 10s to 2s for progress, 30s to 3s for trade milestones
    - **More Milestones**: Progress notifications at 0%, 25%, 50%, 75%, 100% for better visibility
    - **Callback Logging**: on_trade_opened and on_trade_closed now log invocation for debugging
- **Martingale Recovery Priority (v2.9)**:
    - **Risk Check Override**: Saat dalam martingale sequence, stake TIDAK diturunkan oleh volatility adjustment
    - **Higher Cap for Martingale**: Batas stake dinaikkan dari 25% ke 50% balance saat dalam martingale recovery
    - **Stake Preservation**: Stake martingale dipertahankan di configure(), start(), dan risk check
    - **Telegram Message Fallback**: Helper function untuk handle Markdown parsing error dengan fallback ke HTML/plain text
    - **Session Recovery Validation**: Validasi umur file (30 menit max), data integrity check, dan martingale level validation

### Feature Specifications
- **Supported Symbols**: Volatility indices (R_100, R_75, R_50, R_25, R_10, 1HZ100V, 1HZ75V, 1HZ50V) for 5-10 ticks duration, and frxXAUUSD (Gold/USD) for daily duration.
- **Telegram Integration**: Provides interactive commands like `/start`, `/akun`, `/autotrade`, `/stop`, `/status`, and `/help`.
- **Session Management**: Configurable target number of trades with auto-stop functionality.

### System Design Choices
- **File Structure**: Modular Python files for entry point (`main.py`), strategy (`strategy.py`), WebSocket communication (`deriv_ws.py`), trading logic (`trading.py`), symbol configuration (`symbols.py`), pair scanner (`pair_scanner.py`), dan user authentication (`user_auth.py`).
- **Logging**: Dedicated `logs/` directory for trade journals, session summaries, analytics, and error logs.
- **Security**: Deriv API tokens and Telegram bot tokens are stored as encrypted environment variables (Replit Secrets). WebSocket communication uses WSS for encryption.
- **Startup (v2.8)**: Bot starts dengan async pattern dan delete_webhook untuk menghindari Telegram polling conflict. Tidak memerlukan Flask keep-alive server.

## External Dependencies
- `python-telegram-bot`: For Telegram API interaction and bot functionality.
- `websocket-client`: For real-time WebSocket communication with the Deriv API.
- `python-dotenv`: For managing environment variables, although Replit Secrets are primarily used.
- `cryptography`: For encrypting user tokens securely (Fernet/AES-128).