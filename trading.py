"""
=============================================================
TRADING MANAGER - Eksekusi & Money Management v2.0
=============================================================
Modul ini menangani eksekusi trading, Martingale system,
dan tracking hasil trading.

Fitur:
- Auto trading dengan target jumlah trade
- Adaptive Martingale money management (dynamic multiplier)
- Real-time win/loss detection
- Session statistics & analytics
- ATR-based TP/SL monitoring
- Enhanced error handling with exponential backoff

Enhancement v2.0:
- SessionAnalytics class for performance tracking
- Adaptive martingale based on rolling win rate
- Improved risk management
=============================================================
"""

import asyncio
import logging
import json
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
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
    
    Features v2.0:
    - Adaptive Martingale based on rolling win rate
    - Multi-indicator confirmation signals
    - ATR-based TP/SL monitoring
    - Real-time session analytics
    """
    
    MARTINGALE_MULTIPLIER_AGGRESSIVE = 2.5
    MARTINGALE_MULTIPLIER_NORMAL = 2.1
    MARTINGALE_MULTIPLIER_CONSERVATIVE = 1.8
    MAX_MARTINGALE_LEVEL = 5
    
    WIN_RATE_AGGRESSIVE_THRESHOLD = 60.0
    WIN_RATE_CONSERVATIVE_THRESHOLD = 40.0
    
    MAX_LOSS_PERCENT = 0.20
    MAX_CONSECUTIVE_LOSSES = 5
    TRADE_COOLDOWN_SECONDS = 2.0
    MAX_BUY_RETRY = 5
    MAX_DAILY_LOSS = 50.0
    SIGNAL_PROCESSING_TIMEOUT = 120.0
    
    RETRY_BASE_DELAY = 5.0
    RETRY_MAX_DELAY = 60.0
    
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
        
        # Risk Management
        self.consecutive_losses: int = 0
        self.session_start_date: str = ""
        self.daily_loss: float = 0.0
        
        # Statistics
        self.stats = SessionStats()
        self.trade_history: list[TradeResult] = []
        self.analytics = SessionAnalytics()
        
        # Adaptive Martingale tracking
        self.martingale_level: int = 0
        self.in_martingale_sequence: bool = False
        
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
        
    def _get_adaptive_martingale_multiplier(self) -> float:
        """
        Get adaptive martingale multiplier based on rolling win rate.
        
        Returns:
            Multiplier value (1.8 conservative, 2.1 normal, 2.5 aggressive)
        """
        rolling_wr = self.analytics.get_rolling_win_rate()
        
        if rolling_wr >= self.WIN_RATE_AGGRESSIVE_THRESHOLD:
            multiplier = self.MARTINGALE_MULTIPLIER_AGGRESSIVE
            logger.debug(f"📈 Adaptive Martingale: AGGRESSIVE (WR={rolling_wr:.1f}%)")
        elif rolling_wr <= self.WIN_RATE_CONSERVATIVE_THRESHOLD:
            multiplier = self.MARTINGALE_MULTIPLIER_CONSERVATIVE
            logger.debug(f"📉 Adaptive Martingale: CONSERVATIVE (WR={rolling_wr:.1f}%)")
        else:
            multiplier = self.MARTINGALE_MULTIPLIER_NORMAL
            logger.debug(f"⚖️ Adaptive Martingale: NORMAL (WR={rolling_wr:.1f}%)")
            
        return multiplier
        
    def _on_tick(self, price: float, symbol: str):
        """
        Handler untuk setiap tick yang masuk.
        Menambahkan ke strategy dan mengecek signal.
        """
        import time as time_module
        
        # Tambahkan tick ke strategy
        self.strategy.add_tick(price)
        
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
            
            # Progress notification - kirim saat collecting data
            # Send notification at first tick (immediate feedback) and every progress_interval
            should_notify = (
                current_tick_count <= self.required_ticks and 
                (self.tick_count == 1 or self.tick_count % self.progress_interval == 0)
            )
            
            if should_notify:
                logger.info(f"📊 Progress notification triggered: tick_count={self.tick_count}, strategy_ticks={current_tick_count}")
                if self.on_progress:
                    rsi_value = stats['rsi'] if current_tick_count >= 15 else 0
                    trend = stats['trend']
                    logger.info(f"📊 Sending progress: {current_tick_count}/{self.required_ticks} ticks | RSI: {rsi_value} | Trend: {trend}")
                    try:
                        self.on_progress(current_tick_count, self.required_ticks, rsi_value, trend)
                        logger.info("✅ Progress callback executed successfully")
                    except Exception as e:
                        logger.error(f"❌ Error calling on_progress callback: {type(e).__name__}: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                else:
                    logger.warning("⚠️ on_progress callback is None - not registered!")
            
            self._check_and_execute_signal()
            
    def _on_buy_response(self, data: dict):
        """Handler untuk response buy contract"""
        import time as time_module
        
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            error_code = data["error"].get("code", "")
            logger.error(f"❌ Buy failed [{error_code}]: {error_msg}")
            
            # Log error ke file
            self._log_error(f"Buy Error [{error_code}]: {error_msg}")
            
            # Reset processing flags
            self.is_processing_signal = False
            self.signal_processing_start_time = 0.0
            
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
            
        # SUCCESS: Reset retry counter
        self.buy_retry_count = 0
        
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
        
        # Adaptive Martingale logic
        if is_win:
            self.current_stake = self.base_stake
            next_stake = self.base_stake
            
            if self.in_martingale_sequence:
                self.analytics.record_martingale_result(recovered=True)
                logger.info(f"✅ Martingale recovery successful after {self.martingale_level} levels")
            
            self.martingale_level = 0
            self.in_martingale_sequence = False
        else:
            self.in_martingale_sequence = True
            self.martingale_level += 1
            
            if self.martingale_level >= self.MAX_MARTINGALE_LEVEL:
                logger.warning(f"⚠️ Max martingale level ({self.MAX_MARTINGALE_LEVEL}) reached")
                self.analytics.record_martingale_result(recovered=False)
                if self.on_error:
                    self.on_error(f"Max martingale level {self.MAX_MARTINGALE_LEVEL} tercapai. Resetting stake.")
                self.current_stake = self.base_stake
                next_stake = self.base_stake
                self.martingale_level = 0
                self.in_martingale_sequence = False
            else:
                multiplier = self._get_adaptive_martingale_multiplier()
                next_stake = round(self.current_stake * multiplier, 2)
                
                current_balance = self.ws.get_balance()
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
                logger.info(f"📊 Martingale Level {self.martingale_level}: stake ${next_stake:.2f} (multiplier: {multiplier}x)")
            
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
            
        # Reset processing flags SEBELUM cek target
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
            
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
        
        if self.on_session_complete:
            self.on_session_complete(
                self.stats.total_trades,
                self.stats.wins,
                self.stats.losses,
                self.stats.total_profit,
                self.stats.win_rate
            )
    
    def _reset_processing_state(self):
        """Reset semua flags dan state untuk mencegah deadlock"""
        self.is_processing_signal = False
        self.signal_processing_start_time = 0.0
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
    
    def _log_trade_to_journal(self, trade: TradeResult):
        """Log trade ke CSV journal untuk analisis"""
        try:
            journal_file = os.path.join(LOGS_DIR, f"trades_{datetime.now().strftime('%Y%m%d')}.csv")
            file_exists = os.path.exists(journal_file)
            
            with open(journal_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                
                # Write header jika file baru
                if not file_exists:
                    writer.writerow([
                        "timestamp", "trade_number", "symbol", "type", 
                        "entry_price", "exit_price", "stake", "payout", 
                        "profit", "is_win", "rsi", "trend"
                    ])
                
                # Get current RSI and trend
                stats = self.strategy.get_stats()
                
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
                
            logger.info(f"📝 Trade logged to journal: {journal_file}")
        except Exception as e:
            logger.error(f"Failed to log trade to journal: {e}")
    
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
        
    def _execute_trade(self, contract_type: str):
        """
        Eksekusi trade dengan parameter yang sudah diset.
        
        Args:
            contract_type: "CALL" atau "PUT"
        """
        # Set state SEBELUM buy untuk mencegah race condition
        self.state = TradingState.WAITING_RESULT
        self.current_trade_type = contract_type
        
        # Validasi stake berdasarkan symbol
        symbol_config = get_symbol_config(self.symbol)
        min_stake = symbol_config.min_stake if symbol_config else MIN_STAKE_GLOBAL
        if self.current_stake < min_stake:
            self.current_stake = min_stake
        
        current_balance = self.ws.get_balance()
        
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
        multiplier = self._get_adaptive_martingale_multiplier()
        projected_next_stake = self.current_stake * multiplier
        if projected_next_stake > current_balance:
            logger.warning(f"⚠️ Balance mungkin tidak cukup untuk Martingale! Next stake: ${projected_next_stake:.2f}, Balance: ${current_balance:.2f}")
            
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
            
        self.base_stake = stake
        self.current_stake = stake
        self.duration = duration
        self.duration_unit = duration_unit
        self.target_trades = target_trades
        self.symbol = symbol
        
        target_text = f"{target_trades} trades" if target_trades > 0 else "Unlimited"
        
        return (f"✅ Konfigurasi tersimpan:\n"
                f"• Stake: ${stake}\n"
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
        
        # Reset stats untuk session baru
        self.stats = SessionStats()
        self.stats.starting_balance = self.ws.get_balance()
        self.stats.current_balance = self.stats.starting_balance
        self.stats.highest_balance = self.stats.starting_balance
        self.stats.lowest_balance = self.stats.starting_balance
        self.trade_history.clear()
        
        # Reset stake ke base
        self.current_stake = self.base_stake
        
        # Reset tick counter untuk progress tracking
        self.tick_count = 0
        
        # Reset risk management counters
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
        
        # Subscribe ke ticks
        self.ws.subscribe_ticks(self.symbol)
        
        # Update state
        self.state = TradingState.RUNNING
        
        target_text = f"{self.target_trades}" if self.target_trades > 0 else "∞"
        
        return (f"🚀 **AUTO TRADING STARTED**\n\n"
                f"• Symbol: {self.symbol}\n"
                f"• Stake: ${self.base_stake}\n"
                f"• Durasi: {self.duration}{self.duration_unit}\n"
                f"• Target: {target_text} trades\n"
                f"• Saldo Awal: ${self.stats.starting_balance:.2f}\n\n"
                f"⏳ Mengumpulkan data tick untuk analisis RSI...")
                
    def stop(self) -> str:
        """
        Hentikan auto trading.
        
        Returns:
            Pesan ringkasan session
        """
        if self.state == TradingState.IDLE or self.state == TradingState.STOPPED:
            return "⚠️ Auto trading tidak sedang berjalan."
            
        # Unsubscribe dari ticks
        self.ws.unsubscribe_ticks()
        
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
