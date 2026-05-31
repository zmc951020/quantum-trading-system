"""Aurora 标准化日志系统
P3-1修补项 - 统一日志格式/级别/轮转/审计
"""
import logging, logging.handlers, os, json, time, sys
from datetime import datetime

LOG_DIR = os.getenv("AURORA_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

class AuroraJsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", ""),
            "user_id": getattr(record, "user_id", ""),
        }
        if record.exc_info:
            import traceback
            log_entry["exception"] = traceback.format_exception(*record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False, default=str)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_aurora_logging(name="aurora", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(level)

    timed_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, f"{name}.log"),
        when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    timed_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(timed_handler)

    json_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(LOG_DIR, f"{name}_json.log"),
        maxBytes=50 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    json_handler.setFormatter(AuroraJsonFormatter())
    logger.addHandler(json_handler)

    if os.getenv("AURORA_DEBUG"):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(console)

    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(LOG_DIR, f"{name}_error.log"),
        maxBytes=50 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(error_handler)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    return logger

aurora_logger = setup_aurora_logging()