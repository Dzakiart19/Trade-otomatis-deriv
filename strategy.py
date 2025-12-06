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
7. ADX (Average Directional Index) untuk trend strength

Enhancement v2.0:
- Multi-indicator confirmation untuk reduce false signals
- ATR-based dynamic TP/SL
- Trend filter untuk skip sideways market

Enhancement v2.2:
- ADX indicator dan filter dengan +DI/-DI tracking
- Price data validation (NaN/Inf/Negative protection)
- Dynamic volatility-based position sizing
- RSI entry range validation (25-30 for BUY, 70-75 for SELL)
- Enhanced confidence scoring dengan ADX/volatility factors
=============================================================
"""

from typing import List, Optional, Tuple, Any, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_valid_number(value: Any) -> bool:
    """Check if value is a valid finite number (not None, NaN, or Inf)
    
    Args:
        value: Any value to check
        
    Returns:
        True if value is a valid finite number, False otherwise
    """
    if value is None:
        return False
    if not isinstance(value, (int, float)):
        return False
    try:
        if math.isnan(value) or math.isinf(value):
            return False
        return True
    except (TypeError, ValueError):
        return False


def safe_float(value: Any, default: float = 0.0, name: str = "") -> float:
    """Safely convert value to float with NaN/Inf protection
    
    Args:
        value: Value to convert
        default: Default value to return if conversion fails
        name: Optional name for logging
        
    Returns:
        Float value or default if invalid
    """
    if value is None:
        if name:
            logger.debug(f"NaN/Inf check: {name} is None, using default {default}")
        return default
    
    try:
        result = float(value)
        if math.isnan(result):
            if name:
                logger.warning(f"NaN detected in {name}, using default {default}")
            return default
        if math.isinf(result):
            if name:
                logger.warning(f"Inf detected in {name}, using default {default}")
            return default
        return result
    except (TypeError, ValueError) as e:
        if name:
            logger.warning(f"Invalid number in {name}: {e}, using default {default}")
        return default


def safe_divide(numerator: Any, denominator: Any, default: float = 0.0, name: str = "") -> float:
    """Safely divide two numbers with protection against division by zero and NaN/Inf
    
    Args:
        numerator: The numerator value
        denominator: The denominator value
        default: Default value to return if division fails
        name: Optional name for logging
        
    Returns:
        Division result or default if invalid
    """
    num = safe_float(numerator, 0.0)
    denom = safe_float(denominator, 0.0)
    
    if denom == 0.0:
        if name:
            logger.debug(f"Division by zero in {name}, using default {default}")
        return default
    
    try:
        result = num / denom
        if math.isnan(result) or math.isinf(result):
            if name:
                logger.warning(f"NaN/Inf result in {name} division, using default {default}")
            return default
        return result
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as e:
        if name:
            logger.warning(f"Division error in {name}: {e}, using default {default}")
        return default


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
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0


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
    adx_value: float = 0.0
    volatility_zone: str = "NORMAL"
    volatility_multiplier: float = 1.0


class TradingStrategy:
    """
    Kelas utama untuk strategi trading dengan multi-indicator confirmation.
    Menggabungkan RSI, EMA, MACD, Stochastic, ATR, dan ADX.
    
    Enhancement v2.2:
    - ADX indicator untuk trend strength detection
    - Dynamic volatility-based position sizing
    - RSI entry range validation
    - Enhanced confidence scoring
    
    Enhancement v2.3:
    - Multi-timeframe trend confirmation (M5)
    - EMA slope filter for trend direction
    - Enhanced ADX directional conflict detection
    - Volume filter estimation from price movements
    - Price action confirmation with wick validation
    - Signal cooldown system to prevent overtrading
    - Confluence scoring for signal strength
    """
    
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30  # Standard oversold level
    RSI_OVERBOUGHT = 70  # Standard overbought level
    RSI_BUY_ENTRY_MIN = 22  # Tightened: was 20, now 22 for better accuracy
    RSI_BUY_ENTRY_MAX = 30  # Tightened: was 32, now 30 for optimal reversal zone
    RSI_SELL_ENTRY_MIN = 70  # Tightened: was 68, now 70 for better accuracy
    RSI_SELL_ENTRY_MAX = 78  # Tightened: was 80, now 78 for optimal reversal zone
    
    EMA_FAST_PERIOD = 9
    EMA_SLOW_PERIOD = 21
    
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    
    STOCH_PERIOD = 14
    STOCH_SMOOTH = 3
    STOCH_OVERSOLD = 20  # Standard oversold
    STOCH_OVERBOUGHT = 80  # Standard overbought
    
    ATR_PERIOD = 14
    ATR_TP_MULTIPLIER = 2.5
    ATR_SL_MULTIPLIER = 1.5
    
    ADX_PERIOD = 14
    ADX_STRONG_TREND = 22  # Adjusted: was 25, now 22 for better signal frequency
    ADX_WEAK_TREND = 18  # Adjusted: was 20, now 18
    ADX_NO_TREND = 12  # Adjusted: was 15, now 12 for ranging market detection
    
    TREND_TICKS = 3
    MIN_TICK_HISTORY = 30
    MIN_VOLATILITY = 0.05
    
    MIN_CONFIDENCE_THRESHOLD = 0.50  # Balanced: was 0.40, now 0.50 for better accuracy without losing signals
    
    MAX_TICK_HISTORY = 200
    MEMORY_CLEANUP_INTERVAL = 100
    INDICATOR_RESET_THRESHOLD = 500
    RSI_HISTORY_SIZE = 5
    
    COOLDOWN_SECONDS = 12  # Balanced: was 10, now 12 for better entry timing
    VOLUME_HISTORY_SIZE = 20
    EMA_SLOPE_LOOKBACK = 5
    MIN_CONFLUENCE_SCORE = 40  # Balanced: was 20, now 40 for better signal quality (0-100 scale)
    
    ADX_DIRECTIONAL_CONFLICT_THRESHOLD = 15  # HARD BLOCK if DI diff > 15 (gives some tolerance)
    BLOCK_EXTREME_VOLATILITY = True  # HARD BLOCK on EXTREME_HIGH volatility
    BLOCK_EMA_SLOPE_CONFLICT = False  # Soft warning only - don't hard block EMA slope
    
    def __init__(self):
        """Inisialisasi strategy dengan tick history kosong"""
        self.tick_history: List[float] = []
        self.high_history: List[float] = []
        self.low_history: List[float] = []
        self.rsi_history: List[float] = []
        self.ema_fast_history: List[float] = []
        self.volume_history: List[float] = []
        self.last_indicators = IndicatorValues()
        self.total_tick_count = 0
        self._last_memory_log_time = 0
        
        self.last_buy_time: Optional[datetime] = None
        self.last_sell_time: Optional[datetime] = None
        self.last_signal_time: Optional[datetime] = None
        
        self._ema_fast_cache: Optional[float] = None
        self._ema_slow_cache: Optional[float] = None
        self._macd_ema_fast_cache: Optional[float] = None
        self._macd_ema_slow_cache: Optional[float] = None
        self._macd_signal_cache: Optional[float] = None
        self._macd_values_cache: List[float] = []
        self._last_tick_count_for_ema: int = 0
        
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
        
        if not is_valid_number(price):
            logger.warning(f"Invalid tick price received: {price}, skipping")
            return
        
        price = safe_float(price, 0.0)
        if price <= 0:
            logger.warning(f"Non-positive tick price: {price}, skipping")
            return
        
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
        
        if len(self.tick_history) > 1:
            estimated_volume = abs(price - self.tick_history[-2])
            self.volume_history.append(estimated_volume)
            if len(self.volume_history) > self.VOLUME_HISTORY_SIZE:
                self.volume_history = self.volume_history[-self.VOLUME_HISTORY_SIZE:]
        
        if len(self.tick_history) > self.MAX_TICK_HISTORY:
            self.tick_history = self.tick_history[-self.MAX_TICK_HISTORY:]
            self.high_history = self.high_history[-self.MAX_TICK_HISTORY:]
            self.low_history = self.low_history[-self.MAX_TICK_HISTORY:]
        
        if self.total_tick_count % self.MEMORY_CLEANUP_INTERVAL == 0:
            self._perform_memory_cleanup()
        
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
                old_rsi = self.last_indicators.rsi
                old_trend = self.last_indicators.trend_direction
                
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
            
            logger.debug(
                f"📊 Memory stats @ tick {self.total_tick_count}: "
                f"tick_history={len(self.tick_history)} items ({tick_size} bytes), "
                f"total_buffer_size={total_size} bytes"
            )
        except Exception as e:
            logger.debug(f"Memory logging error (non-critical): {e}")
            
    def clear_history(self) -> None:
        """Reset semua history dan EMA cache"""
        self.tick_history.clear()
        self.high_history.clear()
        self.low_history.clear()
        self.rsi_history.clear()
        self.ema_fast_history.clear()
        self.volume_history.clear()
        self.last_indicators = IndicatorValues()
        
        self.last_buy_time = None
        self.last_sell_time = None
        self.last_signal_time = None
        
        self._ema_fast_cache = None
        self._ema_slow_cache = None
        self._macd_ema_fast_cache = None
        self._macd_ema_slow_cache = None
        self._macd_signal_cache = None
        self._macd_values_cache.clear()
        self._last_tick_count_for_ema = 0
        
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.
        EMA = Price * k + EMA_prev * (1 - k)
        k = 2 / (period + 1)
        """
        if len(prices) < period:
            return safe_divide(sum(prices), len(prices), 0.0) if prices else 0.0
            
        k = safe_divide(2, period + 1, 0.0)
        ema = safe_divide(sum(prices[:period]), period, 0.0)
        
        for price in prices[period:]:
            ema = safe_float(price) * k + ema * (1 - k)
            
        return round(ema, 5)
    
    def calculate_ema_incremental(self, period: int, cache_type: str) -> float:
        """
        Calculate EMA incrementally using cached value - O(1) per tick.
        
        Instead of recalculating from scratch every tick (O(n) per call, O(n²) total),
        this method updates the cached EMA with only the latest price.
        
        Formula: EMA_new = price * k + EMA_prev * (1 - k)
        where k = 2 / (period + 1)
        
        Args:
            period: EMA period (e.g., 9 for fast, 21 for slow)
            cache_type: "fast" or "slow" to select which cache to use
            
        Returns:
            Updated EMA value
        """
        if len(self.tick_history) < period:
            return safe_divide(sum(self.tick_history), len(self.tick_history), 0.0) if self.tick_history else 0.0
        
        current_price = safe_float(self.tick_history[-1])
        k = safe_divide(2, period + 1, 0.0)
        
        if cache_type == "fast":
            cached_ema = self._ema_fast_cache
        elif cache_type == "slow":
            cached_ema = self._ema_slow_cache
        else:
            cached_ema = None
        
        need_full_calc = (
            cached_ema is None or 
            self._last_tick_count_for_ema == 0 or
            len(self.tick_history) - self._last_tick_count_for_ema > 1
        )
        
        if need_full_calc:
            ema = self.calculate_ema(self.tick_history, period)
        else:
            # cached_ema is guaranteed not None here due to need_full_calc check
            prev_ema = cached_ema if cached_ema is not None else 0.0
            ema = current_price * k + prev_ema * (1 - k)
            ema = round(ema, 5)
        
        if cache_type == "fast":
            self._ema_fast_cache = ema
        elif cache_type == "slow":
            self._ema_slow_cache = ema
        
        return ema
    
    def calculate_macd_incremental(self) -> Tuple[float, float, float]:
        """
        Calculate MACD incrementally using cached EMA values - O(1) per tick.
        
        Instead of recalculating all EMA subsets for each tick (O(n²) complexity),
        this method uses incremental EMA updates.
        
        Returns: (macd_line, signal_line, histogram)
        """
        if len(self.tick_history) < self.MACD_SLOW + self.MACD_SIGNAL:
            return 0.0, 0.0, 0.0
        
        current_price = safe_float(self.tick_history[-1])
        k_fast = safe_divide(2, self.MACD_FAST + 1, 0.0)
        k_slow = safe_divide(2, self.MACD_SLOW + 1, 0.0)
        k_signal = safe_divide(2, self.MACD_SIGNAL + 1, 0.0)
        
        need_full_calc = (
            self._macd_ema_fast_cache is None or
            self._macd_ema_slow_cache is None or
            self._last_tick_count_for_ema == 0 or
            len(self.tick_history) - self._last_tick_count_for_ema > 1
        )
        
        if need_full_calc:
            ema_fast = self.calculate_ema(self.tick_history, self.MACD_FAST)
            ema_slow = self.calculate_ema(self.tick_history, self.MACD_SLOW)
            
            self._macd_values_cache.clear()
            for i in range(self.MACD_SLOW, len(self.tick_history) + 1):
                subset = self.tick_history[:i]
                ema_f = self.calculate_ema(subset, self.MACD_FAST)
                ema_s = self.calculate_ema(subset, self.MACD_SLOW)
                self._macd_values_cache.append(ema_f - ema_s)
        else:
            # Cache values are guaranteed not None here due to need_full_calc check
            prev_ema_fast = self._macd_ema_fast_cache if self._macd_ema_fast_cache is not None else 0.0
            prev_ema_slow = self._macd_ema_slow_cache if self._macd_ema_slow_cache is not None else 0.0
            ema_fast = current_price * k_fast + prev_ema_fast * (1 - k_fast)
            ema_slow = current_price * k_slow + prev_ema_slow * (1 - k_slow)
            
            new_macd_value = ema_fast - ema_slow
            self._macd_values_cache.append(new_macd_value)
            
            if len(self._macd_values_cache) > self.MAX_TICK_HISTORY:
                self._macd_values_cache = self._macd_values_cache[-self.MAX_TICK_HISTORY:]
        
        self._macd_ema_fast_cache = ema_fast
        self._macd_ema_slow_cache = ema_slow
        
        macd_line = ema_fast - ema_slow
        
        if len(self._macd_values_cache) >= self.MACD_SIGNAL:
            if self._macd_signal_cache is not None and not need_full_calc:
                signal_line = macd_line * k_signal + self._macd_signal_cache * (1 - k_signal)
            else:
                signal_line = self.calculate_ema(self._macd_values_cache, self.MACD_SIGNAL)
            self._macd_signal_cache = signal_line
        else:
            signal_line = safe_divide(sum(self._macd_values_cache), len(self._macd_values_cache), 0.0) if self._macd_values_cache else 0
            self._macd_signal_cache = signal_line
        
        histogram = macd_line - signal_line
        
        return round(macd_line, 6), round(signal_line, 6), round(histogram, 6)
        
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Hitung RSI dengan Wilder's smoothing method.
        """
        if len(prices) < period + 1:
            return 50.0
            
        changes = [safe_float(prices[i]) - safe_float(prices[i-1]) for i in range(1, len(prices))]
        recent_changes = changes[-(period):]
        
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]
        
        avg_gain = safe_divide(sum(gains), period, 0.0)
        avg_loss = safe_divide(sum(losses), period, 0.0)
        
        if avg_loss == 0:
            return 100.0
            
        rs = safe_divide(avg_gain, avg_loss, 0.0)
        rsi = 100 - safe_divide(100, (1 + rs), 0.0)
        
        return round(rsi, 2)
    
    def calculate_adx(self, prices: List[float], highs: List[float], 
                     lows: List[float], period: int = 14) -> Tuple[float, float, float]:
        """
        Calculate ADX (Average Directional Index) with +DI and -DI.
        
        ADX measures trend strength:
        - ADX > 25: Strong trend
        - ADX 20-25: Moderate trend
        - ADX 15-20: Weak trend
        - ADX < 15: No trend / sideways
        
        +DI > -DI: Bullish trend
        -DI > +DI: Bearish trend
        
        Returns:
            Tuple of (ADX, +DI, -DI)
        """
        if len(prices) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
            return 0.0, 0.0, 0.0
        
        try:
            plus_dm_list = []
            minus_dm_list = []
            tr_list = []
            
            for i in range(1, len(prices)):
                high = safe_float(highs[i])
                low = safe_float(lows[i])
                prev_high = safe_float(highs[i-1])
                prev_low = safe_float(lows[i-1])
                prev_close = safe_float(prices[i-1])
                
                plus_dm = max(high - prev_high, 0) if high - prev_high > prev_low - low else 0
                minus_dm = max(prev_low - low, 0) if prev_low - low > high - prev_high else 0
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                
                plus_dm_list.append(plus_dm)
                minus_dm_list.append(minus_dm)
                tr_list.append(tr)
            
            if len(tr_list) < period:
                return 0.0, 0.0, 0.0
            
            smoothed_plus_dm = sum(plus_dm_list[:period])
            smoothed_minus_dm = sum(minus_dm_list[:period])
            smoothed_tr = sum(tr_list[:period])
            
            for i in range(period, len(tr_list)):
                smoothed_plus_dm = smoothed_plus_dm - safe_divide(smoothed_plus_dm, period) + plus_dm_list[i]
                smoothed_minus_dm = smoothed_minus_dm - safe_divide(smoothed_minus_dm, period) + minus_dm_list[i]
                smoothed_tr = smoothed_tr - safe_divide(smoothed_tr, period) + tr_list[i]
            
            plus_di = safe_divide(smoothed_plus_dm * 100, smoothed_tr, 0.0)
            minus_di = safe_divide(smoothed_minus_dm * 100, smoothed_tr, 0.0)
            
            dx_list = []
            temp_plus_dm = sum(plus_dm_list[:period])
            temp_minus_dm = sum(minus_dm_list[:period])
            temp_tr = sum(tr_list[:period])
            
            for i in range(period, len(tr_list)):
                temp_plus_dm = temp_plus_dm - safe_divide(temp_plus_dm, period) + plus_dm_list[i]
                temp_minus_dm = temp_minus_dm - safe_divide(temp_minus_dm, period) + minus_dm_list[i]
                temp_tr = temp_tr - safe_divide(temp_tr, period) + tr_list[i]
                
                temp_plus_di = safe_divide(temp_plus_dm * 100, temp_tr, 0.0)
                temp_minus_di = safe_divide(temp_minus_dm * 100, temp_tr, 0.0)
                
                di_sum = temp_plus_di + temp_minus_di
                di_diff = abs(temp_plus_di - temp_minus_di)
                dx = safe_divide(di_diff * 100, di_sum, 0.0)
                dx_list.append(dx)
            
            if len(dx_list) >= period:
                adx = safe_divide(sum(dx_list[-period:]), period, 0.0)
            elif dx_list:
                adx = safe_divide(sum(dx_list), len(dx_list), 0.0)
            else:
                adx = 0.0
            
            return round(adx, 2), round(plus_di, 2), round(minus_di, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating ADX: {e}")
            return 0.0, 0.0, 0.0
        
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
            signal_line = safe_divide(sum(macd_values), len(macd_values), 0.0) if macd_values else 0
            
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
            period_close = safe_float(prices[i-1])
            period_highs = highs[max(0, i-self.STOCH_PERIOD):i]
            period_lows = lows[max(0, i-self.STOCH_PERIOD):i]
            
            highest_high = max(safe_float(h) for h in period_highs)
            lowest_low = min(safe_float(l) for l in period_lows)
            
            if highest_high == lowest_low:
                k_values.append(50.0)
            else:
                k = safe_divide((period_close - lowest_low) * 100, (highest_high - lowest_low), 50.0)
                k_values.append(k)
                
        if not k_values:
            return 50.0, 50.0
            
        stoch_k = k_values[-1]
        
        if len(k_values) >= self.STOCH_SMOOTH:
            stoch_d = safe_divide(sum(k_values[-self.STOCH_SMOOTH:]), self.STOCH_SMOOTH, 50.0)
        else:
            stoch_d = safe_divide(sum(k_values), len(k_values), 50.0)
            
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
                return max(safe_float(h) for h in highs) - min(safe_float(l) for l in lows)
            return 0.0
            
        true_ranges = []
        for i in range(1, len(prices)):
            high = safe_float(highs[i])
            low = safe_float(lows[i])
            prev_close = safe_float(prices[i-1])
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
            
        recent_tr = true_ranges[-self.ATR_PERIOD:]
        atr = safe_divide(sum(recent_tr), len(recent_tr), 0.0)
        
        return round(atr, 6)
    
    def get_volatility_zone(self) -> Tuple[str, float]:
        """Calculate volatility zone based on ATR percentage.
        
        Adjusted for Synthetic Indices which have higher natural volatility.
        
        Returns:
            Tuple of (zone_name, multiplier)
            - EXTREME_LOW (< 0.01%): 0.5x - Very low volatility, risky
            - LOW (0.01-0.05%): 0.7x - Low volatility, caution
            - NORMAL (0.05-0.2%): 1.0x - Normal trading conditions for synthetics
            - HIGH (0.2-0.5%): 0.85x - High volatility, reduced size
            - EXTREME_HIGH (> 0.5%): 0.7x - Extreme volatility, reduced size
        """
        if not self.tick_history or len(self.tick_history) < self.ATR_PERIOD + 1:
            return "UNKNOWN", 1.0
        
        atr = self.last_indicators.atr
        if atr <= 0:
            atr = self.calculate_atr(self.tick_history, self.high_history, self.low_history)
        
        current_price = safe_float(self.tick_history[-1])
        if current_price <= 0:
            return "UNKNOWN", 1.0
        
        atr_pct = safe_divide(atr * 100, current_price, 0.0)
        
        if atr_pct < 0.01:
            return "EXTREME_LOW", 0.5
        elif atr_pct < 0.05:
            return "LOW", 0.7
        elif atr_pct < 0.2:
            return "NORMAL", 1.0
        elif atr_pct < 0.5:
            return "HIGH", 0.85
        else:
            return "EXTREME_HIGH", 0.7
    
    def check_rsi_momentum(self, current_rsi: float, signal_type: str) -> Tuple[bool, float]:
        """Check RSI momentum direction.
        
        Args:
            current_rsi: Current RSI value
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_favorable, momentum_bonus)
            - is_favorable: True if RSI is moving in the right direction
            - momentum_bonus: Score bonus (0.0 to 0.10)
        """
        self.rsi_history.append(current_rsi)
        if len(self.rsi_history) > self.RSI_HISTORY_SIZE:
            self.rsi_history = self.rsi_history[-self.RSI_HISTORY_SIZE:]
        
        if len(self.rsi_history) < 3:
            return False, 0.0
        
        recent_rsi = self.rsi_history[-3:]
        rsi_change = recent_rsi[-1] - recent_rsi[0]
        
        if signal_type == "BUY":
            if rsi_change < 0 and current_rsi < 40:
                return True, 0.10
            elif rsi_change < -2:
                return True, 0.05
        elif signal_type == "SELL":
            if rsi_change > 0 and current_rsi > 60:
                return True, 0.10
            elif rsi_change > 2:
                return True, 0.05
        
        return False, 0.0
    
    def check_adx_filter(self, adx: float, plus_di: float, minus_di: float, 
                        signal_type: str) -> Tuple[bool, str, float]:
        """Check ADX filter for trend strength with HARD BLOCK for directional conflict.
        
        Enhancement v2.4:
        - HARD BLOCK for directional conflict when diff > ADX_DIRECTIONAL_CONFLICT_THRESHOLD
        - BUY conflict: minus_di > plus_di + threshold → BLOCK
        - SELL conflict: plus_di > minus_di + threshold → BLOCK
        - ADX < ADX_NO_TREND is warning but allowed for ranging market mean-reversion
        
        Args:
            adx: Current ADX value
            plus_di: +DI value
            minus_di: -DI value
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_valid, reason, tp_multiplier)
        """
        if adx < self.ADX_NO_TREND:
            reason = f"⚠️ ADX lemah: {adx:.1f} < {self.ADX_NO_TREND} (ranging market - reduced TP)"
            logger.debug(reason)
            return True, reason, 0.6
        
        directional_conflict = False
        di_info = ""
        di_diff = abs(plus_di - minus_di)
        
        if plus_di > minus_di:
            di_info = f"+DI({plus_di:.1f}) > -DI({minus_di:.1f}) = Bullish"
            if signal_type == "SELL":
                directional_conflict = True
        elif minus_di > plus_di:
            di_info = f"-DI({minus_di:.1f}) > +DI({plus_di:.1f}) = Bearish"
            if signal_type == "BUY":
                directional_conflict = True
        else:
            di_info = f"+DI({plus_di:.1f}) ≈ -DI({minus_di:.1f}) = Neutral"
        
        if directional_conflict and di_diff >= self.ADX_DIRECTIONAL_CONFLICT_THRESHOLD:
            reason = f"🚫 HARD BLOCK: ADX directional conflict {signal_type} vs {di_info} (diff={di_diff:.1f} >= {self.ADX_DIRECTIONAL_CONFLICT_THRESHOLD})"
            logger.warning(reason)
            return False, reason, 0.0
        
        if directional_conflict and di_diff >= 8:
            reason = f"⚠️ ADX directional conflict minor: {signal_type} vs {di_info} (diff={di_diff:.1f})"
            logger.debug(reason)
            return True, reason, 0.7
        
        if adx >= self.ADX_STRONG_TREND:
            reason = f"✅ ADX strong: {adx:.1f} >= {self.ADX_STRONG_TREND} | {di_info}"
            return True, reason, 1.0
        elif adx >= self.ADX_WEAK_TREND:
            reason = f"✅ ADX moderate: {adx:.1f} >= {self.ADX_WEAK_TREND} | {di_info}"
            return True, reason, 0.9
        else:
            reason = f"⚠️ ADX weak: {adx:.1f} < {self.ADX_WEAK_TREND} | {di_info}"
            return True, reason, 0.75
        
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
        
        diff_pct = safe_divide((ema_fast - ema_slow) * 100, ema_slow, 0.0)
        
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
        price_range = max(safe_float(p) for p in recent) - min(safe_float(p) for p in recent)
        avg_price = safe_divide(sum(safe_float(p) for p in recent), len(recent), 1.0)
        
        volatility_pct = safe_divide(price_range * 100, avg_price, 0.0)
            
        return volatility_pct >= self.MIN_VOLATILITY
    
    def check_rsi_entry_range(self, rsi: float, signal_type: str) -> Tuple[bool, str]:
        """Check if RSI is in valid entry range.
        
        Args:
            rsi: Current RSI value
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if signal_type == "BUY":
            if self.RSI_BUY_ENTRY_MIN <= rsi <= self.RSI_BUY_ENTRY_MAX:
                return True, f"RSI in BUY range ({self.RSI_BUY_ENTRY_MIN}-{self.RSI_BUY_ENTRY_MAX})"
            elif rsi < self.RSI_BUY_ENTRY_MIN:
                return True, f"RSI extremely oversold ({rsi:.1f})"
            else:
                return False, f"RSI not in BUY range ({rsi:.1f} not in {self.RSI_BUY_ENTRY_MIN}-{self.RSI_BUY_ENTRY_MAX})"
        elif signal_type == "SELL":
            if self.RSI_SELL_ENTRY_MIN <= rsi <= self.RSI_SELL_ENTRY_MAX:
                return True, f"RSI in SELL range ({self.RSI_SELL_ENTRY_MIN}-{self.RSI_SELL_ENTRY_MAX})"
            elif rsi > self.RSI_SELL_ENTRY_MAX:
                return True, f"RSI extremely overbought ({rsi:.1f})"
            else:
                return False, f"RSI not in SELL range ({rsi:.1f} not in {self.RSI_SELL_ENTRY_MIN}-{self.RSI_SELL_ENTRY_MAX})"
        
        return False, "Invalid signal type"
    
    def check_mtf_trend_confirmation(self, signal_type: str, 
                                      m5_indicators: Optional[Dict[str, float]] = None
                                      ) -> Tuple[bool, str, float]:
        """Multi-Timeframe Trend Confirmation using M5 indicators.
        
        Args:
            signal_type: "BUY" or "SELL"
            m5_indicators: Optional dict with 'ema_fast', 'ema_slow', 'rsi' from M5 timeframe
            
        Returns:
            Tuple of (is_aligned, reason, score_multiplier)
            - is_aligned: True if M5 trend aligns with signal direction
            - reason: Explanation string
            - score_multiplier: 1.0-1.2 for aligned, 0.8-1.0 for neutral/conflict
        """
        if m5_indicators is None:
            return True, "M5 data unavailable - proceeding", 1.0
        
        m5_ema_fast = safe_float(m5_indicators.get('ema_fast', 0), 0.0)
        m5_ema_slow = safe_float(m5_indicators.get('ema_slow', 0), 0.0)
        m5_rsi = safe_float(m5_indicators.get('rsi', 50), 50.0)
        
        if m5_ema_fast == 0 or m5_ema_slow == 0:
            return True, "M5 EMA data incomplete - proceeding", 1.0
        
        if signal_type == "BUY":
            ema_aligned = m5_ema_fast > m5_ema_slow
            rsi_aligned = m5_rsi > 40
            
            if ema_aligned and rsi_aligned:
                reason = f"✅ M5 aligned for BUY: EMA_f({m5_ema_fast:.2f}) > EMA_s({m5_ema_slow:.2f}), RSI({m5_rsi:.1f}) > 40"
                logger.debug(reason)
                return True, reason, 1.15
            elif ema_aligned or rsi_aligned:
                reason = f"⚠️ M5 partial alignment for BUY: EMA{'✓' if ema_aligned else '✗'}, RSI{'✓' if rsi_aligned else '✗'}"
                logger.debug(reason)
                return True, reason, 1.0
            else:
                reason = f"❌ M5 conflict for BUY: EMA_f({m5_ema_fast:.2f}) < EMA_s({m5_ema_slow:.2f}), RSI({m5_rsi:.1f}) < 40"
                logger.debug(reason)
                return False, reason, 0.85
                
        elif signal_type == "SELL":
            ema_aligned = m5_ema_fast < m5_ema_slow
            rsi_aligned = m5_rsi < 60
            
            if ema_aligned and rsi_aligned:
                reason = f"✅ M5 aligned for SELL: EMA_f({m5_ema_fast:.2f}) < EMA_s({m5_ema_slow:.2f}), RSI({m5_rsi:.1f}) < 60"
                logger.debug(reason)
                return True, reason, 1.15
            elif ema_aligned or rsi_aligned:
                reason = f"⚠️ M5 partial alignment for SELL: EMA{'✓' if ema_aligned else '✗'}, RSI{'✓' if rsi_aligned else '✗'}"
                logger.debug(reason)
                return True, reason, 1.0
            else:
                reason = f"❌ M5 conflict for SELL: EMA_f({m5_ema_fast:.2f}) > EMA_s({m5_ema_slow:.2f}), RSI({m5_rsi:.1f}) > 60"
                logger.debug(reason)
                return False, reason, 0.85
        
        return True, "Invalid signal type - proceeding", 1.0
    
    def check_ema_slope(self, signal_type: str) -> Tuple[bool, str, Dict[str, Any]]:
        """EMA Slope Filter to detect trend direction from recent EMA values.
        
        Args:
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_valid, reason, slope_data)
            - is_valid: True if slope is favorable for signal direction
            - reason: Explanation string
            - slope_data: Dict with 'direction', 'slope_value', 'strength'
        """
        slope_data = {
            'direction': 'flat',
            'slope_value': 0.0,
            'strength': 'neutral'
        }
        
        if len(self.tick_history) < self.EMA_SLOW_PERIOD + self.EMA_SLOPE_LOOKBACK:
            return True, "Insufficient data for EMA slope calculation", slope_data
        
        ema_values = []
        lookback_range = min(self.EMA_SLOPE_LOOKBACK, len(self.tick_history) - self.EMA_FAST_PERIOD)
        
        for i in range(lookback_range):
            end_idx = len(self.tick_history) - lookback_range + i + 1
            subset = self.tick_history[:end_idx]
            ema_val = self.calculate_ema(subset, self.EMA_FAST_PERIOD)
            ema_values.append(ema_val)
            
        self.ema_fast_history = ema_values[-self.EMA_SLOPE_LOOKBACK:] if len(ema_values) >= self.EMA_SLOPE_LOOKBACK else ema_values
        
        if len(ema_values) < 2:
            return True, "Not enough EMA values for slope", slope_data
        
        first_ema = ema_values[0]
        last_ema = ema_values[-1]
        
        if first_ema <= 0:
            return True, "Invalid EMA for slope calculation", slope_data
        
        slope_value = safe_divide((last_ema - first_ema) * 100, first_ema, 0.0)
        slope_data['slope_value'] = round(slope_value, 4)
        
        slope_threshold = 0.01
        strong_threshold = 0.05
        
        if slope_value > strong_threshold:
            slope_data['direction'] = 'bullish'
            slope_data['strength'] = 'strong'
        elif slope_value > slope_threshold:
            slope_data['direction'] = 'bullish'
            slope_data['strength'] = 'moderate'
        elif slope_value < -strong_threshold:
            slope_data['direction'] = 'bearish'
            slope_data['strength'] = 'strong'
        elif slope_value < -slope_threshold:
            slope_data['direction'] = 'bearish'
            slope_data['strength'] = 'moderate'
        else:
            slope_data['direction'] = 'flat'
            slope_data['strength'] = 'neutral'
        
        direction = slope_data['direction']
        
        if signal_type == "BUY":
            if direction in ['bullish', 'flat']:
                reason = f"✅ EMA slope OK for BUY: {direction} ({slope_value:.4f}%)"
                logger.debug(reason)
                return True, reason, slope_data
            else:
                if self.BLOCK_EMA_SLOPE_CONFLICT and slope_data['strength'] == 'strong':
                    reason = f"🚫 HARD BLOCK: EMA slope conflict for BUY: strong {direction} ({slope_value:.4f}%)"
                    logger.warning(reason)
                    return False, reason, slope_data
                reason = f"⚠️ EMA slope warning for BUY: {direction} ({slope_value:.4f}%)"
                logger.debug(reason)
                return False, reason, slope_data
                
        elif signal_type == "SELL":
            if direction in ['bearish', 'flat']:
                reason = f"✅ EMA slope OK for SELL: {direction} ({slope_value:.4f}%)"
                logger.debug(reason)
                return True, reason, slope_data
            else:
                if self.BLOCK_EMA_SLOPE_CONFLICT and slope_data['strength'] == 'strong':
                    reason = f"🚫 HARD BLOCK: EMA slope conflict for SELL: strong {direction} ({slope_value:.4f}%)"
                    logger.warning(reason)
                    return False, reason, slope_data
                reason = f"⚠️ EMA slope warning for SELL: {direction} ({slope_value:.4f}%)"
                logger.debug(reason)
                return False, reason, slope_data
        
        return True, "EMA slope check passed", slope_data
    
    def check_volume_filter(self) -> Tuple[bool, str, float]:
        """Volume Filter based on estimated volume from price movements.
        
        Uses volume_history (last 20 ticks estimated from price changes).
        
        Returns:
            Tuple of (is_valid, reason, confidence_multiplier)
            - is_valid: True if volume is acceptable for trading
            - reason: Explanation string
            - confidence_multiplier: 0.8-1.2 based on volume strength
        """
        if len(self.volume_history) < 5:
            return True, "Insufficient volume data - proceeding", 1.0
        
        current_volume = self.volume_history[-1] if self.volume_history else 0.0
        avg_volume = safe_divide(sum(self.volume_history), len(self.volume_history), 0.0)
        
        if avg_volume <= 0:
            return True, "No average volume - proceeding", 1.0
        
        volume_ratio = safe_divide(current_volume, avg_volume, 1.0)
        
        if volume_ratio > 1.5:
            reason = f"🔥 Volume VERY STRONG: ratio={volume_ratio:.2f}x (current={current_volume:.6f}, avg={avg_volume:.6f})"
            logger.debug(reason)
            return True, reason, 1.2
        elif volume_ratio > 1.2:
            reason = f"✅ Volume STRONG: ratio={volume_ratio:.2f}x"
            logger.debug(reason)
            return True, reason, 1.15
        elif volume_ratio > 0.8:
            reason = f"✅ Volume NORMAL: ratio={volume_ratio:.2f}x"
            logger.debug(reason)
            return True, reason, 1.0
        elif volume_ratio > 0.7:
            reason = f"⚠️ Volume WEAK: ratio={volume_ratio:.2f}x"
            logger.debug(reason)
            return True, reason, 0.9
        else:
            reason = f"❌ Volume TOO WEAK: ratio={volume_ratio:.2f}x < 0.7 (BLOCKED)"
            logger.debug(reason)
            return False, reason, 0.0
    
    def check_price_action(self, signal_type: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Price Action Confirmation with Wick Validation.
        
        Detects basic candlestick patterns from tick data:
        - Long upper wick: potential bearish reversal
        - Long lower wick: potential bullish reversal
        
        Args:
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_valid, reason, pattern_info)
            - is_valid: True if price action supports signal
            - reason: Explanation string
            - pattern_info: Dict with pattern details
        """
        pattern_info = {
            'pattern': 'none',
            'upper_wick_ratio': 0.0,
            'lower_wick_ratio': 0.0,
            'body_size': 0.0,
            'warning': None
        }
        
        if len(self.tick_history) < 10 or len(self.high_history) < 10 or len(self.low_history) < 10:
            return True, "Insufficient data for price action analysis", pattern_info
        
        recent_ticks = 5
        open_price = safe_float(self.tick_history[-recent_ticks])
        close_price = safe_float(self.tick_history[-1])
        high_price = max(safe_float(h) for h in self.high_history[-recent_ticks:])
        low_price = min(safe_float(l) for l in self.low_history[-recent_ticks:])
        
        body_size = abs(close_price - open_price)
        total_range = high_price - low_price
        
        if total_range <= 0:
            return True, "No price range detected", pattern_info
        
        pattern_info['body_size'] = body_size
        
        if close_price >= open_price:
            upper_wick = high_price - close_price
            lower_wick = open_price - low_price
        else:
            upper_wick = high_price - open_price
            lower_wick = close_price - low_price
        
        upper_wick_ratio = safe_divide(upper_wick, total_range, 0.0)
        lower_wick_ratio = safe_divide(lower_wick, total_range, 0.0)
        
        pattern_info['upper_wick_ratio'] = round(upper_wick_ratio, 3)
        pattern_info['lower_wick_ratio'] = round(lower_wick_ratio, 3)
        
        long_wick_threshold = 0.4
        has_long_upper_wick = upper_wick_ratio > long_wick_threshold
        has_long_lower_wick = lower_wick_ratio > long_wick_threshold
        
        if has_long_upper_wick and has_long_lower_wick:
            pattern_info['pattern'] = 'doji'
        elif has_long_upper_wick:
            pattern_info['pattern'] = 'long_upper_wick'
        elif has_long_lower_wick:
            pattern_info['pattern'] = 'long_lower_wick'
        else:
            pattern_info['pattern'] = 'normal'
        
        if signal_type == "BUY":
            if has_long_upper_wick and not has_long_lower_wick:
                pattern_info['warning'] = 'Long upper wick detected - potential reversal'
                reason = f"⚠️ BUY warning: {pattern_info['pattern']} (upper_wick={upper_wick_ratio:.1%})"
                logger.debug(reason)
                return False, reason, pattern_info
            elif has_long_lower_wick:
                reason = f"✅ BUY supported: long lower wick suggests buying pressure"
                pattern_info['pattern'] = 'hammer'
                return True, reason, pattern_info
            else:
                return True, f"✅ Price action neutral for BUY", pattern_info
                
        elif signal_type == "SELL":
            if has_long_lower_wick and not has_long_upper_wick:
                pattern_info['warning'] = 'Long lower wick detected - potential reversal'
                reason = f"⚠️ SELL warning: {pattern_info['pattern']} (lower_wick={lower_wick_ratio:.1%})"
                logger.debug(reason)
                return False, reason, pattern_info
            elif has_long_upper_wick:
                reason = f"✅ SELL supported: long upper wick suggests selling pressure"
                pattern_info['pattern'] = 'shooting_star'
                return True, reason, pattern_info
            else:
                return True, f"✅ Price action neutral for SELL", pattern_info
        
        return True, "Price action check passed", pattern_info
    
    def should_generate_signal(self, signal_type: str) -> Tuple[bool, str]:
        """Signal Cooldown System to prevent overtrading.
        
        Checks if enough time has passed since the last signal of the same type.
        
        Args:
            signal_type: "BUY" or "SELL"
            
        Returns:
            Tuple of (can_generate, reason)
            - can_generate: True if cooldown has passed
            - reason: Explanation string
        """
        current_time = datetime.now()
        
        if signal_type == "BUY":
            last_time = self.last_buy_time
            direction = "BUY"
        elif signal_type == "SELL":
            last_time = self.last_sell_time
            direction = "SELL"
        else:
            return True, "Invalid signal type"
        
        if last_time is None:
            return True, f"No previous {direction} signal - ready"
        
        time_diff = (current_time - last_time).total_seconds()
        
        if time_diff < self.COOLDOWN_SECONDS:
            remaining = self.COOLDOWN_SECONDS - time_diff
            reason = f"⏳ Cooldown active for {direction}: {remaining:.1f}s remaining (last signal {time_diff:.1f}s ago)"
            logger.debug(reason)
            return False, reason
        
        return True, f"✅ Cooldown passed for {direction}: {time_diff:.1f}s since last signal"
    
    def update_signal_time(self, signal_type: str) -> None:
        """Update the last signal time after a signal is generated.
        
        Args:
            signal_type: "BUY" or "SELL"
        """
        current_time = datetime.now()
        self.last_signal_time = current_time
        
        if signal_type == "BUY":
            self.last_buy_time = current_time
        elif signal_type == "SELL":
            self.last_sell_time = current_time
    
    def get_confluence_score(self, signal_type: str, 
                              indicators: IndicatorValues,
                              m5_indicators: Optional[Dict[str, float]] = None
                              ) -> Tuple[float, str, Dict[str, Any]]:
        """Confluence Scoring combining all filter results.
        
        Aggregates scores from:
        - ADX filter (0-20 points)
        - EMA slope (0-15 points)
        - Volume filter (0-15 points)
        - Price action (0-15 points)
        - MTF confirmation (0-20 points)
        - RSI momentum (0-15 points)
        
        Args:
            signal_type: "BUY" or "SELL"
            indicators: Current IndicatorValues
            m5_indicators: Optional M5 timeframe indicators
            
        Returns:
            Tuple of (total_score, confidence_level, details)
            - total_score: 0-100 score
            - confidence_level: "STRONG" (>=70), "MEDIUM" (>=50), "WEAK" (<50)
            - details: Dict with individual filter scores
        """
        details = {
            'adx_score': 0,
            'ema_slope_score': 0,
            'volume_score': 0,
            'price_action_score': 0,
            'mtf_score': 0,
            'rsi_momentum_score': 0,
            'filters_passed': [],
            'filters_failed': [],
            'warnings': []
        }
        
        total_score = 0.0
        
        adx_valid, adx_reason, adx_multiplier = self.check_adx_filter(
            indicators.adx, indicators.plus_di, indicators.minus_di, signal_type
        )
        if adx_valid:
            if adx_multiplier >= 1.0:
                details['adx_score'] = 20
            elif adx_multiplier >= 0.85:
                details['adx_score'] = 15
            else:
                details['adx_score'] = 10
            details['filters_passed'].append('ADX')
        else:
            details['adx_score'] = 0
            details['filters_failed'].append('ADX')
        total_score += details['adx_score']
        
        slope_valid, slope_reason, slope_data = self.check_ema_slope(signal_type)
        if slope_valid:
            if slope_data.get('strength') == 'strong':
                details['ema_slope_score'] = 15
            elif slope_data.get('strength') == 'moderate':
                details['ema_slope_score'] = 12
            else:
                details['ema_slope_score'] = 8
            details['filters_passed'].append('EMA_SLOPE')
        else:
            details['ema_slope_score'] = 0
            details['filters_failed'].append('EMA_SLOPE')
            details['warnings'].append(slope_reason)
        total_score += details['ema_slope_score']
        
        vol_valid, vol_reason, vol_multiplier = self.check_volume_filter()
        if vol_valid:
            if vol_multiplier >= 1.15:
                details['volume_score'] = 15
            elif vol_multiplier >= 1.0:
                details['volume_score'] = 12
            else:
                details['volume_score'] = 8
            details['filters_passed'].append('VOLUME')
        else:
            details['volume_score'] = 5
            details['warnings'].append(vol_reason)
        total_score += details['volume_score']
        
        pa_valid, pa_reason, pa_info = self.check_price_action(signal_type)
        if pa_valid:
            if pa_info.get('pattern') in ['hammer', 'shooting_star']:
                details['price_action_score'] = 15
            else:
                details['price_action_score'] = 10
            details['filters_passed'].append('PRICE_ACTION')
        else:
            details['price_action_score'] = 0
            details['filters_failed'].append('PRICE_ACTION')
            details['warnings'].append(pa_reason)
        total_score += details['price_action_score']
        
        mtf_aligned, mtf_reason, mtf_multiplier = self.check_mtf_trend_confirmation(
            signal_type, m5_indicators
        )
        if mtf_aligned:
            if mtf_multiplier >= 1.1:
                details['mtf_score'] = 20
            else:
                details['mtf_score'] = 15
            details['filters_passed'].append('MTF')
        else:
            details['mtf_score'] = 5
            details['filters_failed'].append('MTF')
            details['warnings'].append(mtf_reason)
        total_score += details['mtf_score']
        
        rsi_momentum, momentum_bonus = self.check_rsi_momentum(indicators.rsi, signal_type)
        if momentum_bonus > 0:
            details['rsi_momentum_score'] = int(momentum_bonus * 150)
            details['filters_passed'].append('RSI_MOMENTUM')
        else:
            details['rsi_momentum_score'] = 5
        total_score += details['rsi_momentum_score']
        
        total_score = min(total_score, 100)
        
        if total_score >= 70:
            confidence_level = "STRONG"
        elif total_score >= 50:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "WEAK"
        
        logger.info(
            f"📊 Confluence Score for {signal_type}: {total_score:.0f}/100 ({confidence_level}) | "
            f"Passed: {details['filters_passed']} | Failed: {details['filters_failed']}"
        )
        
        return total_score, confidence_level, details
        
    def calculate_all_indicators(self) -> IndicatorValues:
        """
        Calculate semua indikator sekaligus.
        
        Enhancement v2.4:
        - Uses incremental EMA calculation for O(1) per tick complexity
        - Caches EMA values to avoid O(n²) recalculation
        """
        indicators = IndicatorValues()
        
        if len(self.tick_history) < self.RSI_PERIOD:
            return indicators
            
        indicators.rsi = self.calculate_rsi(self.tick_history, self.RSI_PERIOD)
        
        if len(self.tick_history) >= self.EMA_SLOW_PERIOD:
            indicators.ema_fast = self.calculate_ema_incremental(self.EMA_FAST_PERIOD, "fast")
            indicators.ema_slow = self.calculate_ema_incremental(self.EMA_SLOW_PERIOD, "slow")
            
        if len(self.tick_history) >= self.MACD_SLOW + self.MACD_SIGNAL:
            macd_line, macd_signal, macd_hist = self.calculate_macd_incremental()
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
        
        if len(self.tick_history) >= self.ADX_PERIOD + 1:
            adx, plus_di, minus_di = self.calculate_adx(
                self.tick_history, self.high_history, self.low_history, self.ADX_PERIOD
            )
            indicators.adx = adx
            indicators.plus_di = plus_di
            indicators.minus_di = minus_di
            
        trend_dir, trend_strength = self.detect_trend(self.TREND_TICKS)
        indicators.trend_direction = trend_dir
        indicators.trend_strength = trend_strength
        
        self._last_tick_count_for_ema = len(self.tick_history)
        
        self.last_indicators = indicators
        return indicators
        
    def analyze(self) -> AnalysisResult:
        """
        Analisis utama dengan multi-indicator confirmation.
        
        Enhanced Signal Requirements:
        BUY (CALL): RSI in 25-30 AND EMA9 > EMA21 AND MACD histogram > 0 AND Stoch < 20 AND ADX >= 20
        SELL (PUT): RSI in 70-75 AND EMA9 < EMA21 AND MACD histogram < 0 AND Stoch > 80 AND ADX >= 20
        
        Enhanced Scoring:
        - RSI oversold/overbought: +0.35
        - RSI entry range valid: +0.05 bonus
        - EMA alignment: +0.20
        - MACD confirmation: +0.15
        - Stochastic confirmation: +0.10
        - Trend direction: +0.05
        - ADX trend strength (> 20): +0.15
        - RSI momentum: +0.10
        - EMA price alignment: +0.05
        - Volatility zone adjustment
        """
        result = AnalysisResult(
            signal=Signal.WAIT,
            rsi_value=50.0,
            trend_direction="SIDEWAYS",
            confidence=0.0,
            reason="Data tidak cukup untuk analisis"
        )
        
        min_required = max(self.RSI_PERIOD + 1, self.EMA_SLOW_PERIOD, self.ADX_PERIOD + 1)
        if len(self.tick_history) < min_required:
            logger.info(f"⏳ Collecting data: {len(self.tick_history)}/{min_required} ticks")
            return result
            
        indicators = self.calculate_all_indicators()
        result.indicators = indicators
        result.rsi_value = indicators.rsi
        result.trend_direction = indicators.trend_direction
        result.adx_value = indicators.adx
        
        vol_zone, vol_multiplier = self.get_volatility_zone()
        result.volatility_zone = vol_zone
        result.volatility_multiplier = vol_multiplier
        
        if self.BLOCK_EXTREME_VOLATILITY and vol_zone == "EXTREME_HIGH":
            result.signal = Signal.WAIT
            result.confidence = 0.0
            result.reason = f"🚫 HARD BLOCK: EXTREME_HIGH volatility zone detected - too risky for entry"
            logger.warning(f"🚫 Signal blocked: EXTREME_HIGH volatility zone")
            return result
        
        if indicators.atr > 0:
            result.tp_distance = indicators.atr * self.ATR_TP_MULTIPLIER
            result.sl_distance = indicators.atr * self.ATR_SL_MULTIPLIER
        
        buy_score = 0.0
        sell_score = 0.0
        buy_reasons = []
        sell_reasons = []
        
        if indicators.rsi < self.RSI_OVERSOLD:
            buy_score += 0.35
            buy_reasons.append(f"RSI Oversold ({indicators.rsi:.1f})")
            
            rsi_valid, rsi_reason = self.check_rsi_entry_range(indicators.rsi, "BUY")
            if rsi_valid:
                buy_score += 0.05
                buy_reasons.append(rsi_reason)
        elif indicators.rsi > self.RSI_OVERBOUGHT:
            sell_score += 0.35
            sell_reasons.append(f"RSI Overbought ({indicators.rsi:.1f})")
            
            rsi_valid, rsi_reason = self.check_rsi_entry_range(indicators.rsi, "SELL")
            if rsi_valid:
                sell_score += 0.05
                sell_reasons.append(rsi_reason)
        elif self.RSI_BUY_ENTRY_MIN <= indicators.rsi <= self.RSI_BUY_ENTRY_MAX:
            buy_score += 0.25
            buy_reasons.append(f"RSI in BUY zone ({indicators.rsi:.1f})")
        elif self.RSI_SELL_ENTRY_MIN <= indicators.rsi <= self.RSI_SELL_ENTRY_MAX:
            sell_score += 0.25
            sell_reasons.append(f"RSI in SELL zone ({indicators.rsi:.1f})")
            
        if indicators.ema_fast > 0 and indicators.ema_slow > 0:
            current_price = safe_float(self.tick_history[-1])
            
            if indicators.ema_fast > indicators.ema_slow:
                buy_score += 0.20
                buy_reasons.append("EMA9 > EMA21 (Bullish)")
                
                if current_price > indicators.ema_fast and current_price > indicators.ema_slow:
                    buy_score += 0.05
                    buy_reasons.append("Price above both EMAs")
            elif indicators.ema_fast < indicators.ema_slow:
                sell_score += 0.20
                sell_reasons.append("EMA9 < EMA21 (Bearish)")
                
                if current_price < indicators.ema_fast and current_price < indicators.ema_slow:
                    sell_score += 0.05
                    sell_reasons.append("Price below both EMAs")
                
        if indicators.macd_histogram != 0:
            if indicators.macd_histogram > 0:
                buy_score += 0.15
                buy_reasons.append("MACD Positive")
            else:
                sell_score += 0.15
                sell_reasons.append("MACD Negative")
                
        if indicators.stoch_k < self.STOCH_OVERSOLD:
            buy_score += 0.10
            buy_reasons.append(f"Stoch Oversold ({indicators.stoch_k:.1f})")
        elif indicators.stoch_k > self.STOCH_OVERBOUGHT:
            sell_score += 0.10
            sell_reasons.append(f"Stoch Overbought ({indicators.stoch_k:.1f})")
            
        if indicators.trend_direction == "UP":
            buy_score += 0.05
            buy_reasons.append("Trend Up")
        elif indicators.trend_direction == "DOWN":
            sell_score += 0.05
            sell_reasons.append("Trend Down")
        
        if indicators.adx >= self.ADX_STRONG_TREND:
            if buy_score > sell_score:
                buy_score += 0.15
                buy_reasons.append(f"ADX Strong ({indicators.adx:.1f})")
            elif sell_score > buy_score:
                sell_score += 0.15
                sell_reasons.append(f"ADX Strong ({indicators.adx:.1f})")
        
        if buy_score > sell_score:
            rsi_momentum, momentum_bonus = self.check_rsi_momentum(indicators.rsi, "BUY")
            if momentum_bonus > 0:
                buy_score += momentum_bonus
                buy_reasons.append(f"RSI Momentum +{momentum_bonus:.2f}")
        elif sell_score > buy_score:
            rsi_momentum, momentum_bonus = self.check_rsi_momentum(indicators.rsi, "SELL")
            if momentum_bonus > 0:
                sell_score += momentum_bonus
                sell_reasons.append(f"RSI Momentum +{momentum_bonus:.2f}")
        
        adx_tp_multiplier = 1.0
        
        # Regime detection for smarter entries
        is_trending = indicators.adx >= self.ADX_STRONG_TREND
        is_ranging = indicators.adx < self.ADX_NO_TREND
        
        if buy_score >= self.MIN_CONFIDENCE_THRESHOLD and buy_score > sell_score:
            cooldown_ok, cooldown_reason = self.should_generate_signal("BUY")
            if not cooldown_ok:
                result.signal = Signal.WAIT
                result.confidence = 0.0
                result.reason = cooldown_reason
                logger.debug(f"⏳ BUY blocked by cooldown: {cooldown_reason}")
                return result
            
            adx_valid, adx_reason, adx_tp_multiplier = self.check_adx_filter(
                indicators.adx, indicators.plus_di, indicators.minus_di, "BUY"
            )
            
            if not adx_valid and indicators.adx >= self.ADX_NO_TREND:
                buy_reasons.append(adx_reason)
            elif adx_valid:
                buy_reasons.append(adx_reason)
            
            confluence_score, confidence_level, confluence_details = self.get_confluence_score(
                "BUY", indicators
            )
            
            if confluence_score < self.MIN_CONFLUENCE_SCORE and confidence_level == "WEAK":
                result.signal = Signal.WAIT
                result.confidence = 0.0
                result.reason = f"Confluence too weak ({confluence_score:.0f}/100) | Failed: {confluence_details.get('filters_failed', [])}"
                logger.debug(f"⏳ BUY blocked by weak confluence: {confluence_score:.0f}/100")
                return result
            
            confluence_multiplier = 1.0
            if confidence_level == "STRONG":
                confluence_multiplier = 1.15
            elif confidence_level == "MEDIUM":
                confluence_multiplier = 1.0
            else:
                confluence_multiplier = 0.85
            
            if adx_valid or indicators.adx == 0:
                self.update_signal_time("BUY")
                
                result.signal = Signal.BUY
                final_confidence = min(buy_score * vol_multiplier * adx_tp_multiplier * confluence_multiplier, 1.0)
                result.confidence = final_confidence
                result.reason = " | ".join(buy_reasons)
                
                result.reason += f" | Confluence: {confluence_score:.0f}/100 ({confidence_level})"
                
                if vol_multiplier < 1.0:
                    result.reason += f" | Vol Zone: {vol_zone} ({vol_multiplier:.0%})"
                
                logger.info(f"🟢 BUY Signal: score={buy_score:.2f}, confluence={confluence_score:.0f}/100, final_conf={final_confidence:.2f}, ADX={indicators.adx:.1f}")
                return result
                
        if sell_score >= self.MIN_CONFIDENCE_THRESHOLD and sell_score > buy_score:
            cooldown_ok, cooldown_reason = self.should_generate_signal("SELL")
            if not cooldown_ok:
                result.signal = Signal.WAIT
                result.confidence = 0.0
                result.reason = cooldown_reason
                logger.debug(f"⏳ SELL blocked by cooldown: {cooldown_reason}")
                return result
            
            adx_valid, adx_reason, adx_tp_multiplier = self.check_adx_filter(
                indicators.adx, indicators.plus_di, indicators.minus_di, "SELL"
            )
            
            if not adx_valid and indicators.adx >= self.ADX_NO_TREND:
                sell_reasons.append(adx_reason)
            elif adx_valid:
                sell_reasons.append(adx_reason)
            
            confluence_score, confidence_level, confluence_details = self.get_confluence_score(
                "SELL", indicators
            )
            
            if confluence_score < self.MIN_CONFLUENCE_SCORE and confidence_level == "WEAK":
                result.signal = Signal.WAIT
                result.confidence = 0.0
                result.reason = f"Confluence too weak ({confluence_score:.0f}/100) | Failed: {confluence_details.get('filters_failed', [])}"
                logger.debug(f"⏳ SELL blocked by weak confluence: {confluence_score:.0f}/100")
                return result
            
            confluence_multiplier = 1.0
            if confidence_level == "STRONG":
                confluence_multiplier = 1.15
            elif confidence_level == "MEDIUM":
                confluence_multiplier = 1.0
            else:
                confluence_multiplier = 0.85
            
            if adx_valid or indicators.adx == 0:
                self.update_signal_time("SELL")
                
                result.signal = Signal.SELL
                final_confidence = min(sell_score * vol_multiplier * adx_tp_multiplier * confluence_multiplier, 1.0)
                result.confidence = final_confidence
                result.reason = " | ".join(sell_reasons)
                
                result.reason += f" | Confluence: {confluence_score:.0f}/100 ({confidence_level})"
                
                if vol_multiplier < 1.0:
                    result.reason += f" | Vol Zone: {vol_zone} ({vol_multiplier:.0%})"
                
                logger.info(f"🔴 SELL Signal: score={sell_score:.2f}, confluence={confluence_score:.0f}/100, final_conf={final_confidence:.2f}, ADX={indicators.adx:.1f}")
                return result
                
        result.signal = Signal.WAIT
        result.confidence = 0.0
        ema_trend = self.check_ema_trend()
        result.reason = f"RSI={indicators.rsi:.1f} | ADX={indicators.adx:.1f} | EMA Trend={ema_trend} | Waiting for clear signal"
        
        # Log more details at INFO level for debugging signal generation
        logger.info(f"⏳ WAIT: buy={buy_score:.2f} sell={sell_score:.2f} need={self.MIN_CONFIDENCE_THRESHOLD} | RSI={indicators.rsi:.1f} ADX={indicators.adx:.1f}")
        
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
                "atr": 0,
                "adx": 0,
                "plus_di": 0,
                "minus_di": 0,
                "volatility_zone": "UNKNOWN",
                "volatility_multiplier": 1.0
            }
            
        indicators = self.last_indicators
        vol_zone, vol_mult = self.get_volatility_zone()
        
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
            "atr": indicators.atr,
            "adx": indicators.adx,
            "plus_di": indicators.plus_di,
            "minus_di": indicators.minus_di,
            "volatility_zone": vol_zone,
            "volatility_multiplier": vol_mult
        }
        
    def get_indicator_summary(self) -> str:
        """
        Get formatted summary of all indicators for display.
        """
        ind = self.last_indicators
        vol_zone, vol_mult = self.get_volatility_zone()
        
        rsi_status = "🟢 Oversold" if ind.rsi < 30 else "🔴 Overbought" if ind.rsi > 70 else "⚪ Neutral"
        ema_status = "🟢 Bullish" if ind.ema_fast > ind.ema_slow else "🔴 Bearish" if ind.ema_fast < ind.ema_slow else "⚪ Neutral"
        macd_status = "🟢 Positive" if ind.macd_histogram > 0 else "🔴 Negative"
        stoch_status = "🟢 Oversold" if ind.stoch_k < 20 else "🔴 Overbought" if ind.stoch_k > 80 else "⚪ Neutral"
        
        adx_status = "🟢 Strong" if ind.adx >= 25 else "🟡 Moderate" if ind.adx >= 15 else "🔴 Weak/Sideways"
        di_status = "📈 Bullish" if ind.plus_di > ind.minus_di else "📉 Bearish" if ind.minus_di > ind.plus_di else "↔️ Neutral"
        
        vol_emoji = "⚡" if vol_zone in ["HIGH", "EXTREME_HIGH"] else "🐌" if vol_zone in ["LOW", "EXTREME_LOW"] else "✅"
        
        return (
            f"📊 **INDICATORS**\n\n"
            f"• RSI(14): {ind.rsi:.1f} {rsi_status}\n"
            f"• EMA(9/21): {ind.ema_fast:.2f}/{ind.ema_slow:.2f} {ema_status}\n"
            f"• MACD Hist: {ind.macd_histogram:.6f} {macd_status}\n"
            f"• Stoch(14): {ind.stoch_k:.1f} {stoch_status}\n"
            f"• ATR(14): {ind.atr:.6f}\n"
            f"• ADX(14): {ind.adx:.1f} {adx_status}\n"
            f"• +DI/-DI: {ind.plus_di:.1f}/{ind.minus_di:.1f} {di_status}\n"
            f"• Volatility: {vol_zone} ({vol_mult:.0%}) {vol_emoji}\n"
            f"• Trend: {ind.trend_direction}"
        )
