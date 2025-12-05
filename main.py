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
import asyncio
import logging
from typing import Optional
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

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

deriv_ws: Optional[DerivWebSocket] = None
trading_manager: Optional[TradingManager] = None
active_chat_id: Optional[int] = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    global active_chat_id
    if not update.effective_chat or not update.message:
        return
    active_chat_id = update.effective_chat.id
    
    welcome_text = (
        "🤖 **DERIV AUTO TRADING BOT**\n\n"
        "Bot trading otomatis untuk Binary Options (Volatility Index).\n"
        "Menggunakan strategi RSI + Martingale.\n\n"
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
    help_text = (
        "📚 **PANDUAN PENGGUNAAN**\n\n"
        "**1️⃣ Setup Akun**\n"
        "Gunakan /akun untuk:\n"
        "• Cek saldo real-time\n"
        "• Switch antara Demo/Real\n\n"
        "**2️⃣ Mulai Trading**\n"
        "Format: `/autotrade [stake] [durasi] [target] [symbol]`\n\n"
        "Contoh:\n"
        "• `/autotrade` - Default ($0.50, 5t, 5 trade, R_100)\n"
        "• `/autotrade 0.5` - Stake $0.5\n"
        "• `/autotrade 1 5t 10` - $1, 5 ticks, 10 trade\n"
        "• `/autotrade 0.50 5t 0 R_50` - Unlimited, R_50\n\n"
        "**Format Durasi:**\n"
        "• `5t` = 5 ticks (untuk Synthetic)\n"
        "• `30s` = 30 detik\n"
        "• `1m` = 1 menit\n"
        "• `1d` = 1 hari (untuk XAUUSD)\n\n"
        "**3️⃣ Symbol Tersedia**\n"
        "Short-term (ticks): R_100, R_75, R_50, R_25, R_10\n"
        "1-second: 1HZ100V, 1HZ75V, 1HZ50V\n"
        "Long-term (hari): frxXAUUSD\n\n"
        "**4️⃣ Strategi RSI**\n"
        "• BUY (Call): RSI < 30 (Oversold)\n"
        "• SELL (Put): RSI > 70 (Overbought)\n\n"
        "**5️⃣ Martingale**\n"
        "• WIN: Stake reset ke awal\n"
        "• LOSS: Stake x 2.1\n\n"
        "⚠️ *Trading memiliki risiko tinggi!*"
    )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua inline button callbacks"""
    global deriv_ws, trading_manager
    
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    
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
            "📚 **QUICK HELP**\n\n"
            "• /akun - Kelola akun\n"
            "• /autotrade - Mulai trading\n"
            "• /stop - Stop trading\n"
            "• /status - Cek status\n"
            "• /help - Panduan lengkap"
        )
        keyboard = [[InlineKeyboardButton("« Kembali", callback_data="menu_main")]]
        await query.edit_message_text(
            help_text,
            parse_mode="Markdown",
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
            deriv_ws.disconnect()
            deriv_ws.connect()
            await query.edit_message_text(
                "🔌 Mereset koneksi...\n\nTunggu beberapa detik.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Kembali", callback_data="menu_akun")]
                ])
            )
            


async def send_telegram_message(app: Application, message: str):
    """Helper untuk kirim pesan ke Telegram dari thread lain"""
    global active_chat_id
    if active_chat_id:
        try:
            await app.bot.send_message(
                chat_id=active_chat_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")


def setup_trading_callbacks(app: Application):
    """Setup callback functions untuk notifikasi trading"""
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
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(send_telegram_message(app, message), loop)
        
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
            
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(send_telegram_message(app, message), loop)
        
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
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(send_telegram_message(app, message), loop)
        
    def on_error(error_msg: str):
        """Callback saat terjadi error"""
        message = f"⚠️ **ERROR**\n\n{error_msg}"
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(send_telegram_message(app, message), loop)
        
    trading_manager.on_trade_opened = on_trade_opened
    trading_manager.on_trade_closed = on_trade_closed
    trading_manager.on_session_complete = on_session_complete
    trading_manager.on_error = on_error


def initialize_deriv():
    """Inisialisasi koneksi Deriv WebSocket"""
    global deriv_ws, trading_manager
    
    demo_token = os.environ.get("DERIV_TOKEN_DEMO", "")
    real_token = os.environ.get("DERIV_TOKEN_REAL", "")
    
    if not demo_token and not real_token:
        logger.warning("⚠️ No Deriv tokens found in environment!")
        logger.info("Please set DERIV_TOKEN_DEMO and/or DERIV_TOKEN_REAL in Replit Secrets")
        return False
        
    deriv_ws = DerivWebSocket(
        demo_token=demo_token,
        real_token=real_token
    )
    
    if deriv_ws.connect():
        if deriv_ws.wait_until_ready(timeout=30):
            logger.info("✅ Deriv WebSocket ready!")
            trading_manager = TradingManager(deriv_ws)
            return True
        else:
            logger.error("❌ Deriv WebSocket timeout waiting for authorization")
            return False
    else:
        logger.error("❌ Failed to connect to Deriv")
        return False


def main():
    """Main function - entry point aplikasi"""
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    
    if not telegram_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found!")
        logger.info("Please set TELEGRAM_BOT_TOKEN in Replit Secrets")
        return
        
    start_keep_alive()
    initialize_deriv()
    
    app = ApplicationBuilder().token(telegram_token).build()
    setup_trading_callbacks(app)
    
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
