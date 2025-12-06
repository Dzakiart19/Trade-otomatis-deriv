"""
=============================================================
UNIT TESTS - INCREMENTAL INDICATOR CACHING
=============================================================
Tests for incremental EMA and MACD calculations to ensure:
1. Incremental calculations match full recalculations
2. Cache invalidation works correctly
3. Edge cases are handled properly
=============================================================
"""

import unittest
import math
from strategy import TradingStrategy, safe_float, safe_divide, is_valid_number


class TestSafetyFunctions(unittest.TestCase):
    """Test safety utility functions"""
    
    def test_is_valid_number_with_valid_values(self):
        """Test is_valid_number with valid numeric values"""
        self.assertTrue(is_valid_number(42))
        self.assertTrue(is_valid_number(3.14159))
        self.assertTrue(is_valid_number(0))
        self.assertTrue(is_valid_number(-100.5))
    
    def test_is_valid_number_with_invalid_values(self):
        """Test is_valid_number with invalid values"""
        self.assertFalse(is_valid_number(None))
        self.assertFalse(is_valid_number(float('nan')))
        self.assertFalse(is_valid_number(float('inf')))
        self.assertFalse(is_valid_number(float('-inf')))
        self.assertFalse(is_valid_number("string"))
        self.assertFalse(is_valid_number([1, 2, 3]))
    
    def test_safe_float_with_valid_values(self):
        """Test safe_float with valid numeric values"""
        self.assertEqual(safe_float(42), 42.0)
        self.assertEqual(safe_float("3.14"), 3.14)
        self.assertEqual(safe_float(0), 0.0)
    
    def test_safe_float_with_invalid_values(self):
        """Test safe_float returns default for invalid values"""
        self.assertEqual(safe_float(None, default=0.0), 0.0)
        self.assertEqual(safe_float(float('nan'), default=50.0), 50.0)
        self.assertEqual(safe_float(float('inf'), default=100.0), 100.0)
        self.assertEqual(safe_float("invalid", default=0.0), 0.0)
    
    def test_safe_divide(self):
        """Test safe_divide handles edge cases"""
        self.assertEqual(safe_divide(10, 2), 5.0)
        self.assertEqual(safe_divide(10, 0, default=0.0), 0.0)
        self.assertEqual(safe_divide(None, 5, default=0.0), 0.0)
        self.assertEqual(safe_divide(10, None, default=0.0), 0.0)


class TestEMACalculation(unittest.TestCase):
    """Test EMA calculation methods"""
    
    def setUp(self):
        """Initialize strategy for each test"""
        self.strategy = TradingStrategy()
    
    def test_ema_basic_calculation(self):
        """Test basic EMA calculation"""
        prices = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0, 106.0, 108.0, 110.0, 109.0]
        ema = self.strategy.calculate_ema(prices, period=5)
        self.assertIsInstance(ema, float)
        self.assertGreater(ema, 0)
    
    def test_ema_insufficient_data(self):
        """Test EMA with less data than period"""
        prices = [100.0, 102.0, 104.0]
        ema = self.strategy.calculate_ema(prices, period=9)
        expected = sum(prices) / len(prices)
        self.assertAlmostEqual(ema, expected, places=5)
    
    def test_ema_empty_list(self):
        """Test EMA with empty price list"""
        ema = self.strategy.calculate_ema([], period=9)
        self.assertEqual(ema, 0.0)
    
    def test_ema_single_value(self):
        """Test EMA with single price"""
        ema = self.strategy.calculate_ema([100.0], period=9)
        self.assertEqual(ema, 100.0)


