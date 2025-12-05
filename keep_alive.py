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

# Inisialisasi Flask app
app = Flask(__name__)

# Tracking uptime
start_time = datetime.now()


@app.route("/")
def home():
    """
    Root endpoint - menampilkan status bot.
    Digunakan untuk health check dan monitoring.
    """
    uptime = datetime.now() - start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return jsonify({
        "status": "alive",
        "message": "Deriv Auto Trading Bot is running!",
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "timestamp": datetime.now().isoformat()
    })


@app.route("/health")
def health():
    """
    Health check endpoint untuk monitoring.
    Return 200 OK jika server berjalan normal.
    """
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/ping")
def ping():
    """Simple ping endpoint untuk keep-alive services"""
    return "pong", 200


def run_server():
    """
    Jalankan Flask server di thread terpisah.
    Port diambil dari environment variable atau default 5000.
    """
    port = int(os.environ.get("PORT", 5000))
    
    # Jalankan server dengan threading untuk non-blocking
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
