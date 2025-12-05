"""
=============================================================
MULTI-PAIR SCANNER & RECOMMENDATION MODULE
=============================================================
Modul ini menyediakan fitur scanning untuk multiple trading pairs
secara bersamaan dan memberikan rekomendasi pair terbaik berdasarkan
kekuatan signal dan berbagai faktor teknikal.

Fitur:
- Scan semua synthetic indices yang mendukung ticks secara paralel
- Per-symbol strategy instances untuk analisis independen
- Scoring system berbasis multi-factor (signal, confidence, confluence, ADX, volatility)
- Thread-safe operations dengan proper locking
- Real-time recommendations untuk pair dengan signal terkuat

Penggunaan:
    from pair_scanner import PairScanner
    from deriv_ws import DerivWebSocket
    
    ws = DerivWebSocket(demo_token, real_token)
    scanner = PairScanner(ws)
    scanner.start_scanning()
    
    # Dapatkan status semua pairs
    status = scanner.get_all_pair_status()
    
    # Dapatkan top 3 rekomendasi
    recommendations = scanner.get_recommendations(top_n=3)
    
    scanner.stop_scanning()
=============================================================
"""

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import logging
import threading
import time
import re

from strategy import TradingStrategy, Signal, AnalysisResult
from symbols import SUPPORTED_SYMBOLS, get_short_term_symbols, SymbolConfig
from deriv_ws import DerivWebSocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PairScanner:
    """
    Scanner untuk menganalisis multiple trading pairs secara bersamaan
    dan memberikan rekomendasi pair terbaik berdasarkan signal strength.
    
    Scanner ini melakukan:
    1. Subscribe ke tick stream untuk semua short-term synthetic indices
    2. Route tick data ke masing-masing strategy instance
    3. Analisis periodik untuk setiap pair
    4. Scoring dan ranking berdasarkan multiple factors
    5. Rekomendasi pair terbaik untuk trading
    
    Attributes:
        deriv_ws: Reference ke DerivWebSocket instance untuk subscription
        strategies: Dict mapping symbol ke TradingStrategy instance
        symbol_data: Latest analysis data per symbol
        is_scanning: Status apakah scanner sedang aktif
        scan_interval: Interval evaluasi dalam detik (default 15)
        min_ticks_required: Minimum ticks sebelum analisis valid (default 30)
    """
    
    DEFAULT_SCAN_INTERVAL = 15.0
    DEFAULT_MIN_TICKS = 30
    
    MAX_SCORE = 100.0
    BASE_SCORE_SIGNAL = 50.0
    MAX_CONFIDENCE_BONUS = 30.0
    MAX_CONFLUENCE_BONUS = 20.0
    ADX_STRONG_BONUS = 15.0
    ADX_MODERATE_BONUS = 10.0
    ADX_STRONG_THRESHOLD = 25.0
    ADX_MODERATE_THRESHOLD = 20.0
    EXTREME_VOLATILITY_PENALTY = 10.0
    
    def __init__(self, deriv_ws: DerivWebSocket):
        """
        Inisialisasi PairScanner dengan reference ke DerivWebSocket.
        
        Membuat TradingStrategy instance untuk setiap short-term symbol
        yang didukung (synthetic indices dengan supports_ticks=True).
        
        Args:
            deriv_ws: Instance DerivWebSocket yang sudah connected/authorized
        """
        self.deriv_ws = deriv_ws
        
        self.strategies: Dict[str, TradingStrategy] = {}
        self.symbol_configs: Dict[str, SymbolConfig] = {}
        self.symbol_data: Dict[str, dict] = {}
        self.tick_counts: Dict[str, int] = {}
        
        self.is_scanning: bool = False
        self.scan_interval: float = self.DEFAULT_SCAN_INTERVAL
        self.min_ticks_required: int = self.DEFAULT_MIN_TICKS
        
        self._lock = threading.RLock()
        
        self._initialize_strategies()
        
        logger.info(f"🔍 PairScanner initialized with {len(self.strategies)} symbols")
        
    def _initialize_strategies(self) -> None:
        """
        Inisialisasi TradingStrategy untuk setiap short-term symbol.
        
        Hanya symbol dengan supports_ticks=True yang akan di-scan.
        frxXAUUSD dikecualikan karena hanya mendukung durasi harian.
        """
        short_term_symbols = get_short_term_symbols()
        
        for config in short_term_symbols:
            symbol = config.symbol
            
            if symbol == "frxXAUUSD":
                logger.debug(f"Skipping {symbol} - requires daily duration")
                continue
                
            with self._lock:
                self.strategies[symbol] = TradingStrategy()
                self.symbol_configs[symbol] = config
                self.tick_counts[symbol] = 0
                self.symbol_data[symbol] = {
                    "last_analysis": None,
                    "last_score": 0.0,
                    "last_update": None
                }
                
            logger.debug(f"Initialized strategy for {symbol} ({config.name})")
            
        logger.info(f"📊 Strategies initialized for {len(self.strategies)} pairs")
        
    def _on_tick(self, price: float, symbol: str) -> None:
        """
        Callback untuk tick data dari DerivWebSocket.
        
        Route tick ke strategy yang tepat dan update tick count.
        Thread-safe untuk concurrent tick updates.
        
        Args:
            price: Tick price dari Deriv
            symbol: Symbol identifier (e.g., "R_100")
        """
        try:
            with self._lock:
                if symbol not in self.strategies:
                    logger.warning(f"Received tick for unknown symbol: {symbol}")
                    return
                    
                strategy = self.strategies[symbol]
                strategy.add_tick(price)
                
                self.tick_counts[symbol] = self.tick_counts.get(symbol, 0) + 1
                
            logger.debug(f"Tick {symbol}: {price} (count: {self.tick_counts.get(symbol, 0)})")
                
        except Exception as e:
            logger.error(f"Error processing tick for {symbol}: {e}")
            
    def start_scanning(self) -> bool:
        """
        Mulai scanning dengan subscribe ke semua short-term symbols.
        
        Subscribe ke tick stream untuk setiap symbol menggunakan
        deriv_ws.subscribe_ticks() dengan callback _on_tick.
        
        Returns:
            True jika scanning berhasil dimulai, False jika gagal
        """
        if self.is_scanning:
            logger.warning("⚠️ Scanner already running")
            return True
            
        if not self.deriv_ws.is_connected:
            logger.error("❌ Cannot start scanning - WebSocket not connected")
            return False
            
        if not self.deriv_ws.is_authorized:
            logger.error("❌ Cannot start scanning - Not authorized")
            return False
            
        logger.info("🚀 Starting multi-pair scanner...")
        
        success_count = 0
        fail_count = 0
        
        for symbol in self.strategies.keys():
            try:
                success = self.deriv_ws.subscribe_ticks(
                    symbol=symbol,
                    callback=self._on_tick
                )
                
                if success:
                    success_count += 1
                    logger.debug(f"✓ Subscribed to {symbol}")
                else:
                    fail_count += 1
                    logger.warning(f"✗ Failed to subscribe to {symbol}")
                    
                time.sleep(0.1)
                
            except Exception as e:
                fail_count += 1
                logger.error(f"Error subscribing to {symbol}: {e}")
                
        self.is_scanning = True
        
        logger.info(
            f"✅ Scanner started: {success_count} subscribed, "
            f"{fail_count} failed, {len(self.strategies)} total"
        )
        
        return success_count > 0
        
    def stop_scanning(self) -> None:
        """
        Stop scanning dan unsubscribe dari semua symbols.
        
        Unsubscribe dari setiap symbol yang sudah di-subscribe
        dan reset scanning status.
        """
        if not self.is_scanning:
            logger.debug("Scanner not running, nothing to stop")
            return
            
        logger.info("🛑 Stopping multi-pair scanner...")
        
        for symbol in list(self.strategies.keys()):
            try:
                self.deriv_ws.unsubscribe_ticks(symbol)
                logger.debug(f"Unsubscribed from {symbol}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {symbol}: {e}")
                
        self.is_scanning = False
        
        logger.info("✅ Scanner stopped")
        
    def _extract_confluence_score(self, reason: str) -> float:
        """
        Extract confluence_score dari reason string.
        
        Mencari pattern seperti "Confluence: 75/100" atau "confluence_score: 80"
        di dalam reason text.
        
        Args:
            reason: Analysis reason string
            
        Returns:
            Confluence score (0-100) atau 0 jika tidak ditemukan
        """
        if not reason:
            return 0.0
            
        patterns = [
            r'[Cc]onfluence[:\s]+(\d+(?:\.\d+)?)\s*/\s*100',
            r'[Cc]onfluence[:\s]+(\d+(?:\.\d+)?)%',
            r'confluence_score[:\s]+(\d+(?:\.\d+)?)',
            r'[Cc]onfluence\s+[Ss]core[:\s]+(\d+(?:\.\d+)?)',
            r'\((\d+(?:\.\d+)?)/100\s+confluence\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, reason)
            if match:
                try:
                    score = float(match.group(1))
                    return min(max(score, 0.0), 100.0)
                except (ValueError, IndexError):
                    continue
                    
        return 0.0
        
    def _calculate_pair_score(self, symbol: str, analysis: AnalysisResult) -> float:
        """
        Hitung score untuk trading pair berdasarkan multiple factors.
        
        Scoring system:
        - Base score dari signal type: BUY/SELL = 50, WAIT = 0
        - Confidence bonus: confidence * 30 (max 30)
        - Confluence bonus: confluence_score / 100 * 20 (max 20)
        - ADX bonus: >25 = +15, >20 = +10, else +0
        - Volatility penalty: EXTREME zone = -10
        
        Args:
            symbol: Symbol identifier
            analysis: AnalysisResult dari strategy.analyze()
            
        Returns:
            Final score (0-100)
        """
        try:
            if analysis.signal == Signal.WAIT:
                return 0.0
                
            score = self.BASE_SCORE_SIGNAL
            
            confidence = min(max(analysis.confidence, 0.0), 1.0)
            confidence_bonus = confidence * self.MAX_CONFIDENCE_BONUS
            score += confidence_bonus
            
            confluence_score = self._extract_confluence_score(analysis.reason)
            confluence_bonus = (confluence_score / 100.0) * self.MAX_CONFLUENCE_BONUS
            score += confluence_bonus
            
            adx = analysis.adx_value
            if adx > self.ADX_STRONG_THRESHOLD:
                score += self.ADX_STRONG_BONUS
            elif adx > self.ADX_MODERATE_THRESHOLD:
                score += self.ADX_MODERATE_BONUS
                
            if analysis.volatility_zone == "EXTREME":
                score -= self.EXTREME_VOLATILITY_PENALTY
                
            final_score = max(0.0, min(score, self.MAX_SCORE))
            
            logger.debug(
                f"Score {symbol}: base={self.BASE_SCORE_SIGNAL:.0f}, "
                f"conf_bonus={confidence_bonus:.1f}, "
                f"confl_bonus={confluence_bonus:.1f}, "
                f"adx_bonus={(self.ADX_STRONG_BONUS if adx > 25 else (self.ADX_MODERATE_BONUS if adx > 20 else 0)):.0f}, "
                f"vol_penalty={(-self.EXTREME_VOLATILITY_PENALTY if analysis.volatility_zone == 'EXTREME' else 0):.0f}, "
                f"final={final_score:.1f}"
            )
            
            return round(final_score, 2)
            
        except Exception as e:
            logger.error(f"Error calculating score for {symbol}: {e}")
            return 0.0
            
    def get_tick_count(self, symbol: str) -> int:
        """
        Dapatkan jumlah tick yang sudah diterima untuk symbol.
        
        Args:
            symbol: Symbol identifier
            
        Returns:
            Jumlah tick yang sudah diterima
        """
        with self._lock:
            return self.tick_counts.get(symbol, 0)
            
    def get_all_pair_status(self) -> List[dict]:
        """
        Dapatkan status analisis untuk semua pairs yang di-scan.
        
        Untuk setiap symbol:
        1. Cek apakah sudah punya cukup tick data
        2. Jalankan strategy.analyze() jika data cukup
        3. Hitung score dengan _calculate_pair_score
        
        Returns:
            List of dicts dengan keys:
            - symbol: Symbol identifier
            - name: Display name
            - signal: "CALL", "PUT", atau "WAIT"
            - confidence: 0.0 - 1.0
            - score: 0.0 - 100.0
            - adx: ADX value
            - volatility_zone: "LOW", "NORMAL", "HIGH", "EXTREME"
            - reason: Analysis reason
            - tick_count: Jumlah tick yang sudah diterima
            - has_enough_data: Boolean apakah data cukup untuk analisis
        """
        results = []
        
        for symbol in self.strategies.keys():
            try:
                with self._lock:
                    strategy = self.strategies[symbol]
                    config = self.symbol_configs.get(symbol)
                    tick_count = self.tick_counts.get(symbol, 0)
                    
                has_enough_data = tick_count >= self.min_ticks_required
                
                if has_enough_data:
                    analysis = strategy.analyze()
                    score = self._calculate_pair_score(symbol, analysis)
                    
                    with self._lock:
                        self.symbol_data[symbol] = {
                            "last_analysis": analysis,
                            "last_score": score,
                            "last_update": time.time()
                        }
                        
                    result = {
                        "symbol": symbol,
                        "name": config.name if config else symbol,
                        "signal": analysis.signal.value,
                        "confidence": round(analysis.confidence, 3),
                        "score": score,
                        "adx": round(analysis.adx_value, 2),
                        "volatility_zone": analysis.volatility_zone,
                        "reason": analysis.reason,
                        "tick_count": tick_count,
                        "has_enough_data": True,
                        "rsi": round(analysis.rsi_value, 2),
                        "trend_direction": analysis.trend_direction
                    }
                else:
                    result = {
                        "symbol": symbol,
                        "name": config.name if config else symbol,
                        "signal": "WAIT",
                        "confidence": 0.0,
                        "score": 0.0,
                        "adx": 0.0,
                        "volatility_zone": "UNKNOWN",
                        "reason": f"Insufficient data ({tick_count}/{self.min_ticks_required} ticks)",
                        "tick_count": tick_count,
                        "has_enough_data": False,
                        "rsi": 50.0,
                        "trend_direction": "SIDEWAYS"
                    }
                    
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error getting status for {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "name": symbol,
                    "signal": "WAIT",
                    "confidence": 0.0,
                    "score": 0.0,
                    "adx": 0.0,
                    "volatility_zone": "ERROR",
                    "reason": f"Error: {str(e)}",
                    "tick_count": 0,
                    "has_enough_data": False,
                    "rsi": 50.0,
                    "trend_direction": "SIDEWAYS"
                })
                
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results
        
    def get_recommendations(self, top_n: int = 3) -> List[dict]:
        """
        Dapatkan rekomendasi top N pairs dengan signal terbaik.
        
        Filter hanya pairs dengan signal BUY atau SELL (bukan WAIT),
        sort by score descending, dan return top N.
        
        Args:
            top_n: Jumlah rekomendasi yang diinginkan (default 3)
            
        Returns:
            List of dicts dengan format sama seperti get_all_pair_status(),
            tapi hanya pairs dengan signal aktif dan sorted by score
        """
        all_status = self.get_all_pair_status()
        
        active_signals = [
            pair for pair in all_status
            if pair["signal"] in ["CALL", "PUT"] and pair["has_enough_data"]
        ]
        
        active_signals.sort(key=lambda x: x["score"], reverse=True)
        
        recommendations = active_signals[:top_n]
        
        logger.info(
            f"📊 Recommendations: {len(recommendations)} pairs with active signals "
            f"(out of {len(active_signals)} total active)"
        )
        
        return recommendations
        
    def get_best_pair(self) -> Optional[dict]:
        """
        Dapatkan pair dengan score tertinggi yang memiliki signal aktif.
        
        Shortcut untuk get_recommendations(top_n=1).
        
        Returns:
            Dict dengan info pair terbaik, atau None jika tidak ada signal aktif
        """
        recommendations = self.get_recommendations(top_n=1)
        return recommendations[0] if recommendations else None
        
    def get_scanner_status(self) -> dict:
        """
        Dapatkan status keseluruhan scanner.
        
        Returns:
            Dict dengan:
            - is_scanning: Boolean status scanning
            - total_symbols: Jumlah symbols yang di-scan
            - symbols_with_data: Jumlah symbols dengan data cukup
            - symbols_with_signal: Jumlah symbols dengan signal aktif
            - uptime: Lama scanning dalam detik (jika applicable)
        """
        all_status = self.get_all_pair_status()
        
        symbols_with_data = sum(1 for s in all_status if s["has_enough_data"])
        symbols_with_signal = sum(
            1 for s in all_status 
            if s["signal"] in ["CALL", "PUT"] and s["has_enough_data"]
        )
        
        return {
            "is_scanning": self.is_scanning,
            "total_symbols": len(self.strategies),
            "symbols_with_data": symbols_with_data,
            "symbols_with_signal": symbols_with_signal,
            "scan_interval": self.scan_interval,
            "min_ticks_required": self.min_ticks_required
        }
        
    def clear_all_data(self) -> None:
        """
        Clear semua tick data dan reset strategies.
        
        Berguna untuk reset state tanpa restart scanning.
        """
        with self._lock:
            for symbol, strategy in self.strategies.items():
                strategy.clear_history()
                self.tick_counts[symbol] = 0
                self.symbol_data[symbol] = {
                    "last_analysis": None,
                    "last_score": 0.0,
                    "last_update": None
                }
                
        logger.info("🧹 All scanner data cleared")
        
    def set_scan_interval(self, interval: float) -> None:
        """
        Set interval evaluasi scanner.
        
        Args:
            interval: Interval dalam detik (minimum 5)
        """
        self.scan_interval = max(5.0, interval)
        logger.info(f"⏱️ Scan interval set to {self.scan_interval}s")
        
    def set_min_ticks(self, min_ticks: int) -> None:
        """
        Set minimum ticks required sebelum analisis valid.
        
        Args:
            min_ticks: Minimum tick count (minimum 10)
        """
        self.min_ticks_required = max(10, min_ticks)
        logger.info(f"📊 Min ticks required set to {self.min_ticks_required}")
        
    def get_symbol_strategy(self, symbol: str) -> Optional[TradingStrategy]:
        """
        Dapatkan TradingStrategy instance untuk symbol tertentu.
        
        Args:
            symbol: Symbol identifier
            
        Returns:
            TradingStrategy instance atau None jika tidak ditemukan
        """
        with self._lock:
            return self.strategies.get(symbol)
            
    def __str__(self) -> str:
        """String representation of scanner status"""
        status = self.get_scanner_status()
        return (
            f"PairScanner(scanning={status['is_scanning']}, "
            f"symbols={status['total_symbols']}, "
            f"with_data={status['symbols_with_data']}, "
            f"with_signal={status['symbols_with_signal']})"
        )
        
    def __repr__(self) -> str:
        return self.__str__()
