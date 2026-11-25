import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

# Server socket
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '5000')}"
backlog = 2048

# Worker processes
default_workers = max(2, min(multiprocessing.cpu_count() * 2 + 1, 8))
workers = int(os.getenv("WEB_CONCURRENCY", str(default_workers)))
worker_class = 'sync'
timeout = int(os.getenv("GUNICORN_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "2"))

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv('LOG_LEVEL', 'info').lower()

# Process naming
proc_name = 'compugit_backend'

# Server mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PIDFILE")
umask = 0o077
user = os.getenv("GUNICORN_USER")
group = os.getenv("GUNICORN_GROUP")
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None