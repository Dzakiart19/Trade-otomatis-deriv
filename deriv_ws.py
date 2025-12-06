"""
=============================================================
DERIV WEBSOCKET CLIENT - Low Latency Connection
=============================================================
Modul ini menangani koneksi WebSocket ke Deriv API.
Menggunakan websocket-client native untuk kecepatan maksimal.

Fitur:
- Auto reconnect jika disconnect
- Multi-account support (Demo/Real)
- Multi-symbol tick subscriptions dengan per-symbol callbacks
- Subscribe ke tick stream dan proposal_open_contract
- Thread-safe untuk concurrent operations
- Retry mechanism dengan exponential backoff
- Health check ping/pong periodic

Multi-Symbol Tick Subscriptions (v2.3):
- subscribe_ticks(symbol, callback) - Subscribe dengan optional callback
- unsubscribe_ticks(symbol) - Unsubscribe dari symbol tertentu
- unsubscribe_all_ticks() - Unsubscribe semua subscriptions
- get_subscribed_symbols() - List semua symbol yang di-subscribe
=============================================================
"""

import os
import json
import threading
import time
import logging
import re
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import websocket

from event_bus import get_event_bus, TickEvent, BalanceUpdateEvent

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
    AUTH_TIMEOUT = 30  # detik timeout untuk menunggu auth response (increased from 15)
    
    # Health check settings
    HEALTH_CHECK_INTERVAL = 60  # detik - mengurangi beban ping (increased from 30)
    PING_TIMEOUT = 120  # detik - lebih toleran untuk network latency (increased from 90)
    MAX_MISSED_PONGS = 3  # jumlah pong yang boleh terlewat sebelum reconnect (increased from 2)
    GRACE_PERIOD_SECONDS = 10  # grace period sebelum force reconnect
    PING_JITTER_MAX = 15  # maksimum jitter dalam detik untuk menghindari collision (increased from 5)
    PENDING_REQUEST_TIMEOUT = 60.0  # timeout untuk cleanup pending requests (seconds)
    
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
        app_id = os.environ.get("DERIV_APP_ID", "").strip() or "1089"
        self.ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
        if not os.environ.get("DERIV_APP_ID", "").strip():
            logger.warning("⚠️ DERIV_APP_ID not set or empty, using default: 1089")
        logger.info(f"Using Deriv App ID: {app_id}")
        
        # Status koneksi
        self.ws: Optional[websocket.WebSocketApp] = None
        self._is_connected = False
        self._is_connected_lock = threading.Lock()
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
        self._stop_health_check_event = threading.Event()
        
        # Request tracking - stores {data, timestamp} for timeout cleanup
        self.pending_requests: Dict[int, Dict[str, Any]] = {}
        self.request_id = 0
        
        # Subscriptions - Multi-symbol support
        self.tick_subscriptions: Dict[str, str] = {}  # symbol -> subscription_id
        self.tick_callbacks: Dict[str, Callable] = {}  # symbol -> callback function
        self.contract_subscription_id: Optional[str] = None
        
        # Ticks history support
        self._history_callbacks: Dict[str, Callable] = {}  # req_id -> callback
        self._history_results: Dict[str, List[float]] = {}  # symbol -> prices
        self._history_events: Dict[str, threading.Event] = {}  # symbol -> event
        
        # Backward compatibility - keep legacy single subscription reference
        self.tick_subscription_id: Optional[str] = None  # Deprecated: use tick_subscriptions
        
        # Authorization event for synchronization
        self._auth_event = threading.Event()
        self._auth_success = False
        self._last_auth_error = ""
        
        # Last ping/pong tracking
        self._last_pong_time = time.time()
        self._awaiting_pong = False
        self._missed_pong_count = 0
        
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
    
    @property
    def is_connected(self) -> bool:
        """Thread-safe getter for connection status"""
        with self._is_connected_lock:
            return self._is_connected
    
    @is_connected.setter
    def is_connected(self, value: bool):
        """Thread-safe setter for connection status"""
        with self._is_connected_lock:
            self._is_connected = value
            
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
        self._stop_health_check_event.set()
        
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
            elif msg_type == "history":
                self._handle_ticks_history(data)
            elif msg_type == "ping":
                # Deriv API responds to our ping with: {"msg_type": "ping", "ping": "pong"}
                # This is the pong response to our ping request
                if data.get("ping") == "pong":
                    self._handle_pong(data)
                    logger.debug("Received pong response from Deriv")
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
        
        # InvalidToken - langsung fallback ke demo tanpa retry
        if error_code == "InvalidToken":
            logger.error(f"🚫 Token invalid terdeteksi: {error_msg}")
            logger.error("   Token tidak valid atau sudah expired - tidak perlu retry")
            
            # Jika sedang mencoba real account, langsung fallback ke demo
            if self.current_account_type == AccountType.REAL and self.demo_token:
                logger.info("🔄 InvalidToken pada REAL account - langsung fallback ke DEMO")
                self._try_fallback_to_demo()
            else:
                logger.error("❌ InvalidToken pada DEMO account - tidak bisa fallback")
                logger.error("   Periksa kembali API token di environment variables")
            return
        
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
        self._missed_pong_count = 0  # Reset missed count on successful pong
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
        
        # Publish to event bus
        if self.account_info:
            try:
                bus = get_event_bus()
                bus.publish("balance", BalanceUpdateEvent(
                    balance=new_balance,
                    currency=self.account_info.currency,
                    account_id=self.account_info.account_id
                ))
            except Exception as e:
                logger.debug(f"Error publishing balance event: {e}")
            
    def _handle_tick(self, data: dict):
        """
        Handle tick data stream dengan multi-symbol support.
        
        Routes tick data ke callback yang tepat berdasarkan symbol:
        1. Jika ada per-symbol callback di tick_callbacks, panggil itu
        2. Jika ada global on_tick_callback, panggil juga untuk backward compatibility
        
        Args:
            data: Tick data dari Deriv WebSocket
        """
        if "error" in data:
            return
            
        tick_data = data.get("tick", {})
        price = tick_data.get("quote")
        symbol = tick_data.get("symbol")
        subscription_id = data.get("subscription", {}).get("id")
        
        if not price or not symbol:
            return
            
        # Update subscription ID mapping jika belum ada
        if subscription_id and symbol not in self.tick_subscriptions:
            with self.lock:
                self.tick_subscriptions[symbol] = subscription_id
                logger.debug(f"📊 Registered tick subscription: {symbol} -> {subscription_id}")
        
        price_float = float(price)
        
        # 1. Call per-symbol callback jika ada
        if symbol in self.tick_callbacks:
            try:
                self.tick_callbacks[symbol](price_float, symbol)
            except Exception as e:
                logger.error(f"Error in tick callback for {symbol}: {e}")
        
        # 2. Call global callback untuk backward compatibility
        if self.on_tick_callback:
            try:
                self.on_tick_callback(price_float, symbol)
            except Exception as e:
                logger.error(f"Error in global tick callback: {e}")
        
        # 3. Publish to event bus
        try:
            bus = get_event_bus()
            bus.publish("tick", TickEvent(symbol=symbol, price=price_float))
        except Exception as e:
            logger.debug(f"Error publishing tick event: {e}")
    
    def _handle_ticks_history(self, data: dict):
        """Handle response dari ticks_history request"""
        if "error" in data:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"❌ Ticks history error: {error_msg}")
            return
            
        history = data.get("history", {})
        prices = history.get("prices", [])
        
        echo_req = data.get("echo_req", {})
        symbol = echo_req.get("ticks_history", "")
        req_id = str(data.get("req_id", ""))
        
        if symbol and prices:
            with self.lock:
                self._history_results[symbol] = [float(p) for p in prices]
                
            if symbol in self._history_events:
                self._history_events[symbol].set()
                
            logger.info(f"📊 Received {len(prices)} historical ticks for {symbol}")
            
            if req_id in self._history_callbacks:
                try:
                    callback = self._history_callbacks.pop(req_id)
                    callback(symbol, prices)
                except Exception as e:
                    logger.error(f"Error in history callback: {e}")
            
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
        """
        Authorize dengan retry mechanism.
        
        Enhancement v2.1:
        - Clear pending subscriptions sebelum re-authorize
        - Connection state validation
        """
        # Clear pending subscriptions sebelum authorize
        self._clear_pending_subscriptions()
        
        # Validate connection state
        if not self.is_connected:
            logger.warning("⚠️ Cannot authorize - not connected")
            return
        
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
        """
        Start health check thread untuk monitoring koneksi.
        
        Enhancement v2.2:
        - Jitter 10-20 detik untuk avoid collision
        - Interval 60 detik + jitter untuk mengurangi beban ping
        - Reduced verbose logging untuk ping/pong
        """
        import random
        
        self._stop_health_check_event.clear()
        self._missed_pong_count = 0
        self._grace_period_start = None
        
        def health_check_loop():
            while not self._stop_health_check_event.is_set() and self.is_connected:
                try:
                    # Jitter 10-20 detik untuk avoid collision antar koneksi
                    jitter = random.uniform(10, 20)
                    sleep_time = self.HEALTH_CHECK_INTERVAL + jitter
                    
                    time.sleep(sleep_time)
                    
                    if not self.is_connected:
                        break
                        
                    current_time = time.time()
                    time_since_pong = current_time - self._last_pong_time
                    
                    # Check if previous ping was answered
                    if self._awaiting_pong:
                        self._missed_pong_count += 1
                        # Hanya log warning jika sudah mendekati batas
                        if self._missed_pong_count >= self.MAX_MISSED_PONGS - 1:
                            logger.warning(
                                f"⚠️ Missed pong #{self._missed_pong_count}/{self.MAX_MISSED_PONGS} "
                                f"(last pong: {time_since_pong:.0f}s ago)"
                            )
                        
                        # Only force reconnect after multiple missed pongs AND grace period
                        if self._missed_pong_count >= self.MAX_MISSED_PONGS:
                            # Start grace period if not already started
                            if self._grace_period_start is None:
                                self._grace_period_start = current_time
                                logger.warning(
                                    f"⏳ Grace period {self.GRACE_PERIOD_SECONDS}s sebelum reconnect"
                                )
                            elif current_time - self._grace_period_start >= self.GRACE_PERIOD_SECONDS:
                                # Grace period expired, force reconnect
                                logger.error(
                                    f"❌ Connection dead - no pong for {time_since_pong:.0f}s"
                                )
                                self._force_reconnect()
                                break
                    else:
                        # Pong received, reset counters and grace period
                        if self._missed_pong_count > 0:
                            logger.info(f"✅ Connection recovered after {self._missed_pong_count} missed pongs")
                        self._missed_pong_count = 0
                        self._grace_period_start = None
                    
                    # Send ping (tanpa verbose logging)
                    self._awaiting_pong = True
                    if not self._send({"ping": 1}):
                        logger.warning("❌ Failed to send ping")
                    
                    # Cleanup expired pending requests to prevent memory leak
                    self._cleanup_pending_requests()
                    
                except Exception as e:
                    logger.error(f"Health check error: {type(e).__name__}: {e}")
                    break
                    
        self.health_check_thread = threading.Thread(target=health_check_loop, daemon=True)
        self.health_check_thread.start()
        logger.info("🏥 Health check started (interval=60s, jitter=10-20s)")
        
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
        
    def _check_network_connectivity(self) -> bool:
        """
        Pre-check network connectivity sebelum reconnect.
        Returns True jika network tersedia, False jika tidak.
        """
        import socket
        
        try:
            # Try to resolve DNS untuk Deriv WebSocket server
            socket.setdefaulttimeout(5)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("ws.derivws.com", 443))
            logger.debug("✅ Network connectivity check passed")
            return True
        except socket.error as e:
            logger.warning(f"⚠️ Network connectivity check failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Network check error: {type(e).__name__}: {e}")
            return False
    
    def _clear_pending_subscriptions(self):
        """
        Clear semua pending subscriptions sebelum re-authorize.
        
        Enhancement v2.3 - Multi-symbol support:
        - Clear all tick_subscriptions dictionary
        - Clear all tick_callbacks dictionary
        - Maintain backward compatibility dengan tick_subscription_id
        """
        logger.info("🧹 Clearing pending subscriptions before reconnect...")
        
        with self.lock:
            self.pending_requests.clear()
            
            # Clear multi-symbol subscriptions
            num_tick_subs = len(self.tick_subscriptions)
            self.tick_subscriptions.clear()
            self.tick_callbacks.clear()
            
            # Backward compatibility
            self.tick_subscription_id = None
            self.contract_subscription_id = None
            self.request_id = 0
            
        if num_tick_subs > 0:
            logger.debug(f"Cleared {num_tick_subs} tick subscription(s)")
        logger.debug("Pending subscriptions cleared")
    
    def _validate_connection_state(self) -> bool:
        """Validate connection state sebelum operations"""
        if self._connection_state in ["failed", "disconnected"]:
            logger.debug(f"Connection state validation: {self._connection_state} - not ready")
            return False
        return True
    
    def _cleanup_pending_requests(self):
        """
        Cleanup pending requests yang sudah melewati timeout.
        
        Mencegah memory leak dengan menghapus pending requests
        yang sudah expired (lebih dari PENDING_REQUEST_TIMEOUT detik).
        
        Dipanggil secara periodic dari health check loop.
        
        Telemetry Enhancement v2.4:
        - Logs cleanup statistics at INFO level when expired requests found
        - Logs WARNING if pending queue grows above threshold
        - Tracks oldest pending request age for monitoring
        """
        current_time = time.time()
        expired_requests = []
        oldest_age = 0.0
        total_pending = 0
        
        with self.lock:
            total_pending = len(self.pending_requests)
            
            for req_id, req_data in self.pending_requests.items():
                if isinstance(req_data, dict) and "timestamp" in req_data:
                    elapsed = current_time - req_data["timestamp"]
                    oldest_age = max(oldest_age, elapsed)
                    if elapsed > self.PENDING_REQUEST_TIMEOUT:
                        expired_requests.append(req_id)
                elif isinstance(req_data, dict):
                    expired_requests.append(req_id)
            
            for req_id in expired_requests:
                self.pending_requests.pop(req_id, None)
        
        if expired_requests:
            logger.info(
                f"🧹 Pending request cleanup: removed {len(expired_requests)} expired request(s), "
                f"{total_pending - len(expired_requests)} remaining, "
                f"oldest_age={oldest_age:.1f}s"
            )
        
        if total_pending - len(expired_requests) > 50:
            logger.warning(
                f"⚠️ High pending request count: {total_pending - len(expired_requests)} requests in queue. "
                f"Consider checking for slow responses or network issues."
            )
        elif total_pending > 0:
            logger.debug(
                f"📊 Pending requests: {total_pending} in queue, oldest_age={oldest_age:.1f}s"
            )
    
    def _attempt_reconnect(self):
        """
        Coba reconnect dengan exponential backoff.
        
        Enhancement v2.1:
        - Pre-check network connectivity sebelum reconnect
        - Clear pending subscriptions sebelum re-authorize
        - Connection state validation
        """
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
        
        # Pre-check network connectivity
        if not self._check_network_connectivity():
            logger.warning("⚠️ Network not available, waiting before retry...")
            # Wait additional time if network is not available
            time.sleep(min(delay, 10))
            
            # Check again
            if not self._check_network_connectivity():
                logger.error("❌ Network still unavailable after wait")
                # Don't count this as a failed attempt, just retry
                self.reconnect_count -= 1
                self._attempt_reconnect()
                return
        
        # Clear pending subscriptions sebelum reconnect
        self._clear_pending_subscriptions()
        
        # Validate and connect
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
        self._stop_health_check_event.set()
        
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
        
    def subscribe_ticks(self, symbol: str = DEFAULT_SYMBOL, callback: Optional[Callable] = None) -> bool:
        """
        Subscribe ke tick stream untuk symbol tertentu dengan optional callback.
        
        Multi-symbol support: Bisa subscribe ke multiple symbols dengan callback berbeda.
        Backward compatible: Jika tidak ada callback per-symbol, gunakan global on_tick_callback.
        
        Args:
            symbol: Symbol yang ingin di-subscribe (default: R_100)
            callback: Optional callback function untuk symbol ini.
                      Signature: callback(price: float, symbol: str)
            
        Returns:
            True jika request terkirim
            
        Example:
            # Subscribe dengan global callback
            ws.subscribe_ticks("R_100")
            
            # Subscribe dengan per-symbol callback
            ws.subscribe_ticks("R_50", callback=lambda price, sym: print(f"{sym}: {price}"))
        """
        # Check if already subscribed
        if symbol in self.tick_subscriptions:
            logger.info(f"📊 Already subscribed to {symbol}")
            # Update callback jika diberikan
            if callback:
                with self.lock:
                    self.tick_callbacks[symbol] = callback
                logger.debug(f"Updated callback for {symbol}")
            return True
        
        # Register callback jika diberikan
        if callback:
            with self.lock:
                self.tick_callbacks[symbol] = callback
            logger.debug(f"Registered callback for {symbol}")
        
        payload = {
            "ticks": symbol,
            "subscribe": 1
        }
        
        success = self._send(payload)
        if success:
            logger.info(f"📊 Subscribing to tick stream: {symbol}")
        return success
        
    def unsubscribe_ticks(self, symbol: str) -> bool:
        """
        Unsubscribe dari tick stream untuk symbol tertentu.
        
        Args:
            symbol: Symbol yang ingin di-unsubscribe
            
        Returns:
            True jika request terkirim atau symbol tidak ada dalam subscriptions
        """
        # Check if subscribed
        if symbol not in self.tick_subscriptions:
            logger.debug(f"Not subscribed to {symbol}, nothing to unsubscribe")
            # Cleanup callback jika ada
            with self.lock:
                self.tick_callbacks.pop(symbol, None)
            return True
            
        subscription_id = self.tick_subscriptions.get(symbol)
        
        if subscription_id:
            payload = {
                "forget": subscription_id
            }
            success = self._send(payload)
            
            if success:
                with self.lock:
                    self.tick_subscriptions.pop(symbol, None)
                    self.tick_callbacks.pop(symbol, None)
                logger.info(f"📊 Unsubscribed from {symbol}")
            return success
        else:
            # No subscription_id, just cleanup local state
            with self.lock:
                self.tick_subscriptions.pop(symbol, None)
                self.tick_callbacks.pop(symbol, None)
            return True
    
    def unsubscribe_all_ticks(self) -> None:
        """
        Unsubscribe dari semua tick subscriptions.
        
        Menggunakan forget_all untuk efficiency, lalu clear local state.
        """
        if not self.tick_subscriptions:
            logger.debug("No tick subscriptions to clear")
            return
            
        num_subs = len(self.tick_subscriptions)
        
        payload = {
            "forget_all": "ticks"
        }
        success = self._send(payload)
        
        # Clear local state regardless of send result
        with self.lock:
            self.tick_subscriptions.clear()
            self.tick_callbacks.clear()
            self.tick_subscription_id = None  # Backward compatibility
            
        if success:
            logger.info(f"📊 Unsubscribed from all {num_subs} tick stream(s)")
        else:
            logger.warning(f"⚠️ Failed to send unsubscribe_all, cleared {num_subs} local subscription(s)")
    
    def get_ticks_history(
        self, 
        symbol: str, 
        count: int = 100,
        timeout: float = 10.0,
        callback: Optional[Callable] = None
    ) -> Optional[List[float]]:
        """
        Get historical tick prices for a symbol.
        
        Synchronous call that waits for response or uses callback.
        Used to pre-load data for analysis.
        
        Args:
            symbol: Trading pair symbol (e.g., "R_100")
            count: Number of ticks to retrieve (max 5000)
            timeout: Timeout in seconds to wait for response
            callback: Optional callback for async operation.
                      Signature: callback(symbol: str, prices: List[float])
                      
        Returns:
            List of historical prices, or None if failed/timeout
            
        Example:
            # Synchronous
            prices = ws.get_ticks_history("R_100", count=50)
            
            # Asynchronous with callback
            ws.get_ticks_history("R_100", count=50, callback=my_callback)
        """
        if not self.is_ready():
            logger.warning("Cannot get history: WebSocket not ready")
            return None
            
        count = min(max(count, 10), 5000)
        
        self.request_id += 1
        req_id = str(self.request_id)
        
        self._history_events[symbol] = threading.Event()
        
        if callback:
            self._history_callbacks[req_id] = callback
        
        payload = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "style": "ticks",
            "req_id": int(req_id)
        }
        
        success = self._send(payload)
        
        if not success:
            logger.error(f"Failed to send ticks_history request for {symbol}")
            self._history_events.pop(symbol, None)
            return None
            
        logger.debug(f"📊 Requesting {count} historical ticks for {symbol}")
        
        if callback:
            return None
        
        try:
            event = self._history_events.get(symbol)
            if event and event.wait(timeout):
                with self.lock:
                    prices = self._history_results.pop(symbol, None)
                return prices
            else:
                logger.warning(f"⏳ Timeout waiting for ticks history: {symbol}")
                with self.lock:
                    self._history_callbacks.pop(req_id, None)
                return None
        finally:
            with self.lock:
                self._history_events.pop(symbol, None)
                self._history_results.pop(symbol, None)
    
    def get_subscribed_symbols(self) -> List[str]:
        """
        Get list of currently subscribed symbols.
        
        Returns:
            List of symbol strings that are currently subscribed
            
        Example:
            symbols = ws.get_subscribed_symbols()
            # Returns: ["R_100", "R_50", "R_75"]
        """
        with self.lock:
            return list(self.tick_subscriptions.keys())
        
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
