import logging
import os
from datetime import date
try:
    from aws_lambda_powertools import Logger
    powertools_logger = Logger(service="lambda-flask")
    USE_POWETOOLS = True
except ImportError:
    powertools_logger = None
    USE_POWETOOLS = False

# When this module lives in `app/`, use its parent directory as project root
module_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(module_dir, os.pardir))

# Allow overriding LOG_DIR via environment, otherwise keep logs/ at project root
LOG_DIR = os.getenv('LOG_DIR', os.path.join(project_root, 'logs'))
LOG_DIR = os.path.abspath(LOG_DIR)
LOG_FILE = os.getenv('LOG_FILE', f'{date.today()}.log')
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, LOG_FILE)

# Configure root logger level and add a FileHandler to ensure logs are written
LOG_LEVEL = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s")

# Create or get the module logger
std_logger = logging.getLogger(os.getenv('APP_NAME','CompuGit_Backend'))
std_logger.setLevel(LOG_LEVEL)

# Add file handler if not already present
if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '') == log_path for h in std_logger.handlers):
    file_handler = logging.FileHandler(log_path, mode='a')
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    std_logger.addHandler(file_handler)

def get_logger():
    if USE_POWETOOLS:
        return powertools_logger
    return std_logger

logger = get_logger()
