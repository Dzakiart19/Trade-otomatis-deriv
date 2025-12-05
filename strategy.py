"""
=============================================================
MODUL STRATEGI TRADING - RSI & TREND ANALYSIS
=============================================================
Modul ini berisi logika analisis teknikal untuk menentukan
kapan harus BUY (Call), SELL (Put), atau WAIT.

Strategi yang digunakan:
1. RSI (Relative Strength Index) periode 14
2. Tick Trend Follower (3 tick berturut-turut)
3. Filter Volatilitas (hindari market sideways)
=============================================================
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Setup logging untuk console (tidak spam Telegram)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Signal(Enum):
    """Enum untuk sinyal trading"""
    BUY = "CALL"      # RSI < 30 (Oversold) atau trend naik
    SELL = "PUT"      # RSI > 70 (Overbought) atau trend turun
    WAIT = "WAIT"     # RSI 30-70 atau tidak ada sinyal jelas


@dataclass
class AnalysisResult:
    """Hasil analisis strategi"""
    signal: Signal
    rsi_value: float
    trend_direction: str  # "UP", "DOWN", "SIDEWAYS"
    confidence: float     # 0.0 - 1.0
    reason: str           # Penjelasan mengapa sinyal dihasilkan


class TradingStrategy:
    """
    Kelas utama untuk strategi trading.
    Menggabungkan RSI dan Tick Trend Analysis.
    """
    
    # Konstanta RSI
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30     # Batas bawah (BUY signal)
    RSI_OVERBOUGHT = 70   # Batas atas (SELL signal)
    
    # Konstanta Trend
    TREND_TICKS = 3       # Jumlah tick untuk konfirmasi trend
    MIN_TICK_HISTORY = 20 # Minimum tick yang disimpan
    
    # Filter Volatilitas (dalam pips/points)
    MIN_VOLATILITY = 0.05  # Minimum pergerakan harga untuk dianggap signifikan
    
    def __init__(self):
        """Inisialisasi strategy dengan tick history kosong"""
        self.tick_history: List[float] = []
        self.last_rsi: float = 50.0  # Default RSI netral
        
    def add_tick(self, price: float) -> None:
        """
        Tambahkan tick baru ke history.
        Otomatis buang tick lama jika melebihi batas.
        
        Args:
            price: Harga tick terbaru
        """
        self.tick_history.append(price)
        
        # Jaga agar history tidak terlalu besar (max 50 ticks)
        if len(self.tick_history) > 50:
            self.tick_history = self.tick_history[-50:]
            
    def clear_history(self) -> None:
        """Reset tick history"""
        self.tick_history.clear()
        self.last_rsi = 50.0
        
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Hitung RSI secara manual tanpa library eksternal.
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss (periode tertentu)
        
        Args:
            prices: List harga (minimal period + 1 data)
            period: Periode RSI (default 14)
            
        Returns:
            Nilai RSI (0-100)
        """
        if len(prices) < period + 1:
            # Data tidak cukup, return RSI netral
            return 50.0
            
        # Hitung perubahan harga (price changes)
        changes = []
        for i in range(1, len(prices)):
            changes.append(prices[i] - prices[i-1])
            
        # Ambil perubahan terakhir sesuai periode
        recent_changes = changes[-(period):]
        
        # Pisahkan gain dan loss
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]
        
        # Hitung rata-rata gain dan loss
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        # Hindari division by zero
        if avg_loss == 0:
            return 100.0  # Semua gain, RSI maksimal
            
        # Hitung RS dan RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def detect_trend(self, ticks: int = 3) -> Tuple[str, int]:
        """
        Deteksi arah trend berdasarkan tick terakhir.
        
        Args:
            ticks: Jumlah tick untuk analisis (default 3)
            
        Returns:
            Tuple (arah_trend, consecutive_count)
            - "UP": Harga naik berturut-turut
            - "DOWN": Harga turun berturut-turut
            - "SIDEWAYS": Tidak ada arah jelas
        """
        if len(self.tick_history) < ticks + 1:
            return ("SIDEWAYS", 0)
            
        # Ambil tick terakhir
        recent = self.tick_history[-(ticks + 1):]
        
        # Hitung consecutive up/down
        up_count = 0
        down_count = 0
        
        for i in range(1, len(recent)):
            if recent[i] > recent[i-1]:
                up_count += 1
            elif recent[i] < recent[i-1]:
                down_count += 1
                
        # Tentukan arah trend
        if up_count >= ticks:
            return ("UP", up_count)
        elif down_count >= ticks:
            return ("DOWN", down_count)
        else:
            return ("SIDEWAYS", 0)
            
    def check_volatility(self) -> bool:
        """
        Cek apakah market cukup volatile untuk trading.
        Menghindari market sideways/flat.
        
        Returns:
            True jika volatilitas cukup, False jika terlalu flat
        """
        if len(self.tick_history) < 5:
            return False
            
        # Ambil 5 tick terakhir
        recent = self.tick_history[-5:]
        
        # Hitung range (high - low)
        price_range = max(recent) - min(recent)
        
        # Hitung rata-rata harga untuk persentase
        avg_price = sum(recent) / len(recent)
        
        # Volatilitas dalam persentase
        if avg_price > 0:
            volatility_pct = (price_range / avg_price) * 100
        else:
            volatility_pct = 0
            
        # Return True jika volatilitas > threshold
        return volatility_pct >= self.MIN_VOLATILITY
        
    def analyze(self) -> AnalysisResult:
        """
        Analisis utama yang menggabungkan semua strategi.
        
        Logika:
        1. Hitung RSI dari tick history
        2. Deteksi trend dari tick terakhir
        3. Cek volatilitas market
        4. Generate signal berdasarkan kombinasi faktor
        
        Returns:
            AnalysisResult dengan signal dan detail analisis
        """
        # Default result (WAIT)
        result = AnalysisResult(
            signal=Signal.WAIT,
            rsi_value=50.0,
            trend_direction="SIDEWAYS",
            confidence=0.0,
            reason="Data tidak cukup untuk analisis"
        )
        
        # Cek minimum data
        if len(self.tick_history) < self.RSI_PERIOD + 1:
            logger.info(f"⏳ Analyzing market... (Collecting data: {len(self.tick_history)}/{self.RSI_PERIOD + 1})")
            return result
            
        # Hitung RSI
        rsi = self.calculate_rsi(self.tick_history, self.RSI_PERIOD)
        self.last_rsi = rsi
        
        # Deteksi trend
        trend_direction, trend_strength = self.detect_trend(self.TREND_TICKS)
        
        # Cek volatilitas
        is_volatile = self.check_volatility()
        
        # Update result dengan data analisis
        result.rsi_value = rsi
        result.trend_direction = trend_direction
        
        # Logika penentuan signal
        confidence = 0.0
        reason_parts = []
        
        # === KONDISI BUY (CALL) ===
        if rsi < self.RSI_OVERSOLD:
            # RSI Oversold - sinyal kuat untuk BUY
            confidence += 0.6
            reason_parts.append(f"RSI Oversold ({rsi})")
            
            if trend_direction == "UP":
                # Konfirmasi trend naik
                confidence += 0.3
                reason_parts.append("Trend konfirmasi naik")
                
            if is_volatile:
                confidence += 0.1
                reason_parts.append("Volatilitas cukup")
                
            if confidence >= 0.5:
                result.signal = Signal.BUY
                result.confidence = min(confidence, 1.0)
                result.reason = " | ".join(reason_parts)
                return result
                
        # === KONDISI SELL (PUT) ===
        elif rsi > self.RSI_OVERBOUGHT:
            # RSI Overbought - sinyal kuat untuk SELL
            confidence += 0.6
            reason_parts.append(f"RSI Overbought ({rsi})")
            
            if trend_direction == "DOWN":
                # Konfirmasi trend turun
                confidence += 0.3
                reason_parts.append("Trend konfirmasi turun")
                
            if is_volatile:
                confidence += 0.1
                reason_parts.append("Volatilitas cukup")
                
            if confidence >= 0.5:
                result.signal = Signal.SELL
                result.confidence = min(confidence, 1.0)
                result.reason = " | ".join(reason_parts)
                return result
                
        # === KONDISI WAIT ===
        # RSI di zona netral (30-70)
        result.signal = Signal.WAIT
        result.confidence = 0.0
        result.reason = f"RSI netral ({rsi}) - Menunggu sinyal yang lebih jelas"
        
        # Log ke console saja (tidak spam Telegram)
        logger.info(f"⏳ Analyzing market... RSI: {rsi} | Trend: {trend_direction}")
        
        return result
        
    def get_current_price(self) -> Optional[float]:
        """Dapatkan harga tick terakhir"""
        if self.tick_history:
            return self.tick_history[-1]
        return None
        
    def get_stats(self) -> dict:
        """
        Dapatkan statistik analisis saat ini.
        Berguna untuk debugging dan display.
        """
        if not self.tick_history:
            return {
                "tick_count": 0,
                "rsi": 50.0,
                "trend": "N/A",
                "current_price": 0,
                "high": 0,
                "low": 0
            }
            
        return {
            "tick_count": len(self.tick_history),
            "rsi": self.last_rsi,
            "trend": self.detect_trend()[0],
            "current_price": self.tick_history[-1],
            "high": max(self.tick_history[-20:]) if len(self.tick_history) >= 20 else max(self.tick_history),
            "low": min(self.tick_history[-20:]) if len(self.tick_history) >= 20 else min(self.tick_history)
        }
