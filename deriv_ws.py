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
=============================================================
"""

import json
import threading
import time
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
import websocket

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    Thread-safe dan mendukung auto-reconnect.
    """
    
    # Deriv WebSocket URL
    WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    
    # Reconnect settings
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_DELAY = 5  # detik
    
    def __init__(self, demo_token: str, real_token: str):
        """
        Inisialisasi WebSocket client.
        
        Args:
            demo_token: API token untuk akun demo
            real_token: API token untuk akun real
        """
        self.demo_token = demo_token
        self.real_token = real_token
        
        # Status koneksi
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected = False
        self.is_authorized = False
        self.current_account_type = AccountType.DEMO
        
        # Account info
        self.account_info: Optional[AccountInfo] = None
        
        # Callback functions
        self.on_tick_callback: Optional[Callable] = None
        self.on_contract_update_callback: Optional[Callable] = None
        self.on_buy_response_callback: Optional[Callable] = None
        self.on_balance_update_callback: Optional[Callable] = None
        
        # Threading
        self.ws_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.reconnect_count = 0
        
        # Request tracking
        self.pending_requests: Dict[int, Any] = {}
        self.request_id = 0
        
        # Subscriptions
        self.tick_subscription_id: Optional[str] = None
        self.contract_subscription_id: Optional[str] = None
        
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
        
        # Authorize dengan token
        self._authorize()
        
    def _on_close(self, ws, close_status_code, close_msg):
        """Callback saat koneksi tertutup"""
        logger.warning(f"⚠️ WebSocket closed: {close_msg}")
        self.is_connected = False
        self.is_authorized = False
        
        # Coba reconnect
        self._attempt_reconnect()
        
    def _on_error(self, ws, error):
        """Callback saat terjadi error"""
        logger.error(f"❌ WebSocket error: {error}")
        
    def _on_message(self, ws, message):
        """
        Callback utama untuk handling semua pesan dari Deriv.
        Routing ke handler yang sesuai berdasarkan msg_type.
        """
        try:
            data = json.loads(message)
            msg_type = data.get("msg_type", "")
            
            # Log untuk debugging
            logger.debug(f"Received: {msg_type}")
            
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
            elif msg_type == "error":
                self._handle_error(data)
            elif msg_type == "ping":
                # Respond to ping with pong
                self._send({"pong": 1})
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    def _handle_authorize(self, data: dict):
        """Handle response authorize"""
        if "error" in data:
            logger.error(f"❌ Authorization failed: {data['error']['message']}")
            self.is_authorized = False
            return
            
        auth_info = data.get("authorize", {})
        self.is_authorized = True
        
        # Simpan info akun
        self.account_info = AccountInfo(
            balance=float(auth_info.get("balance", 0)),
            currency=auth_info.get("currency", "USD"),
            account_id=auth_info.get("loginid", ""),
            is_virtual=auth_info.get("is_virtual", 1) == 1
        )
        
        logger.info(f"✅ Authorized: {self.account_info.account_id} | "
                   f"Balance: {self.account_info.balance} {self.account_info.currency}")
        
        # Subscribe ke balance updates
        self._subscribe_balance()
        
    def _handle_balance(self, data: dict):
        """Handle update balance"""
        if "error" in data:
            return
            
        balance_info = data.get("balance", {})
        new_balance = float(balance_info.get("balance", 0))
        
        if self.account_info:
            self.account_info.balance = new_balance
            
        # Trigger callback jika ada
        if self.on_balance_update_callback:
            self.on_balance_update_callback(new_balance)
            
    def _handle_tick(self, data: dict):
        """Handle tick data stream"""
        if "error" in data:
            return
            
        tick_data = data.get("tick", {})
        price = tick_data.get("quote")
        symbol = tick_data.get("symbol")
        
        if price and self.on_tick_callback:
            self.on_tick_callback(float(price), symbol)
            
    def _handle_buy_response(self, data: dict):
        """Handle response dari buy contract"""
        if self.on_buy_response_callback:
            self.on_buy_response_callback(data)
            
    def _handle_contract_update(self, data: dict):
        """Handle update status kontrak (win/loss detection)"""
        if self.on_contract_update_callback:
            self.on_contract_update_callback(data)
            
    def _handle_error(self, data: dict):
        """Handle error message dari Deriv"""
        error = data.get("error", {})
        error_msg = error.get("message", "Unknown error")
        error_code = error.get("code", "")
        
        logger.error(f"❌ Deriv Error [{error_code}]: {error_msg}")
        
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
                self.ws.send(json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"Failed to send: {e}")
            return False
            
    def _authorize(self):
        """Kirim request authorize"""
        token = self.get_current_token()
        if not token:
            logger.error("No token available for authorization")
            return
            
        payload = {
            "authorize": token
        }
        self._send(payload)
        
    def _subscribe_balance(self):
        """Subscribe ke balance updates"""
        payload = {
            "balance": 1,
            "subscribe": 1
        }
        self._send(payload)
        
    def _attempt_reconnect(self):
        """Coba reconnect jika masih dalam batas"""
        if self.reconnect_count >= self.MAX_RECONNECT_ATTEMPTS:
            logger.error("❌ Max reconnect attempts reached. Giving up.")
            return
            
        self.reconnect_count += 1
        logger.info(f"🔄 Reconnecting... Attempt {self.reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS}")
        
        time.sleep(self.RECONNECT_DELAY)
        self.connect()
        
    def connect(self) -> bool:
        """
        Mulai koneksi WebSocket dalam thread terpisah.
        
        Returns:
            True jika thread dimulai, False jika gagal
        """
        try:
            # Buat WebSocket app
            self.ws = websocket.WebSocketApp(
                self.WS_URL,
                on_open=self._on_open,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message
            )
            
            # Jalankan di thread terpisah
            self.ws_thread = threading.Thread(
                target=self.ws.run_forever,
                kwargs={"ping_interval": 30, "ping_timeout": 10},
                daemon=True
            )
            self.ws_thread.start()
            
            logger.info("🚀 WebSocket thread started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
            
    def disconnect(self):
        """Tutup koneksi WebSocket"""
        if self.ws:
            self.ws.close()
            self.is_connected = False
            self.is_authorized = False
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
            return True  # Sudah di akun yang diminta
            
        self.current_account_type = account_type
        logger.info(f"Switching to {account_type.value} account...")
        
        # Re-authorize dengan token baru
        if self.is_connected:
            self._authorize()
            return True
            
        return False
        
    def subscribe_ticks(self, symbol: str = "frxXAUUSD") -> bool:
        """
        Subscribe ke tick stream untuk symbol tertentu.
        
        Args:
            symbol: Symbol yang ingin di-subscribe (default XAUUSD)
            
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
        symbol: str = "frxXAUUSD",
        duration: int = 5,
        duration_unit: str = "t"
    ) -> bool:
        """
        Eksekusi buy contract (CALL/PUT).
        
        Args:
            contract_type: "CALL" atau "PUT"
            amount: Jumlah stake
            symbol: Trading pair
            duration: Durasi kontrak
            duration_unit: "t" (ticks), "s" (seconds), "m" (minutes)
            
        Returns:
            True jika request terkirim
        """
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
        
    def wait_until_ready(self, timeout: int = 30) -> bool:
        """
        Tunggu sampai WebSocket siap (connected & authorized).
        
        Args:
            timeout: Maksimum waktu tunggu dalam detik
            
        Returns:
            True jika siap, False jika timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_ready():
                return True
            time.sleep(0.5)
        return False