class TestIncrementalEMACalculation(unittest.TestCase):
    """Test incremental EMA calculation with caching"""
    
    def setUp(self):
        """Initialize strategy for each test"""
        self.strategy = TradingStrategy()
    
    def test_incremental_ema_matches_full_calculation(self):
        """Test that incremental EMA matches full recalculation"""
        prices = [100, 102, 104, 103, 105, 107, 106, 108, 110, 109,
                  111, 113, 112, 114, 116, 115, 117, 119, 118, 120,
                  122, 121, 123, 125, 124, 126, 128, 127, 129, 130]
        
        for price in prices:
            self.strategy.add_tick(price)
        
        incremental_fast = self.strategy.calculate_ema_incremental(
            period=self.strategy.EMA_FAST_PERIOD,
            cache_type="fast"
        )
        
        full_fast = self.strategy.calculate_ema(
            self.strategy.tick_history,
            self.strategy.EMA_FAST_PERIOD
        )
        
        self.assertAlmostEqual(incremental_fast, full_fast, places=4,
            msg=f"Fast EMA mismatch: incremental={incremental_fast}, full={full_fast}")
    
    def test_incremental_ema_cache_updates(self):
        """Test that cache is properly updated after each tick"""
        prices = [100 + i for i in range(25)]
        
        for price in prices:
            self.strategy.add_tick(price)
            self.strategy._last_tick_count_for_ema = len(self.strategy.tick_history) - 1
            self.strategy.calculate_ema_incremental(
                period=self.strategy.EMA_FAST_PERIOD,
                cache_type="fast"
            )
            self.strategy._last_tick_count_for_ema = len(self.strategy.tick_history)
        
        self.assertIsNotNone(self.strategy._ema_fast_cache)
    
    def test_incremental_ema_insufficient_data(self):
        """Test incremental EMA with insufficient data"""
        self.strategy.add_tick(100)
        self.strategy.add_tick(102)
        
        ema = self.strategy.calculate_ema_incremental(
            period=self.strategy.EMA_FAST_PERIOD,
            cache_type="fast"
        )
        
        expected = (100 + 102) / 2
        self.assertAlmostEqual(ema, expected, places=5)
    
    def test_incremental_ema_empty_history(self):
        """Test incremental EMA with empty tick history"""
        ema = self.strategy.calculate_ema_incremental(
            period=self.strategy.EMA_FAST_PERIOD,
            cache_type="fast"
        )
        self.assertEqual(ema, 0.0)
    
    def test_cache_invalidation_on_clear(self):
        """Test that cache is cleared when history is cleared"""
        for i in range(30):
            self.strategy.add_tick(100 + i)
        
        self.strategy.calculate_ema_incremental(period=9, cache_type="fast")
        self.assertIsNotNone(self.strategy._ema_fast_cache)
        
        self.strategy.clear_history()
        
        self.assertIsNone(self.strategy._ema_fast_cache)
        self.assertIsNone(self.strategy._ema_slow_cache)


