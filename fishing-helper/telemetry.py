import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def session_logger():
    logger = logging.getLogger('pesca-auto')
    if not logger.handlers:
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PescaAuto'
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / 'pesca.log', maxBytes=2_000_000,
                                      backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
