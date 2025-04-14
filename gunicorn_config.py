# gunicorn_config.py

# Use the gevent worker class for WebSocket support
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'

# Number of worker processes
workers = 4  # Adjust based on your Render instance plan

# Bind to the address and port provided by Render (or default)
# Render provides the PORT environment variable
import os
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Optional: Adjust logging
loglevel = 'info'
accesslog = '-' # Log access to stdout
errorlog = '-'  # Log errors to stdout 