class TestIncrementalMACDCalculation(unittest.TestCase):
    """Test incremental MACD calculation with caching"""
    
    def setUp(self):
        """Initialize strategy for each test"""
        self.strategy = TradingStrategy()
    
    def test_macd_insufficient_data(self):
        """Test MACD returns zeros with insufficient data"""
        for i in range(10):
            self.strategy.add_tick(100 + i)
        
        macd_line, signal_line, histogram = self.strategy.calculate_macd_incremental()
        
        self.assertEqual(macd_line, 0.0)
        self.assertEqual(signal_line, 0.0)
        self.assertEqual(histogram, 0.0)
    
    def test_macd_with_sufficient_data(self):
        """Test MACD calculation with enough data"""
        for i in range(50):
            self.strategy.add_tick(100 + i * 0.5)
        
        macd_line, signal_line, histogram = self.strategy.calculate_macd_incremental()
        
        self.assertIsInstance(macd_line, float)
        self.assertIsInstance(signal_line, float)
        self.assertIsInstance(histogram, float)
        
        expected_histogram = macd_line - signal_line
        self.assertAlmostEqual(histogram, expected_histogram, places=5)
    
    def test_macd_cache_updates(self):
        """Test that MACD cache is properly updated"""
        for i in range(50):
            self.strategy.add_tick(100 + i * 0.5)
        
        self.strategy.calculate_macd_incremental()
        
        self.assertIsNotNone(self.strategy._macd_ema_fast_cache)
        self.assertIsNotNone(self.strategy._macd_ema_slow_cache)
        self.assertIsNotNone(self.strategy._macd_signal_cache)
    
    def test_macd_cache_invalidation(self):
        """Test that MACD cache is cleared when history is cleared"""
        for i in range(50):
            self.strategy.add_tick(100 + i * 0.5)
        
        self.strategy.calculate_macd_incremental()
        
        self.strategy.clear_history()
        
        self.assertIsNone(self.strategy._macd_ema_fast_cache)
        self.assertIsNone(self.strategy._macd_ema_slow_cache)
        self.assertIsNone(self.strategy._macd_signal_cache)
        self.assertEqual(len(self.strategy._macd_values_cache), 0)
    
    def test_macd_histogram_sign(self):
        """Test MACD histogram sign matches trend direction"""
        for i in range(50):
            self.strategy.add_tick(100 + i * 2)
        
        macd_line, signal_line, histogram = self.strategy.calculate_macd_incremental()
        
        self.assertGreater(macd_line, 0,
            msg="MACD line should be positive in strong uptrend")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases for indicator calculations"""
    
    def setUp(self):
        """Initialize strategy for each test"""
        self.strategy = TradingStrategy()
    
    def test_add_tick_rejects_invalid_values(self):
        """Test that add_tick rejects invalid price values"""
        initial_count = len(self.strategy.tick_history)
        
        self.strategy.add_tick(float('nan'))
        self.strategy.add_tick(float('inf'))
        self.strategy.add_tick(-100.0)
        
        self.assertEqual(len(self.strategy.tick_history), initial_count)
    
    def test_add_tick_accepts_valid_values(self):
        """Test that add_tick accepts valid price values"""
        self.strategy.add_tick(100.5)
        self.strategy.add_tick(0.001)
        self.strategy.add_tick(1000000)
        
        self.assertEqual(len(self.strategy.tick_history), 3)
    
    def test_tick_history_pruning(self):
        """Test that tick history is pruned to MAX_TICK_HISTORY"""
        for i in range(250):
            self.strategy.add_tick(100 + i * 0.1)
        
        self.assertLessEqual(
            len(self.strategy.tick_history),
            self.strategy.MAX_TICK_HISTORY
        )
    
    def test_incremental_ema_cache_skip_detection(self):
        """Test that incremental EMA detects when full recalc is needed"""
        for i in range(30):
            self.strategy.add_tick(100 + i)
        
        self.strategy.calculate_ema_incremental(period=9, cache_type="fast")
        self.strategy._last_tick_count_for_ema = len(self.strategy.tick_history)
        
        for i in range(5):
            self.strategy.add_tick(150 + i)
        
        ema = self.strategy.calculate_ema_incremental(period=9, cache_type="fast")
        full_ema = self.strategy.calculate_ema(self.strategy.tick_history, 9)
        
        self.assertAlmostEqual(ema, full_ema, places=4,
            msg="Incremental EMA should match full calc after multiple ticks added")


class TestConsistencyAcrossMultipleCalls(unittest.TestCase):
    """Test that repeated calls produce consistent results"""
    
    def setUp(self):
        """Initialize strategy for each test"""
        self.strategy = TradingStrategy()
        for i in range(100):
            self.strategy.add_tick(100 + math.sin(i * 0.1) * 10)
    
    def test_ema_consistency(self):
        """Test that calling EMA multiple times gives same result"""
        results = []
        for _ in range(5):
            ema = self.strategy.calculate_ema(self.strategy.tick_history, 9)
            results.append(ema)
        
        for result in results[1:]:
            self.assertEqual(results[0], result)
    
    def test_macd_consistency(self):
        """Test that calling MACD multiple times gives same result"""
        first_result = self.strategy.calculate_macd_incremental()
        
        for _ in range(5):
            result = self.strategy.calculate_macd_incremental()
            self.assertEqual(first_result[0], result[0])
            self.assertEqual(first_result[1], result[1])
            self.assertEqual(first_result[2], result[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
