"""
common\logger.py
功能描述: 全局日志管理模块，支持JSON格式输出和文件轮转
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from .config import log_config


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(log_record, ensure_ascii=False)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("marketing_agent")
    logger.setLevel(getattr(logging, log_config.LOG_LEVEL.upper()))
    logger.propagate = False

    log_dir = Path(log_config.LOG_FILE_PATH).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = JSONFormatter() if log_config.LOG_FORMAT == "json" else logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_config.LOG_FILE_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()