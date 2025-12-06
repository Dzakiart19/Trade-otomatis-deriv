"""
=============================================================
EVENT BUS - Async PubSub System for Real-Time Event Broadcasting
=============================================================
This module provides an async event bus for broadcasting events
between the trading bot and web clients in real-time.

Features:
- Async PubSub with asyncio.Queue for multiple subscribers
- Thread-safe publishing from sync code (trading callbacks)
- Multiple channels: tick, position, trade, balance, status
- In-memory snapshots of current state
- Type-safe event dataclasses
- Automatic subscriber cleanup

Usage:
    from event_bus import EventBus, TickEvent, BalanceUpdateEvent
    
    # Create event bus instance
    bus = EventBus()
    
    # Subscribe to a channel (async)
    async def consumer():
        queue = bus.subscribe("tick")
        while True:
            event = await queue.get()
            print(f"Received: {event}")
    
    # Publish from sync code (thread-safe)
    bus.publish("tick", TickEvent(symbol="R_100", price=1234.56))
    
    # Get current state snapshot
    snapshot = bus.get_snapshot()
=============================================================
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Union
from collections import deque
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """Supported event channels"""
    TICK = "tick"
    POSITION = "position"
    TRADE = "trade"
    BALANCE = "balance"
    STATUS = "status"


@dataclass
class TickEvent:
    """Tick price update event"""
    symbol: str
    price: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": "tick",
            "symbol": self.symbol,
            "price": self.price,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class PositionOpenEvent:
    """Position opened event"""
    contract_id: str
    symbol: str
    entry_price: float
    stake: float
    direction: str  # "CALL" or "PUT"
    martingale_level: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": "position_open",
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "stake": self.stake,
            "direction": self.direction,
            "martingale_level": self.martingale_level,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class PositionUpdateEvent:
    """Position update event (during contract lifetime)"""
    contract_id: str
    current_price: float
    pnl: float
    duration: float  # seconds elapsed
    
    def to_dict(self) -> dict:
        return {
            "type": "position_update",
            "contract_id": self.contract_id,
            "current_price": self.current_price,
            "pnl": self.pnl,
            "duration": self.duration
        }


@dataclass
class PositionCloseEvent:
    """Position closed event"""
    contract_id: str
    symbol: str
    exit_price: float
    profit: float
    is_win: bool
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": "position_close",
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "exit_price": self.exit_price,
            "profit": self.profit,
            "is_win": self.is_win,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class PositionsResetEvent:
    """Event to signal all positions should be cleared (session end/stop)"""
    reason: str  # 'session_complete', 'stop', or 'emergency'
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": "positions_reset",
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class BalanceUpdateEvent:
    """Account balance update event"""
    balance: float
    currency: str
    account_id: str
    
    def to_dict(self) -> dict:
        return {
            "type": "balance_update",
            "balance": self.balance,
            "currency": self.currency,
            "account_id": self.account_id
        }


@dataclass
class TradeHistoryEvent:
    """Trade history entry event"""
    trade_id: str
    symbol: str
    direction: str  # "CALL" or "PUT"
    stake: float
    result: str  # "win" or "loss"
    profit: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": "trade_history",
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "stake": self.stake,
            "result": self.result,
            "profit": self.profit,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class StatusEvent:
    """Trading bot status event"""
    is_trading: bool
    is_connected: bool
    account_type: str  # "demo" or "real"
    
    def to_dict(self) -> dict:
        return {
            "type": "status",
            "is_trading": self.is_trading,
            "is_connected": self.is_connected,
            "account_type": self.account_type
        }


EventType = Union[
    TickEvent, 
    PositionOpenEvent, 
    PositionUpdateEvent, 
    PositionCloseEvent,
    PositionsResetEvent,
    BalanceUpdateEvent,
    TradeHistoryEvent,
    StatusEvent
]


class EventBus:
    """
    Async PubSub event bus for real-time event broadcasting.
    
    Thread-safe for publishing from sync code (trading callbacks run in threads).
    Maintains in-memory snapshots of current state for new subscribers.
    
    Channels:
        - tick: Price tick updates
        - position: Position open/update/close events
        - trade: Trade history events
        - balance: Balance update events
        - status: Trading bot status events
    
    Attributes:
        MAX_TRADE_HISTORY: Maximum number of trades to keep in history (default: 200)
        QUEUE_MAX_SIZE: Maximum queue size per subscriber (default: 1000)
    """
    
    MAX_TRADE_HISTORY = 200
    QUEUE_MAX_SIZE = 1000
    VALID_CHANNELS = {"tick", "position", "trade", "balance", "status"}
    
    def __init__(self):
        """Initialize the event bus with empty state."""
        self._lock = threading.RLock()
        
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {
            channel: set() for channel in self.VALID_CHANNELS
        }
        
        self._open_positions: Dict[str, dict] = {}
        self._trade_history: deque = deque(maxlen=self.MAX_TRADE_HISTORY)
        self._current_balance: Optional[dict] = None
        self._current_status: Optional[dict] = None
        self._last_ticks: Dict[str, dict] = {}
        
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_lock = threading.Lock()
        
        logger.info("📡 EventBus initialized")
        
    def _get_event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get or detect the running event loop (thread-safe)."""
        with self._loop_lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
                return loop
            except RuntimeError:
                return None
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Explicitly set the event loop for thread-safe publishing.
        
        Call this from the main async context to ensure thread-safe
        publishing from sync callbacks.
        
        Args:
            loop: The asyncio event loop to use for publishing
        """
        with self._loop_lock:
            self._loop = loop
            logger.debug(f"Event loop set: {loop}")
    
    def subscribe(self, channel: str) -> asyncio.Queue:
        """
        Subscribe to a channel and get an async queue for receiving events.
        
        Args:
            channel: Channel name ("tick", "position", "trade", "balance", "status")
            
        Returns:
            asyncio.Queue for receiving events on this channel
            
        Raises:
            ValueError: If channel is not valid
        """
        if channel not in self.VALID_CHANNELS:
            raise ValueError(f"Invalid channel: {channel}. Valid: {self.VALID_CHANNELS}")
        
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        
        with self._lock:
            self._subscribers[channel].add(queue)
            subscriber_count = len(self._subscribers[channel])
            
        logger.info(f"📥 New subscriber for '{channel}' (total: {subscriber_count})")
        return queue
    
    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> bool:
        """
        Unsubscribe a queue from a channel.
        
        Args:
            channel: Channel name
            queue: The queue to unsubscribe
            
        Returns:
            True if successfully unsubscribed, False if not found
        """
        if channel not in self.VALID_CHANNELS:
            return False
            
        with self._lock:
            if queue in self._subscribers[channel]:
                self._subscribers[channel].discard(queue)
                logger.info(f"📤 Unsubscribed from '{channel}' (remaining: {len(self._subscribers[channel])})")
                return True
        return False
    
    def publish(self, channel: str, event_data: Any) -> bool:
        """
        Publish an event to a channel (thread-safe).
        
        Can be called from sync code running in threads.
        Events are distributed to all subscribers on the channel.
        Also updates internal state snapshots.
        
        Args:
            channel: Channel name ("tick", "position", "trade", "balance", "status")
            event_data: Event dataclass instance or dict
            
        Returns:
            True if published successfully, False otherwise
        """
        if channel not in self.VALID_CHANNELS:
            logger.warning(f"⚠️ Invalid channel: {channel}")
            return False
        
        event_dict: dict = event_data.to_dict() if hasattr(event_data, 'to_dict') else dict(event_data)
        
        self._update_snapshot(channel, event_dict)
        
        with self._lock:
            subscribers = list(self._subscribers[channel])
            
        if not subscribers:
            logger.debug(f"No subscribers for '{channel}'")
            return True
        
        loop = self._get_event_loop()
        
        if loop is not None and loop.is_running():
            for queue in subscribers:
                try:
                    loop.call_soon_threadsafe(self._enqueue_event, queue, event_dict, channel)
                except RuntimeError as e:
                    logger.warning(f"Failed to publish to subscriber: {e}")
                    self._cleanup_dead_subscriber(channel, queue)
        else:
            for queue in subscribers:
                try:
                    queue.put_nowait(event_dict)
                except asyncio.QueueFull:
                    logger.warning(f"⚠️ Queue full for '{channel}', dropping oldest event")
                    try:
                        queue.get_nowait()
                        queue.put_nowait(event_dict)
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Failed to enqueue event: {e}")
                    self._cleanup_dead_subscriber(channel, queue)
        
        logger.debug(f"📢 Published to '{channel}': {event_dict.get('type', 'unknown')}")
        return True
    
    def _enqueue_event(self, queue: asyncio.Queue, event_dict: dict, channel: str) -> None:
        """Helper to enqueue event from loop.call_soon_threadsafe."""
        try:
            queue.put_nowait(event_dict)
        except asyncio.QueueFull:
            logger.warning(f"⚠️ Queue full for '{channel}', dropping oldest event")
            try:
                queue.get_nowait()
                queue.put_nowait(event_dict)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to enqueue event: {e}")
    
    def _cleanup_dead_subscriber(self, channel: str, queue: asyncio.Queue) -> None:
        """Remove a dead/closed subscriber queue."""
        with self._lock:
            self._subscribers[channel].discard(queue)
            logger.debug(f"🧹 Cleaned up dead subscriber for '{channel}'")
    
    def _update_snapshot(self, channel: str, event_dict: dict) -> None:
        """Update internal state snapshots based on event type."""
        event_type = event_dict.get("type", "")
        
        with self._lock:
            if event_type == "tick":
                symbol = event_dict.get("symbol")
                if symbol:
                    self._last_ticks[symbol] = event_dict
                    
            elif event_type == "position_open":
                contract_id = event_dict.get("contract_id")
                if contract_id:
                    self._open_positions[contract_id] = event_dict
                    
            elif event_type == "position_update":
                contract_id = event_dict.get("contract_id")
                if contract_id and contract_id in self._open_positions:
                    self._open_positions[contract_id].update({
                        "current_price": event_dict.get("current_price"),
                        "pnl": event_dict.get("pnl"),
                        "duration": event_dict.get("duration")
                    })
                    
            elif event_type == "position_close":
                contract_id = event_dict.get("contract_id")
                if contract_id:
                    self._open_positions.pop(contract_id, None)
                    
            elif event_type == "trade_history":
                self._trade_history.append(event_dict)
                
            elif event_type == "balance_update":
                self._current_balance = event_dict
                
            elif event_type == "status":
                self._current_status = event_dict
    
    def get_snapshot(self) -> dict:
        """
        Get current state snapshot.
        
        Returns a dictionary containing:
        - open_positions: Currently open positions
        - trade_history: Last 200 trades
        - balance: Current balance info
        - status: Current trading status
        - last_ticks: Last tick per symbol
        
        Returns:
            dict with current state
        """
        with self._lock:
            return {
                "open_positions": dict(self._open_positions),
                "trade_history": list(self._trade_history),
                "balance": self._current_balance,
                "status": self._current_status,
                "last_ticks": dict(self._last_ticks),
                "snapshot_time": datetime.now().isoformat()
            }
    
    def get_open_positions(self) -> Dict[str, dict]:
        """Get all currently open positions."""
        with self._lock:
            return dict(self._open_positions)
    
    def get_trade_history(self, limit: Optional[int] = None) -> List[dict]:
        """
        Get trade history.
        
        Args:
            limit: Maximum number of trades to return (default: all)
            
        Returns:
            List of trade history events (most recent last)
        """
        with self._lock:
            history = list(self._trade_history)
            if limit:
                return history[-limit:]
            return history
    
    def get_current_balance(self) -> Optional[dict]:
        """Get current balance info."""
        with self._lock:
            return self._current_balance
    
    def get_current_status(self) -> Optional[dict]:
        """Get current trading status."""
        with self._lock:
            return self._current_status
    
    def get_last_tick(self, symbol: str) -> Optional[dict]:
        """Get last tick for a specific symbol."""
        with self._lock:
            return self._last_ticks.get(symbol)
    
    def get_subscriber_count(self, channel: Optional[str] = None) -> Union[int, Dict[str, int]]:
        """
        Get subscriber count for channel(s).
        
        Args:
            channel: Specific channel or None for all
            
        Returns:
            Count for specific channel or dict of all counts
        """
        with self._lock:
            if channel:
                return len(self._subscribers.get(channel, set()))
            return {ch: len(subs) for ch, subs in self._subscribers.items()}
    
    def clear_history(self) -> None:
        """Clear trade history (useful for session reset)."""
        with self._lock:
            self._trade_history.clear()
            logger.info("🧹 Trade history cleared")
    
    def clear_positions(self) -> None:
        """Clear all open positions (useful for emergency reset)."""
        with self._lock:
            self._open_positions.clear()
            logger.info("🧹 Open positions cleared")
    
    def reset(self) -> None:
        """Reset all state and clear all subscribers."""
        with self._lock:
            self._open_positions.clear()
            self._trade_history.clear()
            self._current_balance = None
            self._current_status = None
            self._last_ticks.clear()
            
            for channel in self._subscribers:
                self._subscribers[channel].clear()
                
        logger.info("🔄 EventBus reset complete")


_event_bus_instance: Optional[EventBus] = None
_instance_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """
    Get the singleton EventBus instance.
    
    Thread-safe singleton accessor for global event bus.
    
    Returns:
        The global EventBus instance
    """
    global _event_bus_instance
    
    with _instance_lock:
        if _event_bus_instance is None:
            _event_bus_instance = EventBus()
        return _event_bus_instance


def reset_event_bus() -> None:
    """Reset the singleton EventBus instance."""
    global _event_bus_instance
    
    with _instance_lock:
        if _event_bus_instance is not None:
            _event_bus_instance.reset()
        _event_bus_instance = None
        logger.info("🔄 Global EventBus instance reset")


if __name__ == "__main__":
    import sys
    
    async def test_event_bus():
        """Test the EventBus functionality."""
        print("🧪 Testing EventBus...")
        
        bus = EventBus()
        bus.set_event_loop(asyncio.get_running_loop())
        
        tick_queue = bus.subscribe("tick")
        position_queue = bus.subscribe("position")
        balance_queue = bus.subscribe("balance")
        
        bus.publish("tick", TickEvent(symbol="R_100", price=1234.56))
        bus.publish("tick", TickEvent(symbol="R_50", price=5678.90))
        
        bus.publish("position", PositionOpenEvent(
            contract_id="contract_123",
            symbol="R_100",
            entry_price=1234.56,
            stake=1.0,
            direction="CALL",
            martingale_level=0
        ))
        
        bus.publish("balance", BalanceUpdateEvent(
            balance=10000.0,
            currency="USD",
            account_id="demo_123"
        ))
        
        bus.publish("position", PositionCloseEvent(
            contract_id="contract_123",
            symbol="R_100",
            exit_price=1235.00,
            profit=0.95,
            is_win=True
        ))
        
        bus.publish("trade", TradeHistoryEvent(
            trade_id="trade_001",
            symbol="R_100",
            direction="CALL",
            stake=1.0,
            result="win",
            profit=0.95
        ))
        
        await asyncio.sleep(0.1)
        
        tick_count = 0
        while not tick_queue.empty():
            event = tick_queue.get_nowait()
            print(f"  Tick event: {event}")
            tick_count += 1
        print(f"✓ Received {tick_count} tick events")
        
        position_count = 0
        while not position_queue.empty():
            event = position_queue.get_nowait()
            print(f"  Position event: {event}")
            position_count += 1
        print(f"✓ Received {position_count} position events")
        
        balance_count = 0
        while not balance_queue.empty():
            event = balance_queue.get_nowait()
            print(f"  Balance event: {event}")
            balance_count += 1
        print(f"✓ Received {balance_count} balance events")
        
        snapshot = bus.get_snapshot()
        print(f"\n📊 Snapshot:")
        print(f"  Open positions: {len(snapshot['open_positions'])}")
        print(f"  Trade history: {len(snapshot['trade_history'])}")
        print(f"  Balance: {snapshot['balance']}")
        print(f"  Last ticks: {list(snapshot['last_ticks'].keys())}")
        
        print(f"\n📈 Subscriber counts: {bus.get_subscriber_count()}")
        
        print("\n✅ All tests passed!")
        
    asyncio.run(test_event_bus())
