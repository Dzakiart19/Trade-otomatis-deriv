"""
=============================================================
TRADING MANAGER - Eksekusi & Money Management v2.2
=============================================================
Modul ini menangani eksekusi trading, Martingale system,
dan tracking hasil trading.

Fitur:
- Auto trading dengan target jumlah trade
- Fixed 2.1x Recovery Martingale (simplified)
- Real-time win/loss detection
- Session statistics & analytics
- ATR-based TP/SL monitoring
- Enhanced error handling with exponential backoff

Enhancement v2.0:
- SessionAnalytics class for performance tracking
- Improved risk management

Enhancement v2.1:
- Buy timeout detection (30 second timeout)
- Circuit breaker for consecutive buy failures
- Enhanced risk management with pre-flight validation
- Session recovery mechanism (auto-save/restore)
- Trade journal CSV validation with atomic writes

Enhancement v2.2:
- Simplified Recovery Martingale with fixed 2.1x multiplier
- Clear recovery logging with cumulative loss tracking
- Max 5 levels then STOP trading (no reset)
=============================================================
"""

import asyncio
import logging
import json
import shutil
import tempfile
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import deque

from strategy import TradingStrategy, Signal, AnalysisResult
from deriv_ws import DerivWebSocket, AccountType
from symbols import (
    SUPPORTED_SYMBOLS, 
    DEFAULT_SYMBOL, 
    MIN_STAKE_GLOBAL,
    get_symbol_config,
    validate_duration_for_symbol,
    get_symbol_list_text
)
import csv
import os

from event_bus import get_event_bus, PositionOpenEvent, PositionCloseEvent, TradeHistoryEvent, StatusEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)


