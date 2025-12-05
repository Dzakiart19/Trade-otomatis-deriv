"""
=============================================================
DERIV AUTO TRADING BOT - MAIN APPLICATION
=============================================================
Bot Telegram untuk auto trading Binary Options di Deriv.
Menggunakan strategi RSI dengan Martingale money management.

Commands:
- /start - Mulai bot dan tampilkan menu
- /akun - Menu akun (cek saldo, switch demo/real)
- /autotrade [stake] [durasi] [target] - Mulai auto trading
- /stop - Hentikan auto trading
- /status - Cek status bot dan trading
- /help - Panduan penggunaan
=============================================================
"""

import os
import sys
import signal
import time
import asyncio
import logging
import threading
import requests
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from deriv_ws import DerivWebSocket, AccountType
from trading import TradingManager, TradingState
from keep_alive import start_keep_alive
from symbols import (
    SUPPORTED_SYMBOLS,
    DEFAULT_SYMBOL,
    MIN_STAKE_GLOBAL,
    get_symbol_config,
    get_short_term_symbols,
    get_long_term_symbols,
    get_symbol_list_text
)

USD_TO_IDR = 15800
CHAT_ID_FILE = "logs/active_chat_id.txt"

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

deriv_ws: Optional[DerivWebSocket] = None
trading_manager: Optional[TradingManager] = None
active_chat_id: Optional[int] = None
chat_id_confirmed: bool = False
shutdown_requested: bool = False
last_progress_notification_time: float = 0.0
MIN_NOTIFICATION_INTERVAL: float = 10.0

import threading
_chat_id_lock = threading.Lock()


def save_chat_id(chat_id: int) -> bool:
    """Save chat_id ke file untuk persistence setelah restart (thread-safe)"""
    with _chat_id_lock:
        try:
            os.makedirs("logs", exist_ok=True)
            with open(CHAT_ID_FILE, "w") as f:
                f.write(str(chat_id))
            logger.info(f"💾 Chat ID saved: {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save chat_id: {e}")
            return False


