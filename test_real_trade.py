#!/usr/bin/env python3
"""
=============================================================
TEST TRADING NYATA - Deriv Demo Account
=============================================================
Script ini melakukan testing REAL trading di akun demo Deriv.
Akan melakukan trade sungguhan dan memantau perubahan saldo.

Penggunaan:
  python test_real_trade.py

Catatan:
  - Pastikan DERIV_TOKEN_DEMO sudah di-set
  - Gunakan akun demo untuk testing
  - Perubahan saldo bisa dicek di web Deriv
=============================================================
"""

import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger("deriv_ws").setLevel(logging.INFO)
logging.getLogger("trading").setLevel(logging.INFO)
logging.getLogger("strategy").setLevel(logging.INFO)

from deriv_ws import DerivWebSocket, AccountType
from trading import TradingManager, TradingState

class RealTradeTest:
    """Class untuk mengelola test trading nyata"""
    
    def __init__(self):
        self.deriv: Optional[DerivWebSocket] = None
        self.trader: Optional[TradingManager] = None
        self.balance_before: float = 0
        self.balance_after: float = 0
        self.test_start_time: Optional[datetime] = None
        self.trades_executed: int = 0
        self.session_completed: bool = False
        
    def on_trade_opened(self, contract_type: str, price: float, stake: float,
                        trade_num: int, target: int):
        """Callback saat posisi dibuka - signature sesuai TradingManager"""
        target_text = f"/{target}" if target > 0 else ""
        logger.info(f"📊 TRADE #{trade_num}{target_text} OPENED: {contract_type} @ {price:.5f} | Stake: ${stake:.2f}")
        self.trades_executed = trade_num
        
    def on_trade_closed(self, is_win: bool, profit: float, balance: float,
                        trade_num: int, target: int, next_stake: float):
        """Callback saat posisi ditutup - signature sesuai TradingManager"""
        target_text = f"/{target}" if target > 0 else ""
        result_emoji = "WIN" if is_win else "LOSS"
        profit_text = f"+${profit:.2f}" if is_win else f"-${abs(profit):.2f}"
        
        logger.info(f"{'✅' if is_win else '❌'} TRADE #{trade_num}{target_text} {result_emoji}: {profit_text}")
        logger.info(f"   💰 Balance: ${balance:.2f} | Next Stake: ${next_stake:.2f}")
        self.balance_after = balance
        
    def on_session_complete(self, total: int, wins: int, losses: int,
                           profit: float, win_rate: float):
        """Callback saat session selesai - signature sesuai TradingManager"""
        self.session_completed = True
        profit_emoji = "📈" if profit >= 0 else "📉"
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("🏁 TRADING SESSION COMPLETED!")
        logger.info("=" * 60)
        logger.info(f"📊 Total Trades: {total}")
        logger.info(f"✅ Wins: {wins}")
        logger.info(f"❌ Losses: {losses}")
        logger.info(f"📈 Win Rate: {win_rate:.1f}%")
        logger.info(f"{profit_emoji} Net Profit: ${profit:+.2f}")
        logger.info("=" * 60)
        
    def on_error(self, error_msg: str):
        """Callback saat terjadi error"""
        logger.error(f"⚠️ TRADING ERROR: {error_msg}")
        
    def connect_deriv(self) -> bool:
        """Koneksi ke Deriv WebSocket"""
        demo_token = os.getenv("DERIV_TOKEN_DEMO")
        if not demo_token:
            logger.error("❌ DERIV_TOKEN_DEMO tidak ditemukan di environment!")
            logger.info("💡 Set di Replit Secrets atau file .env")
            return False
            
        logger.info("📡 Menghubungkan ke Deriv WebSocket...")
        
        self.deriv = DerivWebSocket(
            demo_token=demo_token,
            real_token=os.getenv("DERIV_TOKEN_REAL", "")
        )
        
        self.deriv.connect()
        
        timeout = 30
        start = time.time()
        while not self.deriv.is_authorized and (time.time() - start) < timeout:
            time.sleep(0.5)
            
        if not self.deriv.is_authorized:
            logger.error("❌ Gagal authorize ke Deriv! Cek token.")
            return False
            
        if self.deriv.account_info:
            self.balance_before = self.deriv.account_info.balance
            logger.info(f"✅ Terkoneksi ke akun: {self.deriv.account_info.account_id}")
            logger.info(f"💰 Saldo awal: ${self.balance_before:.2f} USD")
            return True
        else:
            logger.error("❌ Tidak bisa mendapatkan info akun!")
            return False
            
    def setup_trader(self, stake: float = 0.50, duration: int = 5,
                     duration_unit: str = "t", target_trades: int = 3,
                     symbol: str = "R_100"):
        """Setup TradingManager dengan callbacks yang benar"""
        if not self.deriv:
            logger.error("❌ Deriv belum terkoneksi!")
            return False
            
        self.trader = TradingManager(deriv_ws=self.deriv)
        
        self.trader.on_trade_opened = self.on_trade_opened
        self.trader.on_trade_closed = self.on_trade_closed
        self.trader.on_session_complete = self.on_session_complete
        self.trader.on_error = self.on_error
        
        self.trader.configure(
            stake=stake,
            duration=duration,
            duration_unit=duration_unit,
            target_trades=target_trades,
            symbol=symbol
        )
        
        logger.info("")
        logger.info("📋 PARAMETER TRADING:")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Stake: ${stake}")
        logger.info(f"   • Durasi: {duration}{duration_unit}")
        logger.info(f"   • Target: {target_trades} trades")
        logger.info(f"   • Strategi: RSI (BUY<30, SELL>70)")
        logger.info(f"   • Money Management: Martingale x2.1")
        logger.info("")
        
        return True
        
    def run_trading(self, max_wait_minutes: int = 10) -> bool:
        """Jalankan trading dan tunggu sampai selesai"""
        if not self.trader:
            logger.error("❌ Trader belum di-setup!")
            return False
            
        self.test_start_time = datetime.now()
        
        logger.info("🚀 MEMULAI AUTO TRADING...")
        logger.info("⏳ Menunggu sinyal RSI valid (perlu 15+ tick data)...")
        logger.info("")
        
        result = self.trader.start()
        logger.info(result)
        
        if "ERROR" in result.upper() or "TIDAK" in result.upper() or "belum" in result.lower():
            logger.error("❌ Gagal memulai trading!")
            return False
            
        max_wait = max_wait_minutes * 60
        start_time = time.time()
        last_tick_count = 0
        last_trade_count = 0
        
        while self.trader.state in [TradingState.RUNNING, TradingState.WAITING_RESULT]:
            if (time.time() - start_time) >= max_wait:
                logger.warning(f"⏰ Timeout ({max_wait_minutes} menit) tercapai!")
                break
                
            stats = self.trader.strategy.get_stats()
            current_tick = stats['tick_count']
            current_trades = self.trader.stats.total_trades
            
            if current_tick > last_tick_count:
                if current_tick <= 15:
                    logger.info(f"📊 Collecting data: {current_tick}/15 ticks | RSI: {stats['rsi']:.1f}")
                elif current_tick % 10 == 0:
                    logger.info(f"📊 Analyzing... Ticks: {current_tick} | RSI: {stats['rsi']:.1f} | Trend: {stats['trend']}")
                last_tick_count = current_tick
                
            if current_trades > last_trade_count:
                last_trade_count = current_trades
                
            time.sleep(1)
            
        time.sleep(2)
        return True
        
    def show_results(self):
        """Tampilkan hasil test trading"""
        if self.deriv and self.deriv.account_info:
            self.balance_after = self.deriv.account_info.balance
        
        profit = self.balance_after - self.balance_before
        duration = datetime.now() - self.test_start_time if self.test_start_time else None
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 HASIL TEST TRADING NYATA")
        logger.info("=" * 60)
        logger.info(f"⏱️  Durasi: {duration}")
        logger.info(f"💰 Saldo SEBELUM: ${self.balance_before:.2f} USD")
        logger.info(f"💰 Saldo SESUDAH: ${self.balance_after:.2f} USD")
        logger.info(f"{'📈' if profit >= 0 else '📉'} Perubahan: ${profit:+.2f} USD")
        logger.info("")
        
        if self.trader:
            logger.info(f"📊 Total trades: {self.trader.stats.total_trades}")
            logger.info(f"✅ Wins: {self.trader.stats.wins}")
            logger.info(f"❌ Losses: {self.trader.stats.losses}")
            logger.info(f"📈 Win rate: {self.trader.stats.win_rate:.1f}%")
        
        logger.info("")
        if abs(profit) > 0.01:
            logger.info("✅ KONFIRMASI: Saldo BERUBAH! Trading NYATA berhasil!")
            logger.info("👉 Silakan cek di web Deriv untuk verifikasi.")
        else:
            if self.trader and self.trader.stats.total_trades == 0:
                logger.info("⚠️ Belum ada trade yang tereksekusi (menunggu sinyal RSI)")
            else:
                logger.info("⚠️ Saldo tidak berubah signifikan")
                
        logger.info("=" * 60)
        
    def cleanup(self):
        """Bersihkan koneksi"""
        if self.trader and self.trader.state == TradingState.RUNNING:
            self.trader.stop()
        if self.deriv:
            self.deriv.disconnect()
        logger.info("🔌 Koneksi ditutup")


def main():
    """Main function untuk test trading"""
    logger.info("=" * 60)
    logger.info("🚀 DERIV REAL TRADE TEST - Demo Account")
    logger.info("=" * 60)
    logger.info(f"📅 Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    test = RealTradeTest()
    
    try:
        if not test.connect_deriv():
            return 1
            
        if not test.setup_trader(
            stake=0.50,
            duration=5,
            duration_unit="t",  # 5 ticks untuk Volatility Index
            target_trades=3,
            symbol="R_100"  # Volatility 100 Index
        ):
            return 1
            
        test.run_trading(max_wait_minutes=10)
        
        test.show_results()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test dihentikan oleh user")
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        return 1
    finally:
        test.cleanup()
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
