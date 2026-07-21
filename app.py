"""
AD Report Hub — Entry Point
===========================
Run with:
    python app.py
Or production:
    gunicorn -w 2 -b 0.0.0.0:5000 'app:app'
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config
import logging

app = create_app()

logging.getLogger('werkzeug').setLevel(logging.ERROR)

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════╗
║              AD Report Hub                       ║
╚══════════════════════════════════════════════════╝
  → Report AD         /ad/
  → Admin Panel       /admin/
""")
    import os
    ssl_cert = Config.SSL_CERT
    ssl_key  = Config.SSL_KEY
    ssl_ctx  = (ssl_cert, ssl_key) if os.path.exists(ssl_cert) and os.path.exists(ssl_key) else None

    if ssl_ctx:
        print(f"  → SSL enabled ({ssl_cert})")
    else:
        print("  ⚠  SSL certificates not found — running without HTTPS")

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        use_reloader=False,
        ssl_context=ssl_ctx,
    )
