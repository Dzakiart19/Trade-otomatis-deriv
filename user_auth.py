"""
=============================================================
USER AUTHENTICATION MODULE - Secure Per-User Access Control
=============================================================
Modul ini menangani autentikasi user Telegram dengan fitur:
- Penyimpanan token terenkripsi per-user
- Login/Logout flow dengan validasi token
- Rate limiting untuk mencegah brute force
- Whitelist user yang sudah terautentikasi

Security Features:
- Token dienkripsi menggunakan Fernet (AES-128-CBC)
- Tidak pernah menyimpan atau log token plaintext
- Rate limiting untuk login attempts
- Automatic session expiry (optional)
=============================================================
"""

import os
import json
import time
import hashlib
import base64
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUTH_DATA_FILE = "logs/user_auth.json"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
TOKEN_MIN_LENGTH = 15
TOKEN_MAX_LENGTH = 40


@dataclass
class UserSession:
    """Data sesi user yang terautentikasi"""
    user_id: int
    username: Optional[str]
    account_type: str
    encrypted_token: str
    token_fingerprint: str
    created_at: str
    last_used: str
    login_attempts: int = 0
    lockout_until: float = 0.0


class UserAuthManager:
    """
    Manager untuk autentikasi user Telegram.
    Menyimpan dan mengelola token Deriv terenkripsi per-user.
    """
    
    def __init__(self):
        """Inisialisasi auth manager dengan encryption key"""
        self.sessions: Dict[int, UserSession] = {}
        self.pending_logins: Dict[int, Dict[str, Any]] = {}
        self._fernet: Optional[Fernet] = None
        
        self._init_encryption()
        self._load_sessions()
        
        logger.info("🔐 UserAuthManager initialized")
        
    def _init_encryption(self):
        """Inisialisasi Fernet encryption dengan key dari environment"""
        secret = os.environ.get("SESSION_SECRET", "")
        
        if not secret:
            secret = os.urandom(32).hex()
            logger.warning("⚠️ SESSION_SECRET not found, using random key (sessions won't persist across restarts)")
        
        salt = b"deriv_trading_bot_v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        self._fernet = Fernet(key)
        
        logger.info("✅ Encryption initialized")
        
    def _encrypt_token(self, token: str) -> str:
        """Enkripsi token untuk penyimpanan"""
        if not self._fernet:
            raise RuntimeError("Encryption not initialized")
        encrypted = self._fernet.encrypt(token.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
        
    def _decrypt_token(self, encrypted_token: str) -> Optional[str]:
        """Dekripsi token untuk penggunaan"""
        if not self._fernet:
            return None
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_token.encode())
            decrypted = self._fernet.decrypt(encrypted)
            return decrypted.decode()
        except (InvalidToken, Exception) as e:
            logger.error(f"Failed to decrypt token: {e}")
            return None
            
    def _get_token_fingerprint(self, token: str) -> str:
        """Generate fingerprint dari token untuk audit (tidak reversible)"""
        return hashlib.sha256(token.encode()).hexdigest()[:16]
        
    def _load_sessions(self):
        """Load sessions dari file"""
        try:
            if os.path.exists(AUTH_DATA_FILE):
                with open(AUTH_DATA_FILE, "r") as f:
                    data = json.load(f)
                    for user_id_str, session_data in data.items():
                        user_id = int(user_id_str)
                        self.sessions[user_id] = UserSession(**session_data)
                logger.info(f"📂 Loaded {len(self.sessions)} user sessions")
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            self.sessions = {}
            
    def _save_sessions(self):
        """Save sessions ke file"""
        try:
            os.makedirs(os.path.dirname(AUTH_DATA_FILE), exist_ok=True)
            data = {str(uid): asdict(session) for uid, session in self.sessions.items()}
            with open(AUTH_DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug("💾 Sessions saved")
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
            
    def is_authenticated(self, user_id: int) -> bool:
        """Cek apakah user sudah terautentikasi"""
        return user_id in self.sessions
        
    def is_locked_out(self, user_id: int) -> tuple[bool, int]:
        """
        Cek apakah user terkena lockout karena terlalu banyak gagal login.
        Returns: (is_locked, remaining_seconds)
        """
        if user_id not in self.sessions:
            pending = self.pending_logins.get(user_id, {})
            lockout_until = pending.get("lockout_until", 0)
        else:
            lockout_until = self.sessions[user_id].lockout_until
            
        if lockout_until > time.time():
            remaining = int(lockout_until - time.time())
            return True, remaining
        return False, 0
        
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Dapatkan session user jika ada"""
        session = self.sessions.get(user_id)
        if session:
            session.last_used = datetime.now().isoformat()
            self._save_sessions()
        return session
        
    def get_user_token(self, user_id: int) -> Optional[str]:
        """Dapatkan token terdekrisi untuk user (hanya saat diperlukan)"""
        session = self.sessions.get(user_id)
        if not session:
            return None
        return self._decrypt_token(session.encrypted_token)
        
    def get_user_account_type(self, user_id: int) -> Optional[str]:
        """Dapatkan tipe akun user (demo/real)"""
        session = self.sessions.get(user_id)
        return session.account_type if session else None
        
    def start_login(self, user_id: int, username: Optional[str], account_type: str) -> bool:
        """
        Mulai proses login - step 1: pilih tipe akun.
        Returns True jika bisa lanjut, False jika locked out.
        """
        is_locked, remaining = self.is_locked_out(user_id)
        if is_locked:
            logger.warning(f"User {user_id} locked out for {remaining}s")
            return False
            
        self.pending_logins[user_id] = {
            "username": username,
            "account_type": account_type.lower(),
            "started_at": time.time(),
            "attempts": self.pending_logins.get(user_id, {}).get("attempts", 0),
            "lockout_until": 0
        }
        
        logger.info(f"🔑 Login started for user {user_id} ({username}) - {account_type}")
        return True
        
    def complete_login(self, user_id: int, token: str) -> tuple[bool, str]:
        """
        Selesaikan proses login - step 2: validasi dan simpan token.
        Returns: (success, message)
        """
        pending = self.pending_logins.get(user_id)
        if not pending:
            return False, "❌ Tidak ada proses login aktif. Gunakan /login terlebih dahulu."
            
        is_locked, remaining = self.is_locked_out(user_id)
        if is_locked:
            return False, f"❌ Terlalu banyak percobaan gagal. Coba lagi dalam {remaining} detik."
        
        token = token.strip()
        if not self._validate_token_format(token):
            self._record_failed_attempt(user_id)
            attempts = pending.get("attempts", 0) + 1
            remaining_attempts = MAX_LOGIN_ATTEMPTS - attempts
            if remaining_attempts > 0:
                return False, f"❌ Format token tidak valid. Sisa percobaan: {remaining_attempts}"
            else:
                return False, f"❌ Terlalu banyak percobaan gagal. Tunggu {LOGIN_LOCKOUT_SECONDS // 60} menit."
        
        encrypted_token = self._encrypt_token(token)
        fingerprint = self._get_token_fingerprint(token)
        now = datetime.now().isoformat()
        
        session = UserSession(
            user_id=user_id,
            username=pending.get("username"),
            account_type=pending["account_type"],
            encrypted_token=encrypted_token,
            token_fingerprint=fingerprint,
            created_at=now,
            last_used=now,
            login_attempts=0,
            lockout_until=0
        )
        
        self.sessions[user_id] = session
        self._save_sessions()
        
        if user_id in self.pending_logins:
            del self.pending_logins[user_id]
            
        logger.info(f"✅ Login successful for user {user_id} - {pending['account_type']} account")
        
        return True, f"✅ Login berhasil!\n\n• Tipe Akun: {pending['account_type'].upper()}\n• Token ID: ...{fingerprint[-8:]}\n\nGunakan /autotrade untuk mulai trading."
        
    def _validate_token_format(self, token: str) -> bool:
        """Validasi format token Deriv (basic check)"""
        if not token:
            return False
        if len(token) < TOKEN_MIN_LENGTH or len(token) > TOKEN_MAX_LENGTH:
            return False
        if not token.replace("_", "").replace("-", "").isalnum():
            return False
        return True
        
    def _record_failed_attempt(self, user_id: int):
        """Record percobaan login yang gagal"""
        pending = self.pending_logins.get(user_id, {"attempts": 0})
        pending["attempts"] = pending.get("attempts", 0) + 1
        
        if pending["attempts"] >= MAX_LOGIN_ATTEMPTS:
            pending["lockout_until"] = time.time() + LOGIN_LOCKOUT_SECONDS
            logger.warning(f"🔒 User {user_id} locked out after {pending['attempts']} failed attempts")
            
        self.pending_logins[user_id] = pending
        
    def logout(self, user_id: int) -> tuple[bool, str]:
        """Logout user dan hapus session"""
        if user_id not in self.sessions:
            return False, "❌ Anda belum login."
            
        session = self.sessions[user_id]
        account_type = session.account_type
        
        del self.sessions[user_id]
        self._save_sessions()
        
        if user_id in self.pending_logins:
            del self.pending_logins[user_id]
            
        logger.info(f"👋 User {user_id} logged out from {account_type} account")
        
        return True, f"👋 Logout berhasil!\n\nAkun {account_type.upper()} telah dihapus dari bot.\nGunakan /login untuk masuk kembali."
        
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Dapatkan info user tanpa expose token"""
        session = self.sessions.get(user_id)
        if not session:
            return None
            
        return {
            "user_id": session.user_id,
            "username": session.username,
            "account_type": session.account_type,
            "token_fingerprint": session.token_fingerprint,
            "created_at": session.created_at,
            "last_used": session.last_used
        }
        
    def has_pending_login(self, user_id: int) -> bool:
        """Cek apakah user sedang dalam proses login"""
        pending = self.pending_logins.get(user_id)
        if not pending:
            return False
        if time.time() - pending.get("started_at", 0) > 300:
            del self.pending_logins[user_id]
            return False
        return True
        
    def get_pending_account_type(self, user_id: int) -> Optional[str]:
        """Dapatkan tipe akun yang sedang di-login"""
        pending = self.pending_logins.get(user_id)
        return pending.get("account_type") if pending else None
        
    def cancel_login(self, user_id: int):
        """Batalkan proses login yang pending"""
        if user_id in self.pending_logins:
            del self.pending_logins[user_id]
            logger.info(f"🚫 Login cancelled for user {user_id}")


auth_manager = UserAuthManager()


async def ensure_authenticated(update, send_alert: bool = True) -> bool:
    """
    Helper untuk mengecek autentikasi user.
    Bekerja dengan commands (update.message) dan callbacks (update.callback_query).
    
    Args:
        update: Telegram Update object
        send_alert: Jika True, kirim pesan akses ditolak ke user
        
    Returns:
        True jika user terautentikasi, False jika tidak
    """
    if not update.effective_user:
        return False
        
    user_id = update.effective_user.id
    
    if auth_manager.is_authenticated(user_id):
        return True
    
    if send_alert:
        denied_text = (
            "🔒 **AKSES DITOLAK**\n\n"
            "Anda belum login. Gunakan /login untuk masuk dengan token Deriv Anda."
        )
        
        if update.callback_query:
            try:
                await update.callback_query.answer("Anda belum login!", show_alert=True)
                await update.callback_query.edit_message_text(
                    denied_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to send auth denial via callback: {e}")
        elif update.message:
            await update.message.reply_text(
                denied_text,
                parse_mode="Markdown"
            )
    
    return False


def require_auth(func):
    """Decorator untuk mengecek autentikasi sebelum menjalankan command"""
    async def wrapper(update, context, *args, **kwargs):
        if not await ensure_authenticated(update):
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def require_auth_callback(func):
    """Decorator untuk mengecek autentikasi pada callback query handlers"""
    async def wrapper(update, context, *args, **kwargs):
        if not await ensure_authenticated(update):
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


ALLOWED_CALLBACKS_WITHOUT_AUTH = {
    "login_demo",
    "login_real", 
    "login_cancel",
}
