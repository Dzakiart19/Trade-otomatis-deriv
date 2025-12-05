"""
=============================================================
MODUL STRATEGI TRADING - MULTI-INDICATOR ANALYSIS
=============================================================
Modul ini berisi logika analisis teknikal untuk menentukan
kapan harus BUY (Call), SELL (Put), atau WAIT.

Strategi yang digunakan:
1. RSI (Relative Strength Index) periode 14
2. EMA Crossover (EMA 9/21) untuk konfirmasi trend
3. MACD untuk momentum
4. Stochastic untuk konfirmasi overbought/oversold
5. ATR untuk volatilitas dan TP/SL calculation
6. Tick Trend Follower (3 tick berturut-turut)

Enhancement v2.0:
- Multi-indicator confirmation untuk reduce false signals
- ATR-based dynamic TP/SL
- Trend filter untuk skip sideways market
=============================================================
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Signal(Enum):
    """Enum untuk sinyal trading"""
    BUY = "CALL"
    SELL = "PUT"
    WAIT = "WAIT"


@dataclass
class IndicatorValues:
    """Container untuk semua nilai indikator"""
    rsi: float = 50.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    stoch_k: float = 50.0
    stoch_d: float = 50.0
    atr: float = 0.0
    trend_direction: str = "SIDEWAYS"
    trend_strength: int = 0


@dataclass
class AnalysisResult:
    """Hasil analisis strategi"""
    signal: Signal
    rsi_value: float
    trend_direction: str
    confidence: float
    reason: str
    indicators: IndicatorValues = field(default_factory=IndicatorValues)
    tp_distance: float = 0.0
    sl_distance: float = 0.0


class TradingStrategy:
    """
    Kelas utama untuk strategi trading dengan multi-indicator confirmation.
    Menggabungkan RSI, EMA, MACD, Stochastic, dan ATR.
    
    Enhancement v2.1:
    - Sliding window max 200 ticks (dari 100)
    - Periodic memory cleanup tiap 100 ticks
    - Memory usage logging untuk monitoring
    """
    
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    
    EMA_FAST_PERIOD = 9
    EMA_SLOW_PERIOD = 21
    
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    
    STOCH_PERIOD = 14
    STOCH_SMOOTH = 3
    STOCH_OVERSOLD = 20
    STOCH_OVERBOUGHT = 80
    
    ATR_PERIOD = 14
    ATR_TP_MULTIPLIER = 2.5
    ATR_SL_MULTIPLIER = 1.5
    
    TREND_TICKS = 3
    MIN_TICK_HISTORY = 30
    MIN_VOLATILITY = 0.05
    
    MIN_CONFIDENCE_THRESHOLD = 0.5
    
    # Memory management constants
    MAX_TICK_HISTORY = 200  # increased from 100
    MEMORY_CLEANUP_INTERVAL = 100  # cleanup setiap 100 ticks
    INDICATOR_RESET_THRESHOLD = 500  # reset old indicators jika tick_count > 500
    
    def __init__(self):
        """Inisialisasi strategy dengan tick history kosong"""
        self.tick_history: List[float] = []
        self.high_history: List[float] = []
        self.low_history: List[float] = []
        self.last_indicators = IndicatorValues()
        self.total_tick_count = 0  # track total ticks untuk memory management
        self._last_memory_log_time = 0
        
    def add_tick(self, price: float) -> None:
        """
        Tambahkan tick baru ke history.
        Untuk synthetic indices, high/low approximated dari price movement.
        
        Enhancement v2.1:
        - Sliding window max 200 ticks
        - Periodic memory cleanup
        - Memory usage logging
        """
        import time
        import sys
        
        self.tick_history.append(price)
        self.total_tick_count += 1
        
        if len(self.tick_history) > 1:
            prev_price = self.tick_history[-2]
            high = max(price, prev_price)
            low = min(price, prev_price)
        else:
            high = price
            low = price
            
        self.high_history.append(high)
        self.low_history.append(low)
        
        # Sliding window dengan max 200 ticks (increased dari 100)
        if len(self.tick_history) > self.MAX_TICK_HISTORY:
            self.tick_history = self.tick_history[-self.MAX_TICK_HISTORY:]
            self.high_history = self.high_history[-self.MAX_TICK_HISTORY:]
            self.low_history = self.low_history[-self.MAX_TICK_HISTORY:]
        
        # Periodic memory cleanup tiap 100 ticks
        if self.total_tick_count % self.MEMORY_CLEANUP_INTERVAL == 0:
            self._perform_memory_cleanup()
        
        # Log memory usage setiap 100 ticks (throttled)
        current_time = time.time()
        if self.total_tick_count % self.MEMORY_CLEANUP_INTERVAL == 0 and current_time - self._last_memory_log_time >= 30:
            self._log_memory_usage()
            self._last_memory_log_time = current_time
    
    def _perform_memory_cleanup(self) -> None:
        """
        Perform periodic memory cleanup.
        Clear old indicators jika tick_count > threshold.
        """
        try:
            if self.total_tick_count > self.INDICATOR_RESET_THRESHOLD:
                # Reset last indicators periodically untuk mencegah stale data
                old_rsi = self.last_indicators.rsi
                old_trend = self.last_indicators.trend_direction
                
                # Recalculate fresh indicators
                fresh_indicators = self.calculate_all_indicators()
                
                logger.debug(
                    f"🧹 Memory cleanup at tick {self.total_tick_count}: "
                    f"RSI {old_rsi:.1f} -> {fresh_indicators.rsi:.1f}, "
                    f"Trend {old_trend} -> {fresh_indicators.trend_direction}"
                )
        except Exception as e:
            logger.warning(f"Memory cleanup error (non-critical): {e}")
    
    def _log_memory_usage(self) -> None:
        """Log memory usage untuk monitoring"""
        import sys
        try:
            tick_size = sys.getsizeof(self.tick_history)
            high_size = sys.getsizeof(self.high_history)
            low_size = sys.getsizeof(self.low_history)
            total_size = tick_size + high_size + low_size
            
            logger.info(
                f"📊 Memory stats @ tick {self.total_tick_count}: "
                f"tick_history={len(self.tick_history)} items ({tick_size} bytes), "
                f"total_buffer_size={total_size} bytes"
            )
        except Exception as e:
            logger.debug(f"Memory logging error (non-critical): {e}")
            
    def clear_history(self) -> None:
        """Reset semua history"""
        self.tick_history.clear()
        self.high_history.clear()
        self.low_history.clear()
        self.last_indicators = IndicatorValues()
        
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.
        EMA = Price * k + EMA_prev * (1 - k)
        k = 2 / (period + 1)
        """
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
            
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
            
        return round(ema, 5)
        
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Hitung RSI dengan Wilder's smoothing method.
        """
        if len(prices) < period + 1:
            return 50.0
            
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        recent_changes = changes[-(period):]
        
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
        
    def calculate_macd(self, prices: List[float]) -> Tuple[float, float, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        Returns: (macd_line, signal_line, histogram)
        """
        if len(prices) < self.MACD_SLOW + self.MACD_SIGNAL:
            return 0.0, 0.0, 0.0
            
        ema_fast = self.calculate_ema(prices, self.MACD_FAST)
        ema_slow = self.calculate_ema(prices, self.MACD_SLOW)
        
        macd_line = ema_fast - ema_slow
        
        macd_values = []
        for i in range(self.MACD_SLOW, len(prices) + 1):
            subset = prices[:i]
            ema_f = self.calculate_ema(subset, self.MACD_FAST)
            ema_s = self.calculate_ema(subset, self.MACD_SLOW)
            macd_values.append(ema_f - ema_s)
            
        if len(macd_values) >= self.MACD_SIGNAL:
            signal_line = self.calculate_ema(macd_values, self.MACD_SIGNAL)
        else:
            signal_line = sum(macd_values) / len(macd_values) if macd_values else 0
            
        histogram = macd_line - signal_line
        
        return round(macd_line, 6), round(signal_line, 6), round(histogram, 6)
        
    def calculate_stochastic(self, prices: List[float], highs: List[float], 
                            lows: List[float]) -> Tuple[float, float]:
        """
        Calculate Stochastic Oscillator.
        %K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
        %D = SMA of %K
        """
        if len(prices) < self.STOCH_PERIOD:
            return 50.0, 50.0
            
        k_values = []
        for i in range(self.STOCH_PERIOD, len(prices) + 1):
            period_close = prices[i-1]
            period_highs = highs[max(0, i-self.STOCH_PERIOD):i]
            period_lows = lows[max(0, i-self.STOCH_PERIOD):i]
            
            highest_high = max(period_highs)
            lowest_low = min(period_lows)
            
            if highest_high == lowest_low:
                k_values.append(50.0)
            else:
                k = ((period_close - lowest_low) / (highest_high - lowest_low)) * 100
                k_values.append(k)
                
        if not k_values:
            return 50.0, 50.0
            
        stoch_k = k_values[-1]
        
        if len(k_values) >= self.STOCH_SMOOTH:
            stoch_d = sum(k_values[-self.STOCH_SMOOTH:]) / self.STOCH_SMOOTH
        else:
            stoch_d = sum(k_values) / len(k_values)
            
        return round(stoch_k, 2), round(stoch_d, 2)
        
    def calculate_atr(self, prices: List[float], highs: List[float], 
                     lows: List[float]) -> float:
        """
        Calculate Average True Range (ATR).
        TR = max(High - Low, abs(High - Close_prev), abs(Low - Close_prev))
        ATR = SMA of TR
        """
        if len(prices) < self.ATR_PERIOD + 1:
            if len(highs) > 0 and len(lows) > 0:
                return max(highs) - min(lows)
            return 0.0
            
        true_ranges = []
        for i in range(1, len(prices)):
            high = highs[i]
            low = lows[i]
            prev_close = prices[i-1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
            
        recent_tr = true_ranges[-self.ATR_PERIOD:]
        atr = sum(recent_tr) / len(recent_tr)
        
        return round(atr, 6)
        
    def detect_trend(self, ticks: int = 3) -> Tuple[str, int]:
        """
        Deteksi arah trend berdasarkan tick terakhir.
        """
        if len(self.tick_history) < ticks + 1:
            return ("SIDEWAYS", 0)
            
        recent = self.tick_history[-(ticks + 1):]
        
        up_count = 0
        down_count = 0
        
        for i in range(1, len(recent)):
            if recent[i] > recent[i-1]:
                up_count += 1
            elif recent[i] < recent[i-1]:
                down_count += 1
                
        if up_count >= ticks:
            return ("UP", up_count)
        elif down_count >= ticks:
            return ("DOWN", down_count)
        else:
            return ("SIDEWAYS", 0)
            
    def check_ema_trend(self) -> str:
        """
        Check EMA crossover trend.
        Returns: "BULLISH", "BEARISH", or "NEUTRAL"
        """
        if len(self.tick_history) < self.EMA_SLOW_PERIOD:
            return "NEUTRAL"
            
        ema_fast = self.calculate_ema(self.tick_history, self.EMA_FAST_PERIOD)
        ema_slow = self.calculate_ema(self.tick_history, self.EMA_SLOW_PERIOD)
        
        diff_pct = ((ema_fast - ema_slow) / ema_slow) * 100 if ema_slow != 0 else 0
        
        if diff_pct > 0.01:
            return "BULLISH"
        elif diff_pct < -0.01:
            return "BEARISH"
        else:
            return "NEUTRAL"
            
    def check_volatility(self) -> bool:
        """
        Cek apakah market cukup volatile untuk trading.
        """
        if len(self.tick_history) < 5:
            return False
            
        recent = self.tick_history[-5:]
        price_range = max(recent) - min(recent)
        avg_price = sum(recent) / len(recent)
        
        if avg_price > 0:
            volatility_pct = (price_range / avg_price) * 100
        else:
            volatility_pct = 0
            
        return volatility_pct >= self.MIN_VOLATILITY
        
    def calculate_all_indicators(self) -> IndicatorValues:
        """
        Calculate semua indikator sekaligus.
        """
        indicators = IndicatorValues()
        
        if len(self.tick_history) < self.RSI_PERIOD:
            return indicators
            
        indicators.rsi = self.calculate_rsi(self.tick_history, self.RSI_PERIOD)
        
        if len(self.tick_history) >= self.EMA_SLOW_PERIOD:
            indicators.ema_fast = self.calculate_ema(self.tick_history, self.EMA_FAST_PERIOD)
            indicators.ema_slow = self.calculate_ema(self.tick_history, self.EMA_SLOW_PERIOD)
            
        if len(self.tick_history) >= self.MACD_SLOW + self.MACD_SIGNAL:
            macd_line, macd_signal, macd_hist = self.calculate_macd(self.tick_history)
            indicators.macd_line = macd_line
            indicators.macd_signal = macd_signal
            indicators.macd_histogram = macd_hist
            
        if len(self.tick_history) >= self.STOCH_PERIOD:
            stoch_k, stoch_d = self.calculate_stochastic(
                self.tick_history, self.high_history, self.low_history
            )
            indicators.stoch_k = stoch_k
            indicators.stoch_d = stoch_d
            
        if len(self.tick_history) >= self.ATR_PERIOD + 1:
            indicators.atr = self.calculate_atr(
                self.tick_history, self.high_history, self.low_history
            )
            
        trend_dir, trend_strength = self.detect_trend(self.TREND_TICKS)
        indicators.trend_direction = trend_dir
        indicators.trend_strength = trend_strength
        
        self.last_indicators = indicators
        return indicators
        
    def analyze(self) -> AnalysisResult:
        """
        Analisis utama dengan multi-indicator confirmation.
        
        Signal Requirements:
        BUY (CALL): RSI < 30 AND EMA9 > EMA21 AND MACD histogram > 0 AND Stoch < 20
        SELL (PUT): RSI > 70 AND EMA9 < EMA21 AND MACD histogram < 0 AND Stoch > 80
        
        Scoring:
        - RSI oversold/overbought: +0.4
        - EMA alignment: +0.25
        - MACD confirmation: +0.2
        - Stochastic confirmation: +0.15
        """
        result = AnalysisResult(
            signal=Signal.WAIT,
            rsi_value=50.0,
            trend_direction="SIDEWAYS",
            confidence=0.0,
            reason="Data tidak cukup untuk analisis"
        )
        
        min_required = max(self.RSI_PERIOD + 1, self.EMA_SLOW_PERIOD)
        if len(self.tick_history) < min_required:
            logger.info(f"⏳ Collecting data: {len(self.tick_history)}/{min_required} ticks")
            return result
            
        indicators = self.calculate_all_indicators()
        result.indicators = indicators
        result.rsi_value = indicators.rsi
        result.trend_direction = indicators.trend_direction
        
        if indicators.atr > 0:
            current_price = self.tick_history[-1]
            result.tp_distance = indicators.atr * self.ATR_TP_MULTIPLIER
            result.sl_distance = indicators.atr * self.ATR_SL_MULTIPLIER
        
        buy_score = 0.0
        sell_score = 0.0
        buy_reasons = []
        sell_reasons = []
        
        if indicators.rsi < self.RSI_OVERSOLD:
            buy_score += 0.4
            buy_reasons.append(f"RSI Oversold ({indicators.rsi:.1f})")
        elif indicators.rsi > self.RSI_OVERBOUGHT:
            sell_score += 0.4
            sell_reasons.append(f"RSI Overbought ({indicators.rsi:.1f})")
            
        if indicators.ema_fast > 0 and indicators.ema_slow > 0:
            if indicators.ema_fast > indicators.ema_slow:
                buy_score += 0.25
                buy_reasons.append("EMA9 > EMA21 (Bullish)")
            elif indicators.ema_fast < indicators.ema_slow:
                sell_score += 0.25
                sell_reasons.append("EMA9 < EMA21 (Bearish)")
                
        if indicators.macd_histogram != 0:
            if indicators.macd_histogram > 0:
                buy_score += 0.2
                buy_reasons.append("MACD Positive")
            else:
                sell_score += 0.2
                sell_reasons.append("MACD Negative")
                
        if indicators.stoch_k < self.STOCH_OVERSOLD:
            buy_score += 0.15
            buy_reasons.append(f"Stoch Oversold ({indicators.stoch_k:.1f})")
        elif indicators.stoch_k > self.STOCH_OVERBOUGHT:
            sell_score += 0.15
            sell_reasons.append(f"Stoch Overbought ({indicators.stoch_k:.1f})")
            
        if indicators.trend_direction == "UP":
            buy_score += 0.1
            buy_reasons.append("Trend Up")
        elif indicators.trend_direction == "DOWN":
            sell_score += 0.1
            sell_reasons.append("Trend Down")
            
        if buy_score >= self.MIN_CONFIDENCE_THRESHOLD and buy_score > sell_score:
            if indicators.rsi < self.RSI_OVERSOLD:
                result.signal = Signal.BUY
                result.confidence = min(buy_score, 1.0)
                result.reason = " | ".join(buy_reasons)
                logger.info(f"🟢 BUY Signal: score={buy_score:.2f}, reasons={result.reason}")
                return result
                
        if sell_score >= self.MIN_CONFIDENCE_THRESHOLD and sell_score > buy_score:
            if indicators.rsi > self.RSI_OVERBOUGHT:
                result.signal = Signal.SELL
                result.confidence = min(sell_score, 1.0)
                result.reason = " | ".join(sell_reasons)
                logger.info(f"🔴 SELL Signal: score={sell_score:.2f}, reasons={result.reason}")
                return result
                
        result.signal = Signal.WAIT
        result.confidence = 0.0
        ema_trend = self.check_ema_trend()
        result.reason = f"RSI={indicators.rsi:.1f} | EMA Trend={ema_trend} | Waiting for clear signal"
        
        logger.debug(f"⏳ WAIT: buy_score={buy_score:.2f}, sell_score={sell_score:.2f}")
        
        return result
        
    def get_current_price(self) -> Optional[float]:
        """Dapatkan harga tick terakhir"""
        if self.tick_history:
            return self.tick_history[-1]
        return None
        
    def get_tp_sl_prices(self, entry_price: float, contract_type: str) -> Tuple[float, float]:
        """
        Calculate TP dan SL prices berdasarkan ATR.
        
        Args:
            entry_price: Harga entry
            contract_type: "CALL" atau "PUT"
            
        Returns:
            Tuple (take_profit_price, stop_loss_price)
        """
        atr = self.last_indicators.atr if self.last_indicators.atr > 0 else 0.0001
        
        tp_distance = atr * self.ATR_TP_MULTIPLIER
        sl_distance = atr * self.ATR_SL_MULTIPLIER
        
        if contract_type == "CALL":
            tp_price = entry_price + tp_distance
            sl_price = entry_price - sl_distance
        else:
            tp_price = entry_price - tp_distance
            sl_price = entry_price + sl_distance
            
        return round(tp_price, 5), round(sl_price, 5)
        
    def get_stats(self) -> dict:
        """
        Dapatkan statistik analisis saat ini.
        """
        if not self.tick_history:
            return {
                "tick_count": 0,
                "rsi": 50.0,
                "trend": "N/A",
                "current_price": 0,
                "high": 0,
                "low": 0,
                "ema_fast": 0,
                "ema_slow": 0,
                "macd_histogram": 0,
                "stoch_k": 50,
                "atr": 0
            }
            
        indicators = self.last_indicators
        
        return {
            "tick_count": len(self.tick_history),
            "rsi": indicators.rsi,
            "trend": indicators.trend_direction,
            "current_price": self.tick_history[-1],
            "high": max(self.tick_history[-20:]) if len(self.tick_history) >= 20 else max(self.tick_history),
            "low": min(self.tick_history[-20:]) if len(self.tick_history) >= 20 else min(self.tick_history),
            "ema_fast": indicators.ema_fast,
            "ema_slow": indicators.ema_slow,
            "macd_histogram": indicators.macd_histogram,
            "stoch_k": indicators.stoch_k,
            "atr": indicators.atr
        }
        
    def get_indicator_summary(self) -> str:
        """
        Get formatted summary of all indicators for display.
        """
        ind = self.last_indicators
        
        rsi_status = "🟢 Oversold" if ind.rsi < 30 else "🔴 Overbought" if ind.rsi > 70 else "⚪ Neutral"
        ema_status = "🟢 Bullish" if ind.ema_fast > ind.ema_slow else "🔴 Bearish" if ind.ema_fast < ind.ema_slow else "⚪ Neutral"
        macd_status = "🟢 Positive" if ind.macd_histogram > 0 else "🔴 Negative"
        stoch_status = "🟢 Oversold" if ind.stoch_k < 20 else "🔴 Overbought" if ind.stoch_k > 80 else "⚪ Neutral"
        
        return (
            f"📊 **INDICATORS**\n\n"
            f"• RSI(14): {ind.rsi:.1f} {rsi_status}\n"
            f"• EMA 9/21: {ind.ema_fast:.2f}/{ind.ema_slow:.2f} {ema_status}\n"
            f"• MACD Hist: {ind.macd_histogram:.6f} {macd_status}\n"
            f"• Stoch %K: {ind.stoch_k:.1f} {stoch_status}\n"
            f"• ATR(14): {ind.atr:.6f}\n"
            f"• Trend: {ind.trend_direction}"
        )
