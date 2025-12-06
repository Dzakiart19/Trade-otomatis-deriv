"""
=============================================================
WEB SERVER - FastAPI Server with Real-Time WebSocket Dashboard
=============================================================
This module provides a FastAPI web server for the trading bot dashboard.

Features:
- REST API endpoints for summary and trade history
- WebSocket endpoint for real-time event streaming
- Static file serving for frontend dashboard
- Integration with EventBus for live updates
- Token-based authentication for security

Endpoints:
- GET /api/summary - Get current state snapshot
- GET /api/history - Get trade history
- WS /ws/stream - Real-time event stream
- GET / - Serve dashboard frontend

Security:
- All API endpoints require DASHBOARD_SECRET token
- WebSocket requires token in query parameter
- Set DASHBOARD_SECRET environment variable to secure

Usage:
    from web_server import create_app, run_server
    
    app = create_app()
    await run_server(app, host="0.0.0.0", port=5000)
=============================================================
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from event_bus import get_event_bus, Channel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DASHBOARD_SECRET_FILE = ".dashboard_secret"


def get_or_create_dashboard_secret() -> str:
    """Get dashboard secret from env or file, or generate one."""
    secret = os.environ.get("DASHBOARD_SECRET")
    if secret:
        return secret
    
    if os.path.exists(DASHBOARD_SECRET_FILE):
        try:
            with open(DASHBOARD_SECRET_FILE, "r") as f:
                secret = f.read().strip()
                if len(secret) >= 16:
                    return secret
        except Exception:
            pass
    
    secret = secrets.token_urlsafe(32)
    try:
        with open(DASHBOARD_SECRET_FILE, "w") as f:
            f.write(secret)
        logger.info(f"Generated new DASHBOARD_SECRET (saved to {DASHBOARD_SECRET_FILE})")
        logger.info(f"Dashboard Access Token: {secret}")
    except Exception as e:
        logger.warning(f"Could not save dashboard secret: {e}")
    
    return secret


DASHBOARD_SECRET = get_or_create_dashboard_secret()

user_tokens: Dict[str, str] = {}


def validate_telegram_init_data(init_data: str) -> Optional[dict]:
    """
    Validate Telegram WebApp initData using HMAC-SHA256.
    
    Returns user info dict if valid, None if invalid.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, cannot validate Telegram auth")
        return None
    
    try:
        parsed = urllib.parse.parse_qs(init_data)
        
        if "hash" not in parsed:
            return None
        
        received_hash = parsed["hash"][0]
        
        data_pairs = []
        for key, values in parsed.items():
            if key != "hash":
                data_pairs.append(f"{key}={values[0]}")
        
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)
        
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Telegram initData hash validation failed")
            return None
        
        if "user" in parsed:
            user_data = json.loads(parsed["user"][0])
            return user_data
        
        return None
        
    except Exception as e:
        logger.error(f"Error validating Telegram initData: {e}")
        return None


def get_or_create_user_token(telegram_id: str) -> str:
    """Get existing token for user or create a new one."""
    if telegram_id in user_tokens:
        return user_tokens[telegram_id]
    
    token = secrets.token_urlsafe(32)
    user_tokens[telegram_id] = token
    logger.info(f"Generated new token for Telegram user {telegram_id}")
    return token


def verify_token(token: Optional[str]) -> bool:
    """Verify if the provided token matches the dashboard secret or a user token."""
    if not token:
        return False
    if secrets.compare_digest(token, DASHBOARD_SECRET):
        return True
    if token in user_tokens.values():
        return True
    return False


