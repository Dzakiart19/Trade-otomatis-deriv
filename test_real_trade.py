#!/usr/bin/env python3
"""
Script untuk test trading NYATA di Deriv Demo Account.
Akan melakukan trade dan memantau hasilnya sampai selesai.
"""

import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("deriv_ws").setLevel(logging.DEBUG)

from deriv_ws import DerivWebSocket, AccountType
from trading import TradingManager

def on_trade_update(message: str):
    """Callback untuk update trading"""
    logger.info(f"📊 TRADE UPDATE: {message}")

def on_trade_complete(stats: dict):
    """Callback ketika trading selesai"""
    logger.info("=" * 60)
    logger.info("🏁 TRADING SESSION COMPLETED!")
    logger.info("=" * 60)
    logger.info(f"Total Trades: {stats.get('total_trades', 0)}")
    logger.info(f"Wins: {stats.get('wins', 0)}")
    logger.info(f"Losses: {stats.get('losses', 0)}")
    logger.info(f"Win Rate: {stats.get('win_rate', 0):.1f}%")
    logger.info(f"Total Profit: ${stats.get('total_profit', 0):.2f}")
    logger.info(f"Final Balance: ${stats.get('final_balance', 0):.2f}")
    logger.info("=" * 60)

def main():
    logger.info("=" * 60)
    logger.info("🚀 MEMULAI TEST TRADING NYATA DI DERIV")
    logger.info("=" * 60)
    
    demo_token = os.getenv("DERIV_TOKEN_DEMO")
    if not demo_token:
        logger.error("❌ DERIV_TOKEN_DEMO tidak ditemukan!")
        return
    
    deriv = DerivWebSocket(
        demo_token=demo_token,
        real_token=os.getenv("DERIV_TOKEN_REAL", "")
    )
    
    logger.info("📡 Menghubungkan ke Deriv WebSocket...")
    deriv.connect()
    
    timeout = 30
    start = time.time()
    while not deriv.is_authorized and (time.time() - start) < timeout:
        time.sleep(0.5)
    
    if not deriv.is_authorized:
        logger.error("❌ Gagal authorize ke Deriv!")
        return
    
    balance_before = deriv.account_info.balance if deriv.account_info else 0
    logger.info(f"✅ Terkoneksi ke akun: {deriv.account_info.account_id if deriv.account_info else 'Unknown'}")
    logger.info(f"💰 SALDO SEBELUM TRADING: ${balance_before:.2f} USD")
    logger.info("")
    
    trader = TradingManager(deriv_ws=deriv)
    
    trader.on_trade_opened = lambda t, p, s, c, target: logger.info(f"📊 TRADE OPENED: {t} @ ${p:.5f}, Stake: ${s:.2f} [{c}/{target}]")
    trader.on_trade_closed = lambda result: logger.info(f"📊 TRADE CLOSED: {'WIN' if result.is_win else 'LOSS'} | Profit: ${result.profit:+.2f}")
    trader.on_session_complete = lambda stats: on_trade_complete(stats.__dict__)
    trader.on_error = lambda msg: logger.error(f"❌ Error: {msg}")
    
    base_stake = 0.35
    duration = 5
    duration_unit = "t"
    target_trades = 3
    
    logger.info("📋 PARAMETER TRADING:")
    logger.info(f"   - Stake: ${base_stake}")
    logger.info(f"   - Duration: {duration}{duration_unit}")
    logger.info(f"   - Target Trades: {target_trades}")
    logger.info(f"   - Strategy: RSI (BUY<30, SELL>70)")
    logger.info(f"   - Money Management: Martingale x2.1")
    logger.info("")
    
    trader.configure(
        stake=base_stake,
        duration=duration,
        duration_unit=duration_unit,
        target_trades=target_trades
    )
    
    logger.info("🎯 MEMULAI AUTO TRADING...")
    logger.info("⏳ Menunggu sinyal RSI valid (bisa memakan waktu 1-5 menit)...")
    logger.info("")
    
    result = trader.start()
    logger.info(result)
    
    if "ERROR" in result.upper() or "TIDAK" in result.upper():
        logger.error("❌ Gagal memulai trading!")
        return
    
    from trading import TradingState
    
    max_wait = 600
    start_time = time.time()
    last_status = ""
    
    while trader.state == TradingState.RUNNING or trader.state == TradingState.WAITING_RESULT:
        if (time.time() - start_time) >= max_wait:
            logger.warning("⏰ Timeout reached!")
            break
            
        current_status = f"Trades: {trader.stats.total_trades}/{target_trades} | W:{trader.stats.wins} L:{trader.stats.losses}"
        if current_status != last_status:
            logger.info(f"📊 Status: {current_status}")
            last_status = current_status
        time.sleep(2)
    
    time.sleep(3)
    
    balance_after = deriv.account_info.balance if deriv.account_info else 0
    profit = balance_after - balance_before
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 HASIL TEST TRADING NYATA")
    logger.info("=" * 60)
    logger.info(f"💰 Saldo SEBELUM: ${balance_before:.2f} USD")
    logger.info(f"💰 Saldo SESUDAH: ${balance_after:.2f} USD")
    logger.info(f"📈 Perubahan: ${profit:+.2f} USD")
    logger.info("")
    
    if abs(profit) > 0.01:
        logger.info("✅ KONFIRMASI: Saldo BERUBAH! Trading NYATA berhasil!")
        logger.info("👉 Silakan cek di web Deriv untuk verifikasi.")
    else:
        logger.info("⚠️ Saldo tidak berubah (mungkin belum ada trade yang selesai)")
    
    logger.info("=" * 60)
    
    deriv.disconnect()

if __name__ == "__main__":
    main()