class TradingState(Enum):
    """Status trading session"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_RESULT = "waiting_result"
    STOPPED = "stopped"


@dataclass
class TradeResult:
    """Hasil satu trade"""
    trade_number: int
    contract_type: str  # CALL/PUT
    entry_price: float
    exit_price: float
    stake: float
    payout: float
    profit: float
    is_win: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SessionStats:
    """Statistik trading session"""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: float = 0.0
    starting_balance: float = 0.0
    current_balance: float = 0.0
    highest_balance: float = 0.0
    lowest_balance: float = 0.0
    
    @property
    def win_rate(self) -> float:
        """Hitung win rate dalam persentase"""
        if self.total_trades == 0:
            return 0.0
        return (self.wins / self.total_trades) * 100
        
    @property
    def net_profit(self) -> float:
        """Hitung net profit dari awal session"""
        return self.current_balance - self.starting_balance


class SessionAnalytics:
    """
    Performance analytics untuk tracking dan optimization.
    Tracks rolling win rate, hourly performance, dan martingale effectiveness.
    """
    
    ROLLING_WINDOW = 20
    
    def __init__(self):
        self.trade_results: deque = deque(maxlen=100)
        self.hourly_profits: Dict[str, float] = {}
        self.martingale_recoveries: int = 0
        self.martingale_failures: int = 0
        self.rsi_thresholds_performance: Dict[str, Dict] = {}
        self.max_drawdown: float = 0.0
        self.peak_balance: float = 0.0
        
    def add_trade(self, is_win: bool, profit: float, stake: float, 
                  rsi_value: float, current_balance: float):
        """Record trade result for analytics"""
        hour = datetime.now().strftime("%Y-%m-%d %H:00")
        
        self.trade_results.append({
            "timestamp": datetime.now(),
            "is_win": is_win,
            "profit": profit,
            "stake": stake,
            "rsi": rsi_value
        })
        
        if hour not in self.hourly_profits:
            self.hourly_profits[hour] = 0.0
        self.hourly_profits[hour] += profit
        
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        current_drawdown = self.peak_balance - current_balance
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
            
        rsi_bucket = f"{int(rsi_value // 10) * 10}-{int(rsi_value // 10) * 10 + 10}"
        if rsi_bucket not in self.rsi_thresholds_performance:
            self.rsi_thresholds_performance[rsi_bucket] = {"wins": 0, "losses": 0, "profit": 0.0}
        
        if is_win:
            self.rsi_thresholds_performance[rsi_bucket]["wins"] += 1
        else:
            self.rsi_thresholds_performance[rsi_bucket]["losses"] += 1
        self.rsi_thresholds_performance[rsi_bucket]["profit"] += profit
        
    def record_martingale_result(self, recovered: bool):
        """Track martingale recovery success"""
        if recovered:
            self.martingale_recoveries += 1
        else:
            self.martingale_failures += 1
            
    def get_rolling_win_rate(self) -> float:
        """Calculate rolling win rate over last N trades"""
        if not self.trade_results:
            return 50.0
            
        recent = list(self.trade_results)[-self.ROLLING_WINDOW:]
        if not recent:
            return 50.0
            
        wins = sum(1 for t in recent if t["is_win"])
        return (wins / len(recent)) * 100
        
    def get_martingale_success_rate(self) -> float:
        """Calculate martingale recovery success rate"""
        total = self.martingale_recoveries + self.martingale_failures
        if total == 0:
            return 0.0
        return (self.martingale_recoveries / total) * 100
        
    def get_best_rsi_range(self) -> str:
        """Find RSI range with best performance"""
        if not self.rsi_thresholds_performance:
            return "N/A"
            
        best_range = max(
            self.rsi_thresholds_performance.items(),
            key=lambda x: x[1]["profit"],
            default=(None, None)
        )
        return best_range[0] if best_range[0] else "N/A"
        
    def get_summary(self) -> str:
        """Generate analytics summary"""
        rolling_wr = self.get_rolling_win_rate()
        martingale_sr = self.get_martingale_success_rate()
        best_rsi = self.get_best_rsi_range()
        
        return (
            f"📈 **SESSION ANALYTICS**\n\n"
            f"• Rolling WR (last {self.ROLLING_WINDOW}): {rolling_wr:.1f}%\n"
            f"• Max Drawdown: ${self.max_drawdown:.2f}\n"
            f"• Martingale Success: {martingale_sr:.1f}%\n"
            f"• Best RSI Range: {best_rsi}\n"
            f"• Total Trades Analyzed: {len(self.trade_results)}"
        )
        
    def export_to_json(self, filepath: str):
        """Export analytics to JSON file"""
        data = {
            "export_time": datetime.now().isoformat(),
            "rolling_win_rate": self.get_rolling_win_rate(),
            "max_drawdown": self.max_drawdown,
            "peak_balance": self.peak_balance,
            "martingale_recoveries": self.martingale_recoveries,
            "martingale_failures": self.martingale_failures,
            "hourly_profits": self.hourly_profits,
            "rsi_performance": self.rsi_thresholds_performance,
            "trade_count": len(self.trade_results)
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"📊 Analytics exported to {filepath}")


class TradingManager:
    """
    Kelas utama untuk mengelola trading session.
    Menggabungkan strategi, eksekusi, dan money management.
    Mendukung multiple trading pairs dengan validasi otomatis.
    
    Features v2.2:
    - Fixed 2.1x Recovery Martingale (simplified)
    - Multi-indicator confirmation signals
    - ATR-based TP/SL monitoring
    - Real-time session analytics
    """
    
    MARTINGALE_MULTIPLIER = 2.1
    MAX_MARTINGALE_LEVEL = 3
    
    MAX_LOSS_PERCENT = 0.20
    MAX_CONSECUTIVE_LOSSES = 5
    TRADE_COOLDOWN_SECONDS = 2.0
    MAX_BUY_RETRY = 5
    MAX_DAILY_LOSS = 50.0
    SIGNAL_PROCESSING_TIMEOUT = 120.0
    
    RETRY_BASE_DELAY = 5.0
    RETRY_MAX_DELAY = 60.0
    
    # Buy timeout and circuit breaker settings (Task 1)
    BUY_RESPONSE_TIMEOUT = 30.0  # timeout dalam detik untuk buy response
    CIRCUIT_BREAKER_FAILURES = 3  # jumlah consecutive failures untuk trigger circuit breaker
    CIRCUIT_BREAKER_WINDOW = 60.0  # window dalam detik untuk menghitung consecutive failures
    CIRCUIT_BREAKER_COOLDOWN = 120.0  # cooldown dalam detik setelah circuit breaker triggered
    
    # Enhanced risk management settings (Task 4)
    MAX_TOTAL_RISK_PERCENT = 0.20  # auto-stop jika total risk > 20% balance (lebih konservatif)
    RISK_WARNING_PERCENT = 0.15  # warning lebih awal sebelum mencapai risk limit
    MARTINGALE_LOOK_AHEAD_LEVELS = 5  # check sampai martingale level 5 untuk projected losses
    
    # Session recovery settings (Task 5)
    SESSION_RECOVERY_ENABLED = True
    SESSION_SAVE_INTERVAL = 5  # save session setiap 5 trades
    SESSION_RECOVERY_MAX_AGE = 1800  # restore jika bot restart dalam 30 menit (1800 detik)
    SESSION_RECOVERY_FILE = "logs/session_recovery.json"
    
    def __init__(self, deriv_ws: DerivWebSocket):
        """
        Inisialisasi Trading Manager.
        
        Args:
            deriv_ws: Instance DerivWebSocket yang sudah terkoneksi
        """
        self.ws = deriv_ws
        self.strategy = TradingStrategy()
        
        # Trading parameters
        self.base_stake = MIN_STAKE_GLOBAL
        self.current_stake = MIN_STAKE_GLOBAL
        self.duration = 5
        self.duration_unit = "t"  # ticks (5 tick untuk Volatility Index)
        self.target_trades = 0  # 0 = unlimited
        self.symbol = DEFAULT_SYMBOL  # Default symbol dari konfigurasi
        
        # State management
        self.state = TradingState.IDLE
        self.current_contract_id: Optional[str] = None
        self.current_trade_type: Optional[str] = None
        self.entry_price: float = 0.0
        
        # ANTI-DOUBLE BUY: Flag untuk mencegah eksekusi concurrent
        self.is_processing_signal: bool = False
        self.last_trade_time: float = 0.0
        self.buy_retry_count: int = 0
        self.signal_processing_start_time: float = 0.0  # Untuk timeout detection
        
        # Buy timeout tracking (Task 1)
        self.buy_request_time: float = 0.0  # timestamp saat buy request dikirim
        self._buy_timeout_task: Optional[asyncio.Task] = None
        
        # Circuit breaker tracking (Task 1)
        self.buy_failure_times: List[float] = []  # timestamps of recent buy failures
        self.circuit_breaker_active: bool = False
        self.circuit_breaker_end_time: float = 0.0
        
        # Risk Management
        self.consecutive_losses: int = 0
        self.session_start_date: str = ""
        self.daily_loss: float = 0.0
        
        # Session recovery tracking (Task 5)
        self.session_recovery_enabled: bool = self.SESSION_RECOVERY_ENABLED
        
        # Progress notification tracking (Task 7) - Optimized untuk mengurangi spam
        self.last_progress_notification_time: float = 0.0
        self.last_notified_milestone: int = -1  # Track last milestone to avoid duplicate
        self.sent_milestones: set = set()  # Track ALL milestones sent in this session
        self.PROGRESS_MILESTONES = [0, 25, 50, 75, 100]  # More milestones for real-time feel
        self.MIN_PROGRESS_NOTIFICATION_INTERVAL = 3.0  # 3 seconds debounce for faster updates
        
        # Statistics
        self.stats = SessionStats()
        self.trade_history: list[TradeResult] = []
        self.analytics = SessionAnalytics()
        
        # Recovery Martingale tracking (simplified 2.1x multiplier)
        self.martingale_level: int = 0
        self.in_martingale_sequence: bool = False
        self.cumulative_loss: float = 0.0  # Track total losses in current sequence for recovery logging
        
        # Callbacks untuk notifikasi Telegram
        self.on_trade_opened: Optional[Callable] = None
        self.on_trade_closed: Optional[Callable] = None
        self.on_session_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
        
        # Progress tracking
        self.tick_count: int = 0
        self.progress_interval: int = 5
        self.required_ticks: int = 21
        
        # Setup WebSocket callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Setup callback functions untuk WebSocket"""
        self.ws.on_tick_callback = self._on_tick
        self.ws.on_buy_response_callback = self._on_buy_response
        self.ws.on_contract_update_callback = self._on_contract_update
        self.ws.on_balance_update_callback = self._on_balance_update
    
    def _preload_historical_data(self) -> bool:
        """
        Pre-load historical tick data untuk symbol yang dipilih.
        
        Mengambil historical ticks dari Deriv API dan memasukkannya
        ke strategy sehingga analisis bisa langsung dimulai tanpa
        menunggu tick terkumpul.
        
        Returns:
            True jika preload berhasil, False jika gagal
        """
        import time as time_module
        
        required_ticks = self.required_ticks + 30  # Extra buffer untuk indicator calculation
        
        logger.info(f"📥 Pre-loading {required_ticks} historical ticks for {self.symbol}...")
        
        try:
            prices = self.ws.get_ticks_history(
                symbol=self.symbol,
                count=required_ticks,
                timeout=15.0
            )
            
            if prices and len(prices) >= self.required_ticks:
                for price in prices:
                    self.strategy.add_tick(float(price))
                
                logger.info(f"✅ Pre-loaded {len(prices)} ticks for {self.symbol} - siap trading!")
                return True
            else:
                ticks_received = len(prices) if prices else 0
                logger.warning(f"⚠️ Insufficient history for {self.symbol}: {ticks_received}/{required_ticks} ticks")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error pre-loading {self.symbol}: {e}")
            return False
        
    def _get_martingale_multiplier(self) -> float:
        """
        Get fixed martingale multiplier for Recovery Martingale system.
        
        Returns:
            Fixed multiplier value of 2.1x
        """
        return self.MARTINGALE_MULTIPLIER
        
    def _on_tick(self, price: float, symbol: str):
        """
        Handler untuk setiap tick yang masuk.
        Menambahkan ke strategy dan mengecek signal.
        """
        import time as time_module
        
        # Tambahkan tick ke strategy
        self.strategy.add_tick(price)
        
        # Check buy timeout dulu sebelum check state
        if self.buy_request_time > 0:
            if self._check_buy_timeout():
                logger.info("🔄 Buy timeout handled, continuing to next tick")
                return
        
        # Jika sedang dalam posisi, tidak perlu analisis
        if self.state == TradingState.WAITING_RESULT:
            return
            
        # ANTI-DOUBLE BUY: Jika sedang processing signal, check timeout
        current_time = time_module.time()
        if self.is_processing_signal:
            if self.signal_processing_start_time > 0:
                elapsed = current_time - self.signal_processing_start_time
                if elapsed > self.SIGNAL_PROCESSING_TIMEOUT:
                    logger.warning(f"⚠️ Signal processing timeout after {elapsed:.1f}s. Resetting flags.")
                    self._log_error(f"Signal processing timeout after {elapsed:.1f}s")
                    self._reset_processing_state()
                else:
                    logger.debug(f"Skipping tick - signal processing ({elapsed:.1f}s/{self.SIGNAL_PROCESSING_TIMEOUT}s)")
                    return
            else:
                logger.debug("Skipping tick - signal still being processed")
                return
            
        # COOLDOWN CHECK: Cek apakah sudah melewati cooldown time
        if self.last_trade_time > 0:
            time_since_last_trade = current_time - self.last_trade_time
            if time_since_last_trade < self.TRADE_COOLDOWN_SECONDS:
                logger.debug(f"Cooldown active: {self.TRADE_COOLDOWN_SECONDS - time_since_last_trade:.1f}s remaining")
                return
            
        # Jika auto trading aktif, analisis signal
        if self.state == TradingState.RUNNING:
            self.tick_count += 1
            
            stats = self.strategy.get_stats()
            current_tick_count = stats['tick_count']
            
            # Task 7: Progress notification optimization - milestone-based with time debouncing
            # Only notify at milestones (0%, 50%, 100%) with 30s debounce between notifications
            if current_tick_count <= self.required_ticks:
                progress_pct = int((current_tick_count / self.required_ticks) * 100)
                
                # Find the current milestone (0, 50, 100)
                current_milestone = 0
                for milestone in self.PROGRESS_MILESTONES:
                    if progress_pct >= milestone:
                        current_milestone = milestone
                
                # Get indicator values for milestone notification
                rsi_value = stats['rsi'] if current_tick_count >= 15 else 0
                trend = stats['trend']
                
                # Check if we should send notification:
                # 1. Must be a new milestone (not sent before in this session)
                # 2. Must pass time debounce interval (30 seconds)
                # 3. First notification always allowed
                time_since_last_notification = current_time - self.last_progress_notification_time
                is_new_milestone = current_milestone > self.last_notified_milestone
                is_milestone_not_sent = current_milestone not in self.sent_milestones
                is_past_min_interval = time_since_last_notification >= self.MIN_PROGRESS_NOTIFICATION_INTERVAL
                is_first_notification = self.last_progress_notification_time == 0.0
                
                should_notify = (
                    is_new_milestone and 
                    is_milestone_not_sent and
                    (is_first_notification or is_past_min_interval)
                )
                
                if should_notify:
                    # Only log when milestone is reached
                    logger.info(f"📊 Milestone {current_milestone}% reached: {current_tick_count}/{self.required_ticks} ticks | RSI: {rsi_value} | Trend: {trend}")
                    
                    if self.on_progress:
                        try:
                            self.on_progress(current_tick_count, self.required_ticks, rsi_value, trend)
                            self.last_progress_notification_time = current_time
                            self.last_notified_milestone = current_milestone
                            self.sent_milestones.add(current_milestone)  # Track sent milestone
                            logger.debug(f"✅ Progress notification sent for milestone {current_milestone}%")
                        except Exception as e:
                            logger.error(f"❌ Error calling on_progress callback: {type(e).__name__}: {e}")
            
            self._check_and_execute_signal()
            
    def _check_circuit_breaker(self) -> bool:
        """
        Check apakah circuit breaker aktif.
        Returns True jika trading harus dihentikan, False jika boleh lanjut.
        
        Task 1: Circuit breaker jika 3 consecutive buy failures dalam 1 menit.
        Fixed: Prune old entries sebelum check untuk rolling window yang benar.
        """
        import time as time_module
        current_time = time_module.time()
        
        # Prune old failure entries terlebih dahulu (rolling 60s window)
        if self.buy_failure_times:
            window_start = current_time - self.CIRCUIT_BREAKER_WINDOW
            self.buy_failure_times = [t for t in self.buy_failure_times if t >= window_start]
        
        # Cek apakah masih dalam cooldown period
        if self.circuit_breaker_active:
            if current_time < self.circuit_breaker_end_time:
                remaining = self.circuit_breaker_end_time - current_time
                logger.warning(f"⚡ Circuit breaker active - {remaining:.1f}s remaining")
                return True
            else:
                # Cooldown selesai, reset circuit breaker
                logger.info("✅ Circuit breaker cooldown completed, resuming trading")
                self.circuit_breaker_active = False
                self.buy_failure_times.clear()
                
        return False
    
    def _record_buy_failure(self):
        """
        Record buy failure untuk circuit breaker tracking.
        Trigger circuit breaker jika 3 failures dalam 1 menit.
        """
        import time as time_module
        current_time = time_module.time()
        
        # Tambahkan failure time
        self.buy_failure_times.append(current_time)
        
        # Remove old failures di luar window
        window_start = current_time - self.CIRCUIT_BREAKER_WINDOW
        self.buy_failure_times = [t for t in self.buy_failure_times if t >= window_start]
        
        logger.debug(f"Buy failures in window: {len(self.buy_failure_times)}/{self.CIRCUIT_BREAKER_FAILURES}")
        
        # Cek apakah perlu trigger circuit breaker
        if len(self.buy_failure_times) >= self.CIRCUIT_BREAKER_FAILURES:
            logger.error(
                f"⚡ CIRCUIT BREAKER TRIGGERED: {len(self.buy_failure_times)} failures "
                f"dalam {self.CIRCUIT_BREAKER_WINDOW}s window"
            )
            self.circuit_breaker_active = True
            self.circuit_breaker_end_time = current_time + self.CIRCUIT_BREAKER_COOLDOWN
            
            if self.on_error:
                self.on_error(
                    f"Circuit breaker aktif! {len(self.buy_failure_times)}x buy gagal dalam 1 menit. "
                    f"Trading pause {int(self.CIRCUIT_BREAKER_COOLDOWN)}s."
                )
            
            self._log_error(
                f"Circuit breaker triggered: {len(self.buy_failure_times)} failures, "
                f"cooldown until {datetime.fromtimestamp(self.circuit_breaker_end_time).strftime('%H:%M:%S')}"
            )
            return True
        
        return False
    
    def _check_buy_timeout(self):
        """
        Check apakah buy request sudah timeout (30 detik).
        Task 1: Auto-reset state ke RUNNING jika timeout tercapai.
        """
        import time as time_module
        
        if self.buy_request_time <= 0:
            return False
            
        current_time = time_module.time()
        elapsed = current_time - self.buy_request_time
        
        if elapsed >= self.BUY_RESPONSE_TIMEOUT:
            logger.error(f"⏰ BUY TIMEOUT: No response after {elapsed:.1f}s (max: {self.BUY_RESPONSE_TIMEOUT}s)")
            
            self._log_error(f"Buy timeout after {elapsed:.1f}s")
            
            # Record sebagai failure untuk circuit breaker
            self._record_buy_failure()
            
            # Reset state ke RUNNING
            self.buy_request_time = 0.0
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            self.state = TradingState.RUNNING
            
            if self.on_error:
                self.on_error(f"Buy timeout setelah {int(elapsed)}s. Auto-reset state.")
            
            logger.info("🔄 State auto-reset ke RUNNING setelah buy timeout")
            return True
            
        return False
    
    def _on_buy_response(self, data: dict):
        """
        Handler untuk response buy contract.
        
        Enhancement v2.1 (Task 1):
        - Log detail error code dan message
        - Circuit breaker tracking
        - Buy timeout reset
        """
        import time as time_module
        
        # Reset buy request time karena sudah dapat response
        self.buy_request_time = 0.0
        
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            error_code = data["error"].get("code", "")
            error_details = json.dumps(data["error"], indent=2)
            
            logger.error(f"❌ Buy failed [{error_code}]: {error_msg}")
            logger.debug(f"Full error details: {error_details}")
            
            # Log error ke file dengan detail lengkap
            self._log_error(f"Buy Error [{error_code}]: {error_msg}\nDetails: {error_details}")
            
            # Reset processing flags
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            
            # Record failure untuk circuit breaker
            circuit_breaker_triggered = self._record_buy_failure()
            
            # Jika circuit breaker triggered, stop sementara
            if circuit_breaker_triggered:
                self.state = TradingState.RUNNING  # Akan di-block oleh circuit breaker check
                return
            
            # Increment retry counter
            self.buy_retry_count += 1
            
            if self.buy_retry_count >= self.MAX_BUY_RETRY:
                # Max retry tercapai, stop trading
                if self.on_error:
                    self.on_error(f"Trading dihentikan setelah {self.MAX_BUY_RETRY}x gagal. Error: {error_msg}")
                self.state = TradingState.STOPPED
                self.buy_retry_count = 0
                logger.error(f"❌ Max buy retry reached ({self.MAX_BUY_RETRY}x). Trading stopped.")
                return
            
            if self.on_error:
                self.on_error(f"Gagal open posisi (retry {self.buy_retry_count}/{self.MAX_BUY_RETRY}): {error_msg}")
            
            # Exponential backoff delay with jitter
            import random
            base_delay = self.RETRY_BASE_DELAY * (2 ** (self.buy_retry_count - 1))
            delay = min(base_delay, self.RETRY_MAX_DELAY)
            jitter = random.uniform(0, delay * 0.3)
            final_delay = delay + jitter
            
            logger.info(f"⏳ Exponential backoff: waiting {final_delay:.1f}s before retry (base: {base_delay:.1f}s)...")
            time_module.sleep(final_delay)
            
            # Reset state untuk coba lagi
            self.state = TradingState.RUNNING
            return
        
        # SUCCESS: Reset counters
        self.buy_retry_count = 0
        self.buy_failure_times.clear()  # Reset failure tracking on success
        
        buy_info = data.get("buy", {})
        self.current_contract_id = str(buy_info.get("contract_id", ""))
        self.entry_price = float(buy_info.get("buy_price", 0))
        
        # Update last trade time untuk cooldown
        self.last_trade_time = time_module.time()
        
        # Subscribe ke contract updates
        if self.current_contract_id:
            self.ws.subscribe_contract(self.current_contract_id)
            
        logger.info(f"✅ Position opened: Contract ID {self.current_contract_id}")
        
        # Notify via callback
        if self.on_trade_opened:
            self.on_trade_opened(
                self.current_trade_type or "UNKNOWN",
                self.strategy.get_current_price() or 0,
                self.current_stake,
                self.stats.total_trades + 1,
                self.target_trades
            )
        
        # Publish PositionOpenEvent to event bus
        try:
            bus = get_event_bus()
            bus.publish("position", PositionOpenEvent(
                contract_id=self.current_contract_id or "",
                symbol=self.symbol,
                entry_price=self.entry_price,
                stake=self.current_stake,
                direction=self.current_trade_type or "UNKNOWN",
                martingale_level=self.martingale_level
            ))
        except Exception as e:
            logger.debug(f"Error publishing position open event: {e}")
            
    def _on_contract_update(self, data: dict):
        """
        Handler untuk update status kontrak.
        Deteksi win/loss secara real-time.
        """
        if "error" in data:
            return
            
        poc_data = data.get("proposal_open_contract", {})
        
        # Cek apakah kontrak sudah selesai
        is_sold = poc_data.get("is_sold", 0) == 1
        status = poc_data.get("status", "")
        
        if is_sold or status == "sold":
            self._process_trade_result(poc_data)
            
    def _on_balance_update(self, new_balance: float):
        """Handler untuk update balance"""
        self.stats.current_balance = new_balance
        
        # Update highest/lowest
        if new_balance > self.stats.highest_balance:
            self.stats.highest_balance = new_balance
        if new_balance < self.stats.lowest_balance or self.stats.lowest_balance == 0:
            self.stats.lowest_balance = new_balance
            
    def _process_trade_result(self, contract_data: dict):
        """
        Proses hasil trade (win/loss) dan update statistics.
        
        Args:
            contract_data: Data kontrak dari proposal_open_contract
        """
        profit = float(contract_data.get("profit", 0))
        sell_price = float(contract_data.get("sell_price", 0))
        exit_spot = float(contract_data.get("exit_tick", 0))
        
        is_win = profit > 0
        
        # Update stats
        self.stats.total_trades += 1
        if is_win:
            self.stats.wins += 1
            self.consecutive_losses = 0  # Reset consecutive losses on win
        else:
            self.stats.losses += 1
            self.consecutive_losses += 1  # Increment consecutive losses
            self.daily_loss += abs(profit)  # Track daily loss
        self.stats.total_profit += profit
        
        # Simpan hasil trade
        result = TradeResult(
            trade_number=self.stats.total_trades,
            contract_type=self.current_trade_type or "UNKNOWN",
            entry_price=self.entry_price,
            exit_price=exit_spot,
            stake=self.current_stake,
            payout=sell_price,
            profit=profit,
            is_win=is_win
        )
        self.trade_history.append(result)
        
        # Track analytics
        rsi_value = self.strategy.last_indicators.rsi if hasattr(self.strategy, 'last_indicators') else 50.0
        self.analytics.add_trade(
            is_win=is_win,
            profit=profit,
            stake=self.current_stake,
            rsi_value=rsi_value,
            current_balance=self.stats.current_balance
        )
        
        # Log trade ke CSV journal
        self._log_trade_to_journal(result)
        
        # RISK CHECK: Cek consecutive losses
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            logger.warning(f"⚠️ Max consecutive losses reached: {self.consecutive_losses}")
            if self.on_error:
                self.on_error(f"Trading dihentikan! {self.consecutive_losses}x loss berturut-turut.")
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            self._complete_session()
            return
        
        # Recovery Martingale logic (simplified 2.1x multiplier)
        if is_win:
            next_stake = self.base_stake
            
            if self.in_martingale_sequence:
                self.analytics.record_martingale_result(recovered=True)
                recovered_amount = self.cumulative_loss
                logger.info(f"🎉 RECOVERY SUCCESSFUL! Recovered ${recovered_amount:.2f} losses after {self.martingale_level} levels")
                if self.on_error:
                    self.on_error(f"🎉 Recovery successful! Recovered ${recovered_amount:.2f} losses after {self.martingale_level} levels")
            
            self.current_stake = self.base_stake
            self.martingale_level = 0
            self.in_martingale_sequence = False
            self.cumulative_loss = 0.0  # Reset cumulative loss on win
        else:
            self.in_martingale_sequence = True
            self.martingale_level += 1
            self.cumulative_loss += abs(profit)  # Track cumulative loss for recovery logging
            
            if self.martingale_level >= self.MAX_MARTINGALE_LEVEL:
                logger.error(f"❌ MAX MARTINGALE LEVEL ({self.MAX_MARTINGALE_LEVEL}) REACHED - STOPPING TRADING")
                logger.error(f"   Total loss in sequence: ${self.cumulative_loss:.2f}")
                self.analytics.record_martingale_result(recovered=False)
                if self.on_error:
                    self.on_error(
                        f"❌ MAX MARTINGALE LEVEL {self.MAX_MARTINGALE_LEVEL} REACHED!\n"
                        f"Total loss: ${self.cumulative_loss:.2f}\n"
                        f"Trading STOPPED untuk mencegah kerugian lebih besar."
                    )
                self.is_processing_signal = False
                self.signal_processing_start_time = 0.0
                self._complete_session()
                return
            else:
                # BALANCE GUARD: Get current balance BEFORE calculating next stake
                current_balance = self.ws.get_balance()
                multiplier = self._get_martingale_multiplier()
                next_stake = round(self.current_stake * multiplier, 2)
                
                # Pre-check: Ensure next stake doesn't exceed balance
                if next_stake > current_balance:
                    logger.warning(f"⚠️ Martingale stake ${next_stake:.2f} melebihi balance ${current_balance:.2f}")
                    if self.on_error:
                        self.on_error(f"Trading dihentikan! Balance tidak cukup untuk Martingale (${next_stake:.2f} > ${current_balance:.2f})")
                    self.analytics.record_martingale_result(recovered=False)
                    self.is_processing_signal = False
                    self.signal_processing_start_time = 0.0
                    self._complete_session()
                    return
                
                self.current_stake = next_stake
                logger.info(
                    f"📊 MARTINGALE Level {self.martingale_level}/{self.MAX_MARTINGALE_LEVEL}: "
                    f"stake ${next_stake:.2f} (x{multiplier}) | "
                    f"Cumulative Loss: ${self.cumulative_loss:.2f}"
                )
            
        # Notify via callback
        if self.on_trade_closed:
            self.on_trade_closed(
                is_win,
                profit,
                self.stats.current_balance,
                self.stats.total_trades,
                self.target_trades,
                next_stake
            )
        
        # Publish PositionCloseEvent and TradeHistoryEvent to event bus
        try:
            bus = get_event_bus()
            bus.publish("position", PositionCloseEvent(
                contract_id=self.current_contract_id or "",
                symbol=self.symbol,
                exit_price=exit_spot,
                profit=profit,
                is_win=is_win
            ))
            bus.publish("trade", TradeHistoryEvent(
                trade_id=self.current_contract_id or str(self.stats.total_trades),
                symbol=self.symbol,
                direction=self.current_trade_type or "UNKNOWN",
                stake=self.current_stake,
                result="win" if is_win else "loss",
                profit=profit
            ))
        except Exception as e:
            logger.debug(f"Error publishing trade events: {e}")
            
        # Reset processing flags SEBELUM cek target
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
        
        # Task 5: Save session recovery setiap SESSION_SAVE_INTERVAL trades
        if self.session_recovery_enabled and self.stats.total_trades > 0:
            if self.stats.total_trades % self.SESSION_SAVE_INTERVAL == 0:
                self._save_session_recovery()
            
        # Cek apakah target tercapai
        if self.target_trades > 0 and self.stats.total_trades >= self.target_trades:
            self._complete_session()
        else:
            # Reset state untuk trade berikutnya
            self.state = TradingState.RUNNING
            self.current_contract_id = None
            self.current_trade_type = None
            
    def _complete_session(self):
        """Handle ketika session selesai (target tercapai)"""
        self.state = TradingState.STOPPED
        self.is_processing_signal = False
        
        logger.info(f"🏁 Session complete! Total profit: ${self.stats.total_profit:.2f}")
        
        # Task 5: Clear session recovery file setelah session selesai normal
        self._clear_session_recovery()
        
        # Save session summary to file
        self._save_session_summary()
        
        # Export analytics to JSON
        try:
            analytics_file = os.path.join(
                LOGS_DIR, 
                f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self.analytics.export_to_json(analytics_file)
        except Exception as e:
            logger.error(f"Failed to export analytics: {e}")
        
        # Log analytics summary
        logger.info(self.analytics.get_summary())
        
        # Debug: Check if callback is set
        logger.info(f"📞 on_session_complete callback check: {self.on_session_complete is not None}")
        
        if self.on_session_complete:
            try:
                logger.info(f"📞 Calling on_session_complete callback...")
                self.on_session_complete(
                    self.stats.total_trades,
                    self.stats.wins,
                    self.stats.losses,
                    self.stats.total_profit,
                    self.stats.win_rate
                )
                logger.info(f"📞 on_session_complete callback completed successfully")
            except Exception as e:
                logger.error(f"❌ Error calling on_session_complete: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        else:
            logger.warning("⚠️ on_session_complete callback is None, skipping notification")
    
    def _reset_processing_state(self):
        """Reset semua flags dan state untuk mencegah deadlock"""
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
        self.buy_request_time = 0.0
        if self.state == TradingState.WAITING_RESULT:
            self.state = TradingState.RUNNING
        self.current_contract_id = None
        self.current_trade_type = None
        logger.info("🔄 Processing state has been reset")
    
    def _log_error(self, error_msg: str):
        """Log error ke file terpisah untuk troubleshooting"""
        try:
            error_file = os.path.join(LOGS_DIR, "errors.log")
            with open(error_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {error_msg}\n")
        except Exception as e:
            logger.error(f"Failed to write error log: {e}")
    
    def _save_session_recovery(self):
        """
        Auto-save session stats ke JSON file untuk recovery.
        Task 5: Session Recovery Mechanism.
        Dipanggil setiap SESSION_SAVE_INTERVAL trades.
        """
        if not self.session_recovery_enabled:
            return
            
        try:
            import time as time_module
            recovery_data = {
                "save_timestamp": time_module.time(),
                "save_datetime": datetime.now().isoformat(),
                "symbol": self.symbol,
                "base_stake": self.base_stake,
                "current_stake": self.current_stake,
                "duration": self.duration,
                "duration_unit": self.duration_unit,
                "target_trades": self.target_trades,
                "stats": {
                    "total_trades": self.stats.total_trades,
                    "wins": self.stats.wins,
                    "losses": self.stats.losses,
                    "total_profit": self.stats.total_profit,
                    "starting_balance": self.stats.starting_balance,
                    "current_balance": self.stats.current_balance,
                    "highest_balance": self.stats.highest_balance,
                    "lowest_balance": self.stats.lowest_balance
                },
                "martingale_level": self.martingale_level,
                "in_martingale_sequence": self.in_martingale_sequence,
                "consecutive_losses": self.consecutive_losses,
                "daily_loss": self.daily_loss,
                "session_start_date": self.session_start_date
            }
            
            recovery_file = self.SESSION_RECOVERY_FILE
            
            os.makedirs(os.path.dirname(recovery_file), exist_ok=True)
            
            temp_file = recovery_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(recovery_data, f, indent=2, default=str)
            
            shutil.move(temp_file, recovery_file)
            
            logger.info(f"💾 Session recovery saved: {self.stats.total_trades} trades, "
                       f"profit: ${self.stats.total_profit:.2f}")
                       
        except Exception as e:
            logger.error(f"Failed to save session recovery: {e}")
            self._log_error(f"Session recovery save failed: {e}")
    
    def _restore_session_recovery(self) -> bool:
        """
        Restore session data dari recovery file jika bot restart dalam 30 menit.
        Task 5: Session Recovery Mechanism.
        
        Returns:
            True jika session berhasil di-restore, False jika tidak
        """
        if not self.session_recovery_enabled:
            logger.info("📂 Session recovery disabled")
            return False
            
        recovery_file = self.SESSION_RECOVERY_FILE
        
        if not os.path.exists(recovery_file):
            logger.info("📂 No session recovery file found - starting fresh")
            return False
            
        try:
            import time as time_module
            
            with open(recovery_file, 'r', encoding='utf-8') as f:
                recovery_data = json.load(f)
            
            save_timestamp = recovery_data.get("save_timestamp", 0)
            current_time = time_module.time()
            age_seconds = current_time - save_timestamp
            
            if age_seconds > self.SESSION_RECOVERY_MAX_AGE:
                logger.info(f"📂 Session recovery file expired (age: {age_seconds:.0f}s > max: {self.SESSION_RECOVERY_MAX_AGE}s)")
                self._clear_session_recovery()
                return False
            
            stats_data = recovery_data.get("stats", {})
            total_trades = stats_data.get("total_trades", 0)
            wins = stats_data.get("wins", 0)
            losses = stats_data.get("losses", 0)
            
            if total_trades != (wins + losses):
                logger.warning(f"⚠️ Data integrity check failed: total_trades ({total_trades}) != wins ({wins}) + losses ({losses})")
                logger.info("🗑️ Recovery file corrupt - clearing and starting fresh")
                self._clear_session_recovery()
                return False
            
            martingale_level = recovery_data.get("martingale_level", 0)
            if not isinstance(martingale_level, int) or martingale_level < 0 or martingale_level > self.MAX_MARTINGALE_LEVEL:
                logger.warning(f"⚠️ Invalid martingale_level: {martingale_level} (must be 0-{self.MAX_MARTINGALE_LEVEL})")
                logger.info("🗑️ Recovery file corrupt - clearing and starting fresh")
                self._clear_session_recovery()
                return False
            
            current_stake = recovery_data.get("current_stake", MIN_STAKE_GLOBAL)
            if not isinstance(current_stake, (int, float)) or current_stake < MIN_STAKE_GLOBAL:
                logger.warning(f"⚠️ Invalid current_stake: {current_stake} (must be >= {MIN_STAKE_GLOBAL})")
                logger.info("🗑️ Recovery file corrupt - clearing and starting fresh")
                self._clear_session_recovery()
                return False
            
            self.symbol = recovery_data.get("symbol", DEFAULT_SYMBOL)
            self.base_stake = recovery_data.get("base_stake", MIN_STAKE_GLOBAL)
            self.current_stake = current_stake
            self.duration = recovery_data.get("duration", 5)
            self.duration_unit = recovery_data.get("duration_unit", "t")
            self.target_trades = recovery_data.get("target_trades", 0)
            
            self.stats.total_trades = total_trades
            self.stats.wins = wins
            self.stats.losses = losses
            self.stats.total_profit = stats_data.get("total_profit", 0.0)
            self.stats.starting_balance = stats_data.get("starting_balance", 0.0)
            self.stats.current_balance = stats_data.get("current_balance", 0.0)
            self.stats.highest_balance = stats_data.get("highest_balance", 0.0)
            self.stats.lowest_balance = stats_data.get("lowest_balance", 0.0)
            
            self.martingale_level = martingale_level
            self.in_martingale_sequence = recovery_data.get("in_martingale_sequence", False)
            self.consecutive_losses = recovery_data.get("consecutive_losses", 0)
            self.daily_loss = recovery_data.get("daily_loss", 0.0)
            self.session_start_date = recovery_data.get("session_start_date", "")
            
            logger.info(f"🔄 Session RECOVERED from {recovery_data.get('save_datetime', 'unknown')}!")
            logger.info(f"   Symbol: {self.symbol}, Stake: ${self.current_stake:.2f}")
            logger.info(f"   Stats: {self.stats.total_trades} trades, "
                       f"{self.stats.wins}W/{self.stats.losses}L, "
                       f"profit: ${self.stats.total_profit:.2f}")
            logger.info(f"   Martingale Level: {self.martingale_level}")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Recovery file JSON corrupt: {e}")
            self._log_error(f"Session recovery JSON corrupt: {e}")
            self._clear_session_recovery()
            return False
        except Exception as e:
            logger.error(f"Failed to restore session recovery: {e}")
            self._log_error(f"Session recovery restore failed: {e}")
            self._clear_session_recovery()
            return False
    
    def _clear_session_recovery(self):
        """
        Clear recovery file setelah session selesai normal.
        Task 5: Session Recovery Mechanism.
        """
        try:
            recovery_file = self.SESSION_RECOVERY_FILE
            if os.path.exists(recovery_file):
                os.remove(recovery_file)
                logger.info("🗑️ Session recovery file cleared")
        except Exception as e:
            logger.warning(f"Failed to clear session recovery file: {e}")
    
    def _validate_csv_integrity(self, filepath: str) -> bool:
        """
        Validate CSV file integrity sebelum append.
        Task 9: CSV validation.
        
        Returns:
            True jika file valid, False jika corrupt
        """
        if not os.path.exists(filepath):
            return True  # File baru, dianggap valid
            
        try:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                
                expected_header = [
                    "timestamp", "trade_number", "symbol", "type", 
                    "entry_price", "exit_price", "stake", "payout", 
                    "profit", "is_win", "rsi", "trend"
                ]
                
                if header != expected_header:
                    logger.warning(f"⚠️ CSV header mismatch. Expected: {expected_header}, Got: {header}")
                    return False
                
                # Count records untuk validation
                record_count = sum(1 for _ in reader)
                logger.debug(f"CSV validation: {record_count} records found")
                
            return True
        except Exception as e:
            logger.error(f"CSV validation error: {e}")
            return False
    
    def _repair_csv_header(self, filepath: str):
        """
        Auto-repair header jika missing.
        Task 9: CSV validation.
        """
        expected_header = [
            "timestamp", "trade_number", "symbol", "type", 
            "entry_price", "exit_price", "stake", "payout", 
            "profit", "is_win", "rsi", "trend"
        ]
        
        try:
            # Read existing content
            existing_content = []
            if os.path.exists(filepath):
                with open(filepath, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    
                    # Skip existing header if different
                    if header != expected_header:
                        # Check if header looks like data (not header)
                        if header and len(header) == len(expected_header):
                            try:
                                # Try to parse first field as timestamp
                                datetime.strptime(header[0], "%Y-%m-%d %H:%M:%S")
                                # This is data, not header - include it
                                existing_content.append(header)
                            except ValueError:
                                pass  # It's a bad header, skip it
                    
                    existing_content.extend(list(reader))
            
            # Write with correct header
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(expected_header)
                writer.writerows(existing_content)
                
            logger.info(f"✅ CSV header repaired: {filepath}")
        except Exception as e:
            logger.error(f"CSV header repair failed: {e}")
    
    def _backup_csv_if_needed(self, filepath: str, max_records: int = 100):
        """
        Backup CSV file sebelum write jika >100 records.
        Task 9: CSV validation.
        """
        if not os.path.exists(filepath):
            return
            
        try:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                record_count = sum(1 for _ in reader)
            
            if record_count >= max_records:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = filepath.replace('.csv', f'_backup_{timestamp}.csv')
                shutil.copy2(filepath, backup_path)
                logger.info(f"📁 CSV backup created: {backup_path} ({record_count} records)")
        except Exception as e:
            logger.warning(f"CSV backup failed (non-critical): {e}")
    
    def _log_trade_to_journal(self, trade: TradeResult):
        """
        Log trade ke CSV journal untuk analisis.
        
        Enhancement v2.1 (Task 9):
        - Validate CSV file integrity sebelum append
        - Backup file sebelum write jika >100 records
        - Use atomic write dengan temp file + rename
        - Auto-repair header jika missing
        """
        try:
            journal_file = os.path.join(LOGS_DIR, f"trades_{datetime.now().strftime('%Y%m%d')}.csv")
            file_exists = os.path.exists(journal_file)
            
            # Task 9: Validate CSV integrity
            if file_exists and not self._validate_csv_integrity(journal_file):
                logger.warning("⚠️ CSV integrity check failed, attempting repair...")
                self._repair_csv_header(journal_file)
            
            # Task 9: Backup if needed
            if file_exists:
                self._backup_csv_if_needed(journal_file)
            
            # Get current RSI and trend
            stats = self.strategy.get_stats()
            
            # Task 9: Atomic write dengan temp file + rename
            temp_file = None
            try:
                # Create temp file in same directory
                fd, temp_file = tempfile.mkstemp(suffix='.csv', dir=LOGS_DIR)
                os.close(fd)
                
                # Copy existing content to temp file
                if file_exists:
                    shutil.copy2(journal_file, temp_file)
                
                # Append new trade to temp file
                with open(temp_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    
                    # Write header jika file baru
                    if not file_exists:
                        writer.writerow([
                            "timestamp", "trade_number", "symbol", "type", 
                            "entry_price", "exit_price", "stake", "payout", 
                            "profit", "is_win", "rsi", "trend"
                        ])
                    
                    # Write trade data
                    writer.writerow([
                        trade.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        trade.trade_number,
                        self.symbol,
                        trade.contract_type,
                        trade.entry_price,
                        trade.exit_price,
                        trade.stake,
                        trade.payout,
                        trade.profit,
                        "WIN" if trade.is_win else "LOSS",
                        stats.get("rsi", 0),
                        stats.get("trend", "N/A")
                    ])
                    
                    # Flush to OS buffer
                    f.flush()
                    # Ensure data hits disk before rename
                    os.fsync(f.fileno())
                
                # Atomic rename
                shutil.move(temp_file, journal_file)
                temp_file = None  # Mark as successfully moved
                
                logger.info(f"📝 Trade logged to journal (atomic): {journal_file}")
                
            finally:
                # Cleanup temp file jika masih ada (gagal rename)
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Failed to log trade to journal: {e}")
            self._log_error(f"Journal write failed: {e}")
    
    def _save_session_summary(self):
        """Simpan ringkasan session ke file"""
        try:
            summary_file = os.path.join(LOGS_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write("=" * 50 + "\n")
                f.write("SESSION SUMMARY\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Symbol: {self.symbol}\n")
                f.write(f"Base Stake: ${self.base_stake}\n\n")
                f.write("STATISTICS:\n")
                f.write(f"  Total Trades: {self.stats.total_trades}\n")
                f.write(f"  Wins: {self.stats.wins}\n")
                f.write(f"  Losses: {self.stats.losses}\n")
                f.write(f"  Win Rate: {self.stats.win_rate:.1f}%\n\n")
                f.write("BALANCE:\n")
                f.write(f"  Starting: ${self.stats.starting_balance:.2f}\n")
                f.write(f"  Ending: ${self.stats.current_balance:.2f}\n")
                f.write(f"  Highest: ${self.stats.highest_balance:.2f}\n")
                f.write(f"  Lowest: ${self.stats.lowest_balance:.2f}\n")
                f.write(f"  Net P/L: ${self.stats.total_profit:+.2f}\n\n")
                f.write("RISK METRICS:\n")
                f.write(f"  Max Consecutive Losses: {self.consecutive_losses}\n")
                f.write(f"  Daily Loss: ${self.daily_loss:.2f}\n")
                f.write("=" * 50 + "\n")
                
            logger.info(f"📊 Session summary saved to: {summary_file}")
        except Exception as e:
            logger.error(f"Failed to save session summary: {e}")
            
    def _check_and_execute_signal(self):
        """
        Cek signal dari strategi dan eksekusi jika ada.
        Dipanggil setiap tick baru masuk.
        """
        # ANTI-DOUBLE BUY: Double check state dan processing flag
        if self.state != TradingState.RUNNING:
            return
            
        if self.is_processing_signal:
            logger.debug("Signal processing already in progress, skipping...")
            return
        
        # Task 1 FIX: Check circuit breaker sebelum analyze signal
        if self._check_circuit_breaker():
            logger.debug("Circuit breaker active, skipping signal check")
            return
        
        # Task 1 FIX: Check apakah ada pending buy timeout
        if self._check_buy_timeout():
            # State sudah di-reset oleh _check_buy_timeout
            logger.debug("Buy timeout detected, state reset")
            return
            
        # Dapatkan analisis dari strategy
        analysis = self.strategy.analyze()
        
        if analysis.signal == Signal.WAIT:
            # Tidak ada signal, lanjut menunggu
            return
            
        # Ada signal! Set flag processing SEBELUM eksekusi
        import time as time_module
        self.is_processing_signal = True
        self.signal_processing_start_time = time_module.time()
        
        contract_type = analysis.signal.value  # "CALL" atau "PUT"
        
        logger.info(f"📊 Signal: {contract_type} | RSI: {analysis.rsi_value} | "
                   f"Confidence: {analysis.confidence:.2f} | Reason: {analysis.reason}")
        
        self._execute_trade(contract_type)
        
    def _calculate_martingale_projection(self, levels: int = 3) -> float:
        """
        Hitung projected total stake jika Martingale sampai level tertentu.
        Task 4: Check jika projected Martingale stake level 3 masih dalam balance.
        
        Args:
            levels: Jumlah level Martingale ke depan
            
        Returns:
            Total projected stake untuk semua level
        """
        multiplier = self._get_martingale_multiplier()
        total_stake = 0.0
        current_projected_stake = self.current_stake
        
        for level in range(levels):
            total_stake += current_projected_stake
            current_projected_stake = round(current_projected_stake * multiplier, 2)
            
        return total_stake
    
    def _calculate_total_exposure(self) -> float:
        """
        Hitung total exposure jika semua pending trades loss.
        Task 4: Enhanced risk management.
        Fixed: Use fresh balance from WebSocket instead of stale stats.
        
        Returns:
            Total potential loss
        """
        # Current stake + projected martingale losses
        projected_loss = self._calculate_martingale_projection(self.MARTINGALE_LOOK_AHEAD_LEVELS)
        
        # Get fresh balance dari WebSocket (bukan stats yang mungkin stale)
        current_balance = self.ws.get_balance() if self.ws else self.stats.current_balance
        
        # Tambahkan current unrealized loss jika ada
        current_loss = self.stats.starting_balance - current_balance if self.stats.starting_balance > 0 else 0
        
        return projected_loss + max(0, current_loss)
    
    def _calculate_max_safe_stake(self, balance: float, lookahead_levels: Optional[int] = None,
                                    volatility_zone: Optional[str] = None) -> float:
        """
        Hitung stake maksimum yang aman untuk martingale N level.
        
        Enhancement v2.3: Integrate volatility_zone adjustment
        - EXTREME_LOW zone: stake * 0.5
        - LOW zone: stake * 0.7
        - NORMAL zone: stake * 1.0
        - HIGH/EXTREME_HIGH zone: stake * 0.85
        
        Args:
            balance: Current balance
            lookahead_levels: Jumlah level lookahead (default: MARTINGALE_LOOK_AHEAD_LEVELS)
            volatility_zone: Volatility zone dari strategy ("EXTREME_LOW", "LOW", "NORMAL", "HIGH", "EXTREME_HIGH")
            
        Returns:
            Maximum safe stake yang tidak melebihi risk limit
        """
        if lookahead_levels is None:
            lookahead_levels = self.MARTINGALE_LOOK_AHEAD_LEVELS
            
        max_exposure = balance * self.MAX_TOTAL_RISK_PERCENT
        multiplier = self._get_martingale_multiplier()
        n = lookahead_levels
        
        # Sum of geometric series: a + a*r + a*r^2 + ... + a*r^(n-1)
        # = a * (1 - r^n) / (1 - r) where a = stake, r = multiplier
        if multiplier == 1:
            series_multiplier = n
        else:
            series_multiplier = (1 - multiplier**n) / (1 - multiplier)
        
        # max_exposure = stake * series_multiplier
        # stake = max_exposure / series_multiplier
        max_stake = max_exposure / series_multiplier
        
        # Pastikan tidak kurang dari minimum stake
        symbol_config = get_symbol_config(self.symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        
        # Hard cap: stake tidak boleh lebih dari 25% balance
        hard_cap = balance * 0.25
        max_stake = min(max_stake, hard_cap)
        
        # Ensure minimum stake
        max_stake = max(min_stake, max_stake)
        
        # v2.3: Apply volatility zone adjustment AFTER ensuring minimum
        # This allows volatility to reduce stakes above minimum but never below it
        if volatility_zone:
            volatility_adjustments = {
                "EXTREME_LOW": 0.5,
                "LOW": 0.7,
                "NORMAL": 1.0,
                "HIGH": 0.85,
                "EXTREME_HIGH": 0.85,
                "UNKNOWN": 1.0
            }
            vol_multiplier = volatility_adjustments.get(volatility_zone, 1.0)
            if vol_multiplier != 1.0 and max_stake > min_stake:
                old_max_stake = max_stake
                # Apply volatility adjustment but never go below min_stake
                adjusted_stake = max_stake * vol_multiplier
                max_stake = max(min_stake, adjusted_stake)
                logger.info(f"📊 Volatility adjustment: {volatility_zone} -> stake * {vol_multiplier} (${old_max_stake:.2f} -> ${max_stake:.2f})")
        
        return round(max_stake, 2)
    
    def _perform_preflight_risk_check(self, current_balance: float) -> tuple[bool, str]:
        """
        Perform pre-flight risk validation sebelum execute trade.
        Task 4: Enhanced Risk Management Validation.
        
        v2.2 Update: Lebih fleksibel untuk martingale sequence
        - Saat dalam martingale (level > 0), gunakan lookahead 3 level
        - Hard cap 25% balance untuk stake maksimum
        - Selalu cap stake ke nilai aman, jangan stop trading
        - Hanya stop jika balance terlalu rendah untuk min stake
        
        v2.3 Update: Integrate volatility zone adjustment
        - EXTREME_LOW zone: stake * 0.5
        - LOW zone: stake * 0.7
        - NORMAL zone: stake * 1.0
        - HIGH/EXTREME_HIGH zone: stake * 0.85
        
        Returns:
            Tuple (is_safe, message)
        """
        # Get fresh balance dari WebSocket untuk accuracy
        fresh_balance = self.ws.get_balance() if self.ws else current_balance
        if fresh_balance != current_balance:
            logger.debug(f"Balance refreshed: ${current_balance:.2f} -> ${fresh_balance:.2f}")
            current_balance = fresh_balance
        
        symbol_config = get_symbol_config(self.symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        
        # v2.3: Get volatility zone dari strategy untuk stake adjustment
        volatility_zone = "NORMAL"
        try:
            vol_zone, vol_mult = self.strategy.get_volatility_zone()
            volatility_zone = vol_zone
            logger.debug(f"📊 Volatility zone: {volatility_zone} (multiplier: {vol_mult})")
        except Exception as e:
            logger.debug(f"Could not get volatility zone: {e}, using NORMAL")
        
        # MARTINGALE RECOVERY PRIORITY: Jangan turunkan stake saat dalam martingale sequence
        # Ini penting untuk recovery yang efektif setelah loss
        if self.in_martingale_sequence and self.martingale_level > 0:
            # Saat dalam martingale, hanya check apakah balance cukup
            if self.current_stake > current_balance:
                msg = f"Balance ${current_balance:.2f} tidak cukup untuk martingale stake ${self.current_stake:.2f}"
                logger.error(f"🛑 {msg}")
                return False, msg
            
            # Hard cap 50% balance untuk martingale (lebih toleran)
            max_martingale_cap = current_balance * 0.50
            if self.current_stake > max_martingale_cap:
                old_stake = self.current_stake
                self.current_stake = round(max_martingale_cap, 2)
                logger.warning(f"⚠️ Martingale stake capped: ${old_stake:.2f} -> ${self.current_stake:.2f} (max 50% balance)")
            
            logger.info(f"📊 MARTINGALE MODE: stake=${self.current_stake:.2f}, level={self.martingale_level}, balance=${current_balance:.2f}")
            return True, "Martingale recovery mode - stake preserved"
        
        # Normal mode (tidak dalam martingale) - gunakan risk check standar
        lookahead = self.MARTINGALE_LOOK_AHEAD_LEVELS
        
        # Hitung max safe stake dengan lookahead dan volatility zone
        safe_stake = self._calculate_max_safe_stake(current_balance, lookahead, volatility_zone)
        
        # Hard cap: stake tidak boleh lebih dari 25% balance untuk trade awal
        max_stake_cap = current_balance * 0.25
        if self.current_stake > max_stake_cap:
            old_stake = self.current_stake
            self.current_stake = round(max_stake_cap, 2)
            logger.warning(f"⚠️ Stake auto-capped: ${old_stake:.2f} -> ${self.current_stake:.2f} (max 25% balance)")
        
        # Jika current stake melebihi safe stake, cap ke safe stake
        if self.current_stake > safe_stake:
            old_stake = self.current_stake
            
            # Pastikan safe stake tidak di bawah minimum
            if safe_stake >= min_stake:
                self.current_stake = safe_stake
                logger.info(f"📊 Stake adjusted: ${old_stake:.2f} -> ${safe_stake:.2f} (vol zone: {volatility_zone})")
            else:
                # Balance terlalu rendah, tapi tetap coba dengan min stake
                if current_balance >= min_stake:
                    self.current_stake = min_stake
                    logger.warning(f"⚠️ Stake adjusted to minimum: ${old_stake:.2f} -> ${min_stake:.2f}")
                else:
                    # Balance benar-benar tidak cukup
                    msg = f"Balance ${current_balance:.2f} tidak cukup untuk minimum stake ${min_stake:.2f}"
                    logger.error(f"🛑 {msg}")
                    return False, msg
        
        # Pastikan stake tidak di bawah minimum
        if self.current_stake < min_stake:
            if current_balance >= min_stake:
                self.current_stake = min_stake
            else:
                msg = f"Balance ${current_balance:.2f} tidak cukup untuk minimum stake ${min_stake:.2f}"
                logger.error(f"🛑 {msg}")
                return False, msg
        
        # Log info exposure dengan volatility zone
        total_exposure = self._calculate_total_exposure()
        exposure_percent = (total_exposure / current_balance * 100) if current_balance > 0 else 100
        logger.info(f"📊 Risk check: stake=${self.current_stake:.2f}, exposure={exposure_percent:.1f}%, level={self.martingale_level}, vol_zone={volatility_zone}")
        
        return True, "Risk check passed"
    
    def _execute_trade(self, contract_type: str):
        """
        Eksekusi trade dengan parameter yang sudah diset.
        
        Enhancement v2.1:
        - Pre-flight risk validation (Task 4)
        - Buy timeout tracking (Task 1)
        - Circuit breaker check (Task 1)
        
        Args:
            contract_type: "CALL" atau "PUT"
        """
        import time as time_module
        
        # Check circuit breaker terlebih dahulu
        if self._check_circuit_breaker():
            self.state = TradingState.RUNNING
            self.is_processing_signal = False
            return
        
        # Check buy timeout dari request sebelumnya
        if self._check_buy_timeout():
            # State sudah di-reset oleh _check_buy_timeout
            return
        
        # Set state SEBELUM buy untuk mencegah race condition
        self.state = TradingState.WAITING_RESULT
        self.current_trade_type = contract_type
        
        # Validasi stake berdasarkan symbol
        symbol_config = get_symbol_config(self.symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        if self.current_stake < min_stake:
            self.current_stake = min_stake
        
        current_balance = self.ws.get_balance()
        
        # ENHANCED RISK CHECK (Task 4): Pre-flight validation
        is_safe, risk_msg = self._perform_preflight_risk_check(current_balance)
        if not is_safe:
            logger.error(f"🛑 Pre-flight risk check failed: {risk_msg}")
            if self.on_error:
                self.on_error(f"Trading dihentikan! {risk_msg}")
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            self._complete_session()
            return
        
        # RISK CHECK 1: Cek balance cukup
        if self.current_stake > current_balance:
            if self.on_error:
                self.on_error(f"Balance tidak cukup! Stake: ${self.current_stake}, Balance: ${current_balance:.2f}")
            self.state = TradingState.STOPPED
            self.is_processing_signal = False
            return
        
        # RISK CHECK 2: Cek max loss limit (20% dari balance awal)
        if self.stats.starting_balance > 0:
            max_loss = self.stats.starting_balance * self.MAX_LOSS_PERCENT
            current_loss = self.stats.starting_balance - current_balance
            if current_loss >= max_loss:
                logger.warning(f"⚠️ Max loss limit reached! Loss: ${current_loss:.2f} >= ${max_loss:.2f}")
                if self.on_error:
                    self.on_error(f"Trading dihentikan! Max loss {self.MAX_LOSS_PERCENT*100:.0f}% tercapai. Loss: ${current_loss:.2f}")
                self.is_processing_signal = False
                self.signal_processing_start_time = 0.0
                self._complete_session()
                return
        
        # RISK CHECK 3: Cek daily loss limit
        if self.daily_loss >= self.MAX_DAILY_LOSS:
            logger.warning(f"⚠️ Daily loss limit reached! Daily loss: ${self.daily_loss:.2f} >= ${self.MAX_DAILY_LOSS:.2f}")
            if self.on_error:
                self.on_error(f"Trading dihentikan! Daily loss limit ${self.MAX_DAILY_LOSS:.2f} tercapai. Loss hari ini: ${self.daily_loss:.2f}")
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            self._complete_session()
            return
        
        # RISK CHECK 4: Cek apakah stake berikutnya (Martingale) melebihi balance
        multiplier = self._get_martingale_multiplier()
        projected_next_stake = self.current_stake * multiplier
        if projected_next_stake > current_balance:
            logger.warning(f"⚠️ Balance mungkin tidak cukup untuk Martingale! Next stake: ${projected_next_stake:.2f}, Balance: ${current_balance:.2f}")
        
        # Record buy request time untuk timeout tracking (Task 1)
        self.buy_request_time = time_module.time()
        
        # Eksekusi buy
        success = self.ws.buy_contract(
            contract_type=contract_type,
            amount=self.current_stake,
            symbol=self.symbol,
            duration=self.duration,
            duration_unit=self.duration_unit
        )
        
        if not success:
            logger.error("Failed to send buy request")
            self.buy_request_time = 0.0  # Reset timeout tracking
            self._record_buy_failure()  # Record untuk circuit breaker
            self.state = TradingState.RUNNING
            self.is_processing_signal = False
            
    def configure(
        self,
        stake: float = 0.50,
        duration: int = 5,
        duration_unit: str = "t",
        target_trades: int = 0,
        symbol: str = "R_100"
    ) -> str:
        """
        Konfigurasi parameter trading.
        
        Args:
            stake: Jumlah stake per trade
            duration: Durasi kontrak
            duration_unit: Unit durasi ("t"=ticks, "s"=seconds, "m"=minutes)
            target_trades: Target jumlah trade (0=unlimited)
            symbol: Trading pair
            
        Returns:
            Pesan konfirmasi atau error
        """
        # Validasi stake berdasarkan symbol
        symbol_config = get_symbol_config(symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        if stake < min_stake:
            logger.warning(f"⚠️ Stake ${stake} dibawah minimum untuk {symbol}. Disesuaikan ke ${min_stake}")
            stake = min_stake
            
        # Validasi durasi untuk symbol
        is_valid, error_msg = validate_duration_for_symbol(symbol, duration, duration_unit)
        if not is_valid:
            return f"❌ Error: {error_msg}"
        
        # Simpan symbol dulu untuk digunakan di _calculate_max_safe_stake
        self.symbol = symbol
            
        # Log stake vs balance info (tanpa warning berlebihan ke user)
        if self.ws and self.ws.is_ready():
            current_balance = self.ws.get_balance()
            if current_balance > 0:
                max_safe_stake = self._calculate_max_safe_stake(current_balance)
                if stake > max_safe_stake:
                    logger.info(f"📊 Stake ${stake:.2f} akan auto-adjust ke ${max_safe_stake:.2f} saat trading")
            
        self.base_stake = stake
        
        if self.in_martingale_sequence and self.current_stake > stake:
            logger.info(f"📊 Martingale active: keeping stake ${self.current_stake:.2f} (not resetting to ${stake:.2f})")
        else:
            self.current_stake = stake
            
        self.duration = duration
        self.duration_unit = duration_unit
        self.target_trades = target_trades
        
        target_text = f"{target_trades} trades" if target_trades > 0 else "Unlimited"
        
        stake_display = self.current_stake if self.in_martingale_sequence else stake
        return (f"✅ Konfigurasi tersimpan:\n"
                f"• Stake: ${stake_display:.2f}\n"
                f"• Durasi: {duration}{duration_unit}\n"
                f"• Target: {target_text}\n"
                f"• Symbol: {symbol}")
                
    def start(self) -> str:
        """
        Mulai auto trading.
        
        Returns:
            Pesan status
        """
        if self.state == TradingState.RUNNING:
            return "⚠️ Auto trading sudah berjalan!"
            
        if not self.ws.is_ready():
            return "❌ WebSocket belum terkoneksi. Coba lagi nanti."
            
        # Double-check stake validation
        symbol_config = get_symbol_config(self.symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        if self.base_stake < min_stake:
            logger.warning(f"⚠️ Base stake ${self.base_stake} dibawah minimum. Disesuaikan ke ${min_stake}")
            self.base_stake = min_stake
        
        # Task 5: Try to restore session if recovery file exists
        session_restored = self._restore_session_recovery()
        
        if not session_restored:
            # Reset stats untuk session baru jika tidak ada recovery
            self.stats = SessionStats()
            self.stats.starting_balance = self.ws.get_balance()
            self.stats.current_balance = self.stats.starting_balance
            self.stats.highest_balance = self.stats.starting_balance
            self.stats.lowest_balance = self.stats.starting_balance
            self.trade_history.clear()
            
            # Reset stake ke base HANYA jika tidak dalam martingale sequence
            if self.in_martingale_sequence and self.current_stake > self.base_stake:
                logger.info(f"📊 Martingale active: keeping stake ${self.current_stake:.2f} for new session")
            else:
                self.current_stake = self.base_stake
        else:
            # Update current balance from websocket
            current_balance = self.ws.get_balance()
            self.stats.current_balance = current_balance
            if current_balance > self.stats.highest_balance:
                self.stats.highest_balance = current_balance
            if current_balance < self.stats.lowest_balance:
                self.stats.lowest_balance = current_balance
        
        # Reset tick counter untuk progress tracking
        self.tick_count = 0
        
        # Reset progress notification tracking (Task 7)
        self.last_progress_notification_time = 0.0
        self.last_notified_milestone = -1
        self.sent_milestones.clear()  # Reset sent milestones for new session
        
        # Reset risk management counters (hanya jika tidak ada recovery DAN tidak dalam martingale)
        if not session_restored and not self.in_martingale_sequence:
            self.consecutive_losses = 0
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
        self.last_trade_time = 0.0
        self.buy_retry_count = 0
        
        # Reset daily loss jika tanggal berbeda
        today = datetime.now().strftime("%Y-%m-%d")
        if self.session_start_date != today:
            self.session_start_date = today
            self.daily_loss = 0.0
        
        # Clear strategy history untuk fresh analysis
        self.strategy.clear_history()
        
        # Pre-load historical data agar langsung siap trading
        preload_success = self._preload_historical_data()
        
        # Subscribe ke ticks untuk data real-time
        self.ws.subscribe_ticks(self.symbol)
        
        # Update state
        self.state = TradingState.RUNNING
        
        target_text = f"{self.target_trades}" if self.target_trades > 0 else "∞"
        
        # Cek status data setelah preload
        strategy_stats = self.strategy.get_stats()
        tick_count = strategy_stats.get('tick_count', 0)
        rsi_value = strategy_stats.get('rsi', 0)
        
        if preload_success and tick_count >= self.required_ticks:
            status_msg = f"✅ Data siap ({tick_count} ticks) - Signal analysis aktif!"
            ready_status = "SIAP TRADING"
        else:
            status_msg = f"⏳ Melengkapi data ({tick_count}/{self.required_ticks} ticks)..."
            ready_status = "LOADING DATA"
        
        return (f"🚀 **AUTO TRADING STARTED**\n\n"
                f"• Symbol: {self.symbol}\n"
                f"• Stake: ${self.base_stake}\n"
                f"• Durasi: {self.duration}{self.duration_unit}\n"
                f"• Target: {target_text} trades\n"
                f"• Saldo Awal: ${self.stats.starting_balance:.2f}\n\n"
                f"📊 **Status:** {ready_status}\n"
                f"{status_msg}")
                
    def stop(self) -> str:
        """
        Hentikan auto trading.
        
        Returns:
            Pesan ringkasan session
        """
        if self.state == TradingState.IDLE or self.state == TradingState.STOPPED:
            return "⚠️ Auto trading tidak sedang berjalan."
            
        # Unsubscribe dari ticks untuk symbol yang sedang di-trade
        self.ws.unsubscribe_ticks(self.symbol)
        
        # Update state
        self.state = TradingState.STOPPED
        
        # Reset processing flags untuk mencegah deadlock saat restart
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
        
        # Save session summary
        self._save_session_summary()
        
        # Generate summary
        return self._generate_session_summary()
        
    def _generate_session_summary(self) -> str:
        """Generate ringkasan session trading"""
        profit_emoji = "📈" if self.stats.total_profit >= 0 else "📉"
        
        return (f"🏁 **SESSION COMPLETE**\n\n"
                f"📊 **Statistik:**\n"
                f"• Total Trades: {self.stats.total_trades}\n"
                f"• Win: {self.stats.wins} | Loss: {self.stats.losses}\n"
                f"• Win Rate: {self.stats.win_rate:.1f}%\n\n"
                f"{profit_emoji} **Profit/Loss:**\n"
                f"• Net P/L: ${self.stats.total_profit:+.2f}\n"
                f"• Saldo Akhir: ${self.stats.current_balance:.2f}\n"
                f"• Tertinggi: ${self.stats.highest_balance:.2f}\n"
                f"• Terendah: ${self.stats.lowest_balance:.2f}")
                
    def get_status(self) -> str:
        """Dapatkan status trading saat ini"""
        state_emoji = {
            TradingState.IDLE: "⏸️",
            TradingState.RUNNING: "▶️",
            TradingState.PAUSED: "⏸️",
            TradingState.WAITING_RESULT: "⏳",
            TradingState.STOPPED: "⏹️"
        }
        
        emoji = state_emoji.get(self.state, "❓")
        
        strategy_stats = self.strategy.get_stats()
        
        return (f"{emoji} **Status Trading**\n\n"
                f"• State: {self.state.value}\n"
                f"• Tick Count: {strategy_stats['tick_count']}\n"
                f"• RSI: {strategy_stats['rsi']:.2f}\n"
                f"• Trend: {strategy_stats['trend']}\n"
                f"• Current Price: {strategy_stats['current_price']}\n\n"
                f"📊 **Session Stats:**\n"
                f"• Trades: {self.stats.total_trades}\n"
                f"• Win/Loss: {self.stats.wins}/{self.stats.losses}\n"
                f"• Profit: ${self.stats.total_profit:+.2f}")
                
    def parse_duration(self, duration_str: str) -> tuple[int, str]:
        """
        Parse input durasi dari user.
        
        Args:
            duration_str: String seperti "5t", "1m", "30s"
            
        Returns:
            Tuple (duration_value, duration_unit)
        """
        duration_str = duration_str.lower().strip()
        
        # Default values
        duration = 5
        unit = "t"
        
        if duration_str.endswith("t"):
            # Ticks
            duration = int(duration_str[:-1]) if duration_str[:-1].isdigit() else 5
            unit = "t"
        elif duration_str.endswith("m"):
            # Minutes
            duration = int(duration_str[:-1]) if duration_str[:-1].isdigit() else 1
            unit = "m"
        elif duration_str.endswith("s"):
            # Seconds
            duration = int(duration_str[:-1]) if duration_str[:-1].isdigit() else 30
            unit = "s"
        elif duration_str.isdigit():
            # Assume ticks if just number
            duration = int(duration_str)
            unit = "t"
            
        return (duration, unit)