def load_chat_id() -> Optional[int]:
    """Load chat_id dari file setelah bot restart (thread-safe)"""
    with _chat_id_lock:
        try:
            if os.path.exists(CHAT_ID_FILE):
                with open(CHAT_ID_FILE, "r") as f:
                    chat_id_str = f.read().strip()
                    if chat_id_str:
                        chat_id = int(chat_id_str)
                        logger.info(f"📂 Chat ID loaded from file: {chat_id}")
                        return chat_id
        except Exception as e:
            logger.error(f"Failed to load chat_id: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    global active_chat_id, chat_id_confirmed
    if not update.effective_chat or not update.message:
        return
    with _chat_id_lock:
        active_chat_id = update.effective_chat.id
        chat_id_confirmed = True
    save_chat_id(active_chat_id)
    
    welcome_text = (
        "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n"
        "Bot trading otomatis untuk Binary Options (Volatility Index).\n"
        "Menggunakan Multi-Indicator Strategy + Adaptive Martingale.\n\n"
        "📊 **Indicators:** RSI, EMA, MACD, Stochastic, ATR\n\n"
        "📋 **Menu Utama:**\n"
        "• /akun - Kelola akun (saldo, switch demo/real)\n"
        "• /autotrade - Mulai auto trading\n"
        "• /stop - Hentikan trading\n"
        "• /status - Cek status bot\n"
        "• /help - Panduan lengkap\n\n"
        "⚠️ *Trading memiliki risiko. Gunakan dengan bijak.*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Cek Akun", callback_data="menu_akun"),
            InlineKeyboardButton("🚀 Auto Trade", callback_data="menu_autotrade")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="menu_status"),
            InlineKeyboardButton("❓ Help", callback_data="menu_help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def akun_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /akun"""
    global deriv_ws
    if not update.message:
        return
    
    if not deriv_ws or not deriv_ws.is_ready():
        await update.message.reply_text(
            "❌ WebSocket belum terkoneksi. Tunggu beberapa detik..."
        )
        return
        
    account_info = deriv_ws.account_info
    account_type = deriv_ws.current_account_type.value.upper()
    
    if account_info:
        balance_idr = account_info.balance * USD_TO_IDR
        account_text = (
            f"💼 **INFORMASI AKUN**\n\n"
            f"• Tipe: {account_type} {'🎮' if account_info.is_virtual else '💵'}\n"
            f"• ID: `{account_info.account_id}`\n"
            f"• Saldo: **${account_info.balance:.2f}** {account_info.currency}\n"
            f"• Saldo IDR: **Rp {balance_idr:,.0f}**\n"
        )
    else:
        account_text = "❌ Gagal mendapatkan info akun."
        
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Saldo", callback_data="akun_refresh")],
        [
            InlineKeyboardButton("🎮 Switch ke DEMO", callback_data="akun_demo"),
            InlineKeyboardButton("💵 Switch ke REAL", callback_data="akun_real")
        ],
        [InlineKeyboardButton("🔌 Reset Koneksi", callback_data="akun_reset")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        account_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def autotrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /autotrade [stake] [durasi] [target] [symbol]"""
    global trading_manager
    if not update.message:
        return
    
    if not trading_manager:
        await update.message.reply_text("❌ Trading manager belum siap.")
        return
        
    args = context.args if context.args else []
    
    stake = MIN_STAKE_GLOBAL
    duration_str = "5t"  # 5 ticks untuk Volatility Index
    target_trades = 5
    symbol = DEFAULT_SYMBOL
    
    if len(args) >= 1:
        try:
            stake = float(args[0])
            if stake < MIN_STAKE_GLOBAL:
                stake = MIN_STAKE_GLOBAL
                await update.message.reply_text(
                    f"⚠️ Stake minimum adalah ${MIN_STAKE_GLOBAL}. Dikoreksi otomatis."
                )
        except ValueError:
            await update.message.reply_text("❌ Format stake tidak valid. Gunakan angka.")
            return
            
    if len(args) >= 2:
        duration_str = args[1]
        
    if len(args) >= 3:
        try:
            target_trades = int(args[2])
        except ValueError:
            target_trades = 0
            
    if len(args) >= 4:
        input_symbol = args[3].upper()
        if input_symbol in SUPPORTED_SYMBOLS:
            symbol = input_symbol
        else:
            await update.message.reply_text(
                f"⚠️ Symbol '{input_symbol}' tidak dikenal. Menggunakan default: {DEFAULT_SYMBOL}\n\n"
                f"Symbol tersedia: {', '.join(SUPPORTED_SYMBOLS.keys())}"
            )
            
    duration, duration_unit = trading_manager.parse_duration(duration_str)
    
    config_msg = trading_manager.configure(
        stake=stake,
        duration=duration,
        duration_unit=duration_unit,
        target_trades=target_trades,
        symbol=symbol
    )
    
    if config_msg.startswith("❌"):
        await update.message.reply_text(config_msg, parse_mode="Markdown")
        return
    
    start_msg = trading_manager.start()
    
    await update.message.reply_text(
        f"{config_msg}\n\n{start_msg}",
        parse_mode="Markdown"
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stop"""
    global trading_manager
    if not update.message:
        return
    
    if not trading_manager:
        await update.message.reply_text("❌ Trading manager belum siap.")
        return
        
    result = trading_manager.stop()
    await update.message.reply_text(result, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /status"""
    global deriv_ws, trading_manager
    if not update.message:
        return
    
    if deriv_ws and deriv_ws.is_ready():
        ws_status = "✅ Terkoneksi"
        account_type = deriv_ws.current_account_type.value.upper()
        balance = deriv_ws.get_balance()
        balance_idr = balance * USD_TO_IDR
    else:
        ws_status = "❌ Terputus"
        account_type = "N/A"
        balance = 0
        balance_idr = 0
        
    status_text = (
        f"📡 **STATUS BOT**\n\n"
        f"**Koneksi:**\n"
        f"• WebSocket: {ws_status}\n"
        f"• Akun: {account_type}\n"
        f"• Saldo: ${balance:.2f} (Rp {balance_idr:,.0f})\n\n"
    )
    
    if trading_manager:
        status_text += trading_manager.get_status()
    else:
        status_text += "• Trading: Belum aktif"
        
    await update.message.reply_text(status_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help"""
    if not update.message:
        return
    
    try:
        help_text = (
            "📚 <b>PANDUAN PENGGUNAAN</b>\n\n"
            "<b>1️⃣ Setup Akun</b>\n"
            "Gunakan /akun untuk:\n"
            "• Cek saldo real-time\n"
            "• Switch antara Demo/Real\n\n"
            "<b>2️⃣ Mulai Trading</b>\n"
            "Format: <code>/autotrade [stake] [durasi] [target] [symbol]</code>\n\n"
            "Contoh:\n"
            "• <code>/autotrade</code> - Default ($0.50, 5t, 5 trade, R_100)\n"
            "• <code>/autotrade 0.5</code> - Stake $0.5\n"
            "• <code>/autotrade 1 5t 10</code> - $1, 5 ticks, 10 trade\n"
            "• <code>/autotrade 0.50 5t 0 R_50</code> - Unlimited, R_50\n\n"
            "<b>Format Durasi:</b>\n"
            "• <code>5t</code> = 5 ticks (untuk Synthetic)\n"
            "• <code>30s</code> = 30 detik\n"
            "• <code>1m</code> = 1 menit\n"
            "• <code>1d</code> = 1 hari (untuk XAUUSD)\n\n"
            "<b>3️⃣ Symbol Tersedia</b>\n"
            "Short-term (ticks): R_100, R_75, R_50, R_25, R_10\n"
            "1-second: 1HZ100V, 1HZ75V, 1HZ50V\n"
            "Long-term (hari): frxXAUUSD\n\n"
            "<b>4️⃣ Strategi RSI</b>\n"
            "• BUY (Call): RSI &lt; 30 (Oversold)\n"
            "• SELL (Put): RSI &gt; 70 (Overbought)\n\n"
            "<b>5️⃣ Martingale</b>\n"
            "• WIN: Stake reset ke awal\n"
            "• LOSS: Stake x 2.1\n\n"
            "⚠️ <i>Trading memiliki risiko tinggi!</i>"
        )
        
        await update.message.reply_text(help_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in help_command: {e}")
        await update.message.reply_text(
            "📚 PANDUAN PENGGUNAAN\n\n"
            "1. /akun - Cek saldo dan switch akun\n"
            "2. /autotrade - Mulai auto trading\n"
            "3. /stop - Hentikan trading\n"
            "4. /status - Cek status bot\n\n"
            "Contoh: /autotrade 0.50 5t 5 R_100"
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua inline button callbacks"""
    global deriv_ws, trading_manager, active_chat_id, chat_id_confirmed
    
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    
    if query.message and query.message.chat:
        new_chat_id = query.message.chat.id
        with _chat_id_lock:
            if active_chat_id != new_chat_id:
                active_chat_id = new_chat_id
                chat_id_confirmed = True
        save_chat_id(new_chat_id)
    
    data = query.data
    
    if data == "menu_akun":
        if deriv_ws and deriv_ws.account_info:
            account_info = deriv_ws.account_info
            account_type = deriv_ws.current_account_type.value.upper()
            balance_idr = account_info.balance * USD_TO_IDR
            
            account_text = (
                f"💼 **INFORMASI AKUN**\n\n"
                f"• Tipe: {account_type} {'🎮' if account_info.is_virtual else '💵'}\n"
                f"• ID: `{account_info.account_id}`\n"
                f"• Saldo: **${account_info.balance:.2f}** {account_info.currency}\n"
                f"• Saldo IDR: **Rp {balance_idr:,.0f}**\n"
            )
        else:
            account_text = "❌ Akun belum terkoneksi."
            
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Saldo", callback_data="akun_refresh")],
            [
                InlineKeyboardButton("🎮 DEMO", callback_data="akun_demo"),
                InlineKeyboardButton("💵 REAL", callback_data="akun_real")
            ],
            [InlineKeyboardButton("« Kembali", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            account_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "menu_autotrade":
        trade_text = (
            "🚀 **AUTO TRADING**\n\n"
            "Pilih symbol untuk trading:\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Pilih Symbol", callback_data="select_symbol")],
            [InlineKeyboardButton("⚡ Quick Start (R_100)", callback_data="quick_menu")],
            [InlineKeyboardButton("« Kembali", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            trade_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "select_symbol":
        symbol_text = (
            "📊 **PILIH TRADING SYMBOL**\n\n"
            "**Synthetic (Short-term - Ticks):**\n"
            "Cocok untuk auto trading cepat\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("R_100 (Default)", callback_data="sym~R_100"),
                InlineKeyboardButton("R_75", callback_data="sym~R_75")
            ],
            [
                InlineKeyboardButton("R_50", callback_data="sym~R_50"),
                InlineKeyboardButton("R_25", callback_data="sym~R_25")
            ],
            [
                InlineKeyboardButton("1HZ100V (1s)", callback_data="sym~1HZ100V"),
                InlineKeyboardButton("1HZ75V (1s)", callback_data="sym~1HZ75V")
            ],
            [InlineKeyboardButton("🥇 XAUUSD (HARIAN SAJA!)", callback_data="sym~frxXAUUSD")],
            [InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")]
        ]
        await query.edit_message_text(
            symbol_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data.startswith("sym~"):
        symbol = data[4:]
        config = get_symbol_config(symbol)
        if config:
            if config.supports_ticks:
                duration_options = [
                    [
                        InlineKeyboardButton("5 ticks", callback_data=f"trade~{symbol}~5t"),
                        InlineKeyboardButton("10 ticks", callback_data=f"trade~{symbol}~10t")
                    ]
                ]
            else:
                duration_options = [
                    [
                        InlineKeyboardButton("1 hari", callback_data=f"trade~{symbol}~1d"),
                        InlineKeyboardButton("7 hari", callback_data=f"trade~{symbol}~7d")
                    ]
                ]
            
            symbol_info = (
                f"📈 **{config.name}**\n\n"
                f"• Symbol: `{config.symbol}`\n"
                f"• Min Stake: ${config.min_stake}\n"
                f"• Durasi: {config.duration_unit} ({config.description})\n\n"
                "Pilih durasi trading:"
            )
            
            keyboard = duration_options + [
                [InlineKeyboardButton("« Kembali", callback_data="select_symbol")]
            ]
            await query.edit_message_text(
                symbol_info,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    elif data.startswith("trade~"):
        parts = data.split("~")
        if len(parts) >= 3:
            symbol = parts[1]
            duration_str = parts[2]
            
            trade_setup = (
                f"⚙️ **SETUP TRADING**\n\n"
                f"• Symbol: `{symbol}`\n"
                f"• Durasi: {duration_str}\n\n"
                "Pilih stake dan target:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("$0.50 | 5x", callback_data=f"exec~{symbol}~{duration_str}~050~5"),
                    InlineKeyboardButton("$0.50 | 10x", callback_data=f"exec~{symbol}~{duration_str}~050~10")
                ],
                [
                    InlineKeyboardButton("$1 | 5x", callback_data=f"exec~{symbol}~{duration_str}~1~5"),
                    InlineKeyboardButton("$1 | ∞", callback_data=f"exec~{symbol}~{duration_str}~1~0")
                ],
                [InlineKeyboardButton("« Kembali", callback_data=f"sym~{symbol}")]
            ]
            await query.edit_message_text(
                trade_setup,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    elif data.startswith("exec~"):
        parts = data.split("~")
        if len(parts) >= 5 and trading_manager:
            symbol = parts[1]
            duration_str = parts[2]
            stake_str = parts[3]
            target_str = parts[4]
            
            if stake_str == "050":
                stake = 0.50
            else:
                try:
                    stake = float(stake_str)
                except ValueError:
                    stake = MIN_STAKE_GLOBAL
            target = int(target_str)
            
            duration, duration_unit = trading_manager.parse_duration(duration_str)
            config_msg = trading_manager.configure(
                stake=stake,
                duration=duration,
                duration_unit=duration_unit,
                target_trades=target,
                symbol=symbol
            )
            
            if config_msg.startswith("❌"):
                await query.edit_message_text(config_msg, parse_mode="Markdown")
                return
                
            result = trading_manager.start()
            await query.edit_message_text(f"{config_msg}\n\n{result}", parse_mode="Markdown")
            
    elif data == "quick_menu":
        trade_text = (
            "⚡ **QUICK START (R_100)**\n\n"
            "Trading cepat dengan Volatility 100:\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("$0.50 | 5t | 5x", callback_data="exec~R_100~5t~050~5"),
                InlineKeyboardButton("$0.50 | 5t | 10x", callback_data="exec~R_100~5t~050~10")
            ],
            [
                InlineKeyboardButton("$1 | 5t | 5x", callback_data="exec~R_100~5t~1~5"),
                InlineKeyboardButton("$0.50 | 5t | ∞", callback_data="exec~R_100~5t~050~0")
            ],
            [InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")]
        ]
        await query.edit_message_text(
            trade_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "menu_status":
        if trading_manager:
            status_text = trading_manager.get_status()
        else:
            status_text = "❌ Trading manager belum siap."
            
        keyboard = [[InlineKeyboardButton("« Kembali", callback_data="menu_main")]]
        await query.edit_message_text(
            status_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "menu_help":
        help_text = (
            "📚 <b>QUICK HELP</b>\n\n"
            "• /akun - Kelola akun\n"
            "• /autotrade - Mulai trading\n"
            "• /stop - Stop trading\n"
            "• /status - Cek status\n"
            "• /help - Panduan lengkap"
        )
        keyboard = [[InlineKeyboardButton("« Kembali", callback_data="menu_main")]]
        await query.edit_message_text(
            help_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "menu_main":
        welcome_text = (
            "🤖 **DERIV AUTO TRADING BOT**\n\n"
            "Pilih menu di bawah ini:"
        )
        keyboard = [
            [
                InlineKeyboardButton("💰 Cek Akun", callback_data="menu_akun"),
                InlineKeyboardButton("🚀 Auto Trade", callback_data="menu_autotrade")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="menu_status"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help")
            ]
        ]
        await query.edit_message_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "akun_refresh":
        if deriv_ws and deriv_ws.account_info:
            balance = deriv_ws.get_balance()
            balance_idr = balance * USD_TO_IDR
            await query.edit_message_text(
                f"💰 Saldo terkini:\n\n"
                f"• USD: **${balance:.2f}**\n"
                f"• IDR: **Rp {balance_idr:,.0f}**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                ])
            )
        else:
            await query.edit_message_text("❌ Gagal refresh saldo.")
            
    elif data == "akun_demo":
        if deriv_ws:
            deriv_ws.switch_account(AccountType.DEMO)
            await query.edit_message_text(
                "🎮 Beralih ke akun **DEMO**...\n\nTunggu beberapa detik untuk otorisasi.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                ])
            )
            
    elif data == "akun_real":
        if deriv_ws:
            deriv_ws.switch_account(AccountType.REAL)
            await query.edit_message_text(
                "💵 Beralih ke akun **REAL**...\n\n⚠️ *Hati-hati! Ini uang asli!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                ])
            )
            
    elif data == "akun_reset":
        if deriv_ws:
            try:
                logger.info("User requested connection reset")
                deriv_ws.disconnect()
                await asyncio.sleep(1)  # Brief pause before reconnect
                deriv_ws.connect()
                await query.edit_message_text(
                    "🔌 Mereset koneksi...\n\nTunggu beberapa detik.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                    ])
                )
            except Exception as e:
                logger.error(f"Error resetting connection: {e}")
                await query.edit_message_text(
                    f"❌ Gagal mereset koneksi: {str(e)[:50]}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                    ])
                )
            


def escape_markdown(text: str) -> str:
    """Escape karakter khusus untuk Telegram Markdown"""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def escape_markdown_v2(text: str) -> str:
    """
    Escape karakter khusus untuk Telegram MarkdownV2.
    Ini lebih komprehensif dari escape_markdown() dan menjaga formatting.
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', '\\']
    result = text
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    return result


def log_telegram_error(message: str, error: str):
    """Log failed Telegram messages to file for debugging"""
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/telegram_errors.log", "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] Error: {error}\n")
            f.write(f"[{timestamp}] Message: {message[:200]}...\n" if len(message) > 200 else f"[{timestamp}] Message: {message}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        logger.error(f"Failed to log telegram error: {e}")


def send_telegram_message_sync(token: str, message: str, use_html: bool = False):
    """
    Helper synchronous untuk kirim pesan ke Telegram dari thread lain.
    Menggunakan requests library untuk menghindari masalah asyncio event loop.
    
    Features:
    - Thread-safe dengan locking
    - Retry dengan exponential backoff (max 3x)
    - Fallback ke plain text jika Markdown gagal 2x
    - Log failed messages ke file
    
    Args:
        token: Bot token
        message: Pesan yang akan dikirim
        use_html: Jika True, gunakan HTML parse mode, jika False coba Markdown lalu plain text
    """
    global active_chat_id, chat_id_confirmed
    
    with _chat_id_lock:
        current_chat_id = active_chat_id
        is_confirmed = chat_id_confirmed
    
    if not current_chat_id or not is_confirmed:
        logger.warning("No active chat_id or not confirmed. Please send /start to the bot first.")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parse_mode = "HTML" if use_html else "Markdown"
    max_retries = 3
    
    chat_id_to_use = current_chat_id
    markdown_failures = 0
    
    for attempt in range(max_retries):
        try:
            if markdown_failures >= 2:
                payload = {
                    "chat_id": chat_id_to_use,
                    "text": message.replace('**', '').replace('*', '').replace('`', '').replace('_', '')
                }
            else:
                payload = {
                    "chat_id": chat_id_to_use,
                    "text": message,
                    "parse_mode": parse_mode
                }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.debug(f"Message sent successfully to chat {chat_id_to_use}")
                return True
            elif response.status_code == 400:
                response_data = response.json()
                error_desc = response_data.get('description', 'Unknown error')
                
                if 'can\'t parse entities' in error_desc.lower() or 'bad request' in error_desc.lower():
                    markdown_failures += 1
                    logger.warning(f"Markdown parse error (attempt {attempt + 1}/{max_retries}): {error_desc}")
                    
                    if markdown_failures >= 2:
                        logger.info("Falling back to plain text mode")
                        continue
                else:
                    logger.error(f"Telegram API error: {error_desc}")
                    log_telegram_error(message, error_desc)
                    
            elif response.status_code == 429:
                retry_after = response.json().get('parameters', {}).get('retry_after', 5)
                logger.warning(f"Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            else:
                logger.error(f"Telegram API error {response.status_code}: {response.text}")
                log_telegram_error(message, f"Status {response.status_code}: {response.text}")
            
            backoff_time = (2 ** attempt) * 0.5
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {backoff_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff_time)
                
        except requests.exceptions.Timeout:
            logger.error(f"Telegram API timeout (attempt {attempt + 1}/{max_retries})")
            log_telegram_error(message, "Request timeout")
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 0.5)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error (attempt {attempt + 1}/{max_retries}): {e}")
            log_telegram_error(message, str(e))
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 0.5)
        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            log_telegram_error(message, str(e))
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 0.5)
    
    logger.error("All retry attempts failed for Telegram message")
    return False


def setup_trading_callbacks(telegram_token: str):
    """Setup callback functions untuk notifikasi trading
    
    Args:
        telegram_token: Token bot Telegram untuk mengirim pesan
    """
    global trading_manager
    
    if not trading_manager:
        return
        
    def on_trade_opened(contract_type: str, price: float, stake: float, 
                       trade_num: int, target: int):
        """Callback saat posisi dibuka"""
        target_text = f"/{target}" if target > 0 else ""
        stake_idr = stake * USD_TO_IDR
        message = (
            f"⏳ **ENTRY** (Trade {trade_num}{target_text})\n\n"
            f"• Tipe: {contract_type}\n"
            f"• Entry: {price:.5f}\n"
            f"• Stake: ${stake:.2f} (Rp {stake_idr:,.0f})"
        )
        send_telegram_message_sync(telegram_token, message)
        
    def on_trade_closed(is_win: bool, profit: float, balance: float,
                       trade_num: int, target: int, next_stake: float):
        """Callback saat posisi ditutup (win/loss)"""
        target_text = f"/{target}" if target > 0 else ""
        profit_idr = profit * USD_TO_IDR
        balance_idr = balance * USD_TO_IDR
        next_stake_idr = next_stake * USD_TO_IDR
        
        if is_win:
            message = (
                f"✅ **WIN** (Trade {trade_num}{target_text})\n\n"
                f"• Profit: +${profit:.2f} (Rp {profit_idr:,.0f})\n"
                f"• Saldo: ${balance:.2f} (Rp {balance_idr:,.0f})"
            )
        else:
            message = (
                f"❌ **LOSS** (Trade {trade_num}{target_text})\n\n"
                f"• Loss: -${abs(profit):.2f} (Rp {abs(profit_idr):,.0f})\n"
                f"• Saldo: ${balance:.2f} (Rp {balance_idr:,.0f})\n"
                f"• Next Stake: ${next_stake:.2f} (Rp {next_stake_idr:,.0f})"
            )
            
        send_telegram_message_sync(telegram_token, message)
        
    def on_session_complete(total: int, wins: int, losses: int, 
                           profit: float, win_rate: float):
        """Callback saat session selesai"""
        profit_emoji = "📈" if profit >= 0 else "📉"
        profit_idr = profit * USD_TO_IDR
        message = (
            f"🏁 **SESSION COMPLETE**\n\n"
            f"📊 Statistik:\n"
            f"• Total: {total} trades\n"
            f"• Win/Loss: {wins}/{losses}\n"
            f"• Win Rate: {win_rate:.1f}%\n\n"
            f"{profit_emoji} Net P/L: ${profit:+.2f} (Rp {profit_idr:+,.0f})"
        )
        send_telegram_message_sync(telegram_token, message)
        
    def on_error(error_msg: str):
        """Callback saat terjadi error"""
        message = f"⚠️ **ERROR**\n\n{error_msg}"
        send_telegram_message_sync(telegram_token, message)
    
    def on_progress(tick_count: int, required_ticks: int, rsi: float, trend: str):
        """Callback untuk progress notification saat mengumpulkan data"""
        global last_progress_notification_time
        
        try:
            logger.info(f"📊 on_progress called: tick={tick_count}/{required_ticks}, rsi={rsi}, trend={trend}")
            
            current_time = time.time()
            time_since_last = current_time - last_progress_notification_time
            
            if time_since_last < MIN_NOTIFICATION_INTERVAL:
                logger.debug(f"Skipping progress notification (debounce: {time_since_last:.1f}s < {MIN_NOTIFICATION_INTERVAL}s)")
                return
            
            if rsi > 0:
                rsi_text = f"{rsi:.1f}"
            else:
                rsi_text = "calculating..."
                
            progress_pct = int((tick_count / required_ticks) * 100) if required_ticks > 0 else 0
            progress_bar = "▓" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
            
            message = (
                f"📊 **Menganalisis market...**\n\n"
                f"• Progress: [{progress_bar}] {progress_pct}%\n"
                f"• Tick: {tick_count}/{required_ticks}\n"
                f"• RSI: {rsi_text}\n"
                f"• Trend: {trend}\n\n"
                f"⏳ Menunggu sinyal trading..."
            )
            
            result = send_telegram_message_sync(telegram_token, message)
            if result:
                last_progress_notification_time = current_time
                logger.info(f"✅ Progress message sent successfully")
            else:
                logger.warning(f"⚠️ Progress message not sent (no chat_id or error)")
        except Exception as e:
            logger.error(f"❌ Error in on_progress callback: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
    trading_manager.on_trade_opened = on_trade_opened
    trading_manager.on_trade_closed = on_trade_closed
    trading_manager.on_session_complete = on_session_complete
    trading_manager.on_error = on_error
    trading_manager.on_progress = on_progress


def shutdown_handler(signum, frame):
    """
    Graceful shutdown handler untuk SIGTERM dan SIGINT.
    Menunggu trade aktif selesai dan menyimpan session data.
    """
    global shutdown_requested, deriv_ws, trading_manager
    
    signal_name = signal.Signals(signum).name if hasattr(signal.Signals, 'name') else str(signum)
    logger.info(f"🛑 Received shutdown signal: {signal_name}")
    
    shutdown_requested = True
    
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if telegram_token and active_chat_id:
        send_telegram_message_sync(telegram_token, "🛑 **Bot shutting down gracefully...**")
    
    if trading_manager:
        from trading import TradingState
        
        if trading_manager.state in [TradingState.RUNNING, TradingState.WAITING_RESULT]:
            logger.info("⏳ Waiting for active trade to complete (max 5 minutes)...")
            
            max_wait = 300
            wait_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                if trading_manager.state not in [TradingState.RUNNING, TradingState.WAITING_RESULT]:
                    logger.info("✅ Active trade completed")
                    break
                time.sleep(wait_interval)
                elapsed += wait_interval
                logger.info(f"⏳ Still waiting... ({elapsed}s / {max_wait}s)")
            
            if elapsed >= max_wait:
                logger.warning("⚠️ Timeout waiting for trade completion, forcing stop")
        
        result = trading_manager.stop()
        logger.info(f"Trading manager stopped: {result}")
    
    if deriv_ws:
        try:
            deriv_ws.disconnect()
            logger.info("✅ WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    if telegram_token and active_chat_id:
        send_telegram_message_sync(telegram_token, "✅ **Bot shutdown complete.**")
    
    logger.info("🏁 Graceful shutdown complete")
    sys.exit(0)


def initialize_deriv():
    """Inisialisasi koneksi Deriv WebSocket dengan retry dan error handling"""
    global deriv_ws, trading_manager
    
    demo_token = os.environ.get("DERIV_TOKEN_DEMO", "")
    real_token = os.environ.get("DERIV_TOKEN_REAL", "")
    
    logger.info("=" * 50)
    logger.info("INITIALIZING DERIV CONNECTION")
    logger.info("=" * 50)
    
    # Log token availability (tanpa expose token)
    logger.info(f"Demo token available: {'Yes' if demo_token else 'No'}")
    logger.info(f"Real token available: {'Yes' if real_token else 'No'}")
    
    if not demo_token and not real_token:
        logger.warning("⚠️ No Deriv tokens found in environment!")
        logger.info("Please set DERIV_TOKEN_DEMO and/or DERIV_TOKEN_REAL in Replit Secrets")
        logger.info("Bot akan tetap berjalan tapi tidak bisa trading.")
        return False
    
    try:
        deriv_ws = DerivWebSocket(
            demo_token=demo_token,
            real_token=real_token
        )
        
        if deriv_ws.connect():
            # Tunggu authorization dengan timeout
            if deriv_ws.wait_until_ready(timeout=45):
                logger.info("✅ Deriv WebSocket ready!")
                trading_manager = TradingManager(deriv_ws)
                
                # Log account info
                if deriv_ws.account_info:
                    logger.info(f"   Account: {deriv_ws.account_info.account_id}")
                    logger.info(f"   Balance: {deriv_ws.account_info.balance} {deriv_ws.account_info.currency}")
                    logger.info(f"   Type: {'Demo' if deriv_ws.account_info.is_virtual else 'Real'}")
                    
                logger.info("=" * 50)
                return True
            else:
                # Log detail error
                logger.error("❌ Deriv WebSocket timeout waiting for authorization")
                logger.error(f"   Connection state: {deriv_ws.get_connection_status()}")
                logger.error(f"   Last error: {deriv_ws.get_last_auth_error()}")
                logger.info("Bot akan tetap berjalan. Coba /akun untuk reconnect.")
                logger.info("=" * 50)
                
                # Tetap buat trading manager untuk retry nanti
                trading_manager = TradingManager(deriv_ws)
                return False
        else:
            logger.error("❌ Failed to connect to Deriv WebSocket")
            logger.info("Periksa koneksi internet dan coba lagi.")
            logger.info("=" * 50)
            return False
            
    except Exception as e:
        logger.error(f"❌ Exception during Deriv initialization: {type(e).__name__}: {e}")
        logger.info("=" * 50)
        return False


def main():
    """Main function - entry point aplikasi"""
    global active_chat_id, chat_id_confirmed
    
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    
    if not telegram_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found!")
        logger.info("Please set TELEGRAM_BOT_TOKEN in Replit Secrets")
        return
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    logger.info("✅ Signal handlers registered (SIGTERM, SIGINT)")
    
    loaded_chat_id = load_chat_id()
    if loaded_chat_id:
        with _chat_id_lock:
            active_chat_id = loaded_chat_id
        logger.info(f"📂 Chat ID pre-loaded (requires /start to confirm): {active_chat_id}")
        
    start_keep_alive()
    initialize_deriv()
    
    app = ApplicationBuilder().token(telegram_token).build()
    
    setup_trading_callbacks(telegram_token)
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("akun", akun_command))
    app.add_handler(CommandHandler("autotrade", autotrade_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
