import os
import multiprocessing
from dotenv import load_dotenv
load_dotenv()

# Server socket
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '5000')}"
backlog = 2048

# Worker processes
workers = 1 # multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = 'logs/gunicorn-access.log'
errorlog = 'logs/gunicorn-error.log'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()

# Process naming
proc_name = 'compugit_backend'

# Server mechanics
daemon = False
pidfile = 'logs/gunicorn.pid'
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None