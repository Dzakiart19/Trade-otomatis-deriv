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
import hashlib
from typing import Optional, Dict
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
from pair_scanner import PairScanner
from symbols import (
    SUPPORTED_SYMBOLS,
    DEFAULT_SYMBOL,
    MIN_STAKE_GLOBAL,
    get_symbol_config,
    get_short_term_symbols,
    get_long_term_symbols,
    get_symbol_list_text
)
from user_auth import auth_manager, UserAuthManager, ensure_authenticated, ALLOWED_CALLBACKS_WITHOUT_AUTH
from event_bus import get_event_bus

USD_TO_IDR = 15800
CHAT_ID_FILE = "logs/active_chat_id.txt"
USER_CHAT_MAPPING_FILE = "logs/chat_mapping.json"

load_dotenv()


def escape_md_chars(text: str) -> str:
    """Escape special Markdown characters to prevent parsing errors"""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def markdown_to_html(text: str) -> str:
    """Convert basic Markdown to HTML for fallback"""
    import re
    text = text.replace('**', '<b>').replace('*', '<i>')
    text = re.sub(r'<b>([^<]+)<b>', r'<b>\1</b>', text)
    text = re.sub(r'<i>([^<]+)<i>', r'<i>\1</i>', text)
    text = text.replace('`', '<code>').replace('<code><code>', '</code>')
    text = re.sub(r'<code>([^<]+)<code>', r'<code>\1</code>', text)
    return text


