import urllib
from dotenv import load_dotenv
from pathlib import Path
import os
import logging
import logging.config
import logging.handlers

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