async def get_auth_token(authorization: Optional[str] = Header(None)) -> str:
    """Extract and verify auth token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return token


class ConnectionManager:
    """
    Manages WebSocket connections for real-time streaming.
    
    Handles client connections, disconnections, and message broadcasting.
    Subscribes to EventBus channels and forwards events to all connected clients.
    """
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._event_tasks: List[asyncio.Task] = []
        self._running = False
        
    async def connect(self, websocket: WebSocket, token: str) -> bool:
        """Accept a new WebSocket connection after verifying token."""
        if not verify_token(token):
            await websocket.close(code=4001, reason="Invalid token")
            return False
            
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
        snapshot = get_event_bus().get_snapshot()
        try:
            await websocket.send_json({
                "type": "snapshot",
                "data": snapshot
            })
        except Exception as e:
            logger.error(f"Failed to send initial snapshot: {e}")
        
        return True
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
            
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected.add(connection)
        
        for conn in disconnected:
            self.active_connections.discard(conn)
    
    async def start_event_forwarding(self) -> None:
        """Start forwarding EventBus events to WebSocket clients."""
        if self._running:
            return
            
        self._running = True
        bus = get_event_bus()
        
        channels = ["tick", "position", "trade", "balance", "status"]
        for channel in channels:
            task = asyncio.create_task(self._forward_channel(bus, channel))
            self._event_tasks.append(task)
            
        logger.info("Started event forwarding to WebSocket clients")
    
    async def _forward_channel(self, bus, channel: str) -> None:
        """Forward events from a specific channel to WebSocket clients."""
        queue = bus.subscribe(channel)
        
        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await self.broadcast({
                        "type": "event",
                        "channel": channel,
                        "data": event
                    })
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error forwarding {channel} event: {e}")
                    await asyncio.sleep(0.1)
        finally:
            bus.unsubscribe(channel, queue)
            logger.info(f"Stopped forwarding channel: {channel}")
    
    async def stop_event_forwarding(self) -> None:
        """Stop all event forwarding tasks."""
        self._running = False
        
        for task in self._event_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        self._event_tasks.clear()
        logger.info("Stopped all event forwarding")
    
    async def close_all(self) -> None:
        """Close all WebSocket connections."""
        for connection in list(self.active_connections):
            try:
                await connection.close()
            except Exception:
                pass
        self.active_connections.clear()


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    await manager.start_event_forwarding()
    logger.info("Web server started")
    logger.info(f"Dashboard access token: {DASHBOARD_SECRET}")
    
    yield
    
    await manager.stop_event_forwarding()
    await manager.close_all()
    logger.info("Web server shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title="Deriv Trading Bot Dashboard",
        description="Real-time trading dashboard for Deriv auto-trading bot",
        version="1.0.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        """Serve the main dashboard HTML page."""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Deriv Trading Bot Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #1a1a2e; color: #eee; }
                h1 { color: #00d4ff; }
                .loading { color: #888; }
            </style>
        </head>
        <body>
            <h1>Deriv Trading Bot Dashboard</h1>
            <p class="loading">Dashboard files not found. Please create static/index.html</p>
            <p>API endpoints available:</p>
            <ul>
                <li><a href="/api/summary" style="color: #00d4ff;">/api/summary</a> - Current state</li>
                <li><a href="/api/history" style="color: #00d4ff;">/api/history</a> - Trade history</li>
                <li><code>/ws/stream</code> - WebSocket stream</li>
            </ul>
        </body>
        </html>
        """)
    
    @app.post("/api/auth/telegram")
    async def telegram_auth(request: Request):
        """
        Authenticate user via Telegram WebApp initData.
        
        Receives initData from Telegram WebApp, validates it using HMAC-SHA256,
        and returns a user-specific token for dashboard access.
        
        Request body:
            {"initData": "..."}
            
        Returns:
            JSON with success status, token, and user info
        """
        try:
            body = await request.json()
            init_data = body.get("initData")
            
            if not init_data:
                raise HTTPException(status_code=400, detail="Missing initData")
            
            user_info = validate_telegram_init_data(init_data)
            
            if not user_info:
                raise HTTPException(status_code=401, detail="Invalid Telegram authentication")
            
            telegram_id = str(user_info.get("id"))
            if not telegram_id:
                raise HTTPException(status_code=400, detail="Invalid user data")
            
            token = get_or_create_user_token(telegram_id)
            
            logger.info(f"Telegram user authenticated: {user_info.get('first_name')} (ID: {telegram_id})")
            
            return JSONResponse(content={
                "success": True,
                "token": token,
                "user": {
                    "id": telegram_id,
                    "first_name": user_info.get("first_name", ""),
                    "last_name": user_info.get("last_name", ""),
                    "username": user_info.get("username", "")
                }
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Telegram auth error: {e}")
            raise HTTPException(status_code=500, detail="Authentication failed")
    
    @app.get("/api/summary")
    async def get_summary(token: str = Depends(get_auth_token)):
        """
        Get current trading state summary.
        
        Requires Authorization header with valid token.
        
        Returns:
            JSON with open positions, balance, status, and last ticks
        """
        bus = get_event_bus()
        snapshot = bus.get_snapshot()
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "open_positions": snapshot["open_positions"],
                "balance": snapshot["balance"],
                "status": snapshot["status"],
                "last_ticks": snapshot["last_ticks"],
                "snapshot_time": snapshot["snapshot_time"]
            }
        })
    
    @app.get("/api/history")
    async def get_history(
        limit: int = Query(default=50, ge=1, le=200),
        token: str = Depends(get_auth_token)
    ):
        """
        Get trade history.
        
        Requires Authorization header with valid token.
        
        Args:
            limit: Maximum number of trades to return (1-200, default 50)
            
        Returns:
            JSON with trade history list
        """
        bus = get_event_bus()
        history = bus.get_trade_history(limit=limit)
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "trades": history,
                "count": len(history),
                "limit": limit
            }
        })
    
    @app.get("/api/positions")
    async def get_positions(token: str = Depends(get_auth_token)):
        """
        Get currently open positions.
        
        Requires Authorization header with valid token.
        
        Returns:
            JSON with open positions
        """
        bus = get_event_bus()
        positions = bus.get_open_positions()
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "positions": positions,
                "count": len(positions)
            }
        })
    
    @app.get("/api/ticks")
    async def get_ticks(token: str = Depends(get_auth_token)):
        """
        Get last tick prices for all symbols.
        
        Requires Authorization header with valid token.
        
        Returns:
            JSON with last tick per symbol
        """
        bus = get_event_bus()
        snapshot = bus.get_snapshot()
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "ticks": snapshot["last_ticks"]
            }
        })
    
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint (no auth required)."""
        bus = get_event_bus()
        subscriber_counts = bus.get_subscriber_count()
        
        return JSONResponse(content={
            "status": "healthy",
            "websocket_connections": len(manager.active_connections),
            "event_subscribers": subscriber_counts,
            "timestamp": datetime.now().isoformat()
        })
    
    @app.websocket("/ws/stream")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: str = Query(...)
    ):
        """
        WebSocket endpoint for real-time event streaming.
        
        Requires token query parameter for authentication.
        Example: ws://host:port/ws/stream?token=YOUR_TOKEN
        
        Clients receive:
        - Initial snapshot on connect
        - Real-time tick, position, trade, balance, and status events
        
        Message format:
        {
            "type": "snapshot" | "event" | "pong",
            "channel": "tick" | "position" | "trade" | "balance" | "status",
            "data": {...}
        }
        """
        if not await manager.connect(websocket, token):
            return
        
        try:
            while True:
                try:
                    data = await websocket.receive_text()
                    
                    if data == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif data == "snapshot":
                        snapshot = get_event_bus().get_snapshot()
                        await websocket.send_json({
                            "type": "snapshot",
                            "data": snapshot
                        })
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"WebSocket error: {e}")
                    break
        finally:
            manager.disconnect(websocket)
    
    return app


app = create_app()


async def run_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    """
    Run the FastAPI server with uvicorn.
    
    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 5000)
    """
    import uvicorn
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    server = uvicorn.Server(config)
    
    logger.info(f"Starting web server on http://{host}:{port}")
    await server.serve()


def run_server_sync(host: str = "0.0.0.0", port: int = 5000) -> None:
    """
    Run the FastAPI server synchronously (blocking).
    
    Use this for standalone testing.
    
    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 5000)
    """
    import uvicorn
    
    logger.info(f"Starting web server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server_sync()
