"""
=============================================================
TRADING MANAGER - Eksekusi & Money Management
=============================================================
Modul ini menangani eksekusi trading, Martingale system,
dan tracking hasil trading.

Fitur:
- Auto trading dengan target jumlah trade
- Martingale money management
- Real-time win/loss detection
- Session statistics
=============================================================
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from strategy import TradingStrategy, Signal, AnalysisResult
from deriv_ws import DerivWebSocket, AccountType

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


class TradingManager:
    """
    Kelas utama untuk mengelola trading session.
    Menggabungkan strategi, eksekusi, dan money management.
    """
    
    # Konstanta trading
    MIN_STAKE = 0.35  # Stake minimum Deriv
    DEFAULT_STAKE = 0.35
    MARTINGALE_MULTIPLIER = 2.1
    
    def __init__(self, deriv_ws: DerivWebSocket):
        """
        Inisialisasi Trading Manager.
        
        Args:
            deriv_ws: Instance DerivWebSocket yang sudah terkoneksi
        """
        self.ws = deriv_ws
        self.strategy = TradingStrategy()
        
        # Trading parameters
        self.base_stake = self.DEFAULT_STAKE
        self.current_stake = self.DEFAULT_STAKE
        self.duration = 5
        self.duration_unit = "t"  # ticks
        self.target_trades = 0  # 0 = unlimited
        self.symbol = "frxXAUUSD"
        
        # State management
        self.state = TradingState.IDLE
        self.current_contract_id: Optional[str] = None
        self.current_trade_type: Optional[str] = None
        self.entry_price: float = 0.0
        
        # Statistics
        self.stats = SessionStats()
        self.trade_history: list[TradeResult] = []
        
        # Callbacks untuk notifikasi Telegram
        self.on_trade_opened: Optional[Callable] = None
        self.on_trade_closed: Optional[Callable] = None
        self.on_session_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        
        # Setup WebSocket callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Setup callback functions untuk WebSocket"""
        self.ws.on_tick_callback = self._on_tick
        self.ws.on_buy_response_callback = self._on_buy_response
        self.ws.on_contract_update_callback = self._on_contract_update
        self.ws.on_balance_update_callback = self._on_balance_update
        
    def _on_tick(self, price: float, symbol: str):
        """
        Handler untuk setiap tick yang masuk.
        Menambahkan ke strategy dan mengecek signal.
        """
        # Tambahkan tick ke strategy
        self.strategy.add_tick(price)
        
        # Jika sedang dalam posisi, tidak perlu analisis
        if self.state == TradingState.WAITING_RESULT:
            return
            
        # Jika auto trading aktif, analisis signal
        if self.state == TradingState.RUNNING:
            self._check_and_execute_signal()
            
    def _on_buy_response(self, data: dict):
        """Handler untuk response buy contract"""
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            logger.error(f"❌ Buy failed: {error_msg}")
            
            if self.on_error:
                self.on_error(f"Gagal open posisi: {error_msg}")
                
            # Reset state untuk coba lagi
            self.state = TradingState.RUNNING
            return
            
        buy_info = data.get("buy", {})
        self.current_contract_id = str(buy_info.get("contract_id", ""))
        self.entry_price = float(buy_info.get("buy_price", 0))
        
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
        else:
            self.stats.losses += 1
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
        
        # Martingale logic
        if is_win:
            # Reset ke base stake
            self.current_stake = self.base_stake
            next_stake = self.base_stake
        else:
            # Increase stake (Martingale)
            next_stake = round(self.current_stake * self.MARTINGALE_MULTIPLIER, 2)
            self.current_stake = next_stake
            
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
        
        logger.info(f"🏁 Session complete! Total profit: ${self.stats.total_profit:.2f}")
        
        if self.on_session_complete:
            self.on_session_complete(
                self.stats.total_trades,
                self.stats.wins,
                self.stats.losses,
                self.stats.total_profit,
                self.stats.win_rate
            )
            
    def _check_and_execute_signal(self):
        """
        Cek signal dari strategi dan eksekusi jika ada.
        Dipanggil setiap tick baru masuk.
        """
        if self.state != TradingState.RUNNING:
            return
            
        # Dapatkan analisis dari strategy
        analysis = self.strategy.analyze()
        
        if analysis.signal == Signal.WAIT:
            # Tidak ada signal, lanjut menunggu
            return
            
        # Ada signal! Eksekusi trade
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
        self.state = TradingState.WAITING_RESULT
        self.current_trade_type = contract_type
        
        # Validasi stake
        if self.current_stake < self.MIN_STAKE:
            self.current_stake = self.MIN_STAKE
            
        # Cek balance cukup
        if self.current_stake > self.ws.get_balance():
            if self.on_error:
                self.on_error(f"Balance tidak cukup! Stake: ${self.current_stake}, Balance: ${self.ws.get_balance():.2f}")
            self.state = TradingState.STOPPED
            return
            
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
            
    def configure(
        self,
        stake: float = 0.35,
        duration: int = 5,
        duration_unit: str = "t",
        target_trades: int = 0,
        symbol: str = "frxXAUUSD"
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
        # Validasi stake
        if stake < self.MIN_STAKE:
            stake = self.MIN_STAKE
            
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
            
        # Reset stats untuk session baru
        self.stats = SessionStats()
        self.stats.starting_balance = self.ws.get_balance()
        self.stats.current_balance = self.stats.starting_balance
        self.stats.highest_balance = self.stats.starting_balance
        self.stats.lowest_balance = self.stats.starting_balance
        self.trade_history.clear()
        
        # Reset stake ke base
        self.current_stake = self.base_stake
        
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
