"""
=============================================================
FLASK KEEP-ALIVE SERVER
=============================================================
Server Flask ringan untuk menjaga bot tetap aktif di Replit.
Menyediakan endpoint health check dan status sederhana.
=============================================================
"""

import os
import threading
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

start_time = datetime.now()

request_count = 0
last_request_time = None

service_ready = True


def _increment_request_count():
    """Helper function untuk increment request count dan update last_request_time"""
    global request_count, last_request_time
    request_count += 1
    last_request_time = datetime.now()


def _get_uptime_dict():
    """Helper function untuk mendapatkan uptime dalam format dict"""
    uptime = datetime.now() - start_time
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return {
        "formatted": f"{hours}h {minutes}m {seconds}s",
        "total_seconds": total_seconds,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds
    }


@app.route("/")
def home():
    """
    Root endpoint - menampilkan status bot.
    Digunakan untuk health check dan monitoring.
    """
    _increment_request_count()
    
    uptime_info = _get_uptime_dict()
    
    return jsonify({
        "status": "alive",
        "message": "Deriv Auto Trading Bot is running!",
        "uptime": uptime_info["formatted"],
        "timestamp": datetime.now().isoformat()
    })


@app.route("/health")
def health():
    """
    Health check endpoint untuk monitoring.
    Return 200 OK jika server berjalan normal.
    """
    _increment_request_count()
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/ping")
def ping():
    """Simple ping endpoint untuk keep-alive services"""
    _increment_request_count()
    return "pong", 200


@app.route("/metrics")
def metrics():
    """
    Metrics endpoint untuk monitoring real-time.
    Return uptime, request_count, dan last_request_time.
    """
    _increment_request_count()
    
    uptime_info = _get_uptime_dict()
    
    return jsonify({
        "status": "ok",
        "uptime": uptime_info,
        "request_count": request_count,
        "last_request_time": last_request_time.isoformat() if last_request_time else None,
        "start_time": start_time.isoformat(),
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/readiness")
def readiness():
    """
    Readiness endpoint untuk check apakah service ready menerima traffic.
    Return 200 OK jika ready, 503 Service Unavailable jika tidak.
    """
    _increment_request_count()
    
    if service_ready:
        return jsonify({
            "status": "ready",
            "message": "Service is ready to receive traffic",
            "timestamp": datetime.now().isoformat()
        }), 200
    else:
        return jsonify({
            "status": "not_ready",
            "message": "Service is not ready to receive traffic",
            "timestamp": datetime.now().isoformat()
        }), 503


def set_service_ready(ready: bool):
    """
    Set service readiness status.
    Dapat dipanggil dari modul lain untuk mengatur status readiness.
    """
    global service_ready
    service_ready = ready


def run_server():
    """
    Jalankan Flask server di thread terpisah.
    Port diambil dari environment variable atau default 5000.
    """
    port = int(os.environ.get("PORT", 5000))
    
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )


def start_keep_alive():
    """
    Mulai keep-alive server di background thread.
    Dipanggil dari main.py saat bot start.
    """
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print(f"🌐 Keep-alive server started on port {os.environ.get('PORT', 5000)}")
    return server_thread