async def safe_send_message(
    target,
    text: str,
    reply_markup=None,
    is_edit: bool = False
) -> bool:
    """
    Send message with Markdown, fallback to HTML if parsing fails.
    
    Args:
        target: Update.message or CallbackQuery for sending
        text: Message text
        reply_markup: Optional keyboard markup
        is_edit: True if editing existing message
        
    Returns:
        True if message sent successfully
    """
    try:
        if is_edit:
            await target.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await target.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return True
    except Exception as e:
        if "Can't parse entities" in str(e) or "parse" in str(e).lower():
            try:
                html_text = markdown_to_html(text)
                if is_edit:
                    await target.edit_message_text(
                        html_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                else:
                    await target.reply_text(
                        html_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                return True
            except Exception as e2:
                try:
                    plain_text = text.replace('**', '').replace('*', '').replace('`', '')
                    if is_edit:
                        await target.edit_message_text(plain_text, reply_markup=reply_markup)
                    else:
                        await target.reply_text(plain_text, reply_markup=reply_markup)
                    return True
                except Exception as e3:
                    logger.error(f"Failed to send message: {e3}")
                    return False
        else:
            logger.error(f"Message send error: {e}")
            return False

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

deriv_ws: Optional[DerivWebSocket] = None
trading_manager: Optional[TradingManager] = None
pair_scanner: Optional[PairScanner] = None
active_chat_id: Optional[int] = None
chat_id_confirmed: bool = False
shutdown_requested: bool = False
last_progress_notification_time: float = 0.0
MIN_NOTIFICATION_INTERVAL: float = 2.0
current_connected_user_id: Optional[int] = None

import threading
import json
_chat_id_lock = threading.Lock()
_deriv_lock = threading.Lock()
_user_chat_mapping_lock = threading.Lock()

_last_message_hashes: Dict[str, float] = {}
_MESSAGE_HASH_TTL: int = 60
_message_hash_lock = threading.Lock()

_last_send_time: Dict[int, float] = {}
_MIN_SEND_INTERVAL: float = 1.0
_rate_limit_lock = threading.Lock()

user_chat_mapping: Dict[int, int] = {}


def load_user_chat_mapping() -> Dict[int, int]:
    """Load user_id -> chat_id mapping dari file JSON (thread-safe)"""
    global user_chat_mapping
    with _user_chat_mapping_lock:
        try:
            if os.path.exists(USER_CHAT_MAPPING_FILE):
                with open(USER_CHAT_MAPPING_FILE, "r") as f:
                    data = json.load(f)
                    user_chat_mapping = {int(k): int(v) for k, v in data.items()}
                    logger.info(f"📂 User chat mapping loaded: {len(user_chat_mapping)} users")
                    return user_chat_mapping
        except Exception as e:
            logger.error(f"Failed to load user chat mapping: {e}")
        return {}


def save_user_chat_mapping() -> bool:
    """Save user_chat_mapping ke file JSON (thread-safe)"""
    global user_chat_mapping
    with _user_chat_mapping_lock:
        try:
            os.makedirs("logs", exist_ok=True)
            with open(USER_CHAT_MAPPING_FILE, "w") as f:
                json.dump({str(k): v for k, v in user_chat_mapping.items()}, f)
            logger.info(f"💾 User chat mapping saved: {len(user_chat_mapping)} users")
            return True
        except Exception as e:
            logger.error(f"Failed to save user chat mapping: {e}")
            return False


def save_user_chat_id(user_id: int, chat_id: int) -> bool:
    """Save chat_id untuk user tertentu ke mapping (thread-safe)"""
    global user_chat_mapping
    with _user_chat_mapping_lock:
        user_chat_mapping[user_id] = chat_id
        logger.info(f"💾 Chat ID saved for user {user_id}: {chat_id}")
    return save_user_chat_mapping()


def get_user_chat_id(user_id: int) -> Optional[int]:
    """Get chat_id untuk user tertentu dari mapping (thread-safe)"""
    with _user_chat_mapping_lock:
        return user_chat_mapping.get(user_id)


def save_chat_id(chat_id: int) -> bool:
    """Save chat_id ke file untuk persistence setelah restart (thread-safe) - DEPRECATED"""
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
    """Load chat_id dari file setelah bot restart (thread-safe) - DEPRECATED"""
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


def cleanup_old_logs(max_days: int = 1, keep_today_trades: bool = True) -> int:
    """
    Auto-cleanup file log dan backup lama untuk menghemat penyimpanan.
    
    Args:
        max_days: Hapus file lebih tua dari N hari (default: 1)
        keep_today_trades: Simpan file trades hari ini (default: True)
    
    Returns:
        Jumlah file yang dihapus
    """
    import glob
    from datetime import datetime, timedelta
    
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        return 0
    
    deleted_count = 0
    today_str = datetime.now().strftime("%Y%m%d")
    cutoff_time = time.time() - (max_days * 86400)
    
    patterns_to_clean = [
        "trades_*_backup_*.csv",
        "analytics_*.json",
        "session_*.txt",
    ]
    
    for pattern in patterns_to_clean:
        for filepath in glob.glob(os.path.join(logs_dir, pattern)):
            try:
                file_mtime = os.path.getmtime(filepath)
                if file_mtime < cutoff_time:
                    os.remove(filepath)
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {filepath}: {e}")
    
    if not keep_today_trades:
        for filepath in glob.glob(os.path.join(logs_dir, "trades_*.csv")):
            if "_backup_" not in filepath:
                try:
                    if today_str not in filepath:
                        os.remove(filepath)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {filepath}: {e}")
    
    if deleted_count > 0:
        logger.info(f"🧹 Auto-cleanup: Deleted {deleted_count} old log files")
    
    return deleted_count


def connect_user_deriv(user_id: int) -> tuple[bool, str]:
    """
    Koneksi atau reconnect WebSocket dengan token user yang sudah login.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        (success, message)
    """
    global deriv_ws, trading_manager, pair_scanner, current_connected_user_id
    
    with _deriv_lock:
        user_token = auth_manager.get_user_token(user_id)
        account_type = auth_manager.get_user_account_type(user_id)
        
        if not user_token:
            logger.error(f"❌ No token found for user {user_id}")
            auth_manager.clear_invalid_session(user_id)
            return False, "Token tidak ditemukan atau sudah expired. Silakan login ulang dengan /login."
        
        if not account_type:
            account_type = "demo"
        
        logger.info(f"🔌 Connecting Deriv for user {user_id} ({account_type})")
        
        if deriv_ws and deriv_ws.is_connected:
            try:
                deriv_ws.disconnect()
                logger.info("📴 Previous WebSocket disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting previous WS: {e}")
        
        try:
            if account_type.lower() == "demo":
                deriv_ws = DerivWebSocket(
                    demo_token=user_token,
                    real_token=""
                )
                deriv_ws.current_account_type = AccountType.DEMO
            else:
                deriv_ws = DerivWebSocket(
                    demo_token="",
                    real_token=user_token
                )
                deriv_ws.current_account_type = AccountType.REAL
            
            if deriv_ws.connect():
                if deriv_ws.wait_until_ready(timeout=45):
                    logger.info("✅ Deriv WebSocket connected and authorized!")
                    
                    trading_manager = TradingManager(deriv_ws)
                    
                    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                    if telegram_token:
                        setup_trading_callbacks(telegram_token)
                        logger.info("✅ Trading callbacks configured for Telegram notifications")
                    
                    pair_scanner = PairScanner(deriv_ws)
                    pair_scanner.start_scanning()
                    
                    current_connected_user_id = user_id
                    
                    if deriv_ws.account_info:
                        logger.info(f"   Account: {deriv_ws.account_info.account_id}")
                        logger.info(f"   Balance: {deriv_ws.account_info.balance} {deriv_ws.account_info.currency}")
                        
                    return True, "Koneksi berhasil!"
                else:
                    error_msg = deriv_ws.get_last_auth_error() if hasattr(deriv_ws, 'get_last_auth_error') else "Unknown"
                    logger.error(f"❌ Authorization timeout. Error: {error_msg}")
                    return False, f"Gagal otorisasi: {error_msg}"
            else:
                logger.error("❌ Failed to connect to Deriv WebSocket")
                return False, "Gagal koneksi ke Deriv"
                
        except Exception as e:
            logger.error(f"❌ Exception during connection: {type(e).__name__}: {e}")
            return False, f"Error: {str(e)}"


async def connect_user_deriv_async(user_id: int) -> tuple[bool, str]:
    """Async wrapper untuk connect_user_deriv"""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, connect_user_deriv, user_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    global active_chat_id, chat_id_confirmed, deriv_ws, current_connected_user_id
    if not update.effective_chat or not update.message or not update.effective_user:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    with _chat_id_lock:
        active_chat_id = chat_id
        chat_id_confirmed = True
    
    if active_chat_id is not None:
        save_chat_id(active_chat_id)
    
    save_user_chat_id(user_id, chat_id)
    is_logged_in = auth_manager.is_authenticated(user_id)
    
    if is_logged_in:
        needs_connect = (
            not deriv_ws or 
            not deriv_ws.is_ready() or 
            current_connected_user_id != user_id
        )
        
        if needs_connect:
            await update.message.reply_text(
                "🔄 Menghubungkan ke Deriv...\n\nMohon tunggu sebentar.",
                parse_mode="Markdown"
            )
            
            success, msg = await connect_user_deriv_async(user_id)
            
            if not success:
                await update.message.reply_text(
                    f"❌ **Gagal koneksi ke Deriv**\n\n{msg}\n\n"
                    "Coba /login untuk login ulang dengan token baru.",
                    parse_mode="Markdown"
                )
                return
        user_info = auth_manager.get_user_info(user_id)
        account_type = user_info['account_type'].upper() if user_info else "UNKNOWN"
        account_emoji = "🎮" if account_type == "DEMO" else "💵"
        
        welcome_text = (
            f"🤖 **DERIV AUTO TRADING BOT v2.0**\n\n"
            f"Selamat datang kembali! {account_emoji}\n"
            f"Akun: **{account_type}**\n\n"
            f"📊 **Indicators:** RSI, EMA, MACD, Stochastic, ATR\n\n"
            f"📋 **Menu Utama:**\n"
            f"• /akun - Kelola akun (saldo, switch demo/real)\n"
            f"• /autotrade - Mulai auto trading\n"
            f"• /stop - Hentikan trading\n"
            f"• /status - Cek status bot\n"
            f"• /help - Panduan lengkap\n\n"
            f"⚠️ *Trading memiliki risiko. Gunakan dengan bijak.*"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("💰 Cek Akun", callback_data="menu_akun"),
                InlineKeyboardButton("🚀 Auto Trade", callback_data="menu_autotrade")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="menu_status"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help")
            ],
            [InlineKeyboardButton("👋 Logout", callback_data="confirm_logout")]
        ]
    else:
        welcome_text = (
            "🤖 **DERIV AUTO TRADING BOT v2.0**\n\n"
            "Selamat datang! Bot ini adalah bot trading otomatis\n"
            "untuk Binary Options (Volatility Index).\n\n"
            "🔐 **Anda belum login**\n\n"
            "Untuk menggunakan bot ini, Anda harus login terlebih dahulu\n"
            "dengan token API Deriv Anda.\n\n"
            "📍 **Cara Login:**\n"
            "1. Klik tombol LOGIN di bawah\n"
            "2. Pilih tipe akun (Demo/Real)\n"
            "3. Kirim token API Deriv Anda\n\n"
            "⚠️ *Token Anda akan dienkripsi dan disimpan dengan aman.*"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔐 LOGIN", callback_data="start_login")],
            [InlineKeyboardButton("❓ Help", callback_data="menu_help")]
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
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    if not auth_manager.is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 **AKSES DITOLAK**\n\n"
            "Anda belum login. Gunakan /login terlebih dahulu.",
            parse_mode="Markdown"
        )
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
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    if not auth_manager.is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 **AKSES DITOLAK**\n\n"
            "Anda belum login. Gunakan /login terlebih dahulu.",
            parse_mode="Markdown"
        )
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
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    if not auth_manager.is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 **AKSES DITOLAK**\n\n"
            "Anda belum login. Gunakan /login terlebih dahulu.",
            parse_mode="Markdown"
        )
        return
    
    if not trading_manager:
        await update.message.reply_text("❌ Trading manager belum siap.")
        return
        
    result = trading_manager.stop()
    await update.message.reply_text(result, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /status"""
    global deriv_ws, trading_manager
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    if not auth_manager.is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 **AKSES DITOLAK**\n\n"
            "Anda belum login. Gunakan /login terlebih dahulu.",
            parse_mode="Markdown"
        )
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


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /login - Mulai proses login dengan pilih akun Demo/Real"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    if auth_manager.is_authenticated(user_id):
        user_info = auth_manager.get_user_info(user_id)
        if user_info:
            await update.message.reply_text(
                f"✅ Anda sudah login!\n\n"
                f"• Tipe: {user_info['account_type'].upper()}\n"
                f"• Token ID: ...{user_info['token_fingerprint'][-8:]}\n\n"
                f"Gunakan /logout untuk keluar, atau /autotrade untuk trading.",
                parse_mode="Markdown"
            )
            return
    
    is_locked, remaining = auth_manager.is_locked_out(user_id)
    if is_locked:
        await update.message.reply_text(
            f"🔒 **AKUN TERKUNCI**\n\n"
            f"Terlalu banyak percobaan gagal.\n"
            f"Coba lagi dalam {remaining} detik.",
            parse_mode="Markdown"
        )
        return
    
    login_text = (
        "🔐 **LOGIN KE DERIV**\n\n"
        "Pilih tipe akun yang ingin Anda gunakan:\n\n"
        "• **DEMO** 🎮 - Akun virtual untuk latihan\n"
        "• **REAL** 💵 - Akun dengan uang asli\n\n"
        "⚠️ *Token Anda akan dienkripsi dan disimpan dengan aman.*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🎮 DEMO", callback_data="login_demo"),
            InlineKeyboardButton("💵 REAL", callback_data="login_real")
        ],
        [InlineKeyboardButton("❌ Batal", callback_data="login_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        login_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /logout - Logout dari akun"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    success, message = auth_manager.logout(user_id)
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /whoami - Tampilkan info user yang login"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    if not auth_manager.is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 Anda belum login.\n\nGunakan /login untuk masuk dengan token Deriv.",
            parse_mode="Markdown"
        )
        return
    
    user_info = auth_manager.get_user_info(user_id)
    if not user_info:
        await update.message.reply_text("❌ Gagal mendapatkan info user.")
        return
    
    whoami_text = (
        f"👤 **INFO AKUN ANDA**\n\n"
        f"• User ID: `{user_info['user_id']}`\n"
        f"• Username: @{user_info['username'] or 'N/A'}\n"
        f"• Tipe Akun: **{user_info['account_type'].upper()}** "
        f"{'🎮' if user_info['account_type'] == 'demo' else '💵'}\n"
        f"• Token ID: `...{user_info['token_fingerprint'][-8:]}`\n"
        f"• Login: {user_info['created_at'][:19]}\n"
        f"• Terakhir aktif: {user_info['last_used'][:19]}"
    )
    
    keyboard = [
        [InlineKeyboardButton("👋 Logout", callback_data="confirm_logout")],
        [InlineKeyboardButton("🔄 Switch Akun", callback_data="switch_account")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        whoami_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def token_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menerima token dari user saat proses login"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if not message_text:
        return
    
    if message_text.startswith('/'):
        return
    
    if not auth_manager.has_pending_login(user_id):
        return
    
    try:
        await update.message.delete()
        logger.info(f"🗑️ Token message deleted for user {user_id} (security)")
    except Exception as e:
        logger.warning(f"Could not delete token message: {e}")
        await update.message.reply_text(
            "⚠️ *Tidak bisa menghapus pesan token. Harap hapus manual untuk keamanan.*",
            parse_mode="Markdown"
        )
    
    success, result_msg = auth_manager.complete_login(user_id, message_text)
    
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=result_msg,
        parse_mode="Markdown"
    )
    
    if success:
        logger.info(f"✅ User {user_id} logged in successfully")
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔄 Menghubungkan ke Deriv...",
            parse_mode="Markdown"
        )
        
        connect_success, connect_msg = await connect_user_deriv_async(user_id)
        
        if connect_success:
            balance_text = ""
            if deriv_ws and deriv_ws.account_info:
                balance = deriv_ws.account_info.balance
                balance_idr = balance * USD_TO_IDR
                balance_text = f"\n💰 Saldo: **${balance:.2f}** (Rp {balance_idr:,.0f})"
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **Koneksi Berhasil!**{balance_text}\n\n"
                     f"Gunakan /autotrade untuk mulai trading.\n"
                     f"Atau ketik /start untuk menu utama.",
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ **Login berhasil tapi koneksi gagal**\n\n"
                     f"{connect_msg}\n\n"
                     f"Ketik /start untuk mencoba koneksi ulang.",
                parse_mode="Markdown"
            )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua inline button callbacks"""
    global deriv_ws, trading_manager, pair_scanner, active_chat_id, chat_id_confirmed
    
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
        if new_chat_id is not None:
            save_chat_id(new_chat_id)
    
    data = query.data
    user_id = query.from_user.id if query.from_user else None
    
    CALLBACKS_ALLOWED_WITHOUT_AUTH = {
        "login_demo", "login_real", "login_cancel", 
        "start_login", "menu_help"
    }
    
    if data not in CALLBACKS_ALLOWED_WITHOUT_AUTH:
        if not user_id or not auth_manager.is_authenticated(user_id):
            await query.edit_message_text(
                "🔒 **AKSES DITOLAK**\n\n"
                "Anda belum login. Gunakan /login untuk masuk dengan token Deriv Anda.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 LOGIN", callback_data="start_login")]
                ])
            )
            return
    
    if data == "start_login":
        login_text = (
            "🔐 **LOGIN KE DERIV**\n\n"
            "Pilih tipe akun yang ingin Anda gunakan:\n\n"
            "• **DEMO** 🎮 - Akun virtual untuk latihan\n"
            "• **REAL** 💵 - Akun dengan uang asli\n\n"
            "⚠️ *Token Anda akan dienkripsi dan disimpan dengan aman.*"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🎮 DEMO", callback_data="login_demo"),
                InlineKeyboardButton("💵 REAL", callback_data="login_real")
            ],
            [InlineKeyboardButton("❌ Batal", callback_data="login_cancel")]
        ]
        
        await query.edit_message_text(
            login_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "login_demo" or data == "login_real":
        user_id = query.from_user.id if query.from_user else None
        if not user_id:
            await query.edit_message_text("❌ Error: User tidak teridentifikasi.")
            return
        
        account_type = "demo" if data == "login_demo" else "real"
        username = query.from_user.username if query.from_user else None
        
        if not auth_manager.start_login(user_id, username, account_type):
            is_locked, remaining = auth_manager.is_locked_out(user_id)
            await query.edit_message_text(
                f"🔒 **AKUN TERKUNCI**\n\n"
                f"Terlalu banyak percobaan gagal.\n"
                f"Coba lagi dalam {remaining} detik.",
                parse_mode="Markdown"
            )
            return
        
        token_request_text = (
            f"🔑 **MASUKKAN TOKEN {account_type.upper()}**\n\n"
            f"Kirim token API Deriv Anda untuk akun **{account_type.upper()}**.\n\n"
            f"📍 Cara mendapatkan token:\n"
            f"1. Login ke deriv.com\n"
            f"2. Buka Settings → API Token\n"
            f"3. Buat token baru dengan scope 'Trade'\n"
            f"4. Copy dan kirim token ke sini\n\n"
            f"⚠️ *Token akan otomatis dihapus setelah diterima untuk keamanan.*"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Batal", callback_data="login_cancel")]]
        
        await query.edit_message_text(
            token_request_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "login_cancel":
        user_id = query.from_user.id if query.from_user else None
        if user_id:
            auth_manager.cancel_login(user_id)
        
        await query.edit_message_text(
            "❌ Login dibatalkan.\n\nGunakan /login untuk mencoba lagi.",
            parse_mode="Markdown"
        )
        
    elif data == "confirm_logout":
        user_id = query.from_user.id if query.from_user else None
        if not user_id:
            await query.edit_message_text("❌ Error: User tidak teridentifikasi.")
            return
        
        success, message = auth_manager.logout(user_id)
        await query.edit_message_text(message, parse_mode="Markdown")
        
    elif data == "switch_account":
        user_id = query.from_user.id if query.from_user else None
        if user_id:
            auth_manager.logout(user_id)
        
        login_text = (
            "🔄 **SWITCH AKUN**\n\n"
            "Akun sebelumnya telah di-logout.\n"
            "Pilih tipe akun baru:\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🎮 DEMO", callback_data="login_demo"),
                InlineKeyboardButton("💵 REAL", callback_data="login_real")
            ],
            [InlineKeyboardButton("❌ Batal", callback_data="login_cancel")]
        ]
        
        await query.edit_message_text(
            login_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "menu_akun":
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
            "Pilih opsi trading:\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎯 Rekomendasi Saat Ini", callback_data="menu_recommendations")],
            [InlineKeyboardButton("📊 Pilih Symbol Manual", callback_data="select_symbol")],
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
                try:
                    await query.edit_message_text(config_msg, parse_mode="Markdown")
                except Exception:
                    await query.edit_message_text(config_msg)
                return
                
            result = trading_manager.start()
            combined_msg = f"{config_msg}\n\n{result}"
            try:
                await query.edit_message_text(combined_msg, parse_mode="Markdown")
            except Exception:
                try:
                    await query.edit_message_text(markdown_to_html(combined_msg), parse_mode="HTML")
                except Exception:
                    await query.edit_message_text(combined_msg.replace('*', '').replace('`', ''))
            
    elif data == "quick_menu":
        trade_text = (
            "⚡ **QUICK START (R_100)**\n\n"
            "Trading cepat dengan Volatility 100:\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("$0.50 | 5x", callback_data="exec~R_100~5t~050~5"),
                InlineKeyboardButton("$1 | 5x", callback_data="exec~R_100~5t~1~5")
            ],
            [
                InlineKeyboardButton("$2 | 5x", callback_data="exec~R_100~5t~2~5"),
                InlineKeyboardButton("$5 | 5x", callback_data="exec~R_100~5t~5~5")
            ],
            [
                InlineKeyboardButton("$10 | 5x", callback_data="exec~R_100~5t~10~5"),
                InlineKeyboardButton("$25 | 5x", callback_data="exec~R_100~5t~25~5")
            ],
            [
                InlineKeyboardButton("$1 | ∞", callback_data="exec~R_100~5t~1~0"),
                InlineKeyboardButton("$5 | ∞", callback_data="exec~R_100~5t~5~0")
            ],
            [InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")]
        ]
        await query.edit_message_text(
            trade_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_recommendations":
        if not pair_scanner:
            if deriv_ws and deriv_ws.is_ready():
                pair_scanner = PairScanner(deriv_ws)
                pair_scanner.start_scanning()
                logger.info("✅ PairScanner initialized on-demand")
            else:
                await query.edit_message_text(
                    "❌ Scanner belum siap. Koneksi belum terhubung.\n\n"
                    "Coba reset koneksi di menu Akun.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu_recommendations")],
                        [InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")]
                    ])
                )
                return
        
        if not pair_scanner.is_scanning:
            if deriv_ws and deriv_ws.is_ready():
                pair_scanner.start_scanning()
                logger.info("✅ PairScanner re-started")
            
        scanner_status = pair_scanner.get_scanner_status()
        recommendations = pair_scanner.get_recommendations(top_n=5)
        
        if not recommendations:
            if scanner_status['symbols_with_data'] == 0:
                rec_text = (
                    "🎯 **REKOMENDASI SAAT INI**\n\n"
                    "⏳ **Mengumpulkan data...**\n\n"
                    f"• Scanning {scanner_status['total_symbols']} pairs\n"
                    f"• Data tersedia: {scanner_status['symbols_with_data']}\n"
                    f"• Min ticks: {scanner_status['min_ticks_required']}\n\n"
                    "Tunggu 30-60 detik untuk data cukup."
                )
            else:
                all_pairs = pair_scanner.get_all_pair_status()
                pairs_analyzed = [p for p in all_pairs if p.get('has_enough_data', False)]
                
                rec_text = (
                    "🎯 **REKOMENDASI SAAT INI**\n\n"
                    "⚠️ **Tidak ada signal aktif**\n\n"
                    f"• {scanner_status['symbols_with_data']} pairs sudah dianalisis\n"
                    f"• {scanner_status['symbols_with_signal']} dengan signal\n\n"
                )
                
                if pairs_analyzed:
                    rec_text += "📊 **Pairs yang dianalisis:**\n"
                    for p in pairs_analyzed[:8]:
                        trend_icon = "📈" if p.get('trend_direction') == "UP" else ("📉" if p.get('trend_direction') == "DOWN" else "➡️")
                        rec_text += f"• {p['name']} ({p['symbol']}): {trend_icon} {p.get('trend_direction', 'SIDEWAYS')}\n"
                    rec_text += "\n"
                
                rec_text += "Semua pair sedang SIDEWAYS. Tunggu atau pilih manual."
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="menu_recommendations")],
                [InlineKeyboardButton("📊 Pilih Manual", callback_data="select_symbol")],
                [InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")]
            ]
        else:
            rec_text = (
                "🎯 **REKOMENDASI SAAT INI**\n\n"
                "Pair dengan signal terbaik:\n\n"
            )
            
            keyboard = []
            for i, rec in enumerate(recommendations, 1):
                signal_emoji = "🟢" if rec['signal'] == "CALL" else "🔴"
                trend_emoji = "📈" if rec['trend_direction'] == "UP" else ("📉" if rec['trend_direction'] == "DOWN" else "➡️")
                
                rec_text += (
                    f"**{i}. {rec['name']}** {signal_emoji}\n"
                    f"   Signal: {rec['signal']} | Score: {rec['score']:.0f}/100\n"
                    f"   RSI: {rec['rsi']:.1f} | ADX: {rec['adx']:.1f}\n"
                    f"   Trend: {trend_emoji} {rec['trend_direction']}\n"
                    f"   Conf: {rec['confidence']*100:.0f}%\n\n"
                )
                
                btn_text = f"{signal_emoji} {rec['symbol']} ({rec['score']:.0f})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"rec_trade~{rec['symbol']}")])
            
            keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_recommendations")])
            keyboard.append([InlineKeyboardButton("« Kembali", callback_data="menu_autotrade")])
        
        await query.edit_message_text(
            rec_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("rec_trade~"):
        symbol = data[10:]
        config = get_symbol_config(symbol)
        
        if not config:
            await query.edit_message_text(
                f"❌ Symbol {symbol} tidak ditemukan.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Kembali", callback_data="menu_recommendations")]
                ])
            )
            return
        
        if not trading_manager:
            await query.edit_message_text(
                "❌ Trading manager belum siap. Tunggu beberapa detik...",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data=f"rec_trade~{symbol}")],
                    [InlineKeyboardButton("« Kembali", callback_data="menu_recommendations")]
                ])
            )
            return
        
        current_signal = "UNKNOWN"
        current_score = 0
        current_rsi = 50.0
        current_adx = 0
        if pair_scanner:
            all_status = pair_scanner.get_all_pair_status()
            for pair in all_status:
                if pair['symbol'] == symbol:
                    current_signal = pair['signal']
                    current_score = pair['score']
                    current_rsi = pair['rsi']
                    current_adx = pair['adx']
                    break
        
        signal_emoji = "🟢" if current_signal == "CALL" else ("🔴" if current_signal == "PUT" else "⚪")
        
        trade_setup = (
            f"⚙️ **TRADING: {config.name}**\n\n"
            f"• Symbol: `{symbol}`\n"
            f"• Signal: {signal_emoji} **{current_signal}**\n"
            f"• Score: {current_score:.0f}/100\n"
            f"• RSI: {current_rsi:.1f} | ADX: {current_adx:.1f}\n"
            f"• Durasi: 5 ticks\n\n"
            "Pilih stake dan target:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("$0.50 | 5x", callback_data=f"exec~{symbol}~5t~050~5"),
                InlineKeyboardButton("$1 | 5x", callback_data=f"exec~{symbol}~5t~1~5")
            ],
            [
                InlineKeyboardButton("$2 | 5x", callback_data=f"exec~{symbol}~5t~2~5"),
                InlineKeyboardButton("$5 | 5x", callback_data=f"exec~{symbol}~5t~5~5")
            ],
            [
                InlineKeyboardButton("$10 | 5x", callback_data=f"exec~{symbol}~5t~10~5"),
                InlineKeyboardButton("$25 | 5x", callback_data=f"exec~{symbol}~5t~25~5")
            ],
            [
                InlineKeyboardButton("$1 | ∞", callback_data=f"exec~{symbol}~5t~1~0"),
                InlineKeyboardButton("$5 | ∞", callback_data=f"exec~{symbol}~5t~5~0")
            ],
            [InlineKeyboardButton("« Kembali", callback_data="menu_recommendations")]
        ]
        await query.edit_message_text(
            trade_setup,
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


def _get_message_hash(message: str) -> str:
    """Generate hash dari message untuk deduplication (thread-safe)"""
    return hashlib.md5(message.encode('utf-8')).hexdigest()


def _is_duplicate_message(message: str, chat_id: int) -> bool:
    """
    Check apakah message sudah dikirim dalam TTL window (thread-safe).
    Juga membersihkan hash yang sudah expired.
    
    Args:
        message: Pesan yang akan dicek
        chat_id: ID chat target
        
    Returns:
        True jika message adalah duplikat, False jika bukan
    """
    global _last_message_hashes
    
    current_time = time.time()
    msg_hash = f"{chat_id}:{_get_message_hash(message)}"
    
    with _message_hash_lock:
        expired_keys = [
            key for key, timestamp in _last_message_hashes.items()
            if current_time - timestamp > _MESSAGE_HASH_TTL
        ]
        for key in expired_keys:
            del _last_message_hashes[key]
        
        if msg_hash in _last_message_hashes:
            logger.debug(f"Duplicate message detected (hash: {msg_hash[:16]}...)")
            return True
        
        _last_message_hashes[msg_hash] = current_time
        return False


def _check_rate_limit(chat_id: int) -> bool:
    """
    Check dan enforce rate limit per chat_id (thread-safe).
    
    Args:
        chat_id: ID chat target
        
    Returns:
        True jika boleh kirim (tidak rate limited), False jika harus menunggu
    """
    global _last_send_time
    
    current_time = time.time()
    
    with _rate_limit_lock:
        if chat_id in _last_send_time:
            time_since_last = current_time - _last_send_time[chat_id]
            if time_since_last < _MIN_SEND_INTERVAL:
                wait_time = _MIN_SEND_INTERVAL - time_since_last
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s for chat {chat_id}")
                time.sleep(wait_time)
        
        _last_send_time[chat_id] = time.time()
        return True


def send_telegram_message_sync(token: str, message: str, user_id: Optional[int] = None, use_html: bool = False):
    """
    Helper synchronous untuk kirim pesan ke Telegram dari thread lain.
    Menggunakan requests library untuk menghindari masalah asyncio event loop.
    
    SECURITY FIX: Sekarang menggunakan user_id untuk mencari chat_id dari mapping.
    Ini mencegah notifikasi trading dikirim ke user yang salah.
    
    Features:
    - Thread-safe dengan locking
    - Message deduplication dengan hash check (TTL 60 detik)
    - Rate limiting per chat_id (min interval 1 detik)
    - Retry dengan exponential backoff (1s, 2s, 4s, max 8s)
    - Fallback ke plain text setelah 1x Markdown failure
    - Log failed messages ke file
    
    Args:
        token: Bot token
        message: Pesan yang akan dikirim
        user_id: Telegram user ID untuk mencari chat_id (REQUIRED untuk trading notifications)
        use_html: Jika True, gunakan HTML parse mode, jika False coba Markdown lalu plain text
    """
    global active_chat_id, chat_id_confirmed
    
    chat_id_to_use = None
    
    if user_id is not None:
        chat_id_to_use = get_user_chat_id(user_id)
        if not chat_id_to_use:
            logger.warning(f"No chat_id found for user {user_id}. User needs to /start the bot first.")
            return False
        logger.debug(f"Using chat_id {chat_id_to_use} for user {user_id}")
    else:
        with _chat_id_lock:
            current_chat_id = active_chat_id
            is_confirmed = chat_id_confirmed
        
        if not current_chat_id or not is_confirmed:
            logger.warning("No active chat_id or not confirmed. Please send /start to the bot first.")
            return False
        
        chat_id_to_use = current_chat_id
    
    if _is_duplicate_message(message, chat_id_to_use):
        logger.info(f"Skipping duplicate message to chat {chat_id_to_use}")
        return True
    
    _check_rate_limit(chat_id_to_use)
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parse_mode = "HTML" if use_html else "Markdown"
    max_retries = 3
    max_backoff = 8
    
    markdown_failures = 0
    
    for attempt in range(max_retries):
        try:
            if markdown_failures >= 1:
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
                    
                    if markdown_failures >= 1:
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
            
            backoff_time = min(2 ** attempt, max_backoff)
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {backoff_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff_time)
                
        except requests.exceptions.Timeout:
            logger.error(f"Telegram API timeout (attempt {attempt + 1}/{max_retries})")
            log_telegram_error(message, "Request timeout")
            if attempt < max_retries - 1:
                backoff_time = min(2 ** attempt, max_backoff)
                time.sleep(backoff_time)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error (attempt {attempt + 1}/{max_retries}): {e}")
            log_telegram_error(message, str(e))
            if attempt < max_retries - 1:
                backoff_time = min(2 ** attempt, max_backoff)
                time.sleep(backoff_time)
        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            log_telegram_error(message, str(e))
            if attempt < max_retries - 1:
                backoff_time = min(2 ** attempt, max_backoff)
                time.sleep(backoff_time)
    
    logger.error("All retry attempts failed for Telegram message")
    return False


def setup_trading_callbacks(telegram_token: str):
    """Setup callback functions untuk notifikasi trading
    
    SECURITY FIX: Semua callback sekarang menggunakan current_connected_user_id
    untuk memastikan notifikasi hanya dikirim ke user yang sedang trading.
    
    Args:
        telegram_token: Token bot Telegram untuk mengirim pesan
    """
    global trading_manager, current_connected_user_id
    
    if not trading_manager:
        return
        
    def on_trade_opened(contract_type: str, price: float, stake: float, 
                       trade_num: int, target: int):
        """Callback saat posisi dibuka"""
        user_id = current_connected_user_id
        logger.info(f"📤 on_trade_opened callback INVOKED: type={contract_type}, trade={trade_num}, user_id={user_id}")
        
        if not user_id:
            logger.error("❌ on_trade_opened: No user_id available, skipping notification")
            return
            
        target_text = f"/{target}" if target > 0 else ""
        stake_idr = stake * USD_TO_IDR
        message = (
            f"⏳ **ENTRY** (Trade {trade_num}{target_text})\n\n"
            f"• Tipe: {contract_type}\n"
            f"• Entry: {price:.5f}\n"
            f"• Stake: ${stake:.2f} (Rp {stake_idr:,.0f})"
        )
        result = send_telegram_message_sync(telegram_token, message, user_id=user_id)
        logger.info(f"📤 on_trade_opened message sent to user {user_id}: {result}")
        
    def on_trade_closed(is_win: bool, profit: float, balance: float,
                       trade_num: int, target: int, next_stake: float):
        """Callback saat posisi ditutup (win/loss)"""
        user_id = current_connected_user_id
        logger.info(f"📥 on_trade_closed callback INVOKED: win={is_win}, profit={profit}, trade={trade_num}, user_id={user_id}")
        
        if not user_id:
            logger.error("❌ on_trade_closed: No user_id available, skipping notification")
            return
            
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
            
        result = send_telegram_message_sync(telegram_token, message, user_id=user_id)
        logger.info(f"📥 on_trade_closed message sent to user {user_id}: {result}")
        
    def on_session_complete(total: int, wins: int, losses: int, 
                           profit: float, win_rate: float):
        """Callback saat session selesai"""
        user_id = current_connected_user_id
        logger.info(f"🏁 on_session_complete callback INVOKED: total={total}, user_id={user_id}")
        
        if not user_id:
            logger.error("❌ on_session_complete: No user_id available, skipping notification")
            return
            
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
        result = send_telegram_message_sync(telegram_token, message, user_id=user_id)
        logger.info(f"🏁 on_session_complete message sent to user {user_id}: {result}")
        
    def on_error(error_msg: str):
        """Callback saat terjadi error"""
        user_id = current_connected_user_id
        logger.info(f"⚠️ on_error callback INVOKED: error={error_msg[:50]}..., user_id={user_id}")
        
        if not user_id:
            logger.error("❌ on_error: No user_id available, skipping notification")
            return
            
        message = f"⚠️ **ERROR**\n\n{error_msg}"
        result = send_telegram_message_sync(telegram_token, message, user_id=user_id)
        logger.info(f"⚠️ on_error message sent to user {user_id}: {result}")
    
    def on_progress(tick_count: int, required_ticks: int, rsi: float, trend: str):
        """Callback untuk progress notification saat mengumpulkan data"""
        global last_progress_notification_time
        user_id = current_connected_user_id
        
        try:
            logger.info(f"📊 on_progress called: tick={tick_count}/{required_ticks}, rsi={rsi}, trend={trend}, user_id={user_id}")
            
            if not user_id:
                logger.warning("⚠️ on_progress: No user_id available, skipping notification")
                return
            
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
            
            result = send_telegram_message_sync(telegram_token, message, user_id=user_id)
            if result:
                last_progress_notification_time = current_time
                logger.info(f"✅ Progress message sent successfully to user {user_id}")
            else:
                logger.warning(f"⚠️ Progress message not sent to user {user_id} (no chat_id or error)")
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
    shutdown_msg_sent = False
    if telegram_token and current_connected_user_id:
        shutdown_msg_sent = send_telegram_message_sync(telegram_token, "🛑 **Bot shutting down gracefully...**", user_id=current_connected_user_id)
    if not shutdown_msg_sent and telegram_token and active_chat_id:
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
    
    complete_msg_sent = False
    if telegram_token and current_connected_user_id:
        complete_msg_sent = send_telegram_message_sync(telegram_token, "✅ **Bot shutdown complete.**", user_id=current_connected_user_id)
    if not complete_msg_sent and telegram_token and active_chat_id:
        send_telegram_message_sync(telegram_token, "✅ **Bot shutdown complete.**")
    
    logger.info("🏁 Graceful shutdown complete")
    sys.exit(0)


def initialize_deriv():
    """
    Inisialisasi koneksi Deriv WebSocket.
    
    Strategi baru:
    1. Cek apakah ada user session yang tersimpan
    2. Jika ada, coba koneksi dengan token user pertama
    3. Jika tidak ada, bot akan menunggu user login melalui /login
    
    Environment tokens (DERIV_TOKEN_DEMO/REAL) tidak lagi wajib.
    """
    global deriv_ws, trading_manager, pair_scanner, current_connected_user_id
    
    logger.info("=" * 50)
    logger.info("INITIALIZING DERIV BOT")
    logger.info("=" * 50)
    
    sessions = auth_manager.sessions
    logger.info(f"📂 Found {len(sessions)} saved user sessions")
    
    if sessions:
        first_user_id = list(sessions.keys())[0]
        session = sessions[first_user_id]
        logger.info(f"🔑 Found session for user {first_user_id} ({session.account_type})")
        
        success, msg = connect_user_deriv(first_user_id)
        
        if success:
            logger.info("✅ Deriv connected with saved session!")
            logger.info("=" * 50)
            return True
        else:
            logger.warning(f"⚠️ Could not connect with saved session: {msg}")
            logger.info("User dapat mencoba /start untuk reconnect")
            logger.info("=" * 50)
            return False
    else:
        logger.info("📋 No saved sessions found")
        logger.info("🔐 Bot akan menunggu user login dengan /login atau /start")
        logger.info("=" * 50)
        return True


def main():
    """Main function - entry point aplikasi"""
    global active_chat_id, chat_id_confirmed
    
    cleanup_old_logs(max_days=1)
    
    load_user_chat_mapping()
    
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
        
    initialize_deriv()
    
    app = ApplicationBuilder().token(telegram_token).build()
    
    setup_trading_callbacks(telegram_token)
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("akun", akun_command))
    app.add_handler(CommandHandler("autotrade", autotrade_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, token_message_handler))
    
    logger.info("🤖 Bot is starting...")
    
    import asyncio
    
    async def start_web_server():
        """Start FastAPI web server for dashboard"""
        try:
            import uvicorn
            from web_server import app as web_app
            
            config = uvicorn.Config(
                app=web_app,
                host="0.0.0.0",
                port=5000,
                log_level="info",
                access_log=True
            )
            server = uvicorn.Server(config)
            logger.info("🌐 Starting web dashboard on http://0.0.0.0:5000")
            await server.serve()
        except Exception as e:
            logger.error(f"❌ Web server error: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def start_bot():
        """Start bot dengan delete_webhook untuk menghindari conflict"""
        event_bus = get_event_bus()
        event_bus.set_event_loop(asyncio.get_running_loop())
        logger.info("📡 EventBus loop configured for real-time updates")
        
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted, starting polling...")
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        web_server_task = asyncio.create_task(start_web_server())
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            web_server_task.cancel()
            try:
                await web_server_task
            except asyncio.CancelledError:
                pass
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
    
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")


if __name__ == "__main__":
    main()
