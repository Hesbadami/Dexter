import urllib
from dotenv import load_dotenv
from pathlib import Path
import os
import logging
import logging.config
import logging.handlers
from urllib.parse import quote_plus

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(name)s %(process)d %(thread)d %(message)s',
        },
        'simple': {
            'format': '%(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'main_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.environ.get("LOG_PATH"),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 10*1024*1024,
            'backupCount': 5,
        },
    },
    'loggers': {
        '': {
            'handlers': ['console', 'main_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

FISH_SECRET = os.environ.get('FISH_API')
FISH_MODEL_ID = os.environ.get('FISH_MODEL_ID')

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

DB_CFG = {
    'db_user': quote_plus(os.getenv('DB_USER', 'taskuser')),
    'db_password': quote_plus(os.getenv('DB_PASSWORD', '')),
    'db_name': os.getenv('DB_NAME', 'task_manager'),
    'db_host': '127.0.0.1',
    'db_port': '5432'
}

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')