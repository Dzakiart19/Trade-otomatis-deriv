"""
=============================================================
DERIV WEBSOCKET CLIENT - Low Latency Connection
=============================================================
Modul ini menangani koneksi WebSocket ke Deriv API.
Menggunakan websocket-client native untuk kecepatan maksimal.

Fitur:
- Auto reconnect jika disconnect
- Multi-account support (Demo/Real)
- Subscribe ke tick stream dan proposal_open_contract
- Thread-safe untuk concurrent operations
- Retry mechanism dengan exponential backoff
- Health check ping/pong periodic
=============================================================
"""

import os
import json
import threading
import time
import logging
import re
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
import websocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_SYMBOL = "R_100"
MIN_STAKE = 0.50


class AccountType(Enum):
    """Tipe akun Deriv"""
    DEMO = "demo"
    REAL = "real"


@dataclass
class AccountInfo:
    """Informasi akun"""
    balance: float
    currency: str
    account_id: str
    is_virtual: bool


class DerivWebSocket:
    """
    Kelas utama untuk koneksi WebSocket ke Deriv API.
    Thread-safe dan mendukung auto-reconnect dengan retry mechanism.
    """
    
    # Reconnect settings
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_DELAY = 5  # detik base
    MAX_RECONNECT_DELAY = 60  # detik maksimum
    
    # Authorization retry settings
    MAX_AUTH_RETRIES = 3
    AUTH_RETRY_DELAY = 2  # detik base
    AUTH_TIMEOUT = 15  # detik timeout untuk menunggu auth response
    
    # Health check settings
    HEALTH_CHECK_INTERVAL = 30  # detik
    PING_TIMEOUT = 10  # detik
    
    def __init__(self, demo_token: str, real_token: str):
        """
        Inisialisasi WebSocket client.
        
        Args:
            demo_token: API token untuk akun demo
            real_token: API token untuk akun real
        """
        self.demo_token = demo_token.strip() if demo_token else ""
        self.real_token = real_token.strip() if real_token else ""
        
        # Validate tokens on init
        self._validate_tokens()
        
        # Ambil APP_ID dari environment atau gunakan default
        app_id = os.environ.get("DERIV_APP_ID", "1089")
        self.ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
        logger.info(f"Using Deriv App ID: {app_id}")
        
        # Status koneksi
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected = False
        self.is_authorized = False
        self.current_account_type = AccountType.DEMO
        self._connection_state = "disconnected"  # disconnected, connecting, connected, authorizing, ready
        
        # Account info
        self.account_info: Optional[AccountInfo] = None
        
        # Callback functions
        self.on_tick_callback: Optional[Callable] = None
        self.on_contract_update_callback: Optional[Callable] = None
        self.on_buy_response_callback: Optional[Callable] = None
        self.on_balance_update_callback: Optional[Callable] = None
        self.on_connection_status_callback: Optional[Callable] = None
        
        # Threading
        self.ws_thread: Optional[threading.Thread] = None
        self.health_check_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.reconnect_count = 0
        self.auth_retry_count = 0
        self._stop_health_check = False
        
        # Request tracking
        self.pending_requests: Dict[int, Any] = {}
        self.request_id = 0
        
        # Subscriptions
        self.tick_subscription_id: Optional[str] = None
        self.contract_subscription_id: Optional[str] = None
        
        # Authorization event for synchronization
        self._auth_event = threading.Event()
        self._auth_success = False
        self._last_auth_error = ""
        
        # Last ping/pong tracking
        self._last_pong_time = time.time()
        self._awaiting_pong = False
        
    def _validate_tokens(self):
        """Validasi format token API"""
        token_pattern = re.compile(r'^[a-zA-Z0-9]{15,40}$')
        
        if self.demo_token:
            if not token_pattern.match(self.demo_token):
                logger.warning(f"⚠️ Demo token format may be invalid (length: {len(self.demo_token)})")
            else:
                logger.info(f"✓ Demo token validated (length: {len(self.demo_token)})")
                
        if self.real_token:
            if not token_pattern.match(self.real_token):
                logger.warning(f"⚠️ Real token format may be invalid (length: {len(self.real_token)})")
            else:
                logger.info(f"✓ Real token validated (length: {len(self.real_token)})")
                
        if not self.demo_token and not self.real_token:
            logger.error("❌ No valid tokens provided!")
            
    def _update_connection_state(self, state: str):
        """Update connection state dan trigger callback jika ada"""
        old_state = self._connection_state
        self._connection_state = state
        logger.info(f"Connection state: {old_state} -> {state}")
        
        if self.on_connection_status_callback:
            try:
                self.on_connection_status_callback(state)
            except Exception as e:
                logger.error(f"Error in connection status callback: {e}")
        
    def get_current_token(self) -> str:
        """Dapatkan token sesuai tipe akun aktif"""
        if self.current_account_type == AccountType.DEMO:
            return self.demo_token
        return self.real_token
        
    def _get_next_request_id(self) -> int:
        """Generate request ID unik"""
        with self.lock:
            self.request_id += 1
            return self.request_id
            
    def _on_open(self, ws):
        """Callback saat koneksi terbuka"""
        logger.info("✅ WebSocket connected to Deriv")
        self.is_connected = True
        self.reconnect_count = 0
        self._last_pong_time = time.time()
        self._update_connection_state("connected")
        
        # Start health check thread
        self._start_health_check()
        
        # Authorize dengan token
        self._authorize_with_retry()
        
    def _on_close(self, ws, close_status_code, close_msg):
        """Callback saat koneksi tertutup"""
        logger.warning(f"⚠️ WebSocket closed: code={close_status_code}, msg={close_msg}")
        self.is_connected = False
        self.is_authorized = False
        self._update_connection_state("disconnected")
        
        # Stop health check
        self._stop_health_check = True
        
        # Reset auth event
        self._auth_event.clear()
        self._auth_success = False
        
        # Coba reconnect
        self._attempt_reconnect()
        
    def _on_error(self, ws, error):
        """Callback saat terjadi error"""
        logger.error(f"❌ WebSocket error: {type(error).__name__}: {error}")
        
        # Log more details for debugging
        if hasattr(error, 'args') and error.args:
            logger.error(f"   Error details: {error.args}")
        
    def _on_message(self, ws, message):
        """
        Callback utama untuk handling semua pesan dari Deriv.
        Routing ke handler yang sesuai berdasarkan msg_type.
        """
        try:
            data = json.loads(message)
            msg_type = data.get("msg_type", "")
            
            # Log untuk debugging (level DEBUG untuk mengurangi noise)
            if msg_type not in ["tick", "ping", "pong"]:
                logger.debug(f"Received: {msg_type} - {json.dumps(data)[:200]}")
            
            # Handle berdasarkan tipe pesan
            if msg_type == "authorize":
                self._handle_authorize(data)
            elif msg_type == "balance":
                self._handle_balance(data)
            elif msg_type == "tick":
                self._handle_tick(data)
            elif msg_type == "buy":
                self._handle_buy_response(data)
            elif msg_type == "proposal_open_contract":
                self._handle_contract_update(data)
            elif msg_type == "pong":
                self._handle_pong(data)
            elif msg_type == "ping":
                # Respond to ping with pong
                self._send({"pong": 1})
            elif "error" in data:
                self._handle_error(data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
            logger.debug(f"Raw message: {message[:500]}")
        except Exception as e:
            logger.error(f"Error handling message: {type(e).__name__}: {e}")
            
    def _handle_authorize(self, data: dict):
        """Handle response authorize dengan detail logging"""
        if "error" in data:
            error_info = data.get("error", {})
            error_code = error_info.get("code", "unknown")
            error_msg = error_info.get("message", "Unknown error")
            
            logger.error(f"❌ Authorization failed!")
            logger.error(f"   Error code: {error_code}")
            logger.error(f"   Error message: {error_msg}")
            
            self._last_auth_error = f"[{error_code}] {error_msg}"
            self.is_authorized = False
            self._auth_success = False
            self._auth_event.set()  # Signal that auth completed (with failure)
            
            # Check if we should retry
            if self.auth_retry_count < self.MAX_AUTH_RETRIES:
                self._handle_auth_retry(error_code, error_msg)
            else:
                logger.error(f"❌ Max auth retries ({self.MAX_AUTH_RETRIES}) reached")
                # Try fallback to demo if we were trying real
                if self.current_account_type == AccountType.REAL and self.demo_token:
                    self._try_fallback_to_demo()
            return
            
        auth_info = data.get("authorize", {})
        self.is_authorized = True
        self._auth_success = True
        self.auth_retry_count = 0  # Reset retry count on success
        self._update_connection_state("ready")
        
        # Simpan info akun
        self.account_info = AccountInfo(
            balance=float(auth_info.get("balance", 0)),
            currency=auth_info.get("currency", "USD"),
            account_id=auth_info.get("loginid", ""),
            is_virtual=auth_info.get("is_virtual", 1) == 1
        )
        
        logger.info(f"✅ Authorization successful!")
        logger.info(f"   Account ID: {self.account_info.account_id}")
        logger.info(f"   Balance: {self.account_info.balance} {self.account_info.currency}")
        logger.info(f"   Is Virtual: {self.account_info.is_virtual}")
        
        # Signal that auth completed successfully
        self._auth_event.set()
        
        # Subscribe ke balance updates
        self._subscribe_balance()
        
    def _handle_auth_retry(self, error_code: str, error_msg: str):
        """Handle retry logic untuk authorization yang gagal"""
        self.auth_retry_count += 1
        
        # Calculate backoff delay
        delay = self.AUTH_RETRY_DELAY * (2 ** (self.auth_retry_count - 1))
        delay = min(delay, 30)  # Max 30 seconds
        
        logger.info(f"🔄 Retrying authorization in {delay}s (attempt {self.auth_retry_count}/{self.MAX_AUTH_RETRIES})")
        
        # Schedule retry in a separate thread
        def retry_auth():
            time.sleep(delay)
            if self.is_connected and not self.is_authorized:
                self._authorize()
                
        retry_thread = threading.Thread(target=retry_auth, daemon=True)
        retry_thread.start()
        
    def _try_fallback_to_demo(self):
        """Fallback ke demo account jika real gagal"""
        logger.info("🔄 Falling back to DEMO account...")
        self.current_account_type = AccountType.DEMO
        self.auth_retry_count = 0
        self._auth_event.clear()
        
        if self.is_connected:
            self._authorize()
            
    def _handle_pong(self, data: dict):
        """Handle pong response untuk health check"""
        self._last_pong_time = time.time()
        self._awaiting_pong = False
        logger.debug("Received pong - connection healthy")
        
    def _handle_balance(self, data: dict):
        """Handle update balance"""
        if "error" in data:
            logger.warning(f"Balance error: {data.get('error', {}).get('message', 'Unknown')}")
            return
            
        balance_info = data.get("balance", {})
        new_balance = float(balance_info.get("balance", 0))
        
        if self.account_info:
            old_balance = self.account_info.balance
            self.account_info.balance = new_balance
            if old_balance != new_balance:
                logger.info(f"💰 Balance updated: {old_balance} -> {new_balance}")
            
        # Trigger callback jika ada
        if self.on_balance_update_callback:
            try:
                self.on_balance_update_callback(new_balance)
            except Exception as e:
                logger.error(f"Error in balance callback: {e}")
            
    def _handle_tick(self, data: dict):
        """Handle tick data stream"""
        if "error" in data:
            return
            
        tick_data = data.get("tick", {})
        price = tick_data.get("quote")
        symbol = tick_data.get("symbol")
        
        if price and self.on_tick_callback:
            try:
                self.on_tick_callback(float(price), symbol)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")
            
    def _handle_buy_response(self, data: dict):
        """Handle response dari buy contract"""
        if "error" in data:
            error_msg = data.get("error", {}).get("message", "Unknown buy error")
            logger.error(f"❌ Buy error: {error_msg}")
            
        if self.on_buy_response_callback:
            try:
                self.on_buy_response_callback(data)
            except Exception as e:
                logger.error(f"Error in buy response callback: {e}")
            
    def _handle_contract_update(self, data: dict):
        """Handle update status kontrak (win/loss detection)"""
        if self.on_contract_update_callback:
            try:
                self.on_contract_update_callback(data)
            except Exception as e:
                logger.error(f"Error in contract update callback: {e}")
            
    def _handle_error(self, data: dict):
        """Handle error message dari Deriv"""
        error = data.get("error", {})
        error_msg = error.get("message", "Unknown error")
        error_code = error.get("code", "")
        
        logger.error(f"❌ Deriv Error [{error_code}]: {error_msg}")
        
        # Handle specific error codes
        if error_code == "InvalidToken":
            logger.error("   Token tidak valid - periksa kembali API token")
        elif error_code == "AuthorizationRequired":
            logger.error("   Perlu otorisasi ulang")
            self._authorize_with_retry()
        elif error_code == "RateLimit":
            logger.warning("   Rate limited - tunggu beberapa saat")
        
    def _send(self, payload: dict) -> bool:
        """
        Kirim payload ke WebSocket dengan thread-safety.
        
        Args:
            payload: Dictionary yang akan dikirim sebagai JSON
            
        Returns:
            True jika berhasil kirim, False jika gagal
        """
        if not self.is_connected or not self.ws:
            logger.warning("Cannot send: WebSocket not connected")
            return False
            
        try:
            with self.lock:
                message = json.dumps(payload)
                self.ws.send(message)
                
            # Log non-sensitive requests
            msg_type = list(payload.keys())[0] if payload else "unknown"
            if msg_type != "authorize":  # Don't log authorize (contains token)
                logger.debug(f"Sent: {msg_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to send: {type(e).__name__}: {e}")
            return False
            
    def _authorize(self):
        """Kirim request authorize"""
        token = self.get_current_token()
        if not token:
            logger.error("❌ No token available for authorization")
            logger.error(f"   Account type: {self.current_account_type.value}")
            logger.error(f"   Demo token available: {bool(self.demo_token)}")
            logger.error(f"   Real token available: {bool(self.real_token)}")
            self._auth_success = False
            self._auth_event.set()
            return
        
        # Log authorization attempt (hide actual token)
        token_preview = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
        logger.info(f"🔐 Authorizing with {self.current_account_type.value} token ({token_preview})")
        self._update_connection_state("authorizing")
        
        payload = {
            "authorize": token
        }
        
        if not self._send(payload):
            logger.error("❌ Failed to send authorize request")
            self._auth_success = False
            self._auth_event.set()
            
    def _authorize_with_retry(self):
        """Authorize dengan retry mechanism"""
        self.auth_retry_count = 0
        self._auth_event.clear()
        self._auth_success = False
        self._authorize()
        
    def _subscribe_balance(self):
        """Subscribe ke balance updates"""
        payload = {
            "balance": 1,
            "subscribe": 1
        }
        self._send(payload)
        
    def _start_health_check(self):
        """Start health check thread untuk monitoring koneksi"""
        self._stop_health_check = False
        
        def health_check_loop():
            while not self._stop_health_check and self.is_connected:
                try:
                    time.sleep(self.HEALTH_CHECK_INTERVAL)
                    
                    if not self.is_connected:
                        break
                        
                    # Check if we got pong recently
                    time_since_pong = time.time() - self._last_pong_time
                    if self._awaiting_pong and time_since_pong > self.PING_TIMEOUT:
                        logger.warning(f"⚠️ No pong received for {time_since_pong:.1f}s - connection may be dead")
                        # Force reconnect
                        self._force_reconnect()
                        break
                        
                    # Send ping
                    self._awaiting_pong = True
                    self._send({"ping": 1})
                    logger.debug("Sent ping for health check")
                    
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                    break
                    
        self.health_check_thread = threading.Thread(target=health_check_loop, daemon=True)
        self.health_check_thread.start()
        logger.debug("Health check thread started")
        
    def _force_reconnect(self):
        """Force close dan reconnect"""
        logger.info("🔄 Force reconnecting...")
        try:
            if self.ws:
                self.ws.close()
        except:
            pass
        self.is_connected = False
        self.is_authorized = False
        self._attempt_reconnect()
        
    def _attempt_reconnect(self):
        """Coba reconnect dengan exponential backoff"""
        if self.reconnect_count >= self.MAX_RECONNECT_ATTEMPTS:
            logger.error("❌ Max reconnect attempts reached. Giving up.")
            self._update_connection_state("failed")
            return
            
        self.reconnect_count += 1
        
        # Exponential backoff
        delay = min(
            self.RECONNECT_DELAY * (2 ** (self.reconnect_count - 1)),
            self.MAX_RECONNECT_DELAY
        )
        
        logger.info(f"🔄 Reconnecting in {delay}s... (Attempt {self.reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS})")
        self._update_connection_state("reconnecting")
        
        time.sleep(delay)
        self.connect()
        
    def connect(self) -> bool:
        """
        Mulai koneksi WebSocket dalam thread terpisah.
        
        Returns:
            True jika thread dimulai, False jika gagal
        """
        try:
            self._update_connection_state("connecting")
            
            # Enable WebSocket debugging jika needed
            # websocket.enableTrace(True)
            
            # Buat WebSocket app
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message
            )
            
            # Jalankan di thread terpisah dengan ping settings
            self.ws_thread = threading.Thread(
                target=self.ws.run_forever,
                kwargs={
                    "ping_interval": 30,
                    "ping_timeout": 10,
                    "reconnect": 5  # Auto-reconnect after 5 seconds
                },
                daemon=True
            )
            self.ws_thread.start()
            
            logger.info("🚀 WebSocket thread started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {type(e).__name__}: {e}")
            self._update_connection_state("failed")
            return False
            
    def disconnect(self):
        """Tutup koneksi WebSocket"""
        logger.info("Disconnecting WebSocket...")
        self._stop_health_check = True
        
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
                
        self.is_connected = False
        self.is_authorized = False
        self._auth_event.clear()
        self._update_connection_state("disconnected")
        logger.info("WebSocket disconnected")
            
    def switch_account(self, account_type: AccountType) -> bool:
        """
        Switch antara akun Demo dan Real.
        
        Args:
            account_type: AccountType.DEMO atau AccountType.REAL
            
        Returns:
            True jika berhasil switch
        """
        if account_type == self.current_account_type:
            logger.info(f"Already on {account_type.value} account")
            return True  # Sudah di akun yang diminta
        
        # Validate token exists for target account
        if account_type == AccountType.REAL and not self.real_token:
            logger.error("❌ Cannot switch to REAL - no real token configured")
            return False
        if account_type == AccountType.DEMO and not self.demo_token:
            logger.error("❌ Cannot switch to DEMO - no demo token configured")
            return False
            
        self.current_account_type = account_type
        self.is_authorized = False
        self._auth_event.clear()
        logger.info(f"🔄 Switching to {account_type.value} account...")
        
        # Re-authorize dengan token baru
        if self.is_connected:
            self._authorize_with_retry()
            return True
            
        return False
        
    def get_contracts_for(self, symbol: str = DEFAULT_SYMBOL) -> bool:
        """
        Query kontrak yang tersedia untuk symbol.
        Gunakan untuk mendapatkan durasi dan tipe kontrak yang valid.
        
        Args:
            symbol: Symbol untuk query (default: R_100)
            
        Returns:
            True jika request terkirim
        """
        payload = {
            "contracts_for": symbol,
            "currency": "USD",
            "product_type": "basic"
        }
        return self._send(payload)
        
    def subscribe_ticks(self, symbol: str = DEFAULT_SYMBOL) -> bool:
        """
        Subscribe ke tick stream untuk symbol tertentu.
        
        Args:
            symbol: Symbol yang ingin di-subscribe (default: R_100)
            
        Returns:
            True jika request terkirim
        """
        payload = {
            "ticks": symbol,
            "subscribe": 1
        }
        return self._send(payload)
        
    def unsubscribe_ticks(self) -> bool:
        """Unsubscribe dari tick stream"""
        payload = {
            "forget_all": "ticks"
        }
        return self._send(payload)
        
    def subscribe_contract(self, contract_id: str) -> bool:
        """
        Subscribe ke update kontrak untuk monitoring real-time.
        
        Args:
            contract_id: ID kontrak yang ingin di-monitor
            
        Returns:
            True jika request terkirim
        """
        payload = {
            "proposal_open_contract": 1,
            "contract_id": contract_id,
            "subscribe": 1
        }
        return self._send(payload)
        
    def buy_contract(
        self,
        contract_type: str,
        amount: float,
        symbol: str = DEFAULT_SYMBOL,
        duration: int = 5,
        duration_unit: str = "t"
    ) -> bool:
        """
        Eksekusi buy contract (CALL/PUT).
        
        Args:
            contract_type: "CALL" atau "PUT"
            amount: Jumlah stake
            symbol: Trading pair (default: R_100)
            duration: Durasi kontrak
            duration_unit: "t" (ticks), "s" (seconds), "m" (minutes), "d" (days)
            
        Returns:
            True jika request terkirim
        """
        if not self.is_authorized:
            logger.error("Cannot buy: Not authorized")
            return False
            
        req_id = self._get_next_request_id()
        
        payload = {
            "buy": 1,
            "subscribe": 1,
            "price": amount,
            "parameters": {
                "amount": amount,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": duration,
                "duration_unit": duration_unit,
                "symbol": symbol
            },
            "req_id": req_id
        }
        
        logger.info(f"📤 Buying {contract_type} | Stake: ${amount} | Duration: {duration}{duration_unit}")
        return self._send(payload)
        
    def get_balance(self) -> float:
        """Dapatkan balance saat ini"""
        if self.account_info:
            return self.account_info.balance
        return 0.0
        
    def is_ready(self) -> bool:
        """Cek apakah WebSocket siap untuk trading"""
        return self.is_connected and self.is_authorized
        
    def get_connection_status(self) -> str:
        """Dapatkan status koneksi detail"""
        return self._connection_state
        
    def get_last_auth_error(self) -> str:
        """Dapatkan pesan error terakhir saat authorization"""
        return self._last_auth_error
        
    def wait_until_ready(self, timeout: int = 30) -> bool:
        """
        Tunggu sampai WebSocket siap (connected & authorized).
        
        Args:
            timeout: Maksimum waktu tunggu dalam detik
            
        Returns:
            True jika siap, False jika timeout
        """
        logger.info(f"⏳ Waiting for authorization (timeout: {timeout}s)...")
        
        # Wait for auth event with timeout
        auth_completed = self._auth_event.wait(timeout=timeout)
        
        if not auth_completed:
            logger.error(f"❌ Authorization timeout after {timeout}s")
            logger.error(f"   Connection state: {self._connection_state}")
            logger.error(f"   Is connected: {self.is_connected}")
            return False
            
        if self._auth_success:
            logger.info("✅ WebSocket ready for trading")
            return True
        else:
            logger.error(f"❌ Authorization failed: {self._last_auth_error}")
            return False
